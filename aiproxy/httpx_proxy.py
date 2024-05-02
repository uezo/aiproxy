from datetime import datetime
import json
import logging
import time
import traceback
from typing import List, Union
from uuid import uuid4
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response
from sse_starlette.sse import EventSourceResponse
import httpx
from aiproxy.proxy import ProxyBase, RequestFilterBase, ResponseFilterBase, RequestFilterException, ResponseFilterException
from aiproxy.queueclient import QueueClientBase
from aiproxy.accesslog import _AccessLogBase, RequestItemBase, ResponseItemBase, StreamChunkItemBase, ErrorItemBase


logger = logging.getLogger(__name__)


class SessionInfo:
    def __init__(self):
        # Request
        self.request_id = str(uuid4())
        self.request_json = None
        self.request_headers = None
        self.request_url = None
        self.stream = False

        # Response
        self.response_json = None
        self.response_body = None
        self.response_headers = None
        self.duration = 0.0
        self.duration_api = 0.0
        self.status_code = 0

        self.extra_info = {}

        # Status
        self.start_time = time.time()
        self.start_time_api = self.start_time


class SessionRequestItemBase(RequestItemBase):
    def __init__(self, request_id: str, request_json: dict, request_headers: dict):
        super().__init__(request_id, request_json, request_headers)
        self.session: SessionInfo = None

    @classmethod
    def from_session(cls, session: SessionInfo):
        item = cls(session.request_id, session.request_json, session.request_headers)
        item.session = session
        return item


class SessionResponseItemBase(ResponseItemBase):
    def __init__(self, request_id: str, response_json: dict, response_headers: dict = None, duration: float = 0, duration_api: float = 0, status_code: int = 0) -> None:
        super().__init__(request_id, response_json, response_headers, duration, duration_api, status_code)
        self.session: SessionInfo = None

    @classmethod
    def from_session(cls, session: SessionInfo):
        item = cls(session.request_id, session.response_json, session.response_headers, session.duration, session.duration_api, session.status_code)
        item.session = session
        return item


class SessionStreamChunkItemBase(StreamChunkItemBase):
    def __init__(self, request_id: str, response_content: str = None, response_headers: dict = None, duration: float = 0, duration_api: float = 0, status_code: int = 0) -> None:
        super().__init__(request_id, response_content, response_headers, duration, duration_api, status_code)
        self.session: SessionInfo = None

    @classmethod
    def from_session(cls, session: SessionInfo):
        item = cls(session.request_id, session.response_body, session.response_headers, session.duration, session.duration_api, session.status_code)
        item.session = session
        return item


class SessionErrorItemBase(ErrorItemBase):
    def __init__(self, request_id: str, exception: Exception, traceback_info: str, response_json: dict = None, response_headers: dict = None, status_code: int = 0) -> None:
        super().__init__(request_id, exception, traceback_info, response_json, response_headers, status_code)
        self.session: SessionInfo = None

    @classmethod
    def from_session(cls, session: SessionInfo, exception: Exception, traceback_info: str):
        item = cls(session.request_id, exception, traceback_info, session.response_json, session.response_headers, session.status_code)
        item.session = session
        return item


class SessionRequestItemEssential(SessionRequestItemBase):
    def to_accesslog(self, accesslog_cls: _AccessLogBase) -> _AccessLogBase:
        return accesslog_cls(
            request_id=self.request_id,
            created_at=datetime.utcnow(),
            direction="request",
            content="",
            raw_body=self.request_json.decode("utf-8"),
            raw_headers=json.dumps(self.session.request_headers, ensure_ascii=False),
            model=self.session.extra_info["resource_path"]
        )


