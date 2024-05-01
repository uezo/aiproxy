from datetime import datetime
import json
import logging
from typing import List
from fastapi import Request
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
            model=self.request_json.get("model")
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

        chunks = self.response_content.split("\n\n")
        for chunk in chunks:
            chunk_split = chunk.split("data:")
            if len(chunk_split) < 2:
                continue    # Skip invalid data

            print("====")
            print(chunk_split[1])

            chunk_json = json.loads(chunk_split[1].strip())

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
class ClaudeProxy(HTTPXProxy):
    def __init__(
        self,
        *,
        api_key: str = None,
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

        self.api_key = api_key
        self.api_base_url = "https://api.anthropic.com/v1/messages"

    def text_to_response_json(self, text: str) -> dict:
        return {
            "content": [{"type": "text", "text": text}],
            "usage": {"input_tokens": 0, "output_tokens": 0}
        }

    def text_to_response_chunks(self, text: str) -> List[dict]:
        return [
            {"type": "message_start", "message": {"id": "-", "type": "message", "role": "assistant", "content": [], "model": "aiproxy", "stop_reason": None, "stop_sequence": None, "usage": {"input_tokens": 0, "output_tokens": 0}}},
            {"type": "content_block_start", "index": 0, "content_block": {"type": "text", "text": ""}},
            {"type": "ping"},
            {"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": text}},
            {"type": "content_block_stop", "index": 0},
            {"type": "message_delta", "delta": {"stop_reason": "end_turn", "stop_sequence": None}, "usage": {"output_tokens": 0}},
            {"type": "message_stop"}
        ]

    async def parse_request(self, fastapi_request: Request, session: SessionInfo):
        await super().parse_request(fastapi_request, session)
        session.stream = session.request_json.get("stream") is True

    def prepare_httpx_request_headers(self, session: SessionInfo):
        super().prepare_httpx_request_headers(session)
        session.request_headers["x-api-key"] = self.api_key
