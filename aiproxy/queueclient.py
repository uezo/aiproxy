from abc import ABC, abstractmethod
import json
from queue import Queue
from typing import Iterator


class QueueItemBase(ABC):
    def to_dict(self) -> dict:
        d = self.__dict__
        d["type"] = self.__class__.__name__
        return d

    def to_json(self) -> str:
        return json.dumps(self.to_dict())

    @classmethod
    def from_dict(cls, d: dict):
        _d = d.copy()
        del _d["type"]
        return cls(**_d)

    @classmethod
    def from_json(cls, json_str: str):
        return cls.from_dict(json.loads(json_str))


class QueueClientBase(ABC):
    dequeue_interval = 0.5

    @abstractmethod
    def put(self, item: QueueItemBase):
        ...

    @abstractmethod
    def get(self) -> Iterator[QueueItemBase]:
        ...


class DefaultQueueClient(QueueClientBase):
    def __init__(self) -> None:
        self.queue = Queue()
        self.dequeue_interval = 0.5

    def put(self, item: QueueItemBase):
        self.queue.put(item)

    def get(self) -> Iterator[QueueItemBase]:
        items = []
        while not self.queue.empty():
            items.append(self.queue.get())
        return iter(items)
