from datetime import datetime
import json
import logging
from queue import Queue
import traceback
from sqlalchemy import Column, Integer, String, Float, DateTime, create_engine
from sqlalchemy.orm import sessionmaker, declarative_base, declared_attr
import tiktoken


logger = logging.getLogger(__name__)


# Classes for access log queue item
class RequestItem:
    def __init__(self, request_id: str, request_json: dict, request_headers: dict) -> None:
        self.request_id = request_id
        self.request_json = request_json
        self.request_headers = request_headers


class ResponseItem:
    def __init__(self, request_id: str, response_json: dict, duration: float = 0, duration_api: float = 0) -> None:
        self.request_id = request_id
        self.response_json = response_json
        self.duration = duration
        self.duration_api = duration_api


class StreamChunkItem:
    def __init__(self, request_id: str, chunk_json: dict = None, duration: float = 0, duration_api: float = 0, request_json: dict = None) -> None:
        self.request_id = request_id
        self.chunk_json = chunk_json
        self.duration = duration
        self.duration_api = duration_api
        self.request_json = request_json


class _AccessLogBase:
    @declared_attr
    def __tablename__(cls):
        return cls.__name__.lower()

    @declared_attr
    def id(cls):
        return Column(Integer, primary_key=True)

    @declared_attr
    def request_id(cls):
        return Column(String)

    @declared_attr
    def created_at(cls):
        return Column(DateTime)

    @declared_attr
    def direction(cls):
        return Column(String)

    @declared_attr
    def content(cls):
        return Column(String)

    @declared_attr
    def function_call(cls):
        return Column(String)

    @declared_attr
    def tool_calls(cls):
        return Column(String)

    @declared_attr
    def raw_body(cls):
        return Column(String)

    @declared_attr
    def raw_headers(cls):
        return Column(String)

    @declared_attr
    def model(cls):
        return Column(String)

    @declared_attr
    def prompt_tokens(cls):
        return Column(Integer)

    @declared_attr
    def completion_tokens(cls):
        return Column(Integer)

    @declared_attr
    def request_time(cls):
        return Column(Float)

    @declared_attr
    def request_time_api(cls):
        return Column(Float)


AccessLogBase = declarative_base(cls=_AccessLogBase)


class AccessLog(AccessLogBase): ...


