import pytest
from datetime import datetime
import json
from time import sleep
from typing import Union
from uuid import uuid4
from fastapi.responses import JSONResponse
from sse_starlette import EventSourceResponse
from sqlalchemy import Column, String
from openai import Client, APIStatusError
from openai.types.chat import ChatCompletion
from aiproxy import (
    AccessLog,
    RequestFilterBase,
    ResponseFilterBase,
    AccessLogBase
)
from aiproxy.accesslog import AccessLogWorker, _AccessLogBase
from aiproxy.httpx_proxy import SessionInfo
from aiproxy.chatgpt import ChatGPTProxy, ChatGPTRequestItem, ChatGPTResponseItem, ChatGPTStreamResponseItem

sqlite_conn_str = "sqlite:///aiproxy_test.db"

DB_CONNECTION_STR = sqlite_conn_str

# Filters for test
class OverwriteFilter(RequestFilterBase):
    async def filter(self, request_id: str, request_json: dict, request_headers: dict) -> Union[str, None]:
        request_model = request_json["model"]
        if not request_model.startswith("gpt-3.5"):
            # Overwrite request_json
            request_json["model"] = "gpt-3.5-turbo"


class ValueReturnFilter(RequestFilterBase):
    async def filter(self, request_id: str, request_json: dict, request_headers: dict) -> Union[str, None]:
        banned_user = ["uezo"]
        user = request_json.get("user")

        # Return string message to return response right after this filter ends (not to call ChatGPT)
        if not user:
            return "user is required"
        elif user in banned_user:
            return "you can't use this service"


class OverwriteResponseFilter(ResponseFilterBase):
    async def filter(self, request_id: str, response_json: dict) -> Union[dict, None]:
        response_json["choices"][0]["message"]["content"] = "Overwrite in filter"
        return response_json

# Custom log and item for test
class MyAccessLog(AccessLogBase):
    user_id = Column(String)
    ip_address = Column(String)
    device_id = Column(String)


class MyChatGPTRequestItem(ChatGPTRequestItem):
    def to_accesslog(self, accesslog_cls: _AccessLogBase) -> _AccessLogBase:
        accesslog = super().to_accesslog(accesslog_cls)
        accesslog.ip_address = self.request_headers.get("X-Real-IP")
        accesslog.user_id = self.request_headers.get("X-OshaberiAI-UID")
        accesslog.device_id = self.request_headers.get("X-OshaberiAI-DID")

        return accesslog


# Test data
@pytest.fixture
def messages() -> list:
    return [{"role": "user", "content": "東京と名古屋の天気は？"}]

@pytest.fixture
def functions() -> list:
    return [{
        "name": "get_weather",
        "parameters": {
            "type": "object",
            "properties": {
                "location": {
                    "type": "string",
                }
            },
        }
    }]

@pytest.fixture
def tools() -> list:
    return [{
        "type": "function",
        "function": {
            "name": "get_weather",
            "parameters": {
                "type": "object",
                "properties": {
                    "location": {
                        "type": "string",
                    }
                },
            }
        }
    }]

@pytest.fixture
def request_json(messages):
    return {
        "model": "gpt-3.5-turbo",
        "messages": messages,
    }

@pytest.fixture
def request_headers():
    return {
        "Authorization": "Bearer sk-12345678901234567890"
    }

@pytest.fixture
def response_json():
    return {
        'id': 'chatcmpl-8SG30bsif06gDtariKu4kLUAqW8fN',
        'object': 'chat.completion',
        'created': 1701745562,
        'model': 'gpt-3.5-turbo-0613',
        'choices': [{
            'index': 0,
            'message': {
                'role': 'assistant',
                'content': '申し訳ありませんが、具体的な日付を教えていただけないと、具体的な天気情報を提供することができません。'
            },
            'finish_reason': 'stop'
        }],
        'usage': {
            'prompt_tokens': 21,
            'completion_tokens': 50,
            'total_tokens': 71
        },
        'system_fingerprint': None
    }

@pytest.fixture
def response_headers():
    return {"x-aiproxy-request-id": "test-id"}

