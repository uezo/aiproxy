import base64
from datetime import datetime
import json
import logging
import re
import time
import traceback
from typing import List, Union
from uuid import uuid4
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse, Response
import httpx
from botocore.auth import SigV4Auth
from botocore.awsrequest import AWSRequest
from botocore.credentials import Credentials
from .proxy import ProxyBase, RequestFilterBase, ResponseFilterBase, RequestFilterException, ResponseFilterException
from .accesslog import _AccessLogBase, RequestItemBase, ResponseItemBase, StreamChunkItemBase, ErrorItemBase
from .queueclient import QueueClientBase


logger = logging.getLogger(__name__)


class Claude2RequestItem(RequestItemBase):
    def to_accesslog(self, accesslog_cls: _AccessLogBase) -> _AccessLogBase:
        try:
            content = self.request_json["prompt"].split("Human:")[-1].split("Assistant:")[0].strip()
        except:
            logger.error(f"Error at parsing prompt text for log: {self.request_json.get('prompt')}")
            content = None

        return accesslog_cls(
            request_id=self.request_id,
            created_at=datetime.utcnow(),
            direction="request",
            content=content,
            raw_body=json.dumps(self.request_json, ensure_ascii=False),
            raw_headers=json.dumps(self.request_headers, ensure_ascii=False),
            model="anthropic.claude-v2"
        )


class Claude2ResponseItem(ResponseItemBase):
    def to_accesslog(self, accesslog_cls: _AccessLogBase) -> _AccessLogBase:
        return accesslog_cls(
            request_id=self.request_id,
            created_at=datetime.utcnow(),
            direction="response",
            status_code=self.status_code,
            content=self.response_json["completion"],
            function_call=None,
            tool_calls=None,
            raw_body=json.dumps(self.response_json, ensure_ascii=False),
            raw_headers=json.dumps(self.response_headers, ensure_ascii=False),
            model="anthropic.claude-v2",
            prompt_tokens=self.response_headers.get("x-amzn-bedrock-input-token-count", 0),
            completion_tokens=self.response_headers.get("x-amzn-bedrock-output-token-count", 0),
            request_time=self.duration,
            request_time_api=self.duration_api
        )


class Claude2StreamResponseItem(StreamChunkItemBase):
    def to_accesslog(self, chunks: list, accesslog_cls: _AccessLogBase) -> _AccessLogBase:
        chunk_jsons = []
        response_content = ""
        prompt_tokens = 0
        completion_tokens = 0

        # Parse info from chunks
        for chunk in chunks:
            chunk_jsons.append(chunk.chunk_json)
            response_content += chunk.chunk_json["completion"] or ""

        # Tokens
        if len(chunk_jsons) > 0:
            if "amazon-bedrock-invocationMetrics" in chunk_jsons[-1]:
                prompt_tokens = chunk_jsons[-1]["amazon-bedrock-invocationMetrics"]["inputTokenCount"]
                completion_tokens = chunk_jsons[-1]["amazon-bedrock-invocationMetrics"]["outputTokenCount"]
            else:
                # On error response in stream mode
                prompt_tokens = self.response_headers.get("x-amzn-bedrock-input-token-count", 0)
                completion_tokens = self.response_headers.get("x-amzn-bedrock-output-token-count", 0)

        return accesslog_cls(
            request_id=self.request_id,
            created_at=datetime.utcnow(),
            direction="error" if self.response_headers.get("x-amzn-errortype") else "response",
            status_code=self.status_code,
            content=response_content,
            function_call=None,
            tool_calls=None,
            raw_body=json.dumps(chunk_jsons, ensure_ascii=False),
            raw_headers=json.dumps(self.response_headers, ensure_ascii=False),
            model="anthropic.claude-v2",
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            request_time=self.duration,
            request_time_api=self.duration_api
        )


class Claude2ErrorItem(ErrorItemBase):
    ...


queue_item_types = [Claude2RequestItem, Claude2ResponseItem, Claude2StreamResponseItem, Claude2ErrorItem]


