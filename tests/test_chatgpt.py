import pytest
from datetime import datetime
import json
from typing import Union
from uuid import uuid4
from openai import Client, APIStatusError
from openai.types.chat import ChatCompletion
from aiproxy import (
    AccessLog,
    RequestFilterBase,
    ResponseFilterBase,
    ChatGPTProxy
)
from aiproxy.accesslog import AccessLogWorker
from aiproxy.chatgpt import ChatGPTRequestItem, ChatGPTResponseItem, ChatGPTStreamResponseItem

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
def chunks_json():
    return [
        {
            "id": "chatcmpl-8RzBaWVmpPZZJFdxZgynVwZMATday",
            "choices": [
                {
                    "delta": {
                        "content": "",
                        "function_call": None,
                        "role": "assistant",
                        "tool_calls": None
                    },
                    "finish_reason": None,
                    "index": 0
                }
            ],
            "created": 1701680746,
            "model": "gpt-3.5-turbo-0613",
            "object": "chat.completion.chunk",
            "system_fingerprint": None
        },
        {
            "id": "chatcmpl-8RzBaWVmpPZZJFdxZgynVwZMATday",
            "choices": [
                {
                    "delta": {
                        "content": "\u7533",
                        "function_call": None,
                        "role": None,
                        "tool_calls": None
                    },
                    "finish_reason": None,
                    "index": 0
                }
            ],
            "created": 1701680746,
            "model": "gpt-3.5-turbo-0613",
            "object": "chat.completion.chunk",
            "system_fingerprint": None
        },
        {
            "id": "chatcmpl-8RzBaWVmpPZZJFdxZgynVwZMATday",
            "choices": [
                {
                    "delta": {
                        "content": "\u3057",
                        "function_call": None,
                        "role": None,
                        "tool_calls": None
                    },
                    "finish_reason": None,
                    "index": 0
                }
            ],
            "created": 1701680746,
            "model": "gpt-3.5-turbo-0613",
            "object": "chat.completion.chunk",
            "system_fingerprint": None
        },
        {
            "id": "chatcmpl-8RzBaWVmpPZZJFdxZgynVwZMATday",
            "choices": [
                {
                    "delta": {
                        "content": "\u8a33",
                        "function_call": None,
                        "role": None,
                        "tool_calls": None
                    },
                    "finish_reason": None,
                    "index": 0
                }
            ],
            "created": 1701680746,
            "model": "gpt-3.5-turbo-0613",
            "object": "chat.completion.chunk",
            "system_fingerprint": None
        },
        {
            "id": "chatcmpl-8RzBaWVmpPZZJFdxZgynVwZMATday",
            "choices": [
                {
                    "delta": {
                        "content": "\u3042\u308a",
                        "function_call": None,
                        "role": None,
                        "tool_calls": None
                    },
                    "finish_reason": None,
                    "index": 0
                }
            ],
            "created": 1701680746,
            "model": "gpt-3.5-turbo-0613",
            "object": "chat.completion.chunk",
            "system_fingerprint": None
        },
        {
            "id": "chatcmpl-8RzBaWVmpPZZJFdxZgynVwZMATday",
            "choices": [
                {
                    "delta": {
                        "content": "\u307e",
                        "function_call": None,
                        "role": None,
                        "tool_calls": None
                    },
                    "finish_reason": None,
                    "index": 0
                }
            ],
            "created": 1701680746,
            "model": "gpt-3.5-turbo-0613",
            "object": "chat.completion.chunk",
            "system_fingerprint": None
        },
        {
            "id": "chatcmpl-8RzBaWVmpPZZJFdxZgynVwZMATday",
            "choices": [
                {
                    "delta": {
                        "content": "\u305b",
                        "function_call": None,
                        "role": None,
                        "tool_calls": None
                    },
                    "finish_reason": None,
                    "index": 0
                }
            ],
            "created": 1701680746,
            "model": "gpt-3.5-turbo-0613",
            "object": "chat.completion.chunk",
            "system_fingerprint": None
        },
        {
            "id": "chatcmpl-8RzBaWVmpPZZJFdxZgynVwZMATday",
            "choices": [
                {
                    "delta": {
                        "content": "\u3093",
                        "function_call": None,
                        "role": None,
                        "tool_calls": None
                    },
                    "finish_reason": None,
                    "index": 0
                }
            ],
            "created": 1701680746,
            "model": "gpt-3.5-turbo-0613",
            "object": "chat.completion.chunk",
            "system_fingerprint": None
        },
        {
            "id": "chatcmpl-8RzBaWVmpPZZJFdxZgynVwZMATday",
            "choices": [
                {
                    "delta": {
                        "content": "\u304c",
                        "function_call": None,
                        "role": None,
                        "tool_calls": None
                    },
                    "finish_reason": None,
                    "index": 0
                }
            ],
            "created": 1701680746,
            "model": "gpt-3.5-turbo-0613",
            "object": "chat.completion.chunk",
            "system_fingerprint": None
        },
        {
            "id": "chatcmpl-8RzBaWVmpPZZJFdxZgynVwZMATday",
            "choices": [
                {
                    "delta": {
                        "content": "\u3001",
                        "function_call": None,
                        "role": None,
                        "tool_calls": None
                    },
                    "finish_reason": None,
                    "index": 0
                }
            ],
            "created": 1701680746,
            "model": "gpt-3.5-turbo-0613",
            "object": "chat.completion.chunk",
            "system_fingerprint": None
        },
        {
            "id": "chatcmpl-8RzBaWVmpPZZJFdxZgynVwZMATday",
            "choices": [
                {
                    "delta": {
                        "content": "\u6771",
                        "function_call": None,
                        "role": None,
                        "tool_calls": None
                    },
                    "finish_reason": None,
                    "index": 0
                }
            ],
            "created": 1701680746,
            "model": "gpt-3.5-turbo-0613",
            "object": "chat.completion.chunk",
            "system_fingerprint": None
        },
        {
            "id": "chatcmpl-8RzBaWVmpPZZJFdxZgynVwZMATday",
            "choices": [
                {
                    "delta": {
                        "content": "\u4eac",
                        "function_call": None,
                        "role": None,
                        "tool_calls": None
                    },
                    "finish_reason": None,
                    "index": 0
                }
            ],
            "created": 1701680746,
            "model": "gpt-3.5-turbo-0613",
            "object": "chat.completion.chunk",
            "system_fingerprint": None
        },
        {
            "id": "chatcmpl-8RzBaWVmpPZZJFdxZgynVwZMATday",
            "choices": [
                {
                    "delta": {
                        "content": "\u3068",
                        "function_call": None,
                        "role": None,
                        "tool_calls": None
                    },
                    "finish_reason": None,
                    "index": 0
                }
            ],
            "created": 1701680746,
            "model": "gpt-3.5-turbo-0613",
            "object": "chat.completion.chunk",
            "system_fingerprint": None
        },
        {
            "id": "chatcmpl-8RzBaWVmpPZZJFdxZgynVwZMATday",
            "choices": [
                {
                    "delta": {
                        "content": "\u540d",
                        "function_call": None,
                        "role": None,
                        "tool_calls": None
                    },
                    "finish_reason": None,
                    "index": 0
                }
            ],
            "created": 1701680746,
            "model": "gpt-3.5-turbo-0613",
            "object": "chat.completion.chunk",
            "system_fingerprint": None
        },
        {
            "id": "chatcmpl-8RzBaWVmpPZZJFdxZgynVwZMATday",
            "choices": [
                {
                    "delta": {
                        "content": "\u53e4",
                        "function_call": None,
                        "role": None,
                        "tool_calls": None
                    },
                    "finish_reason": None,
                    "index": 0
                }
            ],
            "created": 1701680746,
            "model": "gpt-3.5-turbo-0613",
            "object": "chat.completion.chunk",
            "system_fingerprint": None
        },
        {
            "id": "chatcmpl-8RzBaWVmpPZZJFdxZgynVwZMATday",
            "choices": [
                {
                    "delta": {
                        "content": "\u5c4b",
                        "function_call": None,
                        "role": None,
                        "tool_calls": None
                    },
                    "finish_reason": None,
                    "index": 0
                }
            ],
            "created": 1701680746,
            "model": "gpt-3.5-turbo-0613",
            "object": "chat.completion.chunk",
            "system_fingerprint": None
        },
        {
            "id": "chatcmpl-8RzBaWVmpPZZJFdxZgynVwZMATday",
            "choices": [
                {
                    "delta": {
                        "content": "\u306e",
                        "function_call": None,
                        "role": None,
                        "tool_calls": None
                    },
                    "finish_reason": None,
                    "index": 0
                }
            ],
            "created": 1701680746,
            "model": "gpt-3.5-turbo-0613",
            "object": "chat.completion.chunk",
            "system_fingerprint": None
        },
        {
            "id": "chatcmpl-8RzBaWVmpPZZJFdxZgynVwZMATday",
            "choices": [
                {
                    "delta": {
                        "content": "\u5929",
                        "function_call": None,
                        "role": None,
                        "tool_calls": None
                    },
                    "finish_reason": None,
                    "index": 0
                }
            ],
            "created": 1701680746,
            "model": "gpt-3.5-turbo-0613",
            "object": "chat.completion.chunk",
            "system_fingerprint": None
        },
        {
            "id": "chatcmpl-8RzBaWVmpPZZJFdxZgynVwZMATday",
            "choices": [
                {
                    "delta": {
                        "content": "\u6c17",
                        "function_call": None,
                        "role": None,
                        "tool_calls": None
                    },
                    "finish_reason": None,
                    "index": 0
                }
            ],
            "created": 1701680746,
            "model": "gpt-3.5-turbo-0613",
            "object": "chat.completion.chunk",
            "system_fingerprint": None
        },
        {
            "id": "chatcmpl-8RzBaWVmpPZZJFdxZgynVwZMATday",
            "choices": [
                {
                    "delta": {
                        "content": "\u60c5",
                        "function_call": None,
                        "role": None,
                        "tool_calls": None
                    },
                    "finish_reason": None,
                    "index": 0
                }
            ],
            "created": 1701680746,
            "model": "gpt-3.5-turbo-0613",
            "object": "chat.completion.chunk",
            "system_fingerprint": None
        },
        {
            "id": "chatcmpl-8RzBaWVmpPZZJFdxZgynVwZMATday",
            "choices": [
                {
                    "delta": {
                        "content": "\u5831",
                        "function_call": None,
                        "role": None,
                        "tool_calls": None
                    },
                    "finish_reason": None,
                    "index": 0
                }
            ],
            "created": 1701680746,
            "model": "gpt-3.5-turbo-0613",
            "object": "chat.completion.chunk",
            "system_fingerprint": None
        },
        {
            "id": "chatcmpl-8RzBaWVmpPZZJFdxZgynVwZMATday",
            "choices": [
                {
                    "delta": {
                        "content": "\u3092",
                        "function_call": None,
                        "role": None,
                        "tool_calls": None
                    },
                    "finish_reason": None,
                    "index": 0
                }
            ],
            "created": 1701680746,
            "model": "gpt-3.5-turbo-0613",
            "object": "chat.completion.chunk",
            "system_fingerprint": None
        },
        {
            "id": "chatcmpl-8RzBaWVmpPZZJFdxZgynVwZMATday",
            "choices": [
                {
                    "delta": {
                        "content": "\u63d0",
                        "function_call": None,
                        "role": None,
                        "tool_calls": None
                    },
                    "finish_reason": None,
                    "index": 0
                }
            ],
            "created": 1701680746,
            "model": "gpt-3.5-turbo-0613",
            "object": "chat.completion.chunk",
            "system_fingerprint": None
        },
        {
            "id": "chatcmpl-8RzBaWVmpPZZJFdxZgynVwZMATday",
            "choices": [
                {
                    "delta": {
                        "content": "\u4f9b",
                        "function_call": None,
                        "role": None,
                        "tool_calls": None
                    },
                    "finish_reason": None,
                    "index": 0
                }
            ],
            "created": 1701680746,
            "model": "gpt-3.5-turbo-0613",
            "object": "chat.completion.chunk",
            "system_fingerprint": None
        },
        {
            "id": "chatcmpl-8RzBaWVmpPZZJFdxZgynVwZMATday",
            "choices": [
                {
                    "delta": {
                        "content": "\u3059\u308b",
                        "function_call": None,
                        "role": None,
                        "tool_calls": None
                    },
                    "finish_reason": None,
                    "index": 0
                }
            ],
            "created": 1701680746,
            "model": "gpt-3.5-turbo-0613",
            "object": "chat.completion.chunk",
            "system_fingerprint": None
        },
        {
            "id": "chatcmpl-8RzBaWVmpPZZJFdxZgynVwZMATday",
            "choices": [
                {
                    "delta": {
                        "content": "\u3053",
                        "function_call": None,
                        "role": None,
                        "tool_calls": None
                    },
                    "finish_reason": None,
                    "index": 0
                }
            ],
            "created": 1701680746,
            "model": "gpt-3.5-turbo-0613",
            "object": "chat.completion.chunk",
            "system_fingerprint": None
        },
        {
            "id": "chatcmpl-8RzBaWVmpPZZJFdxZgynVwZMATday",
            "choices": [
                {
                    "delta": {
                        "content": "\u3068",
                        "function_call": None,
                        "role": None,
                        "tool_calls": None
                    },
                    "finish_reason": None,
                    "index": 0
                }
            ],
            "created": 1701680746,
            "model": "gpt-3.5-turbo-0613",
            "object": "chat.completion.chunk",
            "system_fingerprint": None
        },
        {
            "id": "chatcmpl-8RzBaWVmpPZZJFdxZgynVwZMATday",
            "choices": [
                {
                    "delta": {
                        "content": "\u306f",
                        "function_call": None,
                        "role": None,
                        "tool_calls": None
                    },
                    "finish_reason": None,
                    "index": 0
                }
            ],
            "created": 1701680746,
            "model": "gpt-3.5-turbo-0613",
            "object": "chat.completion.chunk",
            "system_fingerprint": None
        },
        {
            "id": "chatcmpl-8RzBaWVmpPZZJFdxZgynVwZMATday",
            "choices": [
                {
                    "delta": {
                        "content": "\u3067",
                        "function_call": None,
                        "role": None,
                        "tool_calls": None
                    },
                    "finish_reason": None,
                    "index": 0
                }
            ],
            "created": 1701680746,
            "model": "gpt-3.5-turbo-0613",
            "object": "chat.completion.chunk",
            "system_fingerprint": None
        },
        {
            "id": "chatcmpl-8RzBaWVmpPZZJFdxZgynVwZMATday",
            "choices": [
                {
                    "delta": {
                        "content": "\u304d",
                        "function_call": None,
                        "role": None,
                        "tool_calls": None
                    },
                    "finish_reason": None,
                    "index": 0
                }
            ],
            "created": 1701680746,
            "model": "gpt-3.5-turbo-0613",
            "object": "chat.completion.chunk",
            "system_fingerprint": None
        },
        {
            "id": "chatcmpl-8RzBaWVmpPZZJFdxZgynVwZMATday",
            "choices": [
                {
                    "delta": {
                        "content": "\u307e",
                        "function_call": None,
                        "role": None,
                        "tool_calls": None
                    },
                    "finish_reason": None,
                    "index": 0
                }
            ],
            "created": 1701680746,
            "model": "gpt-3.5-turbo-0613",
            "object": "chat.completion.chunk",
            "system_fingerprint": None
        },
        {
            "id": "chatcmpl-8RzBaWVmpPZZJFdxZgynVwZMATday",
            "choices": [
                {
                    "delta": {
                        "content": "\u305b",
                        "function_call": None,
                        "role": None,
                        "tool_calls": None
                    },
                    "finish_reason": None,
                    "index": 0
                }
            ],
            "created": 1701680746,
            "model": "gpt-3.5-turbo-0613",
            "object": "chat.completion.chunk",
            "system_fingerprint": None
        },
        {
            "id": "chatcmpl-8RzBaWVmpPZZJFdxZgynVwZMATday",
            "choices": [
                {
                    "delta": {
                        "content": "\u3093",
                        "function_call": None,
                        "role": None,
                        "tool_calls": None
                    },
                    "finish_reason": None,
                    "index": 0
                }
            ],
            "created": 1701680746,
            "model": "gpt-3.5-turbo-0613",
            "object": "chat.completion.chunk",
            "system_fingerprint": None
        },
        {
            "id": "chatcmpl-8RzBaWVmpPZZJFdxZgynVwZMATday",
            "choices": [
                {
                    "delta": {
                        "content": "\u3002",
                        "function_call": None,
                        "role": None,
                        "tool_calls": None
                    },
                    "finish_reason": None,
                    "index": 0
                }
            ],
            "created": 1701680746,
            "model": "gpt-3.5-turbo-0613",
            "object": "chat.completion.chunk",
            "system_fingerprint": None
        },
        {
            "id": "chatcmpl-8RzBaWVmpPZZJFdxZgynVwZMATday",
            "choices": [
                {
                    "delta": {
                        "content": "\u5929",
                        "function_call": None,
                        "role": None,
                        "tool_calls": None
                    },
                    "finish_reason": None,
                    "index": 0
                }
            ],
            "created": 1701680746,
            "model": "gpt-3.5-turbo-0613",
            "object": "chat.completion.chunk",
            "system_fingerprint": None
        },
        {
            "id": "chatcmpl-8RzBaWVmpPZZJFdxZgynVwZMATday",
            "choices": [
                {
                    "delta": {
                        "content": "\u6c17",
                        "function_call": None,
                        "role": None,
                        "tool_calls": None
                    },
                    "finish_reason": None,
                    "index": 0
                }
            ],
            "created": 1701680746,
            "model": "gpt-3.5-turbo-0613",
            "object": "chat.completion.chunk",
            "system_fingerprint": None
        },
        {
            "id": "chatcmpl-8RzBaWVmpPZZJFdxZgynVwZMATday",
            "choices": [
                {
                    "delta": {
                        "content": "\u306b",
                        "function_call": None,
                        "role": None,
                        "tool_calls": None
                    },
                    "finish_reason": None,
                    "index": 0
                }
            ],
            "created": 1701680746,
            "model": "gpt-3.5-turbo-0613",
            "object": "chat.completion.chunk",
            "system_fingerprint": None
        },
        {
            "id": "chatcmpl-8RzBaWVmpPZZJFdxZgynVwZMATday",
            "choices": [
                {
                    "delta": {
                        "content": "\u95a2",
                        "function_call": None,
                        "role": None,
                        "tool_calls": None
                    },
                    "finish_reason": None,
                    "index": 0
                }
            ],
            "created": 1701680746,
            "model": "gpt-3.5-turbo-0613",
            "object": "chat.completion.chunk",
            "system_fingerprint": None
        },
        {
            "id": "chatcmpl-8RzBaWVmpPZZJFdxZgynVwZMATday",
            "choices": [
                {
                    "delta": {
                        "content": "\u3059\u308b",
                        "function_call": None,
                        "role": None,
                        "tool_calls": None
                    },
                    "finish_reason": None,
                    "index": 0
                }
            ],
            "created": 1701680746,
            "model": "gpt-3.5-turbo-0613",
            "object": "chat.completion.chunk",
            "system_fingerprint": None
        },
        {
            "id": "chatcmpl-8RzBaWVmpPZZJFdxZgynVwZMATday",
            "choices": [
                {
                    "delta": {
                        "content": "\u60c5",
                        "function_call": None,
                        "role": None,
                        "tool_calls": None
                    },
                    "finish_reason": None,
                    "index": 0
                }
            ],
            "created": 1701680746,
            "model": "gpt-3.5-turbo-0613",
            "object": "chat.completion.chunk",
            "system_fingerprint": None
        },
        {
            "id": "chatcmpl-8RzBaWVmpPZZJFdxZgynVwZMATday",
            "choices": [
                {
                    "delta": {
                        "content": "\u5831",
                        "function_call": None,
                        "role": None,
                        "tool_calls": None
                    },
                    "finish_reason": None,
                    "index": 0
                }
            ],
            "created": 1701680746,
            "model": "gpt-3.5-turbo-0613",
            "object": "chat.completion.chunk",
            "system_fingerprint": None
        },
        {
            "id": "chatcmpl-8RzBaWVmpPZZJFdxZgynVwZMATday",
            "choices": [
                {
                    "delta": {
                        "content": "\u306f",
                        "function_call": None,
                        "role": None,
                        "tool_calls": None
                    },
                    "finish_reason": None,
                    "index": 0
                }
            ],
            "created": 1701680746,
            "model": "gpt-3.5-turbo-0613",
            "object": "chat.completion.chunk",
            "system_fingerprint": None
        },
        {
            "id": "chatcmpl-8RzBaWVmpPZZJFdxZgynVwZMATday",
            "choices": [
                {
                    "delta": {
                        "content": "\u3001",
                        "function_call": None,
                        "role": None,
                        "tool_calls": None
                    },
                    "finish_reason": None,
                    "index": 0
                }
            ],
            "created": 1701680746,
            "model": "gpt-3.5-turbo-0613",
            "object": "chat.completion.chunk",
            "system_fingerprint": None
        },
        {
            "id": "chatcmpl-8RzBaWVmpPZZJFdxZgynVwZMATday",
            "choices": [
                {
                    "delta": {
                        "content": "\u5929",
                        "function_call": None,
                        "role": None,
                        "tool_calls": None
                    },
                    "finish_reason": None,
                    "index": 0
                }
            ],
            "created": 1701680746,
            "model": "gpt-3.5-turbo-0613",
            "object": "chat.completion.chunk",
            "system_fingerprint": None
        },
        {
            "id": "chatcmpl-8RzBaWVmpPZZJFdxZgynVwZMATday",
            "choices": [
                {
                    "delta": {
                        "content": "\u5019",
                        "function_call": None,
                        "role": None,
                        "tool_calls": None
                    },
                    "finish_reason": None,
                    "index": 0
                }
            ],
            "created": 1701680746,
            "model": "gpt-3.5-turbo-0613",
            "object": "chat.completion.chunk",
            "system_fingerprint": None
        },
        {
            "id": "chatcmpl-8RzBaWVmpPZZJFdxZgynVwZMATday",
            "choices": [
                {
                    "delta": {
                        "content": "\u4e88",
                        "function_call": None,
                        "role": None,
                        "tool_calls": None
                    },
                    "finish_reason": None,
                    "index": 0
                }
            ],
            "created": 1701680746,
            "model": "gpt-3.5-turbo-0613",
            "object": "chat.completion.chunk",
            "system_fingerprint": None
        },
        {
            "id": "chatcmpl-8RzBaWVmpPZZJFdxZgynVwZMATday",
            "choices": [
                {
                    "delta": {
                        "content": "\u5831",
                        "function_call": None,
                        "role": None,
                        "tool_calls": None
                    },
                    "finish_reason": None,
                    "index": 0
                }
            ],
            "created": 1701680746,
            "model": "gpt-3.5-turbo-0613",
            "object": "chat.completion.chunk",
            "system_fingerprint": None
        },
        {
            "id": "chatcmpl-8RzBaWVmpPZZJFdxZgynVwZMATday",
            "choices": [
                {
                    "delta": {
                        "content": "\u30b5",
                        "function_call": None,
                        "role": None,
                        "tool_calls": None
                    },
                    "finish_reason": None,
                    "index": 0
                }
            ],
            "created": 1701680746,
            "model": "gpt-3.5-turbo-0613",
            "object": "chat.completion.chunk",
            "system_fingerprint": None
        },
        {
            "id": "chatcmpl-8RzBaWVmpPZZJFdxZgynVwZMATday",
            "choices": [
                {
                    "delta": {
                        "content": "\u30a4\u30c8",
                        "function_call": None,
                        "role": None,
                        "tool_calls": None
                    },
                    "finish_reason": None,
                    "index": 0
                }
            ],
            "created": 1701680746,
            "model": "gpt-3.5-turbo-0613",
            "object": "chat.completion.chunk",
            "system_fingerprint": None
        },
        {
            "id": "chatcmpl-8RzBaWVmpPZZJFdxZgynVwZMATday",
            "choices": [
                {
                    "delta": {
                        "content": "\u3084",
                        "function_call": None,
                        "role": None,
                        "tool_calls": None
                    },
                    "finish_reason": None,
                    "index": 0
                }
            ],
            "created": 1701680746,
            "model": "gpt-3.5-turbo-0613",
            "object": "chat.completion.chunk",
            "system_fingerprint": None
        },
        {
            "id": "chatcmpl-8RzBaWVmpPZZJFdxZgynVwZMATday",
            "choices": [
                {
                    "delta": {
                        "content": "\u5929",
                        "function_call": None,
                        "role": None,
                        "tool_calls": None
                    },
                    "finish_reason": None,
                    "index": 0
                }
            ],
            "created": 1701680746,
            "model": "gpt-3.5-turbo-0613",
            "object": "chat.completion.chunk",
            "system_fingerprint": None
        },
        {
            "id": "chatcmpl-8RzBaWVmpPZZJFdxZgynVwZMATday",
            "choices": [
                {
                    "delta": {
                        "content": "\u6c17",
                        "function_call": None,
                        "role": None,
                        "tool_calls": None
                    },
                    "finish_reason": None,
                    "index": 0
                }
            ],
            "created": 1701680746,
            "model": "gpt-3.5-turbo-0613",
            "object": "chat.completion.chunk",
            "system_fingerprint": None
        },
        {
            "id": "chatcmpl-8RzBaWVmpPZZJFdxZgynVwZMATday",
            "choices": [
                {
                    "delta": {
                        "content": "\u30a2",
                        "function_call": None,
                        "role": None,
                        "tool_calls": None
                    },
                    "finish_reason": None,
                    "index": 0
                }
            ],
            "created": 1701680746,
            "model": "gpt-3.5-turbo-0613",
            "object": "chat.completion.chunk",
            "system_fingerprint": None
        },
        {
            "id": "chatcmpl-8RzBaWVmpPZZJFdxZgynVwZMATday",
            "choices": [
                {
                    "delta": {
                        "content": "\u30d7",
                        "function_call": None,
                        "role": None,
                        "tool_calls": None
                    },
                    "finish_reason": None,
                    "index": 0
                }
            ],
            "created": 1701680746,
            "model": "gpt-3.5-turbo-0613",
            "object": "chat.completion.chunk",
            "system_fingerprint": None
        },
        {
            "id": "chatcmpl-8RzBaWVmpPZZJFdxZgynVwZMATday",
            "choices": [
                {
                    "delta": {
                        "content": "\u30ea",
                        "function_call": None,
                        "role": None,
                        "tool_calls": None
                    },
                    "finish_reason": None,
                    "index": 0
                }
            ],
            "created": 1701680746,
            "model": "gpt-3.5-turbo-0613",
            "object": "chat.completion.chunk",
            "system_fingerprint": None
        },
        {
            "id": "chatcmpl-8RzBaWVmpPZZJFdxZgynVwZMATday",
            "choices": [
                {
                    "delta": {
                        "content": "\u3092",
                        "function_call": None,
                        "role": None,
                        "tool_calls": None
                    },
                    "finish_reason": None,
                    "index": 0
                }
            ],
            "created": 1701680746,
            "model": "gpt-3.5-turbo-0613",
            "object": "chat.completion.chunk",
            "system_fingerprint": None
        },
        {
            "id": "chatcmpl-8RzBaWVmpPZZJFdxZgynVwZMATday",
            "choices": [
                {
                    "delta": {
                        "content": "\u3054",
                        "function_call": None,
                        "role": None,
                        "tool_calls": None
                    },
                    "finish_reason": None,
                    "index": 0
                }
            ],
            "created": 1701680746,
            "model": "gpt-3.5-turbo-0613",
            "object": "chat.completion.chunk",
            "system_fingerprint": None
        },
        {
            "id": "chatcmpl-8RzBaWVmpPZZJFdxZgynVwZMATday",
            "choices": [
                {
                    "delta": {
                        "content": "\u5229",
                        "function_call": None,
                        "role": None,
                        "tool_calls": None
                    },
                    "finish_reason": None,
                    "index": 0
                }
            ],
            "created": 1701680746,
            "model": "gpt-3.5-turbo-0613",
            "object": "chat.completion.chunk",
            "system_fingerprint": None
        },
        {
            "id": "chatcmpl-8RzBaWVmpPZZJFdxZgynVwZMATday",
            "choices": [
                {
                    "delta": {
                        "content": "\u7528",
                        "function_call": None,
                        "role": None,
                        "tool_calls": None
                    },
                    "finish_reason": None,
                    "index": 0
                }
            ],
            "created": 1701680746,
            "model": "gpt-3.5-turbo-0613",
            "object": "chat.completion.chunk",
            "system_fingerprint": None
        },
        {
            "id": "chatcmpl-8RzBaWVmpPZZJFdxZgynVwZMATday",
            "choices": [
                {
                    "delta": {
                        "content": "\u304f\u3060\u3055\u3044",
                        "function_call": None,
                        "role": None,
                        "tool_calls": None
                    },
                    "finish_reason": None,
                    "index": 0
                }
            ],
            "created": 1701680746,
            "model": "gpt-3.5-turbo-0613",
            "object": "chat.completion.chunk",
            "system_fingerprint": None
        },
        {
            "id": "chatcmpl-8RzBaWVmpPZZJFdxZgynVwZMATday",
            "choices": [
                {
                    "delta": {
                        "content": "\u3002",
                        "function_call": None,
                        "role": None,
                        "tool_calls": None
                    },
                    "finish_reason": None,
                    "index": 0
                }
            ],
            "created": 1701680746,
            "model": "gpt-3.5-turbo-0613",
            "object": "chat.completion.chunk",
            "system_fingerprint": None
        },
        {
            "id": "chatcmpl-8RzBaWVmpPZZJFdxZgynVwZMATday",
            "choices": [
                {
                    "delta": {
                        "content": None,
                        "function_call": None,
                        "role": None,
                        "tool_calls": None
                    },
                    "finish_reason": "stop",
                    "index": 0
                }
            ],
            "created": 1701680746,
            "model": "gpt-3.5-turbo-0613",
            "object": "chat.completion.chunk",
            "system_fingerprint": None
        }
    ]