@pytest.fixture
def chunked_content():
    return """
data: {"id":"chatcmpl-9JgLISX5sX016TyYaFOHshbBHQQfx","object":"chat.completion.chunk","created":1714478024,"model":"gpt-3.5-turbo-0125","system_fingerprint":"fp_3b956da36b","choices":[{"index":0,"delta":{"role":"assistant","content":""},"logprobs":null,"finish_reason":null}]}

data: {"id":"chatcmpl-9JgLISX5sX016TyYaFOHshbBHQQfx","object":"chat.completion.chunk","created":1714478024,"model":"gpt-3.5-turbo-0125","system_fingerprint":"fp_3b956da36b","choices":[{"index":0,"delta":{"content":"は"},"logprobs":null,"finish_reason":null}]}

data: {"id":"chatcmpl-9JgLISX5sX016TyYaFOHshbBHQQfx","object":"chat.completion.chunk","created":1714478024,"model":"gpt-3.5-turbo-0125","system_fingerprint":"fp_3b956da36b","choices":[{"index":0,"delta":{"content":"い"},"logprobs":null,"finish_reason":null}]}

data: {"id":"chatcmpl-9JgLISX5sX016TyYaFOHshbBHQQfx","object":"chat.completion.chunk","created":1714478024,"model":"gpt-3.5-turbo-0125","system_fingerprint":"fp_3b956da36b","choices":[{"index":0,"delta":{"content":"、"},"logprobs":null,"finish_reason":null}]}

data: {"id":"chatcmpl-9JgLISX5sX016TyYaFOHshbBHQQfx","object":"chat.completion.chunk","created":1714478024,"model":"gpt-3.5-turbo-0125","system_fingerprint":"fp_3b956da36b","choices":[{"index":0,"delta":{"content":"お"},"logprobs":null,"finish_reason":null}]}

data: {"id":"chatcmpl-9JgLISX5sX016TyYaFOHshbBHQQfx","object":"chat.completion.chunk","created":1714478024,"model":"gpt-3.5-turbo-0125","system_fingerprint":"fp_3b956da36b","choices":[{"index":0,"delta":{"content":"し"},"logprobs":null,"finish_reason":null}]}

data: {"id":"chatcmpl-9JgLISX5sX016TyYaFOHshbBHQQfx","object":"chat.completion.chunk","created":1714478024,"model":"gpt-3.5-turbo-0125","system_fingerprint":"fp_3b956da36b","choices":[{"index":0,"delta":{"content":"ゃ"},"logprobs":null,"finish_reason":null}]}

data: {"id":"chatcmpl-9JgLISX5sX016TyYaFOHshbBHQQfx","object":"chat.completion.chunk","created":1714478024,"model":"gpt-3.5-turbo-0125","system_fingerprint":"fp_3b956da36b","choices":[{"index":0,"delta":{"content":"べ"},"logprobs":null,"finish_reason":null}]}

data: {"id":"chatcmpl-9JgLISX5sX016TyYaFOHshbBHQQfx","object":"chat.completion.chunk","created":1714478024,"model":"gpt-3.5-turbo-0125","system_fingerprint":"fp_3b956da36b","choices":[{"index":0,"delta":{"content":"り"},"logprobs":null,"finish_reason":null}]}

data: {"id":"chatcmpl-9JgLISX5sX016TyYaFOHshbBHQQfx","object":"chat.completion.chunk","created":1714478024,"model":"gpt-3.5-turbo-0125","system_fingerprint":"fp_3b956da36b","choices":[{"index":0,"delta":{"content":"で"},"logprobs":null,"finish_reason":null}]}

data: {"id":"chatcmpl-9JgLISX5sX016TyYaFOHshbBHQQfx","object":"chat.completion.chunk","created":1714478024,"model":"gpt-3.5-turbo-0125","system_fingerprint":"fp_3b956da36b","choices":[{"index":0,"delta":{"content":"き"},"logprobs":null,"finish_reason":null}]}

data: {"id":"chatcmpl-9JgLISX5sX016TyYaFOHshbBHQQfx","object":"chat.completion.chunk","created":1714478024,"model":"gpt-3.5-turbo-0125","system_fingerprint":"fp_3b956da36b","choices":[{"index":0,"delta":{"content":"ます"},"logprobs":null,"finish_reason":null}]}

data: {"id":"chatcmpl-9JgLISX5sX016TyYaFOHshbBHQQfx","object":"chat.completion.chunk","created":1714478024,"model":"gpt-3.5-turbo-0125","system_fingerprint":"fp_3b956da36b","choices":[{"index":0,"delta":{"content":"！"},"logprobs":null,"finish_reason":null}]}

data: {"id":"chatcmpl-9JgLISX5sX016TyYaFOHshbBHQQfx","object":"chat.completion.chunk","created":1714478024,"model":"gpt-3.5-turbo-0125","system_fingerprint":"fp_3b956da36b","choices":[{"index":0,"delta":{"content":"何"},"logprobs":null,"finish_reason":null}]}

data: {"id":"chatcmpl-9JgLISX5sX016TyYaFOHshbBHQQfx","object":"chat.completion.chunk","created":1714478024,"model":"gpt-3.5-turbo-0125","system_fingerprint":"fp_3b956da36b","choices":[{"index":0,"delta":{"content":"を"},"logprobs":null,"finish_reason":null}]}

data: {"id":"chatcmpl-9JgLISX5sX016TyYaFOHshbBHQQfx","object":"chat.completion.chunk","created":1714478024,"model":"gpt-3.5-turbo-0125","system_fingerprint":"fp_3b956da36b","choices":[{"index":0,"delta":{"content":"お"},"logprobs":null,"finish_reason":null}]}

data: {"id":"chatcmpl-9JgLISX5sX016TyYaFOHshbBHQQfx","object":"chat.completion.chunk","created":1714478024,"model":"gpt-3.5-turbo-0125","system_fingerprint":"fp_3b956da36b","choices":[{"index":0,"delta":{"content":"話"},"logprobs":null,"finish_reason":null}]}

data: {"id":"chatcmpl-9JgLISX5sX016TyYaFOHshbBHQQfx","object":"chat.completion.chunk","created":1714478024,"model":"gpt-3.5-turbo-0125","system_fingerprint":"fp_3b956da36b","choices":[{"index":0,"delta":{"content":"し"},"logprobs":null,"finish_reason":null}]}

data: {"id":"chatcmpl-9JgLISX5sX016TyYaFOHshbBHQQfx","object":"chat.completion.chunk","created":1714478024,"model":"gpt-3.5-turbo-0125","system_fingerprint":"fp_3b956da36b","choices":[{"index":0,"delta":{"content":"し"},"logprobs":null,"finish_reason":null}]}

data: {"id":"chatcmpl-9JgLISX5sX016TyYaFOHshbBHQQfx","object":"chat.completion.chunk","created":1714478024,"model":"gpt-3.5-turbo-0125","system_fingerprint":"fp_3b956da36b","choices":[{"index":0,"delta":{"content":"ま"},"logprobs":null,"finish_reason":null}]}

data: {"id":"chatcmpl-9JgLISX5sX016TyYaFOHshbBHQQfx","object":"chat.completion.chunk","created":1714478024,"model":"gpt-3.5-turbo-0125","system_fingerprint":"fp_3b956da36b","choices":[{"index":0,"delta":{"content":"し"},"logprobs":null,"finish_reason":null}]}

data: {"id":"chatcmpl-9JgLISX5sX016TyYaFOHshbBHQQfx","object":"chat.completion.chunk","created":1714478024,"model":"gpt-3.5-turbo-0125","system_fingerprint":"fp_3b956da36b","choices":[{"index":0,"delta":{"content":"ょ"},"logprobs":null,"finish_reason":null}]}

data: {"id":"chatcmpl-9JgLISX5sX016TyYaFOHshbBHQQfx","object":"chat.completion.chunk","created":1714478024,"model":"gpt-3.5-turbo-0125","system_fingerprint":"fp_3b956da36b","choices":[{"index":0,"delta":{"content":"う"},"logprobs":null,"finish_reason":null}]}

data: {"id":"chatcmpl-9JgLISX5sX016TyYaFOHshbBHQQfx","object":"chat.completion.chunk","created":1714478024,"model":"gpt-3.5-turbo-0125","system_fingerprint":"fp_3b956da36b","choices":[{"index":0,"delta":{"content":"か"},"logprobs":null,"finish_reason":null}]}

data: {"id":"chatcmpl-9JgLISX5sX016TyYaFOHshbBHQQfx","object":"chat.completion.chunk","created":1714478024,"model":"gpt-3.5-turbo-0125","system_fingerprint":"fp_3b956da36b","choices":[{"index":0,"delta":{"content":"？"},"logprobs":null,"finish_reason":null}]}

data: {"id":"chatcmpl-9JgLISX5sX016TyYaFOHshbBHQQfx","object":"chat.completion.chunk","created":1714478024,"model":"gpt-3.5-turbo-0125","system_fingerprint":"fp_3b956da36b","choices":[{"index":0,"delta":{},"logprobs":null,"finish_reason":"stop"}]}

data: [DONE]
"""

