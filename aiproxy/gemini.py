from datetime import datetime
import json
import logging
import re
import time
import traceback
from typing import List
import httpx
from fastapi import Request
from fastapi.responses import StreamingResponse
from .proxy import RequestFilterBase, ResponseFilterBase
from .httpx_proxy import HTTPXProxy, SessionInfo, SessionRequestItemBase, SessionResponseItemBase, SessionStreamChunkItemBase, SessionErrorItemBase
from .accesslog import _AccessLogBase
from .queueclient import QueueClientBase


logger = logging.getLogger(__name__)


class GeminiRequestItem(SessionRequestItemBase):
    def to_accesslog(self, accesslog_cls: _AccessLogBase) -> _AccessLogBase:
        accesslog = accesslog_cls(
            request_id=self.request_id,
            created_at=datetime.utcnow(),
            direction="request",
            content=self.request_json["contents"][-1]["parts"][0].get("text"),
            raw_body=json.dumps(self.request_json, ensure_ascii=False),
            raw_headers=json.dumps(self.request_headers, ensure_ascii=False),
            model=self.session.extra_info["model"]
        )

        return accesslog


class GeminiResponseItem(SessionResponseItemBase):
    def to_accesslog(self, accesslog_cls: _AccessLogBase) -> _AccessLogBase:
        content = ""
        tool_calls = None
        for p in self.response_json["candidates"][0]["content"]["parts"]:
            if t := p.get("text"):
                content = t
            if f := p.get("functionCall"):
                tool_calls = f
 
        response_headers = json.dumps(dict(self.response_headers.items()), ensure_ascii=False) if self.response_headers is not None else None

        return accesslog_cls(
            request_id=self.request_id,
            created_at=datetime.utcnow(),
            direction="response",
            status_code=self.status_code,
            content=content,
            function_call=None,
            tool_calls=json.dumps(tool_calls, ensure_ascii=False) if tool_calls is not None else None,
            raw_body=json.dumps(self.response_json, ensure_ascii=False),
            raw_headers=response_headers,
            model=self.session.extra_info["model"],
            prompt_tokens=0,
            completion_tokens=0,
            request_time=self.duration,
            request_time_api=self.duration_api
        )


class GeminiStreamResponseItem(SessionStreamChunkItemBase):
    def to_accesslog(self, accesslog_cls: _AccessLogBase) -> _AccessLogBase:
        response_json = json.loads(self.response_content)

        content = ""
        function_calls = []
        for chunk in response_json:
            if "candidates" in chunk:
                for cand in chunk["candidates"]:
                    if "content" in cand and "parts" in cand["content"]:
                        for p in cand["content"]["parts"]:
                            if text := p.get("text"):
                                content += text
                            if function_call := p.get("functionCall"):
                                function_calls.append(function_call)

        # Serialize
        function_calls_str = json.dumps(function_calls, ensure_ascii=False) if len(function_calls) > 0 else None
        response_headers = json.dumps(dict(self.response_headers.items()), ensure_ascii=False) if self.response_headers is not None else None

        return accesslog_cls(
            request_id=self.request_id,
            created_at=datetime.utcnow(),
            direction="response",
            status_code=self.status_code,
            content=content,
            function_call=function_calls_str,
            tool_calls=None,
            raw_body=json.dumps(response_json, ensure_ascii=False),
            raw_headers=response_headers,
            model=self.session.extra_info["model"],
            prompt_tokens=0,
            completion_tokens=0,
            request_time=self.duration,
            request_time_api=self.duration_api
        )


class GeminiErrorItem(SessionErrorItemBase):
    ...


queue_item_types = [GeminiRequestItem, GeminiResponseItem, GeminiStreamResponseItem, GeminiErrorItem]