@pytest.fixture
def chunks_function():
    return [
        {
            "id": "chatcmpl-8RzHboLVZGBoFMc5gEGrMdcGHGPWs",
            "choices": [
                {
                    "delta": {
                        "content": None,
                        "function_call": {
                            "arguments": "",
                            "name": "get_weather"
                        },
                        "role": "assistant",
                        "tool_calls": None
                    },
                    "finish_reason": None,
                    "index": 0
                }
            ],
            "created": 1701681119,
            "model": "gpt-3.5-turbo-0613",
            "object": "chat.completion.chunk",
            "system_fingerprint": None
        },
        {
            "id": "chatcmpl-8RzHboLVZGBoFMc5gEGrMdcGHGPWs",
            "choices": [
                {
                    "delta": {
                        "content": None,
                        "function_call": {
                            "arguments": "{\n",
                            "name": None
                        },
                        "role": None,
                        "tool_calls": None
                    },
                    "finish_reason": None,
                    "index": 0
                }
            ],
            "created": 1701681119,
            "model": "gpt-3.5-turbo-0613",
            "object": "chat.completion.chunk",
            "system_fingerprint": None
        },
        {
            "id": "chatcmpl-8RzHboLVZGBoFMc5gEGrMdcGHGPWs",
            "choices": [
                {
                    "delta": {
                        "content": None,
                        "function_call": {
                            "arguments": " ",
                            "name": None
                        },
                        "role": None,
                        "tool_calls": None
                    },
                    "finish_reason": None,
                    "index": 0
                }
            ],
            "created": 1701681119,
            "model": "gpt-3.5-turbo-0613",
            "object": "chat.completion.chunk",
            "system_fingerprint": None
        },
        {
            "id": "chatcmpl-8RzHboLVZGBoFMc5gEGrMdcGHGPWs",
            "choices": [
                {
                    "delta": {
                        "content": None,
                        "function_call": {
                            "arguments": " \"",
                            "name": None
                        },
                        "role": None,
                        "tool_calls": None
                    },
                    "finish_reason": None,
                    "index": 0
                }
            ],
            "created": 1701681119,
            "model": "gpt-3.5-turbo-0613",
            "object": "chat.completion.chunk",
            "system_fingerprint": None
        },
        {
            "id": "chatcmpl-8RzHboLVZGBoFMc5gEGrMdcGHGPWs",
            "choices": [
                {
                    "delta": {
                        "content": None,
                        "function_call": {
                            "arguments": "location",
                            "name": None
                        },
                        "role": None,
                        "tool_calls": None
                    },
                    "finish_reason": None,
                    "index": 0
                }
            ],
            "created": 1701681119,
            "model": "gpt-3.5-turbo-0613",
            "object": "chat.completion.chunk",
            "system_fingerprint": None
        },
        {
            "id": "chatcmpl-8RzHboLVZGBoFMc5gEGrMdcGHGPWs",
            "choices": [
                {
                    "delta": {
                        "content": None,
                        "function_call": {
                            "arguments": "\":",
                            "name": None
                        },
                        "role": None,
                        "tool_calls": None
                    },
                    "finish_reason": None,
                    "index": 0
                }
            ],
            "created": 1701681119,
            "model": "gpt-3.5-turbo-0613",
            "object": "chat.completion.chunk",
            "system_fingerprint": None
        },
        {
            "id": "chatcmpl-8RzHboLVZGBoFMc5gEGrMdcGHGPWs",
            "choices": [
                {
                    "delta": {
                        "content": None,
                        "function_call": {
                            "arguments": " \"",
                            "name": None
                        },
                        "role": None,
                        "tool_calls": None
                    },
                    "finish_reason": None,
                    "index": 0
                }
            ],
            "created": 1701681119,
            "model": "gpt-3.5-turbo-0613",
            "object": "chat.completion.chunk",
            "system_fingerprint": None
        },
        {
            "id": "chatcmpl-8RzHboLVZGBoFMc5gEGrMdcGHGPWs",
            "choices": [
                {
                    "delta": {
                        "content": None,
                        "function_call": {
                            "arguments": "\u6771",
                            "name": None
                        },
                        "role": None,
                        "tool_calls": None
                    },
                    "finish_reason": None,
                    "index": 0
                }
            ],
            "created": 1701681119,
            "model": "gpt-3.5-turbo-0613",
            "object": "chat.completion.chunk",
            "system_fingerprint": None
        },
        {
            "id": "chatcmpl-8RzHboLVZGBoFMc5gEGrMdcGHGPWs",
            "choices": [
                {
                    "delta": {
                        "content": None,
                        "function_call": {
                            "arguments": "\u4eac",
                            "name": None
                        },
                        "role": None,
                        "tool_calls": None
                    },
                    "finish_reason": None,
                    "index": 0
                }
            ],
            "created": 1701681119,
            "model": "gpt-3.5-turbo-0613",
            "object": "chat.completion.chunk",
            "system_fingerprint": None
        },
        {
            "id": "chatcmpl-8RzHboLVZGBoFMc5gEGrMdcGHGPWs",
            "choices": [
                {
                    "delta": {
                        "content": None,
                        "function_call": {
                            "arguments": "\"\n",
                            "name": None
                        },
                        "role": None,
                        "tool_calls": None
                    },
                    "finish_reason": None,
                    "index": 0
                }
            ],
            "created": 1701681119,
            "model": "gpt-3.5-turbo-0613",
            "object": "chat.completion.chunk",
            "system_fingerprint": None
        },
        {
            "id": "chatcmpl-8RzHboLVZGBoFMc5gEGrMdcGHGPWs",
            "choices": [
                {
                    "delta": {
                        "content": None,
                        "function_call": {
                            "arguments": "}",
                            "name": None
                        },
                        "role": None,
                        "tool_calls": None
                    },
                    "finish_reason": None,
                    "index": 0
                }
            ],
            "created": 1701681119,
            "model": "gpt-3.5-turbo-0613",
            "object": "chat.completion.chunk",
            "system_fingerprint": None
        },
        {
            "id": "chatcmpl-8RzHboLVZGBoFMc5gEGrMdcGHGPWs",
            "choices": [
                {
                    "delta": {
                        "content": None,
                        "function_call": None,
                        "role": None,
                        "tool_calls": None
                    },
                    "finish_reason": "stop",
                    "index": 0
                }
            ],
            "created": 1701681119,
            "model": "gpt-3.5-turbo-0613",
            "object": "chat.completion.chunk",
            "system_fingerprint": None
        }
    ]