@pytest.fixture
def chunked_function():
    return """
data: {"id":"chatcmpl-9Jh2AEqsFhgxJODlR9mjFILdXhCgZ","object":"chat.completion.chunk","created":1714480682,"model":"gpt-3.5-turbo-0125","system_fingerprint":"fp_3b956da36b","choices":[{"index":0,"delta":{"role":"assistant","content":null,"function_call":{"name":"get_weather","arguments":""}},"logprobs":null,"finish_reason":null}]}

data: {"id":"chatcmpl-9Jh2AEqsFhgxJODlR9mjFILdXhCgZ","object":"chat.completion.chunk","created":1714480682,"model":"gpt-3.5-turbo-0125","system_fingerprint":"fp_3b956da36b","choices":[{"index":0,"delta":{"function_call":{"arguments":"{\\""}},"logprobs":null,"finish_reason":null}]}

data: {"id":"chatcmpl-9Jh2AEqsFhgxJODlR9mjFILdXhCgZ","object":"chat.completion.chunk","created":1714480682,"model":"gpt-3.5-turbo-0125","system_fingerprint":"fp_3b956da36b","choices":[{"index":0,"delta":{"function_call":{"arguments":"location"}},"logprobs":null,"finish_reason":null}]}

data: {"id":"chatcmpl-9Jh2AEqsFhgxJODlR9mjFILdXhCgZ","object":"chat.completion.chunk","created":1714480682,"model":"gpt-3.5-turbo-0125","system_fingerprint":"fp_3b956da36b","choices":[{"index":0,"delta":{"function_call":{"arguments":"\\":\\""}},"logprobs":null,"finish_reason":null}]}

data: {"id":"chatcmpl-9Jh2AEqsFhgxJODlR9mjFILdXhCgZ","object":"chat.completion.chunk","created":1714480682,"model":"gpt-3.5-turbo-0125","system_fingerprint":"fp_3b956da36b","choices":[{"index":0,"delta":{"function_call":{"arguments":"名"}},"logprobs":null,"finish_reason":null}]}

data: {"id":"chatcmpl-9Jh2AEqsFhgxJODlR9mjFILdXhCgZ","object":"chat.completion.chunk","created":1714480682,"model":"gpt-3.5-turbo-0125","system_fingerprint":"fp_3b956da36b","choices":[{"index":0,"delta":{"function_call":{"arguments":"古"}},"logprobs":null,"finish_reason":null}]}

data: {"id":"chatcmpl-9Jh2AEqsFhgxJODlR9mjFILdXhCgZ","object":"chat.completion.chunk","created":1714480682,"model":"gpt-3.5-turbo-0125","system_fingerprint":"fp_3b956da36b","choices":[{"index":0,"delta":{"function_call":{"arguments":"屋"}},"logprobs":null,"finish_reason":null}]}

data: {"id":"chatcmpl-9Jh2AEqsFhgxJODlR9mjFILdXhCgZ","object":"chat.completion.chunk","created":1714480682,"model":"gpt-3.5-turbo-0125","system_fingerprint":"fp_3b956da36b","choices":[{"index":0,"delta":{"function_call":{"arguments":"\\"}"}},"logprobs":null,"finish_reason":null}]}

data: {"id":"chatcmpl-9Jh2AEqsFhgxJODlR9mjFILdXhCgZ","object":"chat.completion.chunk","created":1714480682,"model":"gpt-3.5-turbo-0125","system_fingerprint":"fp_3b956da36b","choices":[{"index":0,"delta":{},"logprobs":null,"finish_reason":"function_call"}]}

data: [DONE]
"""

