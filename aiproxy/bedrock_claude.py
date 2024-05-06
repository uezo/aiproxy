import base64
from datetime import datetime
import json
import logging
import re
import time
import traceback
from typing import List, Union
import httpx
from fastapi import Request
from fastapi.responses import StreamingResponse, JSONResponse
from botocore.auth import SigV4Auth
from botocore.awsrequest import AWSRequest
from botocore.credentials import Credentials
from aiproxy.proxy import RequestFilterBase, ResponseFilterBase
from aiproxy.httpx_proxy import HTTPXProxy, SessionInfo, SessionRequestItemBase, SessionResponseItemBase, SessionStreamChunkItemBase, SessionErrorItemBase
from aiproxy.accesslog import _AccessLogBase
from aiproxy.queueclient import QueueClientBase


logger = logging.getLogger(__name__)


class ClaudeRequestItem(SessionRequestItemBase):
    def to_accesslog(self, accesslog_cls: _AccessLogBase) -> _AccessLogBase:
        try:
            content = self.request_json["messages"][-1]["content"]
            if isinstance(content, list):
                content = content[-1]
            if isinstance(content, dict):
                if content["type"] == "text":
                    content = content["text"]
                elif content["type"] == "text":
                    content = "(image)"
                else:
                    content = "(other)"

        except Exception:
            logger.error(f"Error at parsing request for log: {self.request_json}")
            content = None

        return accesslog_cls(
            request_id=self.request_id,
            created_at=datetime.utcnow(),
            direction="request",
            content=content,
            raw_body=json.dumps(self.request_json, ensure_ascii=False),
            raw_headers=json.dumps(self.request_headers, ensure_ascii=False),
            model=self.session.extra_info["model"]
        )


class ClaudeResponseItem(SessionResponseItemBase):
    def to_accesslog(self, accesslog_cls: _AccessLogBase) -> _AccessLogBase:
        content = None
        prompt_tokens = 0
        completion_tokens = 0
        try:
            content = self.response_json["content"][0]["text"]
            prompt_tokens = self.response_json["usage"]["input_tokens"] \
                if "usage" in self.response_json else 0
            completion_tokens = self.response_json["usage"]["output_tokens"] \
                if "usage" in self.response_json else 0
        except Exception:
            logger.error(f"Error at parsing response for log: {self.response_json}")

        return accesslog_cls(
            request_id=self.request_id,
            created_at=datetime.utcnow(),
            direction="response",
            status_code=self.status_code,
            content=content,
            function_call=None,
            tool_calls=None,
            raw_body=json.dumps(self.response_json, ensure_ascii=False),
            raw_headers=json.dumps(self.response_headers, ensure_ascii=False),
            model=self.response_json.get("model"),
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            request_time=self.duration,
            request_time_api=self.duration_api
        )


class ClaudeStreamResponseItem(SessionStreamChunkItemBase):
    def to_accesslog(self, accesslog_cls: _AccessLogBase) -> _AccessLogBase:
        response_text = ""
        model = ""
        prompt_tokens = 0
        completion_tokens = 0

        self.response_content = str(self.session.extra_info["response_events"])
        try:
            for chunk in self.session.extra_info["response_events"]:
                # Parse JSON data from bytes chunk
                for m in re.findall(rb"event\{.*?\}", chunk):
                    b64bytes = json.loads(m[5:].decode("utf-8"))["bytes"]
                    chunk_json = json.loads(base64.b64decode(b64bytes).decode())

                    # Get metadata of request
                    if chunk_json["type"] == "message_start":
                        msg = chunk_json["message"]
                        model = msg["model"]
                        prompt_tokens = msg["usage"]["input_tokens"]

                    # Get content chunk
                    elif chunk_json["type"] == "content_block_delta":
                        response_text += chunk_json["delta"]["text"] or ""

                    # Get metadata of response
                    elif chunk_json["type"] == "message_delta":
                        completion_tokens = chunk_json["usage"]["output_tokens"]
        except Exception as ex:
            logger.error(f"Error at to_accesslog: {ex}\n{traceback.format_exc()}")

        return accesslog_cls(
            request_id=self.request_id,
            created_at=datetime.utcnow(),
            direction="response",
            status_code=self.status_code,
            content=response_text,
            function_call=None,
            tool_calls=None,
            raw_body=self.response_content,
            raw_headers=json.dumps(self.response_headers, ensure_ascii=False),
            model=model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            request_time=self.duration,
            request_time_api=self.duration_api
        )


class ClaudeErrorItem(SessionErrorItemBase):
    ...


queue_item_types = [ClaudeRequestItem, ClaudeResponseItem, ClaudeStreamResponseItem, ClaudeErrorItem]