@pytest.fixture
def chunks_tools():
    return [
        {
            "id": "chatcmpl-8RzQ18VWw1jxIzcFXGdGKrKusELgD",
            "choices": [
                {
                    "delta": {
                        "content": None,
                        "function_call": None,
                        "role": "assistant",
                        "tool_calls": None
                    },
                    "finish_reason": None,
                    "index": 0
                }
            ],
            "created": 1701681641,
            "model": "gpt-3.5-turbo-1106",
            "object": "chat.completion.chunk",
            "system_fingerprint": "fp_eeff13170a"
        },
        {
            "id": "chatcmpl-8RzQ18VWw1jxIzcFXGdGKrKusELgD",
            "choices": [
                {
                    "delta": {
                        "content": None,
                        "function_call": None,
                        "role": None,
                        "tool_calls": [
                            {
                                "index": 0,
                                "id": "call_vCJBXdx4kkyl16bIBy6i3SwD",
                                "function": {
                                    "arguments": "",
                                    "name": "get_weather"
                                },
                                "type": "function"
                            }
                        ]
                    },
                    "finish_reason": None,
                    "index": 0
                }
            ],
            "created": 1701681641,
            "model": "gpt-3.5-turbo-1106",
            "object": "chat.completion.chunk",
            "system_fingerprint": "fp_eeff13170a"
        },
        {
            "id": "chatcmpl-8RzQ18VWw1jxIzcFXGdGKrKusELgD",
            "choices": [
                {
                    "delta": {
                        "content": None,
                        "function_call": None,
                        "role": None,
                        "tool_calls": [
                            {
                                "index": 0,
                                "id": None,
                                "function": {
                                    "arguments": "{\"lo",
                                    "name": None
                                },
                                "type": None
                            }
                        ]
                    },
                    "finish_reason": None,
                    "index": 0
                }
            ],
            "created": 1701681641,
            "model": "gpt-3.5-turbo-1106",
            "object": "chat.completion.chunk",
            "system_fingerprint": "fp_eeff13170a"
        },
        {
            "id": "chatcmpl-8RzQ18VWw1jxIzcFXGdGKrKusELgD",
            "choices": [
                {
                    "delta": {
                        "content": None,
                        "function_call": None,
                        "role": None,
                        "tool_calls": [
                            {
                                "index": 0,
                                "id": None,
                                "function": {
                                    "arguments": "catio",
                                    "name": None
                                },
                                "type": None
                            }
                        ]
                    },
                    "finish_reason": None,
                    "index": 0
                }
            ],
            "created": 1701681641,
            "model": "gpt-3.5-turbo-1106",
            "object": "chat.completion.chunk",
            "system_fingerprint": "fp_eeff13170a"
        },
        {
            "id": "chatcmpl-8RzQ18VWw1jxIzcFXGdGKrKusELgD",
            "choices": [
                {
                    "delta": {
                        "content": None,
                        "function_call": None,
                        "role": None,
                        "tool_calls": [
                            {
                                "index": 0,
                                "id": None,
                                "function": {
                                    "arguments": "n\": \"T",
                                    "name": None
                                },
                                "type": None
                            }
                        ]
                    },
                    "finish_reason": None,
                    "index": 0
                }
            ],
            "created": 1701681641,
            "model": "gpt-3.5-turbo-1106",
            "object": "chat.completion.chunk",
            "system_fingerprint": "fp_eeff13170a"
        },
        {
            "id": "chatcmpl-8RzQ18VWw1jxIzcFXGdGKrKusELgD",
            "choices": [
                {
                    "delta": {
                        "content": None,
                        "function_call": None,
                        "role": None,
                        "tool_calls": [
                            {
                                "index": 0,
                                "id": None,
                                "function": {
                                    "arguments": "okyo",
                                    "name": None
                                },
                                "type": None
                            }
                        ]
                    },
                    "finish_reason": None,
                    "index": 0
                }
            ],
            "created": 1701681641,
            "model": "gpt-3.5-turbo-1106",
            "object": "chat.completion.chunk",
            "system_fingerprint": "fp_eeff13170a"
        },
        {
            "id": "chatcmpl-8RzQ18VWw1jxIzcFXGdGKrKusELgD",
            "choices": [
                {
                    "delta": {
                        "content": None,
                        "function_call": None,
                        "role": None,
                        "tool_calls": [
                            {
                                "index": 0,
                                "id": None,
                                "function": {
                                    "arguments": "\"}",
                                    "name": None
                                },
                                "type": None
                            }
                        ]
                    },
                    "finish_reason": None,
                    "index": 0
                }
            ],
            "created": 1701681641,
            "model": "gpt-3.5-turbo-1106",
            "object": "chat.completion.chunk",
            "system_fingerprint": "fp_eeff13170a"
        },
        {
            "id": "chatcmpl-8RzQ18VWw1jxIzcFXGdGKrKusELgD",
            "choices": [
                {
                    "delta": {
                        "content": None,
                        "function_call": None,
                        "role": None,
                        "tool_calls": [
                            {
                                "index": 1,
                                "id": "call_2pt8XB57mFTaij7CSeIVQm4j",
                                "function": {
                                    "arguments": "",
                                    "name": "get_weather"
                                },
                                "type": "function"
                            }
                        ]
                    },
                    "finish_reason": None,
                    "index": 0
                }
            ],
            "created": 1701681641,
            "model": "gpt-3.5-turbo-1106",
            "object": "chat.completion.chunk",
            "system_fingerprint": "fp_eeff13170a"
        },
        {
            "id": "chatcmpl-8RzQ18VWw1jxIzcFXGdGKrKusELgD",
            "choices": [
                {
                    "delta": {
                        "content": None,
                        "function_call": None,
                        "role": None,
                        "tool_calls": [
                            {
                                "index": 1,
                                "id": None,
                                "function": {
                                    "arguments": "{\"lo",
                                    "name": None
                                },
                                "type": None
                            }
                        ]
                    },
                    "finish_reason": None,
                    "index": 0
                }
            ],
            "created": 1701681641,
            "model": "gpt-3.5-turbo-1106",
            "object": "chat.completion.chunk",
            "system_fingerprint": "fp_eeff13170a"
        },
        {
            "id": "chatcmpl-8RzQ18VWw1jxIzcFXGdGKrKusELgD",
            "choices": [
                {
                    "delta": {
                        "content": None,
                        "function_call": None,
                        "role": None,
                        "tool_calls": [
                            {
                                "index": 1,
                                "id": None,
                                "function": {
                                    "arguments": "catio",
                                    "name": None
                                },
                                "type": None
                            }
                        ]
                    },
                    "finish_reason": None,
                    "index": 0
                }
            ],
            "created": 1701681641,
            "model": "gpt-3.5-turbo-1106",
            "object": "chat.completion.chunk",
            "system_fingerprint": "fp_eeff13170a"
        },
        {
            "id": "chatcmpl-8RzQ18VWw1jxIzcFXGdGKrKusELgD",
            "choices": [
                {
                    "delta": {
                        "content": None,
                        "function_call": None,
                        "role": None,
                        "tool_calls": [
                            {
                                "index": 1,
                                "id": None,
                                "function": {
                                    "arguments": "n\": \"N",
                                    "name": None
                                },
                                "type": None
                            }
                        ]
                    },
                    "finish_reason": None,
                    "index": 0
                }
            ],
            "created": 1701681641,
            "model": "gpt-3.5-turbo-1106",
            "object": "chat.completion.chunk",
            "system_fingerprint": "fp_eeff13170a"
        },
        {
            "id": "chatcmpl-8RzQ18VWw1jxIzcFXGdGKrKusELgD",
            "choices": [
                {
                    "delta": {
                        "content": None,
                        "function_call": None,
                        "role": None,
                        "tool_calls": [
                            {
                                "index": 1,
                                "id": None,
                                "function": {
                                    "arguments": "agoy",
                                    "name": None
                                },
                                "type": None
                            }
                        ]
                    },
                    "finish_reason": None,
                    "index": 0
                }
            ],
            "created": 1701681641,
            "model": "gpt-3.5-turbo-1106",
            "object": "chat.completion.chunk",
            "system_fingerprint": "fp_eeff13170a"
        },
        {
            "id": "chatcmpl-8RzQ18VWw1jxIzcFXGdGKrKusELgD",
            "choices": [
                {
                    "delta": {
                        "content": None,
                        "function_call": None,
                        "role": None,
                        "tool_calls": [
                            {
                                "index": 1,
                                "id": None,
                                "function": {
                                    "arguments": "a\"}",
                                    "name": None
                                },
                                "type": None
                            }
                        ]
                    },
                    "finish_reason": None,
                    "index": 0
                }
            ],
            "created": 1701681641,
            "model": "gpt-3.5-turbo-1106",
            "object": "chat.completion.chunk",
            "system_fingerprint": "fp_eeff13170a"
        },
        {
            "id": "chatcmpl-8RzQ18VWw1jxIzcFXGdGKrKusELgD",
            "choices": [
                {
                    "delta": {
                        "content": None,
                        "function_call": None,
                        "role": None,
                        "tool_calls": None
                    },
                    "finish_reason": "tool_calls",
                    "index": 0
                }
            ],
            "created": 1701681641,
            "model": "gpt-3.5-turbo-1106",
            "object": "chat.completion.chunk",
            "system_fingerprint": "fp_eeff13170a"
        }
    ]