@pytest.fixture
def chunked_tools():
    return """
data: {"id":"chatcmpl-9Jij02QHWARdjqLLfZgv3B2RzkC1z","object":"chat.completion.chunk","created":1714487182,"model":"gpt-3.5-turbo-0125","system_fingerprint":"fp_3b956da36b","choices":[{"index":0,"delta":{"role":"assistant","content":null,"tool_calls":[{"index":0,"id":"call_uIfE0D0tMU4p2vKusFbiU1OR","type":"function","function":{"name":"get_weather","arguments":""}}]},"logprobs":null,"finish_reason":null}]}

data: {"id":"chatcmpl-9Jij02QHWARdjqLLfZgv3B2RzkC1z","object":"chat.completion.chunk","created":1714487182,"model":"gpt-3.5-turbo-0125","system_fingerprint":"fp_3b956da36b","choices":[{"index":0,"delta":{"tool_calls":[{"index":0,"function":{"arguments":"{\\""}}]},"logprobs":null,"finish_reason":null}]}

data: {"id":"chatcmpl-9Jij02QHWARdjqLLfZgv3B2RzkC1z","object":"chat.completion.chunk","created":1714487182,"model":"gpt-3.5-turbo-0125","system_fingerprint":"fp_3b956da36b","choices":[{"index":0,"delta":{"tool_calls":[{"index":0,"function":{"arguments":"location"}}]},"logprobs":null,"finish_reason":null}]}

data: {"id":"chatcmpl-9Jij02QHWARdjqLLfZgv3B2RzkC1z","object":"chat.completion.chunk","created":1714487182,"model":"gpt-3.5-turbo-0125","system_fingerprint":"fp_3b956da36b","choices":[{"index":0,"delta":{"tool_calls":[{"index":0,"function":{"arguments":"\\":\\""}}]},"logprobs":null,"finish_reason":null}]}

data: {"id":"chatcmpl-9Jij02QHWARdjqLLfZgv3B2RzkC1z","object":"chat.completion.chunk","created":1714487182,"model":"gpt-3.5-turbo-0125","system_fingerprint":"fp_3b956da36b","choices":[{"index":0,"delta":{"tool_calls":[{"index":0,"function":{"arguments":"名"}}]},"logprobs":null,"finish_reason":null}]}

data: {"id":"chatcmpl-9Jij02QHWARdjqLLfZgv3B2RzkC1z","object":"chat.completion.chunk","created":1714487182,"model":"gpt-3.5-turbo-0125","system_fingerprint":"fp_3b956da36b","choices":[{"index":0,"delta":{"tool_calls":[{"index":0,"function":{"arguments":"古"}}]},"logprobs":null,"finish_reason":null}]}

data: {"id":"chatcmpl-9Jij02QHWARdjqLLfZgv3B2RzkC1z","object":"chat.completion.chunk","created":1714487182,"model":"gpt-3.5-turbo-0125","system_fingerprint":"fp_3b956da36b","choices":[{"index":0,"delta":{"tool_calls":[{"index":0,"function":{"arguments":"屋"}}]},"logprobs":null,"finish_reason":null}]}

data: {"id":"chatcmpl-9Jij02QHWARdjqLLfZgv3B2RzkC1z","object":"chat.completion.chunk","created":1714487182,"model":"gpt-3.5-turbo-0125","system_fingerprint":"fp_3b956da36b","choices":[{"index":0,"delta":{"tool_calls":[{"index":0,"function":{"arguments":"\\"}"}}]},"logprobs":null,"finish_reason":null}]}

data: {"id":"chatcmpl-9Jij02QHWARdjqLLfZgv3B2RzkC1z","object":"chat.completion.chunk","created":1714487182,"model":"gpt-3.5-turbo-0125","system_fingerprint":"fp_3b956da36b","choices":[{"index":0,"delta":{},"logprobs":null,"finish_reason":"tool_calls"}]}

data: [DONE]
"""


def test_request_item_to_accesslog(messages, request_json, request_headers, functions, tools):
    request_json["functions"] = functions
    request_json["tools"] = tools

    session = SessionInfo()
    session.request_json = request_json
    session.request_headers = request_headers

    item = ChatGPTRequestItem.from_session(session)
    accesslog = item.to_accesslog(AccessLog)

    assert accesslog.request_id == session.request_id
    assert isinstance(accesslog.created_at, datetime)
    assert accesslog.direction == "request"
    assert accesslog.content == messages[-1]["content"]
    assert accesslog.function_call is None
    assert accesslog.tool_calls is None
    assert accesslog.raw_body == json.dumps(request_json, ensure_ascii=False)
    assert accesslog.raw_headers == json.dumps(request_headers, ensure_ascii=False)
    assert accesslog.model == request_json["model"]


def test_request_item_to_accesslog_array_content_textonly(messages, request_json, request_headers, functions, tools):
    request_json["functions"] = functions
    request_json["tools"] = tools
    text_content = request_json["messages"][0]["content"]
    request_json["messages"][0]["content"] = [{"type": "text", "text": text_content}]

    session = SessionInfo()
    session.request_json = request_json
    session.request_headers = request_headers

    item = ChatGPTRequestItem.from_session(session)
    accesslog = item.to_accesslog(AccessLog)

    assert accesslog.request_id == session.request_id
    assert isinstance(accesslog.created_at, datetime)
    assert accesslog.direction == "request"
    assert accesslog.content == text_content
    assert accesslog.function_call is None
    assert accesslog.tool_calls is None
    assert accesslog.raw_body == json.dumps(request_json, ensure_ascii=False)
    assert accesslog.raw_headers == json.dumps(request_headers, ensure_ascii=False)
    assert accesslog.model == request_json["model"]


def test_request_item_to_accesslog_array_content_notext(messages, request_json, request_headers, functions, tools):
    request_json["functions"] = functions
    request_json["tools"] = tools
    urls = [{"type": "image_url", "image_url": "url1"}, {"type": "image_url", "image_url": "url2"}]
    request_json["messages"][0]["content"] = urls

    session = SessionInfo()
    session.request_json = request_json
    session.request_headers = request_headers

    item = ChatGPTRequestItem.from_session(session)
    accesslog = item.to_accesslog(AccessLog)

    assert accesslog.request_id == session.request_id
    assert isinstance(accesslog.created_at, datetime)
    assert accesslog.direction == "request"
    assert accesslog.content == json.dumps(urls)
    assert accesslog.function_call is None
    assert accesslog.tool_calls is None
    assert accesslog.raw_body == json.dumps(request_json, ensure_ascii=False)
    assert accesslog.raw_headers == json.dumps(request_headers, ensure_ascii=False)
    assert accesslog.model == request_json["model"]


def test_request_item_to_accesslog_array_content_includetext(messages, request_json, request_headers, functions, tools):
    request_json["functions"] = functions
    request_json["tools"] = tools
    text_content = request_json["messages"][0]["content"]
    request_json["messages"][0]["content"] = [{"type": "image_url", "image_url": "url1"}, {"type": "image_url", "image_url": "url2"}, {"type": "text", "text": text_content}]

    session = SessionInfo()
    session.request_json = request_json
    session.request_headers = request_headers

    item = ChatGPTRequestItem.from_session(session)
    accesslog = item.to_accesslog(AccessLog)


    assert accesslog.request_id == session.request_id
    assert isinstance(accesslog.created_at, datetime)
    assert accesslog.direction == "request"
    assert accesslog.content == text_content
    assert accesslog.function_call is None
    assert accesslog.tool_calls is None
    assert accesslog.raw_body == json.dumps(request_json, ensure_ascii=False)
    assert accesslog.raw_headers == json.dumps(request_headers, ensure_ascii=False)
    assert accesslog.model == request_json["model"]


