from abc import ABC, abstractmethod
from collections.abc import Iterable
from datetime import datetime
import json
import logging
from time import sleep
import traceback
from typing import Generator, List
from sqlalchemy import Column, Integer, String, Float, DateTime, create_engine
from sqlalchemy.orm import sessionmaker, declarative_base, declared_attr
from .queueclient import DefaultQueueClient, QueueItemBase, QueueClientBase


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
class RequestItemBase(QueueItemBase):
    def __init__(self, request_id: str, request_json: dict, request_headers: dict) -> None:
        self.request_id = request_id
        self.request_json = request_json
        self.request_headers = request_headers

    @abstractmethod
    def to_accesslog(self, accesslog_cls: _AccessLogBase) -> _AccessLogBase:
        ...


class ResponseItemBase(QueueItemBase):
    def __init__(self, request_id: str, response_json: dict, response_headers: dict = None, duration: float = 0, duration_api: float = 0) -> None:
        self.request_id = request_id
        self.response_json = response_json
        self.response_headers = response_headers
        self.duration = duration
        self.duration_api = duration_api

    @abstractmethod
    def to_accesslog(self, accesslog_cls: _AccessLogBase) -> _AccessLogBase:
        ...


class StreamChunkItemBase(QueueItemBase):
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


class ErrorItemBase(QueueItemBase):
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

    def to_dict(self) -> dict:
        return {
            "type": self.__class__.__name__,
            "request_id": self.request_id,
            "exception": str(self.exception),
            "traceback_info": self.traceback_info,
            "response_json": self.response_json,
            "response_headers": self.response_headers
        }


class WorkerShutdownItem(QueueItemBase):
    ...


AccessLogBase = declarative_base(cls=_AccessLogBase)


class AccessLog(AccessLogBase): ...


class AccessLogWorker:
    def __init__(self, *, connection_str: str = "sqlite:///aiproxy.db", db_engine = None, accesslog_cls = AccessLog, queue_client: QueueClientBase = None):
        if db_engine:
            self.db_engine = db_engine
        else:
            self.db_engine = create_engine(connection_str)
        self.accesslog_cls = accesslog_cls
        self.accesslog_cls.metadata.create_all(bind=self.db_engine)
        self.get_session = sessionmaker(autocommit=False, autoflush=False, bind=self.db_engine)
        self.queue_client = queue_client or DefaultQueueClient()
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

    def process_item(self, item: QueueItemBase):
        try:
            # Request
            if isinstance(item, RequestItemBase):
                self.insert_request(item.to_accesslog(self.accesslog_cls))

            # Non-stream response
            elif isinstance(item, ResponseItemBase):
                self.insert_response(item.to_accesslog(self.accesslog_cls))

            # Stream response
            elif isinstance(item, StreamChunkItemBase):
                if not self.chunk_buffer.get(item.request_id):
                    self.chunk_buffer[item.request_id] = []

                if item.duration == 0:
                    self.chunk_buffer[item.request_id].append(item)

                else:
                    # Last chunk data for specific request_id
                    self.insert_response(item.to_accesslog(
                        self.chunk_buffer[item.request_id], self.accesslog_cls
                    ))
                    # Remove chunks from buffer
                    del self.chunk_buffer[item.request_id]

            # Error response
            elif isinstance(item, ErrorItemBase):
                self.insert_response(item.to_accesslog(self.accesslog_cls))

        except Exception as ex:
            logger.error(f"Error at processing queue item: {ex}\n{traceback.format_exc()}")


    def run(self):
        while True:
            try:
                for item in self.queue_client.get():
                    if isinstance(item, WorkerShutdownItem) or item is None:
                        return
                    self.process_item(item)

            except Exception as ex:
                logger.error(f"Error at processing loop: {ex}\n{traceback.format_exc()}")

            sleep(self.queue_client.dequeue_interval)