def test_request_item_to_accesslog(messages, request_json, request_headers, functions, tools):
    request_id = str(uuid4())
    request_json["functions"] = functions
    request_json["tools"] = tools
    item = ChatGPTRequestItem(request_id, request_json, request_headers)

    accesslog = item.to_accesslog(AccessLog)

    assert accesslog.request_id == request_id
    assert isinstance(accesslog.created_at, datetime)
    assert accesslog.direction == "request"
    assert accesslog.content == messages[-1]["content"]
    assert accesslog.function_call is None
    assert accesslog.tool_calls is None
    assert accesslog.raw_body == json.dumps(request_json, ensure_ascii=False)
    assert accesslog.raw_headers == json.dumps(request_headers, ensure_ascii=False)
    assert accesslog.model == request_json["model"]


def test_response_item_to_accesslog(response_json):
    request_id = str(uuid4())
    item = ChatGPTResponseItem(request_id, response_json, None, 1.0, 2.0)

    accesslog = item.to_accesslog(AccessLog)

    assert accesslog.request_id == request_id
    assert isinstance(accesslog.created_at, datetime)
    assert accesslog.direction == "response"
    assert accesslog.content == response_json["choices"][0]["message"]["content"]
    assert accesslog.function_call is None
    assert accesslog.tool_calls is None
    assert accesslog.raw_body == json.dumps(response_json, ensure_ascii=False)
    assert accesslog.raw_headers is None
    assert accesslog.model == response_json["model"]
    assert accesslog.prompt_tokens == response_json["usage"]["prompt_tokens"]
    assert accesslog.completion_tokens == response_json["usage"]["completion_tokens"]
    assert accesslog.request_time == item.duration
    assert accesslog.request_time_api == item.duration_api