def test_response_item_to_accesslog(response_json, response_headers):
    session = SessionInfo()
    session.response_json = response_json
    session.response_headers = response_headers
    session.duration = 2.0
    session.duration_api = 1.0
    session.status_code = 200

    item = ChatGPTResponseItem.from_session(session)
    accesslog = item.to_accesslog(AccessLog)

    assert accesslog.request_id == session.request_id
    assert isinstance(accesslog.created_at, datetime)
    assert accesslog.direction == "response"
    assert accesslog.status_code == 200
    assert accesslog.content == response_json["choices"][0]["message"]["content"]
    assert accesslog.function_call is None
    assert accesslog.tool_calls is None
    assert accesslog.raw_body == json.dumps(response_json, ensure_ascii=False)
    assert accesslog.raw_headers == json.dumps(response_headers, ensure_ascii=True)
    assert accesslog.model == response_json["model"]
    assert accesslog.prompt_tokens == response_json["usage"]["prompt_tokens"]
    assert accesslog.completion_tokens == response_json["usage"]["completion_tokens"]
    assert accesslog.request_time == item.duration
    assert accesslog.request_time_api == item.duration_api


def test_response_item_to_accesslog_function(response_json, response_headers):
    response_json["choices"][0]["message"]["content"] = ""
    response_json["choices"][0]["message"]["function_call"] = {"name": "get_weather", "arguments": '{\n  "location": "東京"\n}'}

    session = SessionInfo()
    session.response_json = response_json
    session.response_headers = response_headers
    session.duration = 2.0
    session.duration_api = 1.0
    session.status_code = 200

    item = ChatGPTResponseItem.from_session(session)
    accesslog = item.to_accesslog(AccessLog)

    assert accesslog.request_id == session.request_id
    assert isinstance(accesslog.created_at, datetime)
    assert accesslog.direction == "response"
    assert accesslog.status_code == 200
    assert accesslog.content == ""
    assert json.loads(accesslog.function_call) == response_json["choices"][0]["message"]["function_call"]
    assert accesslog.tool_calls is None
    assert accesslog.raw_body == json.dumps(response_json, ensure_ascii=False)
    assert accesslog.raw_headers == json.dumps(response_headers, ensure_ascii=False)
    assert accesslog.model == response_json["model"]
    assert accesslog.prompt_tokens == response_json["usage"]["prompt_tokens"]
    assert accesslog.completion_tokens == response_json["usage"]["completion_tokens"]
    assert accesslog.request_time == item.duration
    assert accesslog.request_time_api == item.duration_api


def test_response_item_to_accesslog_tools(response_json, response_headers):
    response_json["choices"][0]["message"]["content"] = ""
    response_json["choices"][0]["message"]["tool_calls"] = [
        {"type": "function", "function": {"name": "get_weather", "arguments": '{\n  "location": "東京"\n}'}},
        {"type": "function", "function": {"name": "get_weather", "arguments": '{\n  "location": "名古屋"\n}'}},
    ]

    session = SessionInfo()
    session.response_json = response_json
    session.response_headers = response_headers
    session.duration = 2.0
    session.duration_api = 1.0
    session.status_code = 200

    item = ChatGPTResponseItem.from_session(session)
    accesslog = item.to_accesslog(AccessLog)

    assert accesslog.request_id == session.request_id
    assert isinstance(accesslog.created_at, datetime)
    assert accesslog.direction == "response"
    assert accesslog.status_code == 200
    assert accesslog.content == ""
    assert accesslog.function_call is None
    assert json.loads(accesslog.tool_calls) == response_json["choices"][0]["message"]["tool_calls"]
    assert accesslog.raw_body == json.dumps(response_json, ensure_ascii=False)
    assert accesslog.raw_headers == json.dumps(response_headers, ensure_ascii=False)
    assert accesslog.model == response_json["model"]
    assert accesslog.prompt_tokens == response_json["usage"]["prompt_tokens"]
    assert accesslog.completion_tokens == response_json["usage"]["completion_tokens"]
    assert accesslog.request_time == item.duration
    assert accesslog.request_time_api == item.duration_api


def test_stream_response_item_to_accesslog(chunked_content, response_headers, request_json):
    session = SessionInfo()
    session.request_json = request_json
    session.response_body = chunked_content
    session.response_headers = response_headers
    session.duration = 2.0
    session.duration_api = 1.0
    session.status_code = 200

    item = ChatGPTStreamResponseItem.from_session(session)
    accesslog = item.to_accesslog(AccessLog)

    assert accesslog.request_id == session.request_id
    assert isinstance(accesslog.created_at, datetime)
    assert accesslog.direction == "response"
    assert accesslog.status_code == 200
    assert accesslog.content == "はい、おしゃべりできます！何をお話ししましょうか？"
    assert accesslog.function_call is None
    assert accesslog.tool_calls is None
    assert accesslog.raw_body == chunked_content
    assert accesslog.raw_headers == json.dumps(response_headers, ensure_ascii=False)
    assert accesslog.model == "gpt-3.5-turbo-0125"
    assert accesslog.prompt_tokens > 0
    assert accesslog.completion_tokens > 0
    assert accesslog.request_time == item.duration
    assert accesslog.request_time_api == item.duration_api


def test_stream_response_item_to_accesslog_function(chunked_function, request_json, response_headers):
    session = SessionInfo()
    session.request_json = request_json
    session.response_body = chunked_function
    session.response_headers = response_headers
    session.duration = 2.0
    session.duration_api = 1.0
    session.status_code = 200

    item = ChatGPTStreamResponseItem.from_session(session)
    accesslog = item.to_accesslog(AccessLog)

    assert accesslog.request_id == session.request_id
    assert isinstance(accesslog.created_at, datetime)
    assert accesslog.direction == "response"
    assert accesslog.status_code == 200
    assert accesslog.content == ""
    assert accesslog.function_call == json.dumps({"name": "get_weather", "arguments": "{\"location\":\"名古屋\"}"}, ensure_ascii=False)
    assert accesslog.tool_calls is None
    assert accesslog.raw_body == chunked_function
    assert accesslog.raw_headers == json.dumps(response_headers, ensure_ascii=False)
    assert accesslog.model == "gpt-3.5-turbo-0125"
    assert accesslog.prompt_tokens > 0
    assert accesslog.completion_tokens > 0
    assert accesslog.request_time == item.duration
    assert accesslog.request_time_api == item.duration_api


