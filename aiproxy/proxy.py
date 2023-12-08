from abc import ABC, abstractmethod
import logging
from typing import List, Union
from fastapi import FastAPI
from fastapi.responses import Response
from .queueclient import QueueClientBase


logger = logging.getLogger(__name__)


# Classes for filter
class RequestFilterBase(ABC):
    @abstractmethod
    async def filter(self, request_id: str, request_json: dict, request_headers: dict) -> Union[str, None]:
        ...


class ResponseFilterBase(ABC):
    @abstractmethod
    async def filter(self, request_id: str, response_json: dict) -> Union[dict, None]:
        ...


class FilterException(Exception):
    def __init__(self, message: str, status_code: int = 400) -> None:
        self.message = message
        self.status_code = status_code


class RequestFilterException(FilterException): ...


class ResponseFilterException(FilterException): ...


class ProxyBase(ABC):
    def __init__(
        self,
        *,
        request_filters: List[RequestFilterBase] = None,
        response_filters: List[ResponseFilterBase] = None,
        access_logger_queue: QueueClientBase
    ):
        # Filters
        self.request_filters = request_filters or []
        self.response_filters = response_filters or []

        # Access logger queue
        self.access_logger_queue = access_logger_queue

    def add_filter(self, filter: Union[RequestFilterBase, ResponseFilterBase]):
        if isinstance(filter, RequestFilterBase):
            self.request_filters.append(filter)
            logger.info(f"request filter: {filter.__class__.__name__}")
        elif isinstance(filter, ResponseFilterBase):
            self.response_filters.append(filter)
            logger.info(f"response filter: {filter.__class__.__name__}")
        else:
            logger.warning(f"Invalid filter: {filter.__class__.__name__}")

    def add_response_headers(self, response: Response, request_id: str, headers: dict = None):
        response.headers["X-AIProxy-Request-Id"] = request_id
        if headers:
            for k, v in headers.items():
                response.headers[k] = v

    @abstractmethod
    def add_route(self, app: FastAPI, base_url: str):
        ...
