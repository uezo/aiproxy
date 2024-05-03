from datetime import datetime
import json
import logging
from typing import List
import tiktoken
from fastapi import Request
from .proxy import RequestFilterBase, ResponseFilterBase
from .httpx_proxy import HTTPXProxy, SessionInfo, SessionRequestItemBase, SessionResponseItemBase, SessionStreamChunkItemBase, SessionErrorItemBase
from .accesslog import _AccessLogBase
from .queueclient import QueueClientBase

logger = logging.getLogger(__name__)


class ChatGPTRequestItem(SessionRequestItemBase):
    def to_accesslog(self, accesslog_cls: _AccessLogBase) -> _AccessLogBase:
        request_headers_copy = self.request_headers.copy()
        if auth := request_headers_copy.get("authorization"):
            request_headers_copy["authorization"] = auth[:12] + "*****" + auth[-2:]

        content = self.request_json["messages"][-1]["content"]
        if isinstance(content, list):
            for c in content:
                if c["type"] == "text":
                    content = c["text"]
                    break
            else:
                content = json.dumps(content)

        accesslog = accesslog_cls(
            request_id=self.request_id,
            created_at=datetime.utcnow(),
            direction="request",
            content=content,
            raw_body=json.dumps(self.request_json, ensure_ascii=False),
            raw_headers=json.dumps(request_headers_copy, ensure_ascii=False),
            model=self.request_json.get("model")
        )

        return accesslog


class ChatGPTResponseItem(SessionResponseItemBase):
    def to_accesslog(self, accesslog_cls: _AccessLogBase) -> _AccessLogBase:
        content=self.response_json["choices"][0]["message"].get("content")
        function_call=self.response_json["choices"][0]["message"].get("function_call")
        tool_calls=self.response_json["choices"][0]["message"].get("tool_calls")
        response_headers = json.dumps(dict(self.response_headers.items()), ensure_ascii=False) if self.response_headers is not None else None
        model=self.response_json["model"]
        prompt_tokens=self.response_json["usage"]["prompt_tokens"]
        completion_tokens=self.response_json["usage"]["completion_tokens"]

        return accesslog_cls(
            request_id=self.request_id,
            created_at=datetime.utcnow(),
            direction="response",
            status_code=self.status_code,
            content=content,
            function_call=json.dumps(function_call, ensure_ascii=False) if function_call is not None else None,
            tool_calls=json.dumps(tool_calls, ensure_ascii=False) if tool_calls is not None else None,
            raw_body=json.dumps(self.response_json, ensure_ascii=False),
            raw_headers=response_headers,
            model=model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            request_time=self.duration,
            request_time_api=self.duration_api
        )


token_encoder = tiktoken.get_encoding("cl100k_base")

def count_token(content: str):
    return len(token_encoder.encode(content))

def count_request_token(request_json: dict):
    tokens_per_message = 3
    tokens_per_name = 1
    token_count = 0

    # messages
    for m in request_json["messages"]:
        token_count += tokens_per_message
        for k, v in m.items():
            if isinstance(v, list):
                for c in v:
                    if c.get("type") == "text":
                        token_count += count_token(c["text"])
            else:
                token_count += count_token(v)
            if k == "name":
                token_count += tokens_per_name

    # functions
    if functions := request_json.get("functions"):
        for f in functions:
            token_count += count_token(json.dumps(f))

    # function_call
    if function_call := request_json.get("function_call"):
        if isinstance(function_call, dict):
            token_count += count_token(json.dumps(function_call))
        else:
            token_count += count_token(function_call)

    # tools
    if tools := request_json.get("tools"):
        for t in tools:
            token_count += count_token(json.dumps(t))

    if tool_choice := request_json.get("tool_choice"):
        token_count += count_token(json.dumps(tool_choice))

    token_count += 3
    return token_count


class ChatGPTStreamResponseItem(SessionStreamChunkItemBase):
    def to_accesslog(self, accesslog_cls: _AccessLogBase) -> _AccessLogBase:
        response_text = ""
        model = ""
        function_call = None
        tool_calls = None
        prompt_tokens = 0
        completion_tokens = 0

        # Parse info from chunks
        chunks = self.response_content.split("\n\n")
        for chunk in chunks:
            chunk_strip = chunk.strip()
            if not chunk_strip.startswith("data:"):
                continue    # Skip invalid data
            if chunk_strip.endswith("[DONE]"):
                break       # Break when [DONE]

            chunk_json = json.loads(chunk_strip[5:])

            if len(chunk_json["choices"]) == 0:
                # Azure returns the first delta with empty choices
                continue
            
            if not model and "model" in chunk_json:
                model = chunk_json.get("model")

            delta = chunk_json["choices"][0]["delta"]

            # Make tool_calls
            if delta.get("tool_calls"):
                if tool_calls is None:
                    tool_calls = []
                if delta["tool_calls"][0]["function"].get("name"):
                    tool_calls.append({
                        "type": "function",
                        "function": {
                            "name": delta["tool_calls"][0]["function"]["name"],
                            "arguments": ""
                        }
                    })
                elif delta["tool_calls"][0]["function"].get("arguments"):
                    tool_calls[-1]["function"]["arguments"] += delta["tool_calls"][0]["function"].get("arguments") or ""

            # Make function_call
            elif delta.get("function_call"):
                if function_call is None:
                    function_call = {}
                if delta["function_call"].get("name"):
                    function_call["name"] = delta["function_call"]["name"]
                    function_call["arguments"] = ""
                elif delta["function_call"].get("arguments"):
                    function_call["arguments"] += delta["function_call"]["arguments"]

            # Text content
            else:
                response_text += delta.get("content") or ""
        
        # Serialize
        function_call_str = json.dumps(function_call, ensure_ascii=False) if function_call is not None else None
        tool_calls_str = json.dumps(tool_calls, ensure_ascii=False) if tool_calls is not None else None
        response_headers = json.dumps(dict(self.response_headers.items()), ensure_ascii=False) if self.response_headers is not None else None

        # Count tokens
        prompt_tokens = count_request_token(self.session.request_json)

        if tool_calls_str:
            completion_tokens = count_token(tool_calls_str)
        elif function_call_str:
            completion_tokens = count_token(function_call_str)
        else:
            completion_tokens = count_token(response_text)

        return accesslog_cls(
            request_id=self.request_id,
            created_at=datetime.utcnow(),
            direction="response",
            status_code=self.status_code,
            content=response_text,
            function_call=function_call_str,
            tool_calls=tool_calls_str,
            raw_body=self.response_content,
            raw_headers=response_headers,
            model=model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            request_time=self.duration,
            request_time_api=self.duration_api
        )