# Reverse proxy application for Google AI Studio Gemini API
class GeminiProxy(HTTPXProxy):
    def __init__(
        self,
        *,
        api_key: str = None,
        timeout=60.0,
        request_filters: List[RequestFilterBase] = None,
        response_filters: List[ResponseFilterBase] = None,
        request_item_class: type = GeminiRequestItem,
        response_item_class: type = GeminiResponseItem,
        stream_response_item_class: type = GeminiStreamResponseItem,
        error_item_class: type = GeminiErrorItem,
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

        self.api_key = api_key
        self.api_base_url = "https://generativelanguage.googleapis.com/v1beta/models/{model}:{method}?key={api_key}"

    def text_to_response_json(self, text: str) -> dict:
        return {
            "candidates": [{
                "content": {"parts": [{"text": text}], "role": "model"},
                "finishReason": "STOP",
                "index": 0,
                "safetyRatings": [
                    {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "probability": "NEGLIGIBLE"},
                    {"category": "HARM_CATEGORY_HATE_SPEECH", "probability": "NEGLIGIBLE"},
                    {"category": "HARM_CATEGORY_HARASSMENT", "probability": "NEGLIGIBLE"},
                    {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "probability": "NEGLIGIBLE"}
                ]
            }],
            "promptFeedback": {
                "safetyRatings": [
                    {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "probability": "NEGLIGIBLE"},
                    {"category": "HARM_CATEGORY_HATE_SPEECH", "probability": "NEGLIGIBLE"},
                    {"category": "HARM_CATEGORY_HARASSMENT", "probability": "NEGLIGIBLE"},
                    {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "probability": "NEGLIGIBLE"}
                ]
            }
        }

    def text_to_response_chunks(self, text: str) -> List[dict]:
        first_chunk = {
            "candidates": [{
                "content": {
                    "parts": [{"text": ""}],
                    "role": "model"
                },
                "finishReason": "STOP",
                "index": 0
            }]
        }
        text_chunk = {
            "candidates": [
                {
                "content": {
                    "parts": [
                    {
                        "text": text
                    }
                    ],
                    "role": "model"
                },
                "finishReason": "STOP",
                "index": 0,
                "safetyRatings": [
                    {
                    "category": "HARM_CATEGORY_SEXUALLY_EXPLICIT",
                    "probability": "NEGLIGIBLE"
                    },
                    {
                    "category": "HARM_CATEGORY_HATE_SPEECH",
                    "probability": "NEGLIGIBLE"
                    },
                    {
                    "category": "HARM_CATEGORY_HARASSMENT",
                    "probability": "NEGLIGIBLE"
                    },
                    {
                    "category": "HARM_CATEGORY_DANGEROUS_CONTENT",
                    "probability": "NEGLIGIBLE"
                    }
                ]
                }
            ]
        }
        last_chunk = {
            "candidates": [
                {
                "content": {
                    "parts": [
                    {
                        "text": ""
                    }
                    ],
                    "role": "model"
                },
                "finishReason": "STOP",
                "index": 0,
                "safetyRatings": [
                    {
                    "category": "HARM_CATEGORY_SEXUALLY_EXPLICIT",
                    "probability": "NEGLIGIBLE"
                    },
                    {
                    "category": "HARM_CATEGORY_HATE_SPEECH",
                    "probability": "NEGLIGIBLE"
                    },
                    {
                    "category": "HARM_CATEGORY_HARASSMENT",
                    "probability": "NEGLIGIBLE"
                    },
                    {
                    "category": "HARM_CATEGORY_DANGEROUS_CONTENT",
                    "probability": "NEGLIGIBLE"
                    }
                ]
                }
            ]
        }
        return [first_chunk, text_chunk, last_chunk]

    async def parse_request(self, fastapi_request: Request, session: SessionInfo):
        await super().parse_request(fastapi_request, session)
        session.stream = ":streamGenerateContent" in str(session.request_url)
        session.extra_info["model"] = re.search(r"models/(.*?):", session.request_url).group(1)

    def make_url(self, session: SessionInfo):
        return self.api_base_url.format(
            model=session.extra_info["model"],
            method="streamGenerateContent" if session.stream else "generateContent",
            api_key=self.api_key
        )

    def make_stream_response(self, async_client: httpx.AsyncClient, stream_response: httpx.Response, session: SessionInfo):
        async def process_stream():
            session.response_body = ""
            try:
                # Yield chunked responses
                async for b in stream_response.aiter_raw():
                    session.response_body += b.decode("utf-8")
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