# Reverse proxy application for Anthropic Claude3 API
class BedrockClaudeProxy(HTTPXProxy):
    def __init__(
        self,
        *,
        aws_access_key_id: str = None,
        aws_secret_access_key: str = None,
        region_name: str = None,
        timeout=60.0,
        request_filters: List[RequestFilterBase] = None,
        response_filters: List[ResponseFilterBase] = None,
        request_item_class: type = ClaudeRequestItem,
        response_item_class: type = ClaudeResponseItem,
        stream_response_item_class: type = ClaudeStreamResponseItem,
        error_item_class: type = ClaudeErrorItem,
        access_logger_queue: QueueClientBase
    ):
        super().__init__(
            timeout=timeout,
            request_filters=request_filters,
            response_filters=response_filters,
            request_item_class=request_item_class,
            response_item_class=response_item_class,
            stream_response_item_class=stream_response_item_class,
            error_item_class=error_item_class,
            access_logger_queue=access_logger_queue
        )

        self.api_base_url = f"https://bedrock-runtime.{region_name}.amazonaws.com"
        self.api_chat_resource_path = "/model/{model_and_method:path}"
        self.api_service_id = "bedrock-claude"

        self.authorizer = SigV4Auth(
            credentials=Credentials(
                access_key=aws_access_key_id,
                secret_key=aws_secret_access_key
            ),
            service_name="bedrock",
            region_name=region_name
        )

    def text_to_response_json(self, text: str) -> dict:
        return {
            "content": [{"type": "text", "text": text}],
            "usage": {"input_tokens": 0, "output_tokens": 0}
        }

    async def filter_request(self, session: SessionInfo) -> Union[None, JSONResponse]:
        for f in self.request_filters:
            if completion_content := await f.filter(session.request_id, session.request_json, session.request_headers):
                # Make JsonResponse when filter returns content
                session.response_json = self.text_to_response_json(completion_content)
                json_response = JSONResponse(session.response_json)
                self.add_response_headers(json_response, session.request_id)
                session.response_headers = dict(json_response.headers)

                # Response log
                self.access_logger_queue.put(
                    self.response_item_class.from_session(session=session)
                )

                # Return response
                if session.stream:
                    logger.warning("ClaudeProxy for Bedrock doesn't support instant reply from RequestFilter in stream mode. Return message as 400 bad request.")
                    json_response.status_code = 400

                return json_response

        return None

    async def parse_request(self, fastapi_request: Request, session: SessionInfo):
        await super().parse_request(fastapi_request, session)
        session.stream = "invoke-with-response-stream" in str(session.request_url)
        session.extra_info["model"] = re.search(r"model/(.*?)/", session.request_url).group(1)

    def get_aws_request_header_with_cred(self, url: str, request_headers: dict, bedrock_params: dict):
        ar = AWSRequest(
            method="POST",
            url=url,
            headers=request_headers,
            data=json.dumps(bedrock_params).encode()
        )
        self.authorizer.add_auth(ar)
        ar.prepare()
        return ar.headers

    def prepare_httpx_request_headers(self, session: SessionInfo):
        super().prepare_httpx_request_headers(session)

        # Remove headers to prevent signature error
        if "authorization" in session.request_headers:
            del session.request_headers["authorization"]
        if "connection" in session.request_headers:
            del session.request_headers["connection"]

        # Add AWS Authorization header
        session.request_headers["authorization"] = \
            self.get_aws_request_header_with_cred(
                self.make_url(session),
                session.request_headers,
                session.request_json
            )["authorization"]

    def make_url(self, session: SessionInfo):
        return f"{self.api_base_url}/model/{session.extra_info['model']}/{('invoke-with-response-stream' if session.stream else 'invoke')}"

    def make_stream_response(self, async_client: httpx.AsyncClient, stream_response: httpx.Response, session: SessionInfo):
        async def process_stream():
            session.extra_info["response_events"] = []
            try:
                # Yield chunked responses
                async for b in stream_response.aiter_raw():
                    session.extra_info["response_events"].append(b)
                    yield b
            
            finally:
                # Make response log
                try:
                    now = time.time()
                    session.duration = now - session.start_time
                    session.duration_api = now - session.start_time_api
                    self.access_logger_queue.put(
                        self.stream_response_item_class.from_session(session)
                    )

                except Exception as ex:
                    logger.error(f"Failed in making log items: {ex}\n{traceback.format_exc()}")
                    logger.error(f"response_content: {session.response_body}")
                
                finally:
                    await async_client.aclose()

        return StreamingResponse(
            process_stream(),
            status_code=session.status_code,
            headers=session.response_headers
        )