def test_stream_response_item_to_accesslog_tools(chunked_tools, request_json, response_headers):
    session = SessionInfo()
    session.request_json = request_json
    session.response_body = chunked_tools
    session.response_headers = response_headers
    session.duration = 2.0
    session.duration_api = 1.0
    session.status_code = 200

    item = ChatGPTStreamResponseItem.from_session(session)
    accesslog = item.to_accesslog(AccessLog)

    assert accesslog.request_id == session.request_id
    assert isinstance(accesslog.created_at, datetime)
    assert accesslog.direction == "response"
    assert accesslog.status_code == 200
    assert accesslog.content == ""
    assert accesslog.function_call is None
    assert accesslog.tool_calls == json.dumps([{"type": "function", "function": {"name": "get_weather", "arguments": "{\"location\":\"名古屋\"}"}}], ensure_ascii=False)
    assert accesslog.raw_body == chunked_tools
    assert accesslog.raw_headers == json.dumps(response_headers, ensure_ascii=False)
    assert accesslog.model == "gpt-3.5-turbo-0125"
    assert accesslog.prompt_tokens > 0
    assert accesslog.completion_tokens > 0
    assert accesslog.request_time == item.duration
    assert accesslog.request_time_api == item.duration_api


@pytest.fixture
def worker():
    return AccessLogWorker(connection_str=DB_CONNECTION_STR)

@pytest.fixture
def chatgpt_proxy(worker):
    return ChatGPTProxy(access_logger_queue=worker.queue_client)

@pytest.fixture
def db(worker):
    return worker.get_session()

@pytest.fixture
def openai_client():
    return Client(base_url="http://127.0.0.1:8000/openai")

@pytest.mark.asyncio
async def test_request_filter_overwrite(chatgpt_proxy, request_json, request_headers):
    request_json["model"] = "gpt-4"

    chatgpt_proxy.add_filter(OverwriteFilter())

    session = SessionInfo()
    session.request_json = request_json
    session.request_headers = request_headers
    session.request_url = "http://127.0.0.1:8000/path/to/gpt"

    await chatgpt_proxy.filter_request(session)

    assert request_json["model"] == "gpt-3.5-turbo"


@pytest.mark.asyncio
async def test_request_filter_valuereturn(chatgpt_proxy, request_json, request_headers):
    chatgpt_proxy.add_filter(ValueReturnFilter())

    session = SessionInfo()
    session.request_json = request_json
    session.request_headers = request_headers
    session.request_url = "http://127.0.0.1:8000/path/to/gpt"

    # Non-stream
    json_response = await chatgpt_proxy.filter_request(session)
    assert isinstance(json_response, JSONResponse)
    assert json_response.headers.get("x-aiproxy-request-id") is not None
    ret = json.loads(json_response.body.decode())
    assert ret["choices"][0]["message"]["content"] == "user is required"

    session.request_json["user"] = "uezo"
    json_response = await chatgpt_proxy.filter_request(session)
    assert isinstance(json_response, JSONResponse)
    assert json_response.headers.get("x-aiproxy-request-id") is not None
    ret = json.loads(json_response.body.decode())
    assert ret["choices"][0]["message"]["content"] == "you can't use this service"

    session.request_json["user"] = "unagi"
    none_response = await chatgpt_proxy.filter_request(session)
    assert none_response is None

    # Stream
    session.stream = True
    session.request_json["user"] = "uezo"
    sse_response = await chatgpt_proxy.filter_request(session)
    assert isinstance(sse_response, EventSourceResponse)
    assert sse_response.headers.get("x-aiproxy-request-id") is not None

    session.request_json["user"] = "unagi"
    session.request_json["stream"] = True
    none_response = await chatgpt_proxy.filter_request(session)
    assert none_response is None


@pytest.mark.asyncio
async def test_response_filter_valuereturn(chatgpt_proxy, response_json):
    request_id = str(uuid4())

    chatgpt_proxy.add_filter(OverwriteResponseFilter())

    resp = ChatCompletion.model_validate(response_json)
    ret = await chatgpt_proxy.filter_response(request_id, resp.model_dump())

    assert ret["choices"][0]["message"]["content"] == "Overwrite in filter"


def test_post_content(messages, request_headers, openai_client, db):
    api_resp = openai_client.chat.completions.with_raw_response.create(
        model="gpt-3.5-turbo", messages=messages
    )

    comp_resp = api_resp.parse()
    headers = api_resp.headers
    request_id = headers.get("x-aiproxy-request-id")

    assert request_id is not None
    assert "天気" in comp_resp.choices[0].message.content

    # Wait for processing queued items
    sleep(2.0)

    db_request = db.query(AccessLog).where(AccessLog.request_id == request_id, AccessLog.direction == "request").first()
    db_resonse = db.query(AccessLog).where(AccessLog.request_id == request_id, AccessLog.direction == "response").first()

    assert db_request.content == messages[-1]["content"]
    assert db_resonse.content == comp_resp.choices[0].message.content
    assert json.loads(db_resonse.raw_body) == json.loads(api_resp.content)
    # NOTE: It doesn't completely same because FastAPI/Uvicorn adds some values. (e.g. date, server)
    # 'date': 'Mon, 11 Dec 2023 14:06:05 GMT, Mon, 11 Dec 2023 14:06:08 GMT'
    # 'server': 'uvicorn, cloudflare'
    # assert json.loads(db_resonse.raw_headers) == dict(headers.items())
    # Check some headear items
    db_headers = json.loads(db_resonse.raw_headers)
    assert "openai-model" in db_headers
    assert "openai-processing-ms" in db_headers
    assert db_resonse.status_code == api_resp.status_code