def test_response_item_to_accesslog_function(response_json, functions):
    request_id = str(uuid4())

    response_json["choices"][0]["message"]["content"] = ""
    response_json["choices"][0]["message"]["function_call"] = {"name": "get_weather", "arguments": '{\n  "location": "東京"\n}'}
    
    item = ChatGPTResponseItem(request_id, response_json, None, 1.0, 2.0)

    accesslog = item.to_accesslog(AccessLog)

    assert accesslog.request_id == request_id
    assert isinstance(accesslog.created_at, datetime)
    assert accesslog.direction == "response"
    assert accesslog.content == ""
    assert json.loads(accesslog.function_call) == response_json["choices"][0]["message"]["function_call"]
    assert accesslog.tool_calls is None
    assert accesslog.raw_body == json.dumps(response_json, ensure_ascii=False)
    assert accesslog.raw_headers is None
    assert accesslog.model == response_json["model"]
    assert accesslog.prompt_tokens == response_json["usage"]["prompt_tokens"]
    assert accesslog.completion_tokens == response_json["usage"]["completion_tokens"]
    assert accesslog.request_time == item.duration
    assert accesslog.request_time_api == item.duration_api


def test_response_item_to_accesslog_tools(response_json):
    request_id = str(uuid4())

    response_json["choices"][0]["message"]["content"] = ""
    response_json["choices"][0]["message"]["tool_calls"] = [
        {"type": "function", "function": {"name": "get_weather", "arguments": '{\n  "location": "東京"\n}'}},
        {"type": "function", "function": {"name": "get_weather", "arguments": '{\n  "location": "名古屋"\n}'}},
    ]

    item = ChatGPTResponseItem(request_id, response_json, None, 1.0, 2.0)

    accesslog = item.to_accesslog(AccessLog)

    assert accesslog.request_id == request_id
    assert isinstance(accesslog.created_at, datetime)
    assert accesslog.direction == "response"
    assert accesslog.content == ""
    assert accesslog.function_call is None
    assert json.loads(accesslog.tool_calls) == response_json["choices"][0]["message"]["tool_calls"]
    assert accesslog.raw_body == json.dumps(response_json, ensure_ascii=False)
    assert accesslog.raw_headers is None
    assert accesslog.model == response_json["model"]
    assert accesslog.prompt_tokens == response_json["usage"]["prompt_tokens"]
    assert accesslog.completion_tokens == response_json["usage"]["completion_tokens"]
    assert accesslog.request_time == item.duration
    assert accesslog.request_time_api == item.duration_api