class AccessLogWorker:
    def __init__(self, *, connection_str: str = "sqlite:///aiproxy.db", db_engine = None, accesslog_cls = AccessLog, log_queue: Queue = None):
        self.token_encoder = tiktoken.get_encoding("cl100k_base")
        if db_engine:
            self.db_engine = db_engine
        else:
            self.db_engine = create_engine(connection_str)
        self.accesslog_cls = accesslog_cls
        self.accesslog_cls.metadata.create_all(bind=self.db_engine)
        self.get_session = sessionmaker(autocommit=False, autoflush=False, bind=self.db_engine)
        self.log_queue = log_queue or Queue()
        self.chunk_buffer = {}

    def count_token(self, content: str):
        return len(self.token_encoder.encode(content))

    def count_request_token(self, request_json: dict):
        tokens_per_message = 3
        tokens_per_name = 1
        token_count = 0

        # messages
        for m in request_json["messages"]:
            token_count += tokens_per_message
            for k, v in m.items():
                token_count += self.count_token(v)
                if k == "name":
                    token_count += tokens_per_name

        # functions
        if functions := request_json.get("functions"):
            for f in functions:
                token_count += self.count_token(json.dumps(f))

        # function_call
        if function_call := request_json.get("function_call"):
            if isinstance(function_call, dict):
                token_count += self.count_token(json.dumps(function_call))
            else:
                token_count += self.count_token(function_call)

        # tools
        if tools := request_json.get("tools"):
            for t in tools:
                token_count += self.count_token(json.dumps(t))

        if tool_choice := request_json.get("tool_choice"):
            token_count += self.count_token(json.dumps(tool_choice))

        token_count += 3
        return token_count

    def insert_request(self, request_id: str, request_json: dict, request_headers: dict):
        db = self.get_session()
        auth = request_headers.get("authorization")

        try:
            if auth:
                request_headers["authorization"] = auth[:12] + "*****" + auth[-2:]

            db.add(self.accesslog_cls(
                request_id=request_id,
                created_at=datetime.utcnow(),
                direction="request",
                content=request_json["messages"][-1]["content"],
                raw_body=json.dumps(request_json, ensure_ascii=False),
                raw_headers=json.dumps(request_headers),
                model=request_json.get("model")
            ))
            db.commit()
        
        except Exception as ex:
            logger.error(f"Error at insert_request: {ex}\n{traceback.format_exc()}")
        
        finally:
            if auth:
                request_headers["authorization"] = auth

            db.close()

    def insert_response(self, request_id: str, response_json: dict, content: str, function_call: dict, tool_calls: list, model: str, prompt_tokens: int, completion_tokens: int, duration: float, duration_api: float):
        db = self.get_session()

        try:
            db.add(self.accesslog_cls(
                request_id=request_id,
                created_at=datetime.utcnow(),
                direction="response",
                content=content,
                function_call=json.dumps(function_call, ensure_ascii=False) if function_call is not None else None,
                tool_calls=json.dumps(tool_calls, ensure_ascii=False) if tool_calls is not None else None,
                raw_body=json.dumps(response_json),
                model=model,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                request_time=duration,
                request_time_api=duration_api
            ))
            db.commit()

        except Exception as ex:
            logger.error(f"Error at insert_request: {ex}\n{traceback.format_exc()}")
        
        finally:
            db.close()

    def run(self):
        while True:
            try:
                data = self.log_queue.get()

                # Request
                if isinstance(data, RequestItem):
                    self.insert_request(data.request_id, data.request_json, data.request_headers)

                # Non-stream response
                elif isinstance(data, ResponseItem):
                    self.insert_response(
                        request_id=data.request_id,
                        response_json=data.response_json,
                        content=data.response_json["choices"][0]["message"].get("content"),
                        function_call=data.response_json["choices"][0]["message"].get("function_call"),
                        tool_calls=data.response_json["choices"][0]["message"].get("function_call"),
                        model=data.response_json["model"],
                        prompt_tokens=data.response_json["usage"]["prompt_tokens"],
                        completion_tokens=data.response_json["usage"]["completion_tokens"],
                        duration=data.duration,
                        duration_api=data.duration_api
                    )

                # Stream response
                elif isinstance(data, StreamChunkItem):
                    if data.duration == 0:
                        if not self.chunk_buffer.get(data.request_id):
                            self.chunk_buffer[data.request_id] = []
                        self.chunk_buffer[data.request_id].append(data)

                    else:
                        # Last chunk data for specific request_id
                        chunks = []
                        response_content = ""
                        function_call = None
                        tool_calls = None
                        prompt_tokens = 0
                        completion_tokens = 0

                        # Parse info from chunks
                        for chunk in self.chunk_buffer[data.request_id]:
                            chunks.append(chunk.chunk_json)
                            delta = chunk.chunk_json["choices"][0]["delta"]

                            # Make tool_calls
                            if delta.get("tool_calls"):
                                if tool_calls is None:
                                    tool_calls = []
                                if delta["tool_calls"][0]["function"]["name"]:
                                    tool_calls.append({
                                        "name": delta["tool_calls"][0]["function"]["name"],
                                        "arguments": ""
                                    })
                                else:
                                    tool_calls[-1]["arguments"] += delta["tool_calls"][0]["function"]["arguments"]

                            # Make function_call
                            elif delta.get("function_call"):
                                if function_call is None:
                                    function_call = {}
                                if delta["function_call"]["name"]:
                                    function_call["name"] = delta["function_call"]["name"]
                                    function_call["arguments"] = ""
                                elif delta["function_call"]["arguments"]:
                                    function_call["arguments"] += delta["function_call"]["arguments"]

                            # Text content
                            else:
                                response_content += delta["content"] or ""
                        
                        # Count tokens
                        prompt_tokens = self.count_request_token(data.request_json)

                        if tool_calls:
                            completion_tokens = self.count_token(json.dumps(tool_calls, ensure_ascii=False))
                        elif function_call:
                            completion_tokens = self.count_token(json.dumps(function_call, ensure_ascii=False))
                        else:
                            completion_tokens = self.count_token(json.dumps(response_content, ensure_ascii=False))

                        # Persist
                        self.insert_response(
                            request_id=data.request_id,
                            response_json=chunks,
                            content=response_content,
                            function_call=function_call,
                            tool_calls=tool_calls,
                            model=chunks[0]["model"],
                            prompt_tokens=prompt_tokens,
                            completion_tokens=completion_tokens,
                            duration=data.duration,
                            duration_api=data.duration_api
                        )

                        # Remove chunks from buffer
                        del self.chunk_buffer[data.request_id]

                # Shutdown
                elif data is None:
                    break

                self.log_queue.task_done()

            except Exception as ex:
                logger.error(f"Error at processing queue: {ex}\n{traceback.format_exc()}")