# NOTE: Restart AIProxy instance with custom log worker before this case
@pytest.mark.skip("skip")
def test_post_content_custom_log(messages, request_headers, openai_client, db):
    extra_headers = {
        "x-user-id": "user_1234567890",
        "x-device-id": "device_1234567890",
        "x-ip-address": "111.222.333.444"
    }

    api_resp = openai_client.chat.completions.with_raw_response.create(
        model="gpt-3.5-turbo", messages=messages, extra_headers=extra_headers
    )

    comp_resp = api_resp.parse()
    headers = api_resp.headers
    request_id = headers.get("x-aiproxy-request-id")

    assert request_id is not None
    assert "天気" in comp_resp.choices[0].message.content

    # Wait for processing queued items
    sleep(2.0)

    db_request = db.query(MyAccessLog).where(MyAccessLog.request_id == request_id, MyAccessLog.direction == "request").first()
    db_resonse = db.query(MyAccessLog).where(MyAccessLog.request_id == request_id, MyAccessLog.direction == "response").first()

    assert db_request.content == messages[-1]["content"]
    assert db_resonse.content == comp_resp.choices[0].message.content
    assert json.loads(db_resonse.raw_body) == json.loads(api_resp.content)
    # NOTE: It doesn't completely same because FastAPI/Uvicorn adds some values. (e.g. date, server)
    # 'date': 'Mon, 11 Dec 2023 14:06:05 GMT, Mon, 11 Dec 2023 14:06:08 GMT'
    # 'server': 'uvicorn, cloudflare'
    # assert json.loads(db_resonse.raw_headers) == dict(headers.items())
    # Check some headear items
    db_headers = json.loads(db_resonse.raw_headers)
    assert "openai-model" in db_headers
    assert "openai-processing-ms" in db_headers
    assert db_resonse.status_code == api_resp.status_code

    assert db_request.user_id == extra_headers["x-user-id"]
    assert db_request.device_id == extra_headers["x-device-id"]
    assert db_request.ip_address == extra_headers["x-ip-address"]


def test_post_content_function(messages, request_headers, functions, openai_client, db):
    api_resp = openai_client.chat.completions.with_raw_response.create(
        model="gpt-3.5-turbo", messages=messages, functions=functions
    )

    comp_resp = api_resp.parse()
    headers = api_resp.headers

    request_id = headers.get("x-aiproxy-request-id")
    assert request_id is not None

    function_call = comp_resp.choices[0].message.function_call
    assert function_call is not None

    # Wait for processing queued items
    sleep(2.0)

    db_request = db.query(AccessLog).where(AccessLog.request_id == request_id, AccessLog.direction == "request").first()
    db_resonse = db.query(AccessLog).where(AccessLog.request_id == request_id, AccessLog.direction == "response").first()

    assert db_request.content == messages[-1]["content"]
    assert json.loads(db_resonse.function_call) == function_call.model_dump()
    assert json.loads(db_resonse.raw_body) == json.loads(api_resp.content)
    # NOTE: It doesn't completely same because FastAPI/Uvicorn adds some values. (e.g. date, server)
    # 'date': 'Mon, 11 Dec 2023 14:06:05 GMT, Mon, 11 Dec 2023 14:06:08 GMT'
    # 'server': 'uvicorn, cloudflare'
    # assert json.loads(db_resonse.raw_headers) == dict(headers.items())
    # Check some headear items
    db_headers = json.loads(db_resonse.raw_headers)
    assert "openai-model" in db_headers
    assert "openai-processing-ms" in db_headers
    assert db_resonse.status_code == api_resp.status_code


def test_post_content_tools(messages, request_headers, tools, openai_client, db):
    api_resp = openai_client.chat.completions.with_raw_response.create(
        model="gpt-3.5-turbo", messages=messages, tools=tools
    )

    comp_resp = api_resp.parse()
    headers = api_resp.headers

    request_id = headers.get("x-aiproxy-request-id")
    assert request_id is not None

    tool_calls = comp_resp.choices[0].message.tool_calls
    assert tool_calls is not None

    # Wait for processing queued items
    sleep(2.0)

    db_request = db.query(AccessLog).where(AccessLog.request_id == request_id, AccessLog.direction == "request").first()
    db_resonse = db.query(AccessLog).where(AccessLog.request_id == request_id, AccessLog.direction == "response").first()

    assert db_request.content == messages[-1]["content"]
    assert json.loads(db_resonse.tool_calls) == [t.model_dump() for t in tool_calls]
    assert json.loads(db_resonse.raw_body) == json.loads(api_resp.content)   
    # NOTE: It doesn't completely same because FastAPI/Uvicorn adds some values. (e.g. date, server)
    # 'date': 'Mon, 11 Dec 2023 14:06:05 GMT, Mon, 11 Dec 2023 14:06:08 GMT'
    # 'server': 'uvicorn, cloudflare'
    # assert json.loads(db_resonse.raw_headers) == dict(headers.items())
    # Check some headear items
    db_headers = json.loads(db_resonse.raw_headers)
    assert "openai-model" in db_headers
    assert "openai-processing-ms" in db_headers
    assert db_resonse.status_code == api_resp.status_code


def test_post_content_apierror(messages, request_headers, openai_client, db):
    with pytest.raises(APIStatusError) as apisterr:
        api_resp = openai_client.chat.completions.with_raw_response.create(
            model="gpt-100.0-twin-turbo", messages=messages
        )
    
    api_resp = apisterr.value.response

    assert api_resp.status_code == 404

    headers = api_resp.headers
    request_id = headers.get("x-aiproxy-request-id")

    assert request_id is not None

    # Wait for processing queued items
    sleep(2.0)

    db_request = db.query(AccessLog).where(AccessLog.request_id == request_id, AccessLog.direction == "request").first()
    db_resonse = db.query(AccessLog).where(AccessLog.request_id == request_id, AccessLog.direction == "error").first()

    assert db_request.content == messages[-1]["content"]
    assert db_resonse.status_code == api_resp.status_code


def test_post_content_stream(messages, request_headers, openai_client, db):
    api_resp = openai_client.chat.completions.with_raw_response.create(
        model="gpt-3.5-turbo", messages=messages, stream=True
    )

    headers = api_resp.headers
    request_id = headers.get("x-aiproxy-request-id")
    assert request_id is not None

    chunks = ""
    content = ""
    for b in api_resp.http_response.iter_raw():
        chunk_str = b.decode("utf-8")
        chunk_str = chunk_str.replace("\r", "").replace("event: \n", "")
        chunks += chunk_str
        for data_str in chunk_str.split("\n\n"):
            if "data:" in data_str:
                try:
                    chunk = json.loads(chunk_str.split("data:")[1])
                    content += chunk["choices"][0]["delta"]["content"]
                except:
                    pass

    # Wait for processing queued items
    sleep(5.0)

    db_request = db.query(AccessLog).where(AccessLog.request_id == request_id, AccessLog.direction == "request").first()
    db_resonse = db.query(AccessLog).where(AccessLog.request_id == request_id, AccessLog.direction == "response").first()

    assert db_request.content == messages[-1]["content"]
    assert db_resonse.content == content
    assert db_resonse.raw_body == chunks
    # NOTE: It doesn't completely same because FastAPI/Uvicorn adds some values. (e.g. date, server)
    # 'date': 'Mon, 11 Dec 2023 14:06:05 GMT, Mon, 11 Dec 2023 14:06:08 GMT'
    # 'server': 'uvicorn, cloudflare'
    # assert json.loads(db_resonse.raw_headers) == dict(headers.items())
    # Check some headear items
    db_headers = json.loads(db_resonse.raw_headers)
    assert "openai-model" in db_headers
    assert "openai-processing-ms" in db_headers
    assert db_resonse.status_code == api_resp.status_code