def test_stream_response_item_to_accesslog(chunks_json, request_json):
    request_id = str(uuid4())
    chunks = []
    content = ""
    for c in chunks_json:
        chunks.append(ChatGPTStreamResponseItem(request_id, c))
        if c["choices"] and c["choices"][0]["delta"]["content"]:
            content += c["choices"][0]["delta"]["content"]

    last_chunk = ChatGPTStreamResponseItem(request_id, duration=1.0, duration_api=2.0, request_json=request_json)
    accesslog = last_chunk.to_accesslog(chunks, AccessLog)

    assert accesslog.request_id == request_id
    assert isinstance(accesslog.created_at, datetime)
    assert accesslog.direction == "response"
    assert accesslog.content == content
    assert accesslog.function_call is None
    assert accesslog.tool_calls is None
    assert accesslog.raw_body == json.dumps(chunks_json, ensure_ascii=False)
    assert accesslog.raw_headers is None
    assert accesslog.model == chunks_json[0]["model"]
    assert accesslog.prompt_tokens > 0
    assert accesslog.completion_tokens > 0
    assert accesslog.request_time == last_chunk.duration
    assert accesslog.request_time_api == last_chunk.duration_api


def test_stream_response_item_to_accesslog_function(chunks_function, request_json):
    request_id = str(uuid4())
    chunks = []
    function_call = {"name": "", "arguments": ""}
    for c in chunks_function:
        chunks.append(ChatGPTStreamResponseItem(request_id, c))
        if c["choices"] and c["choices"][0]["delta"]["function_call"]:
            if not function_call["name"] and c["choices"][0]["delta"]["function_call"]["name"]:
                function_call["name"] = c["choices"][0]["delta"]["function_call"]["name"]
            function_call["arguments"] += c["choices"][0]["delta"]["function_call"]["arguments"]

    last_chunk = ChatGPTStreamResponseItem(request_id, duration=1.0, duration_api=2.0, request_json=request_json)
    accesslog = last_chunk.to_accesslog(chunks, AccessLog)

    assert accesslog.request_id == request_id
    assert isinstance(accesslog.created_at, datetime)
    assert accesslog.direction == "response"
    assert accesslog.content == ""
    assert accesslog.function_call == json.dumps(function_call, ensure_ascii=False)
    assert accesslog.tool_calls is None
    assert accesslog.raw_body == json.dumps(chunks_function, ensure_ascii=False)
    assert accesslog.raw_headers is None
    assert accesslog.model == chunks_function[0]["model"]
    assert accesslog.prompt_tokens > 0
    assert accesslog.completion_tokens > 0
    assert accesslog.request_time == last_chunk.duration
    assert accesslog.request_time_api == last_chunk.duration_api


