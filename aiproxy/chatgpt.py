from datetime import datetime
import json
import logging
import os
import time
import traceback
from typing import List, Union, AsyncGenerator
from uuid import uuid4
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from sse_starlette.sse import EventSourceResponse, AsyncContentStream
from openai import AsyncClient, APIStatusError, APIResponseValidationError, APIError, OpenAIError
from openai.types.chat import ChatCompletion
import tiktoken
from .proxy import ProxyBase, RequestFilterBase, ResponseFilterBase, RequestFilterException, ResponseFilterException
from .accesslog import _AccessLogBase, RequestItemBase, ResponseItemBase, StreamChunkItemBase, ErrorItemBase
from .queueclient import QueueClientBase


logger = logging.getLogger(__name__)


class ChatGPTRequestItem(RequestItemBase):
    def to_accesslog(self, accesslog_cls: _AccessLogBase) -> _AccessLogBase:
        request_headers_copy = self.request_headers.copy()
        if auth := request_headers_copy.get("authorization"):
            request_headers_copy["authorization"] = auth[:12] + "*****" + auth[-2:]

        accesslog = accesslog_cls(
            request_id=self.request_id,
            created_at=datetime.utcnow(),
            direction="request",
            content=self.request_json["messages"][-1]["content"],
            raw_body=json.dumps(self.request_json, ensure_ascii=False),
            raw_headers=json.dumps(request_headers_copy, ensure_ascii=False),
            model=self.request_json.get("model")
        )

        return accesslog


class ChatGPTResponseItem(ResponseItemBase):
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


class ChatGPTStreamResponseItem(StreamChunkItemBase):
    def to_accesslog(self, chunks: list, accesslog_cls: _AccessLogBase) -> _AccessLogBase:
        chunk_jsons = []
        response_content = ""
        function_call = None
        tool_calls = None
        prompt_tokens = 0
        completion_tokens = 0

        # Parse info from chunks
        for chunk in chunks:
            chunk_jsons.append(chunk.chunk_json)

            if len(chunk.chunk_json["choices"]) == 0:
                # Azure returns the first delta with empty choices
                continue

            delta = chunk.chunk_json["choices"][0]["delta"]

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
                response_content += delta.get("content") or ""
        
        # Serialize
        function_call_str = json.dumps(function_call, ensure_ascii=False) if function_call is not None else None
        tool_calls_str = json.dumps(tool_calls, ensure_ascii=False) if tool_calls is not None else None
        response_headers = json.dumps(dict(self.response_headers.items()), ensure_ascii=False) if self.response_headers is not None else None

        # Count tokens
        prompt_tokens = count_request_token(self.request_json)

        if tool_calls_str:
            completion_tokens = count_token(tool_calls_str)
        elif function_call_str:
            completion_tokens = count_token(function_call_str)
        else:
            completion_tokens = count_token(response_content)

        return accesslog_cls(
            request_id=self.request_id,
            created_at=datetime.utcnow(),
            direction="response",
            status_code=self.status_code,
            content=response_content,
            function_call=function_call_str,
            tool_calls=tool_calls_str,
            raw_body=json.dumps(chunk_jsons, ensure_ascii=False),
            raw_headers=response_headers,
            model=chunk_jsons[0]["model"],
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            request_time=self.duration,
            request_time_api=self.duration_api
        )


class ChatGPTErrorItem(ErrorItemBase):
    ...


queue_item_types = [ChatGPTRequestItem, ChatGPTResponseItem, ChatGPTStreamResponseItem, ChatGPTErrorItem]


