__version__ = "0.4.4"

import logging

logger = logging.getLogger("aiproxy")
logger.setLevel(logging.INFO)
log_format = logging.Formatter("[%(levelname)s] %(asctime)s : %(message)s")
streamHandler = logging.StreamHandler()
streamHandler.setFormatter(log_format)
logger.addHandler(streamHandler)


from .proxy import (
    RequestFilterBase,
    ResponseFilterBase,
    RequestFilterException,
    ResponseFilterException
)

from .accesslog import (
    AccessLogBase,
    AccessLog,
    AccessLogWorker
)

from .chatgpt import ChatGPTProxy