def test_stream_response_item_to_accesslog_tools(chunks_tools, request_json):
    request_id = str(uuid4())
    chunks = []
    tool_calls = []
    for c in chunks_tools:
        chunks.append(ChatGPTStreamResponseItem(request_id, c))
        if c["choices"] and c["choices"][0]["delta"]["tool_calls"]:
            if c["choices"][0]["delta"]["tool_calls"][0]["type"] is not None:
                tool_calls.append({"type": "function", "function": {"name": c["choices"][0]["delta"]["tool_calls"][0]["function"]["name"], "arguments": ""}})
            elif c["choices"][0]["delta"]["tool_calls"][0]["function"].get("arguments"):
                tool_calls[-1]["function"]["arguments"] += c["choices"][0]["delta"]["tool_calls"][0]["function"]["arguments"]

    last_chunk = ChatGPTStreamResponseItem(request_id, duration=1.0, duration_api=2.0, request_json=request_json)
    accesslog = last_chunk.to_accesslog(chunks, AccessLog)

    assert accesslog.request_id == request_id
    assert isinstance(accesslog.created_at, datetime)
    assert accesslog.direction == "response"
    assert accesslog.content == ""
    assert accesslog.function_call is None
    assert accesslog.tool_calls == json.dumps(tool_calls)
    assert accesslog.raw_body == json.dumps(chunks_tools, ensure_ascii=True)       # これ・・・・？
    assert accesslog.raw_headers is None
    assert accesslog.model == chunks_tools[0]["model"]
    assert accesslog.prompt_tokens > 0
    assert accesslog.completion_tokens > 0
    assert accesslog.request_time == last_chunk.duration
    assert accesslog.request_time_api == last_chunk.duration_api