# Reverse proxy application for ChatGPT
class ChatGPTProxy(ProxyBase):
    _empty_openai_api_key = "OPENAI_API_KEY_IS_NOT_SET"

    def __init__(
        self,
        *,
        api_key: str = None,
        async_client: AsyncClient = None,
        max_retries: int = 0,
        request_filters: List[RequestFilterBase] = None,
        response_filters: List[ResponseFilterBase] = None,
        access_logger_queue: QueueClientBase
    ):
        super().__init__(
            request_filters=request_filters,
            response_filters=response_filters,
            access_logger_queue=access_logger_queue
        )

        # ChatGPT client
        if async_client:
            self.client = async_client
        else:
            self.client = AsyncClient(
                api_key=api_key or os.getenv("OPENAI_API_KEY") or self._empty_openai_api_key,
                max_retries=max_retries
            )

    async def filter_request(self, request_id: str, request_json: dict, request_headers: dict) -> Union[dict, JSONResponse, EventSourceResponse]:
        for f in self.request_filters:
            if json_resp := await f.filter(request_id, request_json, request_headers):
                # Return response if filter returns string
                resp_for_log = {
                    "id": "-",
                    "choices": [{"message": {"role": "assistant", "content": json_resp}, "finish_reason": "stop", "index": 0}],
                    "created": 0,
                    "model": "request_filter",
                    "object": "chat.completion",
                    "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
                }
                # Response log
                self.access_logger_queue.put(ChatGPTResponseItem(
                    request_id=request_id,
                    response_json=resp_for_log,
                    status_code=200
                ))

                if request_json.get("stream"):
                    # Stream
                    async def filter_response_stream(content: str):
                        # First delta
                        resp = {
                            "id": "-",
                            "choices": [{"delta": {"role": "assistant", "content": ""}, "finish_reason": None, "index": 0}],
                            "created": 0,
                            "model": "request_filter",
                            "object": "chat.completion",
                            "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
                        }
                        yield json.dumps(resp)
                        # Last delta
                        resp["choices"][0] = {"delta": {"content": content}, "finish_reason": "stop", "index": 0}
                        yield json.dumps(resp)

                    return self.return_response_with_headers(EventSourceResponse(
                        filter_response_stream(json_resp)
                    ), request_id)

                else:
                    # Non-stream
                    return self.return_response_with_headers(JSONResponse(resp_for_log), request_id)

        return request_json

    async def filter_response(self, request_id: str, response: ChatCompletion) -> ChatCompletion:
        response_json = response.model_dump()

        for f in self.response_filters:
            if json_resp := await f.filter(request_id, response_json):
                return response.model_validate(json_resp)

        return response.model_validate(response_json)

    def return_response_with_headers(self, resp: JSONResponse, request_id: str):
        self.add_response_headers(response=resp, request_id=request_id)
        return resp

    def add_route(self, app: FastAPI, base_url: str):
        @app.post(base_url)
        async def handle_request(request: Request):
            request_id = str(uuid4())

            try:
                start_time = time.time()
                request_json = await request.json()
                request_headers = dict(request.headers.items())

                # Log request
                self.access_logger_queue.put(ChatGPTRequestItem(
                    request_id=request_id,
                    request_json=request_json,
                    request_headers=request_headers
                ))

                # Filter request
                request_json = await self.filter_request(request_id, request_json, request_headers)
                if isinstance(request_json, JSONResponse) or isinstance(request_json, EventSourceResponse):
                    return request_json

                # Call API
                start_time_api = time.time()
                if self.client.api_key != self._empty_openai_api_key:
                    # Always use server api key if set to client
                    raw_response = await self.client.chat.completions.with_raw_response.create(**request_json)
                elif user_auth_header := request_headers.get("authorization"):  # Lower case from client.
                    raw_response = await self.client.chat.completions.with_raw_response.create(
                        **request_json, extra_headers={"Authorization": user_auth_header}   # Pascal to server
                    )
                else:
                    # Call API anyway ;)
                    raw_response = await self.client.chat.completions.with_raw_response.create(**request_json)

                completion_response = raw_response.parse()
                completion_response_headers = raw_response.headers
                completion_status_code = raw_response.status_code
                if "content-encoding" in completion_response_headers:
                    completion_response_headers.pop("content-encoding") # Remove "br" that will be changed by this proxy

                # Handling response from API
                if request_json.get("stream"):
                    async def process_stream(stream: AsyncContentStream) -> AsyncGenerator[str, None]:
                        # Async content generator
                        try:
                            async for chunk in stream:
                                self.access_logger_queue.put(ChatGPTStreamResponseItem(
                                    request_id=request_id,
                                    chunk_json=chunk.model_dump()
                                ))
                                if chunk:
                                    yield chunk.model_dump_json()
                        
                        finally:
                            # Response log
                            now = time.time()
                            self.access_logger_queue.put(ChatGPTStreamResponseItem(
                                request_id=request_id,
                                response_headers=completion_response_headers,
                                duration=now - start_time,
                                duration_api=now - start_time_api,
                                request_json=request_json,
                                status_code=completion_status_code
                            ))

                    return self.return_response_with_headers(EventSourceResponse(
                        process_stream(completion_response),
                        headers=completion_response_headers
                    ), request_id)

                else:
                    duration_api = time.time() - start_time_api

                    # Filter response
                    completion_response = await self.filter_response(request_id, completion_response)

                    # Response log
                    self.access_logger_queue.put(ChatGPTResponseItem(
                        request_id=request_id,
                        response_json=completion_response.model_dump(),
                        response_headers=completion_response_headers,
                        duration=time.time() - start_time,
                        duration_api=duration_api,
                        status_code=completion_status_code
                    ))

                    return self.return_response_with_headers(JSONResponse(
                        content=completion_response.model_dump(),
                        headers=completion_response_headers
                    ), request_id)

                    return self.return_response_with_headers(JSONResponse(
                        content=completion_response.model_dump(),
                        headers=completion_response_headers
                    ), request_id)

            # Error handlers
            except RequestFilterException as rfex:
                logger.error(f"Request filter error: {rfex}\n{traceback.format_exc()}")

                resp_json = {"error": {"message": rfex.message, "type": "request_filter_error", "param": None, "code": None}}

                # Error log
                self.access_logger_queue.put(ChatGPTErrorItem(
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
                self.access_logger_queue.put(ChatGPTErrorItem(
                    request_id=request_id,
                    exception=rfex,
                    traceback_info=traceback.format_exc(),
                    response_json=resp_json,
                    status_code=rfex.status_code
                ))

                return self.return_response_with_headers(JSONResponse(resp_json, status_code=rfex.status_code), request_id)

            except (APIStatusError, APIResponseValidationError) as status_err:
                logger.error(f"APIStatusError from ChatGPT: {status_err}\n{traceback.format_exc()}")

                # Error log
                try:
                    resp_json = status_err.response.json()
                except:
                    resp_json = str(status_err.response.content)

                self.access_logger_queue.put(ChatGPTErrorItem(
                    request_id=request_id,
                    exception=status_err,
                    traceback_info=traceback.format_exc(),
                    response_json=resp_json,
                    status_code=status_err.status_code
                ))

                return self.return_response_with_headers(JSONResponse(resp_json, status_code=status_err.status_code), request_id)

            except APIError as api_err:
                logger.error(f"APIError from ChatGPT: {status_err}\n{traceback.format_exc()}")

                resp_json = {"error": {"message": api_err.message, "type": api_err.type, "param": api_err.param, "code": api_err.code}}

                # Error log
                self.access_logger_queue.put(ChatGPTErrorItem(
                    request_id=request_id,
                    exception=api_err,
                    traceback_info=traceback.format_exc(),
                    response_json=resp_json,
                    status_code=502
                ))

                return self.return_response_with_headers(JSONResponse(resp_json, status_code=502), request_id)

            except OpenAIError as oai_err:
                logger.error(f"OpenAIError: {oai_err}\n{traceback.format_exc()}")

                resp_json = {"error": {"message": str(oai_err), "type": "openai_error", "param": None, "code": None}}

                # Error log
                self.access_logger_queue.put(ChatGPTErrorItem(
                    request_id=request_id,
                    exception=oai_err,
                    traceback_info=traceback.format_exc(),
                    response_json=resp_json,
                    status_code=502
                ))

                return self.return_response_with_headers(JSONResponse(resp_json, status_code=502), request_id)

            except Exception as ex:
                logger.error(f"Error at server: {ex}\n{traceback.format_exc()}")

                resp_json = {"error": {"message": "Proxy error", "type": "proxy_error", "param": None, "code": None}}

                # Error log
                self.access_logger_queue.put(ChatGPTErrorItem(
                    request_id=request_id,
                    exception=ex,
                    traceback_info=traceback.format_exc(),
                    response_json=resp_json,
                    status_code=502
                ))

                return self.return_response_with_headers(JSONResponse(resp_json, status_code=502), request_id)
