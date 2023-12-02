import json
import logging
import os
from queue import Queue
import time
import traceback
from typing import List, Union, AsyncGenerator
from uuid import uuid4
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from sse_starlette.sse import EventSourceResponse, AsyncContentStream
from openai import AsyncClient, APIStatusError, APIResponseValidationError, APIError, OpenAIError
from openai.types.chat import ChatCompletion
from .proxy import ProxyBase, RequestFilterBase, ResponseFilterBase, RequestFilterException, ResponseFilterException
from .accesslog import RequestItem, ResponseItem, StreamChunkItem


logger = logging.getLogger(__name__)


# Reverse proxy application for ChatGPT
class ChatGPTProxy(ProxyBase):
    _empty_openai_api_key = "OPENAI_API_KEY_IS_NOT_SET"

    def __init__(
        self,
        *,
        api_key: str = None,
        async_client: AsyncClient = None,
        request_filters: List[RequestFilterBase] = None,
        response_filters: List[ResponseFilterBase] = None,
        access_logger_queue: Queue
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
                api_key=api_key or os.getenv("OPENAI_API_KEY") or self._empty_openai_api_key
            )

    async def filter_request(self, request_id: str, request_json: dict, request_headers: dict) -> Union[dict, ChatCompletion, EventSourceResponse]:
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
                self.access_logger_queue.put(ResponseItem(
                    request_id=request_id,
                    response_json=resp_for_log
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

                    return EventSourceResponse(filter_response_stream(json_resp))

                else:
                    # Non-stream
                    return ChatCompletion.model_validate(resp_for_log)

        return request_json

    async def filter_response(self, request_id: str, response: ChatCompletion) -> ChatCompletion:
        response_json = response.model_dump()

        for f in self.response_filters:
            if json_resp := await f.filter(request_id, response_json):
                return response.model_validate(json_resp)

        return response.model_validate(response_json)

    def add_route(self, app: FastAPI, base_url: str):
        @app.post(base_url)
        async def handle_request(request: Request):
            try:
                start_time = time.time()
                request_id = str(uuid4())
                request_json = await request.json()
                request_headers = dict(request.headers.items())

                # Log request
                self.access_logger_queue.put(RequestItem(
                    request_id=request_id,
                    request_json=request_json,
                    request_headers=request_headers
                ))

                # Filter request
                request_json = await self.filter_request(request_id, request_json, request_headers)
                if isinstance(request_json, ChatCompletion) or isinstance(request_json, EventSourceResponse):
                    return request_json

                # Call API
                start_time_api = time.time()
                if self.client.api_key != self._empty_openai_api_key:
                    # Always use server api key if set to client
                    response = await self.client.chat.completions.create(**request_json)
                elif user_auth_header := request_headers.get("authorization"):  # Lower case from client.
                    response = await self.client.chat.completions.create(
                        **request_json, extra_headers={"Authorization": user_auth_header}   # Pascal to server
                    )
                else:
                    # Call API anyway ;)
                    response = await self.client.chat.completions.create(**request_json)

                # Handling response from API
                if request_json.get("stream"):
                    async def process_stream(stream: AsyncContentStream) -> AsyncGenerator[str, None]:
                        # Async content generator
                        async for chunk in stream:
                            self.access_logger_queue.put(StreamChunkItem(
                                request_id=request_id,
                                chunk_json=chunk.model_dump()
                            ))
                            if chunk:
                                yield chunk.model_dump_json()

                        duration = time.time() - start_time
                        duration_api = time.time() - start_time_api

                        # Response log
                        self.access_logger_queue.put(StreamChunkItem(
                            request_id=request_id,
                            duration=duration,
                            duration_api=duration_api,
                            request_json=request_json
                        ))

                    return EventSourceResponse(process_stream(response))

                else:
                    duration_api = time.time() - start_time_api

                    # Filter response
                    response = await self.filter_response(request_id, response)

                    # Response log
                    self.access_logger_queue.put(ResponseItem(
                        request_id=request_id,
                        response_json=response.model_dump(),
                        duration=time.time() - start_time,
                        duration_api=duration_api
                    ))

                    return response

            # Error handlers
            except RequestFilterException as rfex:
                logger.error(f"Request filter error: {rfex}\n{traceback.format_exc()}")
                return JSONResponse(
                    {"error": {"message": rfex.message, "type": "request_filter_error", "param": None, "code": None}},
                    status_code=rfex.status_code
                )

            except ResponseFilterException as rfex:
                logger.error(f"Response filter error: {rfex}\n{traceback.format_exc()}")
                return JSONResponse(
                    {"error": {"message": rfex.message, "type": "response_filter_error", "param": None, "code": None}},
                    status_code=rfex.status_code
                )

            except (APIStatusError, APIResponseValidationError) as status_err:
                logger.error(f"APIStatusError from ChatGPT: {status_err}\n{traceback.format_exc()}")
                return JSONResponse(
                    status_err.response.json(),
                    status_code=status_err.status_code
                )

            except APIError as api_err:
                logger.error(f"APIError from ChatGPT: {status_err}\n{traceback.format_exc()}")
                return JSONResponse(
                    {"error": {"message": api_err.message, "type": api_err.type, "param": api_err.param, "code": api_err.code}},
                    status_code=502
                )

            except OpenAIError as oai_err:
                logger.error(f"OpenAIError: {status_err}\n{traceback.format_exc()}")
                return JSONResponse(
                    {"error": {"message": str(oai_err), "type": "openai_error", "param": None, "code": None}},
                    status_code=502
                )

            except Exception as ex:
                logger.error(f"Error at server: {ex}\n{traceback.format_exc()}")
                return JSONResponse(
                    {"error": {"message": "Proxy error", "type": "proxy_error", "param": None, "code": None}},
                    status_code=500
                )
