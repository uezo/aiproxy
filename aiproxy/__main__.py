import argparse
from contextlib import asynccontextmanager
import logging
import os
from fastapi import FastAPI
from aiproxy import ChatGPTProxy, AccessLogWorker
import threading
import uvicorn

# Get API Key from env
env_openai_api_key = os.getenv("OPENAI_API_KEY")

# Get arguments
parser = argparse.ArgumentParser(description="UnaProxy usage")
parser.add_argument("--host", type=str, default="127.0.0.1", required=False, help="hostname or ipaddress")
parser.add_argument("--port", type=int, default="8000", required=False, help="port number")
parser.add_argument("--openai_api_key", type=str, default=env_openai_api_key, required=False, help="OpenAI API Key")
args = parser.parse_args()

# Setup logger
logger = logging.getLogger()
logger.setLevel(logging.INFO)
log_format = logging.Formatter("%(asctime)s %(levelname)8s %(message)s")
streamHandler = logging.StreamHandler()
streamHandler.setFormatter(log_format)
logger.addHandler(streamHandler)

# Setup access log worker
worker = AccessLogWorker()

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Start access log worker
    threading.Thread(target=worker.run, daemon=True).start()
    yield
    # Stop access log worker
    worker.queue_client.put(None)

# Setup ChatGPTProxy
proxy = ChatGPTProxy(api_key=args.openai_api_key, access_logger_queue=worker.queue_client)

# Setup server application
app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
proxy.add_route(app, "/chat/completions")

uvicorn.run(app, host=args.host, port=args.port)
