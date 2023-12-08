from abc import ABC, abstractmethod
from datetime import datetime
import json
import logging
from queue import Queue
import traceback
from sqlalchemy import Column, Integer, String, Float, DateTime, create_engine
from sqlalchemy.orm import sessionmaker, declarative_base, declared_attr


logger = logging.getLogger(__name__)


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


# Classes for access log queue item
class RequestItemBase(ABC):
    def __init__(self, request_id: str, request_json: dict, request_headers: dict) -> None:
        self.request_id = request_id
        self.request_json = request_json
        self.request_headers = request_headers

    @abstractmethod
    def to_accesslog(self, accesslog_cls: _AccessLogBase) -> _AccessLogBase:
        ...


class ResponseItemBase(ABC):
    def __init__(self, request_id: str, response_json: dict, response_headers: dict = None, duration: float = 0, duration_api: float = 0) -> None:
        self.request_id = request_id
        self.response_json = response_json
        self.response_headers = response_headers
        self.duration = duration
        self.duration_api = duration_api

    @abstractmethod
    def to_accesslog(self, accesslog_cls: _AccessLogBase) -> _AccessLogBase:
        ...


class StreamChunkItemBase(ABC):
    def __init__(self, request_id: str, chunk_json: dict = None, response_headers: dict = None, duration: float = 0, duration_api: float = 0, request_json: dict = None) -> None:
        self.request_id = request_id
        self.chunk_json = chunk_json
        self.response_headers = response_headers
        self.duration = duration
        self.duration_api = duration_api
        self.request_json = request_json

    @abstractmethod
    def to_accesslog(self, chunks: list, accesslog_cls: _AccessLogBase) -> _AccessLogBase:
        ...


class ErrorItemBase(ABC):
    def __init__(self, request_id: str, exception: Exception, traceback_info: str, response_json: dict = None, response_headers: dict = None) -> None:
        self.request_id = request_id
        self.exception = exception
        self.traceback_info = traceback_info
        self.response_json = response_json
        self.response_headers = response_headers

    def to_accesslog(self, accesslog_cls: _AccessLogBase) -> _AccessLogBase:
        if isinstance(self.response_json, dict):
            try:
                raw_body = json.dumps(self.response_json, ensure_ascii=False)
            except Exception:
                raw_body = str(self.response_json)
        else:
            raw_body = str(self.response_json)

        return accesslog_cls(
            request_id=self.request_id,
            created_at=datetime.utcnow(),
            direction="error",
            content=f"{self.exception}\n{self.traceback_info}",
            raw_body=raw_body,
            raw_headers=json.dumps(self.response_headers, ensure_ascii=False) if self.response_headers else None,
            model="error_handler"
        )


AccessLogBase = declarative_base(cls=_AccessLogBase)


class AccessLog(AccessLogBase): ...


class AccessLogWorker:
    def __init__(self, *, connection_str: str = "sqlite:///aiproxy.db", db_engine = None, accesslog_cls = AccessLog, log_queue: Queue = None):
        if db_engine:
            self.db_engine = db_engine
        else:
            self.db_engine = create_engine(connection_str)
        self.accesslog_cls = accesslog_cls
        self.accesslog_cls.metadata.create_all(bind=self.db_engine)
        self.get_session = sessionmaker(autocommit=False, autoflush=False, bind=self.db_engine)
        self.log_queue = log_queue or Queue()
        self.chunk_buffer = {}

    def insert_request(self, accesslog: _AccessLogBase):
        db = self.get_session()

        try:
            db.add(accesslog)
            db.commit()

        except Exception as ex:
            logger.error(f"Error at insert_request: {ex}\n{traceback.format_exc()}")
        
        finally:
            db.close()

    def insert_response(self, accesslog: _AccessLogBase):
        db = self.get_session()

        try:
            db.add(accesslog)
            db.commit()

        except Exception as ex:
            logger.error(f"Error at insert_response: {ex}\n{traceback.format_exc()}")
        
        finally:
            db.close()

    def run(self):
        while True:
            try:
                data = self.log_queue.get()

                # Request
                if isinstance(data, RequestItemBase):
                    self.insert_request(data.to_accesslog(self.accesslog_cls))

                # Non-stream response
                elif isinstance(data, ResponseItemBase):
                    self.insert_response(data.to_accesslog(self.accesslog_cls))

                # Stream response
                elif isinstance(data, StreamChunkItemBase):
                    if not self.chunk_buffer.get(data.request_id):
                        self.chunk_buffer[data.request_id] = []

                    if data.duration == 0:
                        self.chunk_buffer[data.request_id].append(data)

                    else:
                        # Last chunk data for specific request_id
                        self.insert_response(data.to_accesslog(
                            self.chunk_buffer[data.request_id], self.accesslog_cls
                        ))
                        # Remove chunks from buffer
                        del self.chunk_buffer[data.request_id]

                # Error response
                elif isinstance(data, ErrorItemBase):
                    self.insert_response(data.to_accesslog(self.accesslog_cls))

                # Shutdown
                elif data is None:
                    break

                self.log_queue.task_done()

            except Exception as ex:
                logger.error(f"Error at processing queue: {ex}\n{traceback.format_exc()}")