def test_post_content_stream_function(messages, request_headers, functions, openai_client, db):
    api_resp = openai_client.chat.completions.with_raw_response.create(
        model="gpt-3.5-turbo", messages=messages, stream=True, functions=functions
    )

    headers = api_resp.headers

    request_id = headers.get("x-aiproxy-request-id")
    assert request_id is not None

    chunks = ""
    function_call = {"name": "", "arguments": ""}
    for b in api_resp.http_response.iter_raw():
        chunk_str = b.decode("utf-8")
        chunk_str = chunk_str.replace("\r", "").replace("event: \n", "")
        chunks += chunk_str
        for data_str in chunk_str.split("\n\n"):
            if "data:" in data_str:
                try:
                    chunk = json.loads(chunk_str.split("data:")[1])
                    if "choices" in chunk and "delta" in chunk["choices"][0] and "function_call" in chunk["choices"][0]["delta"]:
                        if "name" in chunk["choices"][0]["delta"]["function_call"] and not function_call["name"]:
                            function_call["name"] = chunk["choices"][0]["delta"]["function_call"]["name"]
                        else:
                            function_call["arguments"] += chunk["choices"][0]["delta"]["function_call"]["arguments"]
                except:
                    pass

    # Wait for processing queued items
    sleep(10.0)

    db_request = db.query(AccessLog).where(AccessLog.request_id == request_id, AccessLog.direction == "request").first()
    db_resonse = db.query(AccessLog).where(AccessLog.request_id == request_id, AccessLog.direction == "response").first()

    assert db_request.content == messages[-1]["content"]
    assert json.loads(db_resonse.function_call) == function_call
    assert db_resonse.raw_body == chunks
    # NOTE: It doesn't completely same because FastAPI/Uvicorn adds some values. (e.g. date, server)
    # 'date': 'Mon, 11 Dec 2023 14:06:05 GMT, Mon, 11 Dec 2023 14:06:08 GMT'
    # 'server': 'uvicorn, cloudflare'
    # assert json.loads(db_resonse.raw_headers) == dict(headers.items())
    # Check some headear items
    db_headers = json.loads(db_resonse.raw_headers)
    assert "openai-model" in db_headers
    assert "openai-processing-ms" in db_headers
    assert db_resonse.status_code == api_resp.status_code


def test_post_content_stream_tools(messages, request_headers, tools, openai_client, db):
    api_resp = openai_client.chat.completions.with_raw_response.create(
        model="gpt-3.5-turbo", messages=messages, stream=True, tools=tools
    )

    headers = api_resp.headers

    request_id = headers.get("x-aiproxy-request-id")
    assert request_id is not None

    chunks = ""
    tool_calls = []
    for b in api_resp.http_response.iter_raw():
        chunk_str = b.decode("utf-8")
        chunk_str = chunk_str.replace("\r", "").replace("event: \n", "")
        chunks += chunk_str
        for data_str in chunk_str.split("\n\n"):
            if "data:" in data_str:
                try:
                    chunk = json.loads(chunk_str.split("data:")[1])
                    if "choices" in chunk and "delta" in chunk["choices"][0] and "tool_calls" in chunk["choices"][0]["delta"]:
                        if "type" in chunk["choices"][0]["delta"]["tool_calls"][0] and chunk["choices"][0]["delta"]["tool_calls"][0]["type"] is not None:
                            tool_calls.append({"type": "function", "function": {"name": chunk["choices"][0]["delta"]["tool_calls"][0]["function"]["name"], "arguments": ""}})
                        else:
                            tool_calls[-1]["function"]["arguments"] += chunk["choices"][0]["delta"]["tool_calls"][0]["function"]["arguments"]
                except:
                    pass

    # Wait for processing queued items
    sleep(10.0)

    db_request = db.query(AccessLog).where(AccessLog.request_id == request_id, AccessLog.direction == "request").first()
    db_resonse = db.query(AccessLog).where(AccessLog.request_id == request_id, AccessLog.direction == "response").first()

    assert db_request.content == messages[-1]["content"]
    assert json.loads(db_resonse.tool_calls) == tool_calls
    assert db_resonse.raw_body == chunks
    # NOTE: It doesn't completely same because FastAPI/Uvicorn adds some values. (e.g. date, server)
    # 'date': 'Mon, 11 Dec 2023 14:06:05 GMT, Mon, 11 Dec 2023 14:06:08 GMT'
    # 'server': 'uvicorn, cloudflare'
    # assert json.loads(db_resonse.raw_headers) == dict(headers.items())
    # Check some headear items
    db_headers = json.loads(db_resonse.raw_headers)
    assert "openai-model" in db_headers
    assert "openai-processing-ms" in db_headers
    assert db_resonse.status_code == api_resp.status_code


def test_post_content_stream_apierror(messages, request_headers, openai_client, db):
    with pytest.raises(APIStatusError) as apisterr:
        api_resp = openai_client.chat.completions.with_raw_response.create(
            model="gpt-100.0-twin-turbo", messages=messages, stream=True
        )
    
    api_resp = apisterr.value.response

    assert api_resp.status_code == 404

    headers = api_resp.headers
    request_id = headers.get("x-aiproxy-request-id")

    assert request_id is not None

    # Wait for processing queued items
    sleep(2.0)

    db_request = db.query(AccessLog).where(AccessLog.request_id == request_id, AccessLog.direction == "request").first()
    db_resonse = db.query(AccessLog).where(AccessLog.request_id == request_id, AccessLog.direction == "error").first()

    assert db_request.content == messages[-1]["content"]
    assert db_resonse.status_code == api_resp.status_code