# Reverse proxy application for Claude2 on AWS Bedrock
class Claude2Proxy(ProxyBase):
    def __init__(
        self,
        *,
        aws_access_key_id: str = None,
        aws_secret_access_key: str = None,
        region_name: str = None,
        timeout=60.0,
        request_filters: List[RequestFilterBase] = None,
        response_filters: List[ResponseFilterBase] = None,
        access_logger_queue: QueueClientBase
    ):
        super().__init__(
            request_filters=request_filters,
            response_filters=response_filters,
            access_logger_queue=access_logger_queue
        )

        self.aws_access_key_id = aws_access_key_id
        self.aws_secret_access_key = aws_secret_access_key
        self.region_name = region_name
        self.aws_url = f"https://bedrock-runtime.{self.region_name}.amazonaws.com"

        # AWS credentials
        self.authorizer = SigV4Auth(
            credentials=Credentials(
                access_key=self.aws_access_key_id,
                secret_key=self.aws_secret_access_key
            ),
            service_name="bedrock",
            region_name=self.region_name
        )

        # HTTP Client (should close on end)
        self.http_client = httpx.AsyncClient(timeout=timeout)

    async def filter_request(self, request_id: str, request_json: dict, request_headers: dict, stream: bool) -> Union[dict, JSONResponse]:
        for f in self.request_filters:
            if completion_content := await f.filter(request_id, request_json, request_headers):
                # Return response if filter returns JsonResponse
                resp_for_log = {
                    "completion": completion_content
                }
                # Response log
                self.access_logger_queue.put(Claude2ResponseItem(
                    request_id=request_id,
                    response_json=resp_for_log,
                    response_headers={
                        "x-amzn-bedrock-input-token-count": 0,
                        "x-amzn-bedrock-output-token-count": 0
                    },
                    status_code=400 if stream else 200
                ))

                if stream:
                    logger.warning("Claude2Proxy doesn't support instant reply from RequestFilter. Return message as 400 bad request.")
                    return self.return_response_with_headers(JSONResponse({"message": completion_content}, status_code=400), request_id)
                else:
                    return self.return_response_with_headers(JSONResponse(resp_for_log), request_id)

        return request_json

    async def filter_response(self, request_id: str, response_json: dict) -> dict:
        for f in self.response_filters:
            if immediately_return_json_resp := await f.filter(request_id, response_json):
                return immediately_return_json_resp

        return response_json

    def get_aws_request_header_with_cred(self, url: str, bedrock_params: dict):
        ar = AWSRequest(
            method="POST",
            url=url,
            headers={
                "Content-Type": "application/json",
                "X-Amzn-Bedrock-Accept": "application/json",
            },
            data=json.dumps(bedrock_params).encode()
        )
        self.authorizer.add_auth(ar)
        ar.prepare()
        return ar.headers

    def return_response_with_headers(self, resp: Response, request_id: str):
        self.add_response_headers(response=resp, request_id=request_id)
        return resp

    def add_route(self, app: FastAPI, base_url: str):
        @app.post(base_url + "/{invoke_method}")
        async def handle_request(request: Request, invoke_method: str):
            request_id = str(uuid4())

            try:
                start_time = time.time()
                request_json = await request.json()
                request_headers = dict(request.headers.items())

                # Log request
                self.access_logger_queue.put(Claude2RequestItem(
                    request_id=request_id,
                    request_json=request_json,
                    request_headers=request_headers
                ))

                # Filter request
                request_json = await self.filter_request(request_id, request_json, request_headers, invoke_method == "invoke-with-response-stream")
                if isinstance(request_json, JSONResponse):
                    return request_json

                # Call API and handling response from API
                url = f"{self.aws_url}/model/anthropic.claude-v2/{invoke_method}"
                aws_request_header = self.get_aws_request_header_with_cred(url, request_json)
                start_time_api = time.time()

                if invoke_method == "invoke-with-response-stream":
                    async def process_stream(stream_response: httpx.Response, status_code: int):
                        try:
                            async for chunk in stream_response.aiter_raw():
                                # Parse JSON data from bytes chunk
                                for m in re.findall(rb"event\{.*?\}", chunk):
                                    b64bytes = json.loads(m[5:].decode("utf-8"))["bytes"]
                                    chunk_json = json.loads(base64.b64decode(b64bytes).decode())
                                    self.access_logger_queue.put(Claude2StreamResponseItem(
                                        request_id=request_id,
                                        chunk_json=chunk_json
                                    ))

                                yield chunk

                            # Add hearedes for log
                            self.return_response_with_headers(stream_response, request_id)

                        finally:
                            # Response log
                            now = time.time()
                            self.access_logger_queue.put(Claude2StreamResponseItem(
                                request_id=request_id,
                                response_headers=dict(stream_response.headers.items()),
                                duration=now - start_time,
                                duration_api=now - start_time_api,
                                request_json=request_json,
                                status_code=status_code
                            ))

                    stream_request = httpx.Request(method="POST", url=url, headers=dict(aws_request_header), json=request_json)
                    stream_response = await self.http_client.send(request=stream_request, stream=True)

                    # DO NOT raise status error here to return error info in stream

                    return self.return_response_with_headers(StreamingResponse(
                        process_stream(stream_response, stream_response.status_code),
                        status_code=stream_response.status_code,
                        headers=stream_response.headers
                    ), request_id)

                else:
                    completion_response = await self.http_client.post(url=url, headers=dict(aws_request_header), json=request_json)
                    completion_response.raise_for_status()

                    duration_api = time.time() - start_time_api
                    response_json = completion_response.json()

                    # Filter response
                    original_response_json = response_json.copy()
                    filtered_response_json = await self.filter_response(request_id, response_json)

                    # Make JSON response
                    if original_response_json != filtered_response_json:
                        json_response = JSONResponse(original_response_json, completion_response.status_code, completion_response.headers)
                    else:
                        # Remove incorrect content-length
                        completion_response.headers.pop("Content-Length")
                        json_response = JSONResponse(filtered_response_json, completion_response.status_code, completion_response.headers)

                    self.add_response_headers(json_response, request_id)

                    # Response log
                    self.access_logger_queue.put(Claude2ResponseItem(
                        request_id=request_id,
                        response_json=filtered_response_json,
                        response_headers=dict(json_response.headers.items()),
                        duration=time.time() - start_time,
                        duration_api=duration_api,
                        status_code=completion_response.status_code
                    ))

                    return json_response

            # Error handlers
            except RequestFilterException as rfex:
                logger.error(f"Request filter error: {rfex}\n{traceback.format_exc()}")

                resp_json = {"error": {"message": rfex.message, "type": "request_filter_error", "param": None, "code": None}}

                # Error log
                self.access_logger_queue.put(Claude2ErrorItem(
                    request_id=request_id,
                    exception=rfex,
                    traceback_info=traceback.format_exc(),
                    response_json=resp_json,
                    status_code=rfex.status_code
                ))

                return self.return_response_with_headers(JSONResponse(resp_json, status_code=rfex.status_code), request_id)

            except ResponseFilterException as rfex:
                logger.error(f"Response filter error: {rfex}\n{traceback.format_exc()}")

                resp_json = {"error": {"message": rfex.message, "type": "response_filter_error", "param": None, "code": None}}

                # Error log
                self.access_logger_queue.put(Claude2ErrorItem(
                    request_id=request_id,
                    exception=rfex,
                    traceback_info=traceback.format_exc(),
                    response_json=resp_json,
                    status_code=rfex.status_code
                ))

                return self.return_response_with_headers(JSONResponse(resp_json, status_code=rfex.status_code), request_id)

            except httpx.HTTPStatusError as htex:
                logger.error(f"Error at server: {htex}\n{traceback.format_exc()}")

                # Error log
                try:
                    resp_json = htex.response.json()
                except:
                    try:
                        resp_json = str(await htex.response.aread())
                    except:
                        logger.warning("Error")

                self.access_logger_queue.put(Claude2ErrorItem(
                    request_id=request_id,
                    exception=htex,
                    traceback_info=traceback.format_exc(),
                    response_json=resp_json,
                    status_code=htex.response.status_code
                ))

                htex.response.headers.pop("content-length")

                return self.return_response_with_headers(JSONResponse(
                    resp_json,
                    status_code=htex.response.status_code,
                    headers=htex.response.headers
                ), request_id)

            except Exception as ex:
                logger.error(f"Error at server: {ex}\n{traceback.format_exc()}")

                resp_json = {"error": {"message": "Proxy error", "type": "proxy_error", "param": None, "code": None}}

                # Error log
                self.access_logger_queue.put(Claude2ErrorItem(
                    request_id=request_id,
                    exception=ex,
                    traceback_info=traceback.format_exc(),
                    response_json=resp_json,
                    status_code=502
                ))

                return self.return_response_with_headers(JSONResponse(resp_json, status_code=502), request_id)