@pytest.fixture
def worker():
    return AccessLogWorker(connection_str="sqlite:///aiproxy_test.db")

@pytest.fixture
def chatgpt_proxy(worker):
    return ChatGPTProxy(access_logger_queue=worker.log_queue)

@pytest.fixture
def db(worker):
    return worker.get_session()

@pytest.fixture
def openai_client():
    return Client(base_url="http://127.0.0.1:8000")

@pytest.mark.asyncio
async def test_request_filter_overwrite(chatgpt_proxy, request_json, request_headers):
    request_id = str(uuid4())
    request_json["model"] = "gpt-4"

    chatgpt_proxy.add_filter(OverwriteFilter())
    await chatgpt_proxy.filter_request(request_id, request_json, request_headers)

    assert request_json["model"] == "gpt-3.5-turbo"


@pytest.mark.asyncio
async def test_request_filter_valuereturn(chatgpt_proxy, request_json, request_headers):
    request_id = str(uuid4())

    chatgpt_proxy.add_filter(ValueReturnFilter())

    ret = await chatgpt_proxy.filter_request(request_id, request_json, request_headers)
    assert ret.choices[0].message.content == "user is required"

    request_json["user"] = "uezo"
    ret = await chatgpt_proxy.filter_request(request_id, request_json, request_headers)
    assert ret.choices[0].message.content == "you can't use this service"

    request_json["user"] = "unagi"
    ret = await chatgpt_proxy.filter_request(request_id, request_json, request_headers)
    assert ret == request_json


@pytest.mark.asyncio
async def test_response_filter_valuereturn(chatgpt_proxy, response_json):
    request_id = str(uuid4())

    chatgpt_proxy.add_filter(OverwriteResponseFilter())

    resp = ChatCompletion.model_validate(response_json)
    ret = await chatgpt_proxy.filter_response(request_id, resp)

    assert ret.choices[0].message.content == "Overwrite in filter"


def test_post_content(messages, request_headers, openai_client, db):
    api_resp = openai_client.chat.completions.with_raw_response.create(
        model="gpt-3.5-turbo", messages=messages
    )

    comp_resp = api_resp.parse()
    headers = api_resp.headers
    request_id = headers.get("x-aiproxy-request-id")

    assert request_id is not None
    assert "天気" in comp_resp.choices[0].message.content

    db_request = db.query(AccessLog).where(AccessLog.request_id == request_id, AccessLog.direction == "request").first()
    db_resonse = db.query(AccessLog).where(AccessLog.request_id == request_id, AccessLog.direction == "response").first()

    assert db_request.content == messages[-1]["content"]
    assert db_resonse.content == comp_resp.choices[0].message.content


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

    db_request = db.query(AccessLog).where(AccessLog.request_id == request_id, AccessLog.direction == "request").first()
    db_resonse = db.query(AccessLog).where(AccessLog.request_id == request_id, AccessLog.direction == "response").first()

    print(function_call)
    assert db_request.content == messages[-1]["content"]
    assert json.loads(db_resonse.function_call) == function_call.model_dump()


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

    db_request = db.query(AccessLog).where(AccessLog.request_id == request_id, AccessLog.direction == "request").first()
    db_resonse = db.query(AccessLog).where(AccessLog.request_id == request_id, AccessLog.direction == "response").first()

    assert db_request.content == messages[-1]["content"]
    assert json.loads(db_resonse.tool_calls) == [t.model_dump() for t in tool_calls]


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

    db_request = db.query(AccessLog).where(AccessLog.request_id == request_id, AccessLog.direction == "request").first()
    db_resonse = db.query(AccessLog).where(AccessLog.request_id == request_id, AccessLog.direction == "error").first()

    assert db_request.content == messages[-1]["content"]
    assert str(apisterr.value) in db_resonse.content


def test_post_content_stream(messages, request_headers, openai_client, db):
    api_resp = openai_client.chat.completions.with_raw_response.create(
        model="gpt-3.5-turbo", messages=messages, stream=True
    )

    comp_resp = api_resp.parse()
    headers = api_resp.headers

    request_id = headers.get("x-aiproxy-request-id")
    assert request_id is not None

    content = ""
    for chunk in comp_resp:
        if chunk.choices and chunk.choices[0].delta and chunk.choices[0].delta.content:
            content += chunk.choices[0].delta.content

    db_request = db.query(AccessLog).where(AccessLog.request_id == request_id, AccessLog.direction == "request").first()
    db_resonse = db.query(AccessLog).where(AccessLog.request_id == request_id, AccessLog.direction == "response").first()

    assert db_request.content == messages[-1]["content"]
    assert db_resonse.content == content


def test_post_content_stream_function(messages, request_headers, functions, openai_client, db):
    api_resp = openai_client.chat.completions.with_raw_response.create(
        model="gpt-3.5-turbo", messages=messages, stream=True, functions=functions
    )

    comp_resp = api_resp.parse()
    headers = api_resp.headers

    request_id = headers.get("x-aiproxy-request-id")
    assert request_id is not None

    function_call = {"name": "", "arguments": ""}
    for chunk in comp_resp:
        if chunk.choices and chunk.choices[0].delta and chunk.choices[0].delta.function_call:
            if chunk.choices[0].delta.function_call.name and not function_call["name"]:
                function_call["name"] = chunk.choices[0].delta.function_call.name
            else:
                function_call["arguments"] += chunk.choices[0].delta.function_call.arguments

    db_request = db.query(AccessLog).where(AccessLog.request_id == request_id, AccessLog.direction == "request").first()
    db_resonse = db.query(AccessLog).where(AccessLog.request_id == request_id, AccessLog.direction == "response").first()

    assert db_request.content == messages[-1]["content"]
    assert json.loads(db_resonse.function_call) == function_call


def test_post_content_stream_tools(messages, request_headers, tools, openai_client, db):
    api_resp = openai_client.chat.completions.with_raw_response.create(
        model="gpt-3.5-turbo", messages=messages, stream=True, tools=tools
    )

    comp_resp = api_resp.parse()
    headers = api_resp.headers

    request_id = headers.get("x-aiproxy-request-id")
    assert request_id is not None

    tool_calls = []
    for chunk in comp_resp:
        if chunk.choices and chunk.choices[0].delta and chunk.choices[0].delta.tool_calls:
            if chunk.choices[0].delta.tool_calls[0].type is not None:
                tool_calls.append({"type": "function", "function": {"name": chunk.choices[0].delta.tool_calls[0].function.name, "arguments": ""}})
            elif chunk.choices[0].delta.tool_calls[0].function.arguments:
                tool_calls[-1]["function"]["arguments"] += chunk.choices[0].delta.tool_calls[0].function.arguments

    db_request = db.query(AccessLog).where(AccessLog.request_id == request_id, AccessLog.direction == "request").first()
    db_resonse = db.query(AccessLog).where(AccessLog.request_id == request_id, AccessLog.direction == "response").first()

    assert db_request.content == messages[-1]["content"]
    assert json.loads(db_resonse.tool_calls) == tool_calls


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

    db_request = db.query(AccessLog).where(AccessLog.request_id == request_id, AccessLog.direction == "request").first()
    db_resonse = db.query(AccessLog).where(AccessLog.request_id == request_id, AccessLog.direction == "error").first()

    assert db_request.content == messages[-1]["content"]
    assert str(apisterr.value) in db_resonse.content
