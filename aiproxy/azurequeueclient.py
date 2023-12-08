import json
import logging
from typing import Iterator
from azure.storage.queue import QueueClient
from .queueclient import QueueClientBase, QueueItemBase


logger = logging.getLogger(__name__)


class AzureStorageQueueClient(QueueClientBase):
    def __init__(self, connection_str: str, name: str, dequeue_interval: float = 1.0) -> None:
        logger.warning("!! AzureStorageQueueClient is an experimental implementation. This client causes performance issues especially when putting chunks in stream mode !!")
        self.queue_client = QueueClient.from_connection_string(connection_str, name)
        self.itemtypes = {}
        self.dequeue_interval = dequeue_interval

    def add_item_types(self, item_types: list):
        for t in item_types:
            if not self.itemtypes.get(t.__name__):
                self.itemtypes[t.__name__] = t

    def put(self, item: QueueItemBase):
        self.queue_client.send_message(item.to_json())

    def get(self) -> Iterator[QueueItemBase]:
        for m in self.queue_client.receive_messages():
            d = json.loads(m.content)
            cls = self.itemtypes.get(d["type"])
            if cls:
                yield cls.from_dict(d)
                self.queue_client.delete_message(m)
            else:
                logger.warning(f"Unknown queue item type: {d['type']}")
