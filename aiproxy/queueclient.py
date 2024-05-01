from abc import ABC, abstractmethod
import json
from queue import Queue
from typing import Iterator


class QueueItemBase(ABC):
    ...


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