class SessionResponseItemEssential(SessionResponseItemBase):
    def to_accesslog(self, accesslog_cls: _AccessLogBase) -> _AccessLogBase:
        return accesslog_cls(
            request_id=self.request_id,
            created_at=datetime.utcnow(),
            direction="response",
            status_code=self.status_code,
            content="",
            function_call=None,
            tool_calls=None,
            raw_body=self.response_json.decode("utf-8"),
            raw_headers=json.dumps(self.response_headers, ensure_ascii=False),
            model=self.session.extra_info["resource_path"],
            prompt_tokens=0,
            completion_tokens=0,
            request_time=self.duration,
            request_time_api=self.duration_api
        )


# HTTPX-based reverse proxy application
class HTTPXProxy(ProxyBase):
    def __init__(
        self,
        *,
        timeout=60.0,
        request_filters: List[RequestFilterBase] = None,
        response_filters: List[ResponseFilterBase] = None,
        request_item_class: type = None,
        response_item_class: type = None,
        stream_response_item_class: type = None,
        error_item_class: type = None,
        access_logger_queue: QueueClientBase
    ):
        super().__init__(
            request_filters=request_filters,
            response_filters=response_filters,
            access_logger_queue=access_logger_queue
        )

        self.timeout = timeout

        # Log items
        self.request_item_class: SessionRequestItemBase = request_item_class
        self.response_item_class: SessionResponseItemBase = response_item_class
        self.stream_response_item_class: SessionStreamChunkItemBase = stream_response_item_class
        self.error_item_class: SessionErrorItemBase = error_item_class

        self.api_base_url = "empty_url"
        self.api_chat_resource_path = "/path/to/chat"
        self.api_service_id = "empty_id"
        self.api_chat_method = "POST"

    # Filter
    def text_to_response_json(self, text: str) -> dict:
        raise NotImplementedError("'text_to_response_json' must be implemented to use request filter")

    def text_to_response_chunks(self, text: str) -> list[dict]:
        raise NotImplementedError("'text_to_response_chunks' must be implemented to use request filter")

    async def filter_request(self, session: SessionInfo) -> Union[None, JSONResponse, EventSourceResponse]:
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

                # Return stream/non-stream response
                if session.stream:
                    async def filter_response_stream(deltas: list[dict]):
                        async for d in deltas:
                            yield d

                    sse_resp = EventSourceResponse(
                        filter_response_stream(self.text_to_response_chunks(completion_content))
                    )
                    self.add_response_headers(sse_resp, session.request_id)
                    return sse_resp

                else:
                    return json_response

        return None

    async def filter_response(self, request_id: str, response_json: dict) -> dict:
        for f in self.response_filters:
            if immediately_return_json_resp := await f.filter(request_id, response_json):
                return immediately_return_json_resp

        return response_json

    # Parser and preparation for request and response
    async def parse_request(self, fastapi_request: Request, session: SessionInfo):
        session.request_json = await fastapi_request.json()
        session.request_headers = dict(fastapi_request.headers.items())
        session.request_url = str(fastapi_request.url)

    async def parse_response(self, httpx_response: httpx.Response, session: SessionInfo):
        session.response_headers = dict(httpx_response.headers)
        session.status_code = httpx_response.status_code
        if not session.stream:
            session.response_json = httpx_response.json()
            session.duration_api = time.time() - session.start_time_api

    def prepare_httpx_request_headers(self, session: SessionInfo):
        if session.request_headers.get("host"):
            del session.request_headers["host"]
        if session.request_headers.get("content-length"):
            del session.request_headers["content-length"]

    def prepare_httpx_response_headers(self, session: SessionInfo):
        if session.response_headers.get("date"):
            del session.response_headers["date"]
        if session.response_headers.get("content-length"):
            del session.response_headers["content-length"]
        if session.response_headers.get("content-encoding"):
            del session.response_headers["content-encoding"]
        if session.response_headers.get("cache-control"):
            del session.response_headers["cache-control"]

        session.response_headers["X-AIProxy-Request-Id"] = session.request_id

    def make_url(self, session: SessionInfo):
        return self.api_base_url + self.api_chat_resource_path

    # Make responses
    async def make_json_response(self, async_client: httpx.AsyncClient, session: SessionInfo):
        try:
            # Filter response
            original_response_json = session.response_json.copy()
            filtered_response_json = await self.filter_response(session.request_id, session.response_json)
            session.response_json = original_response_json if original_response_json == filtered_response_json else filtered_response_json

            # Make JSON response
            json_response = JSONResponse(
                session.response_json,
                session.status_code,
                session.response_headers
            )

            # Response log
            session.duration = time.time() - session.start_time
            self.access_logger_queue.put(
                self.response_item_class.from_session(session=session)
            )

            return json_response

        finally:
            await async_client.aclose()

    def make_stream_response(self, async_client: httpx.AsyncClient, stream_response: httpx.Response, session: SessionInfo):
        async def process_stream():
            session.response_body = ""
            try:
                # Yield chunked responses
                chunk_buffer = ""
                async for b in stream_response.aiter_raw():
                    chunk = b.decode("utf-8")
                    session.response_body += chunk
                    if chunk.endswith("\n\n"):
                        chunk = (chunk_buffer + chunk).strip().split("\n\n")
                        chunk_buffer = ""
                    else:
                        chunk_buffer += chunk
                        continue

                    for ev in chunk:
                        event_type = ""
                        datas = []
                        for line in ev.split("\n"):
                            if line.startswith("event:"):
                                event_type = line[6:].strip()
                            elif line.startswith("data:"):
                                datas.append(line[5:].strip())

                        if event_type:
                            yield {"event": event_type, "data": "\n".join(datas)}
                        else:
                            yield {"data": "\n".join(datas)}
            
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

        return EventSourceResponse(
            process_stream(),
            status_code=session.status_code,
            headers=session.response_headers
        )

    def make_error_response(self, session: SessionInfo, status_code: int, ex: Exception, error_type: str, **kwargs) -> JSONResponse:
        # Make error response
        resp_json = {"error": {"message": str(ex), "type": error_type}}
        json_response = JSONResponse(resp_json, status_code=status_code)
        self.add_response_headers(json_response, session.request_id)

        # Error log
        self.access_logger_queue.put(self.error_item_class.from_session(
            session=session,
            exception=ex,
            traceback_info=traceback.format_exc()
        ))

        return json_response

    # Request handler
    def add_route(self, app: FastAPI):
        @app.api_route(f"/{self.api_service_id}{self.api_chat_resource_path}", methods=[self.api_chat_method])
        async def handle_chat_request(request: Request):
            session = SessionInfo()

            try:
                await self.parse_request(request, session)
                # Log request
                self.access_logger_queue.put(self.request_item_class.from_session(session))

                # Filter request
                if filtered_response := await self.filter_request(session):
                    return filtered_response

                session.start_time_api = time.time()

                # Call API and handling response from API
                async_client = httpx.AsyncClient(timeout=self.timeout)
                try:
                    self.prepare_httpx_request_headers(session)
                    httpx_request = httpx.Request(method="POST", url=self.make_url(session), headers=session.request_headers, json=session.request_json)
                    httpx_response = await async_client.send(request=httpx_request, stream=session.stream)
                    await self.parse_response(httpx_response, session)
                    self.prepare_httpx_response_headers(session)
                    httpx_response.raise_for_status()
                except Exception as ex:
                    await async_client.aclose()
                    raise ex

                if session.stream:
                    return self.make_stream_response(
                        async_client,
                        httpx_response,
                        session
                    )
                else:
                    return await self.make_json_response(
                        async_client,
                        session
                    )

            # Error handlers
            except RequestFilterException as rfex:
                logger.error(f"Request filter error: {rfex}\n{traceback.format_exc()}")
                return self.make_error_response(session, rfex.status_code, rfex, "request_filter_error")

            except ResponseFilterException as rfex:
                logger.error(f"Response filter error: {rfex}\n{traceback.format_exc()}")
                return self.make_error_response(session, rfex.status_code, rfex, "response_filter_error")

            except httpx.HTTPStatusError as htex:
                logger.error(f"Error at server: {htex}\n{traceback.format_exc()}")

                # Error log
                try:
                    resp_json = htex.response.json()
                except:
                    try:
                        content = await htex.response.aread()
                        if isinstance(content, bytes):
                            content = content.decode("utf-8")
                        else:
                            content = str(content)
                        resp_json = json.loads(content)
                    except:
                        resp_json = {"type": "error", "error": {"type": "http_error", "message": "Failed in parsing error response."}}

                self.prepare_httpx_response_headers(session)

                self.access_logger_queue.put(self.error_item_class.from_session(
                    session=session,
                    exception=htex,
                    traceback_info=traceback.format_exc()
                ))

                return JSONResponse(
                    resp_json,
                    status_code=htex.response.status_code,
                    headers=session.response_headers
                )

            except Exception as ex:
                logger.error(f"Error at server: {ex}\n{traceback.format_exc()}")
                return self.make_error_response(session, 502, ex, "proxy_error")

        @app.api_route(f"/{self.api_service_id}/{{resource_path:path}}", methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "HEAD", "PATCH"])
        async def handle_request(request: Request, resource_path: str):
            session = SessionInfo()

            try:
                # Parse request
                session.request_json = await request.body()
                session.request_headers = dict(request.headers.items())
                session.request_url = str(request.url)
                session.extra_info["resource_path"] = "/" + resource_path

                # Log request
                self.access_logger_queue.put(SessionRequestItemEssential.from_session(session))


                # Call API and handling response from API
                async_client = httpx.AsyncClient(timeout=self.timeout)
                try:
                    self.prepare_httpx_request_headers(session)
                    httpx_request = httpx.Request(method=request.method, url=self.api_base_url + "/" + resource_path, headers=session.request_headers, data=session.request_json)
                    httpx_response = await async_client.send(request=httpx_request)

                    # Parse response
                    session.response_headers = dict(httpx_response.headers)
                    session.status_code = httpx_response.status_code
                    session.response_json = httpx_response.content
                    session.duration_api = time.time() - session.start_time_api

                    self.prepare_httpx_response_headers(session)
                    httpx_response.raise_for_status()

                    # Make response
                    response = Response(
                        session.response_json,
                        session.status_code,
                        session.response_headers
                    )

                    # Response log
                    session.duration = time.time() - session.start_time
                    self.access_logger_queue.put(
                        SessionResponseItemEssential.from_session(session=session)
                    )

                    return response

                except Exception as ex:
                    await async_client.aclose()
                    raise ex

            # Error handlers
            except RequestFilterException as rfex:
                logger.error(f"Request filter error: {rfex}\n{traceback.format_exc()}")
                return self.make_error_response(session, rfex.status_code, rfex, "request_filter_error")

            except ResponseFilterException as rfex:
                logger.error(f"Response filter error: {rfex}\n{traceback.format_exc()}")
                return self.make_error_response(session, rfex.status_code, rfex, "response_filter_error")

            except httpx.HTTPStatusError as htex:
                logger.error(f"Error at server: {htex}\n{traceback.format_exc()}")

                # Error log
                try:
                    resp_json = htex.response.json()
                except:
                    try:
                        content = await htex.response.aread()
                        if isinstance(content, bytes):
                            content = content.decode("utf-8")
                        else:
                            content = str(content)
                        resp_json = json.loads(content)
                    except:
                        resp_json = {"type": "error", "error": {"type": "http_error", "message": "Failed in parsing error response."}}

                self.prepare_httpx_response_headers(session)

                self.access_logger_queue.put(self.error_item_class.from_session(
                    session=session,
                    exception=htex,
                    traceback_info=traceback.format_exc()
                ))

                return JSONResponse(
                    resp_json,
                    status_code=htex.response.status_code,
                    headers=session.response_headers
                )

            except Exception as ex:
                logger.error(f"Error at server: {ex}\n{traceback.format_exc()}")
                return self.make_error_response(session, 502, ex, "proxy_error")