class ChatGPTErrorItem(SessionErrorItemBase):
    ...


queue_item_types = [ChatGPTRequestItem, ChatGPTResponseItem, ChatGPTStreamResponseItem, ChatGPTErrorItem]


# Reverse proxy application for OpenAI ChatGPT API
class ChatGPTProxy(HTTPXProxy):
    def __init__(
        self,
        *,
        api_key: str = None,
        timeout=60.0,
        request_filters: List[RequestFilterBase] = None,
        response_filters: List[ResponseFilterBase] = None,
        request_item_class: type = ChatGPTRequestItem,
        response_item_class: type = ChatGPTResponseItem,
        stream_response_item_class: type = ChatGPTStreamResponseItem,
        error_item_class: type = ChatGPTErrorItem,
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
        self.api_base_url = "https://api.openai.com/v1"
        self.api_chat_resource_path = "/chat/completions"
        self.api_service_id = "openai"

    def text_to_response_json(self, text: str) -> dict:
        return {
            "id": "-",
            "object": "chat.completion",
            "created": int(datetime.utcnow().timestamp()),
            "model": "request_filter",
            "choices": [{
                "index": 0,
                "message": {
                "role": "assistant",
                "content": text,
                },
                "finish_reason": "stop"
            }],
            "usage": {
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "total_tokens": 0
            }
        }

    def text_to_response_chunks(self, text: str) -> List[dict]:
        first_chunk = {
            "id": "-",
            "choices": [{"delta": {"role": "assistant", "content": ""}, "finish_reason": None, "index": 0}],
            "created": 0,
            "model": "request_filter",
            "object": "chat.completion",
            "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
        }
        last_chunk = {
            "id": "-",
            "choices": [{"delta": {"content": text}, "finish_reason": "stop", "index": 0}],
            "created": 0,
            "model": "request_filter",
            "object": "chat.completion",
            "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
        }
        return [first_chunk, last_chunk]

    async def parse_request(self, fastapi_request: Request, session: SessionInfo):
        await super().parse_request(fastapi_request, session)
        session.stream = session.request_json.get("stream") is True

    def prepare_httpx_request_headers(self, session: SessionInfo):
        super().prepare_httpx_request_headers(session)
        session.request_headers["authorization"] = f"Bearer {self.api_key}"


# Reverse proxy application for Azure OpenAI Service API
class AzureOpenAIProxy(ChatGPTProxy):
    def __init__(
        self,
        *,
        api_key: str = None,
        resource_name: str = None,
        deployment_id: str = None,
        api_version: str = None,
        timeout=60.0,
        request_filters: List[RequestFilterBase] = None,
        response_filters: List[ResponseFilterBase] = None,
        request_item_class: type = ChatGPTRequestItem,
        response_item_class: type = ChatGPTResponseItem,
        stream_response_item_class: type = ChatGPTStreamResponseItem,
        error_item_class: type = ChatGPTErrorItem,
        access_logger_queue: QueueClientBase
    ):
        super().__init__(
            api_key=api_key,
            timeout=timeout,
            request_filters=request_filters,
            response_filters=response_filters,
            request_item_class=request_item_class,
            response_item_class=response_item_class,
            stream_response_item_class=stream_response_item_class,
            error_item_class=error_item_class,
            access_logger_queue=access_logger_queue
        )

        self.api_base_url = "https://{resource_name}.openai.azure.com/openai/deployments/{deployment_id}/chat/completions?api-version={api_version}"
        self.resource_name = resource_name
        self.deployment_id = deployment_id
        self.api_version = api_version

    def prepare_httpx_request_headers(self, session: SessionInfo):
        super().prepare_httpx_request_headers(session)
        session.request_headers["api-key"] = self.api_key

    def make_url(self, session: SessionInfo):
        return self.api_base_url.format(
            resource_name=self.resource_name,
            deployment_id=self.deployment_id,
            api_version=self.api_version
        )
