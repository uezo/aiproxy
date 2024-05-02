import argparse
from contextlib import asynccontextmanager
import logging
import os
import threading
import uvicorn
from fastapi import FastAPI
from aiproxy import AccessLogWorker, __version__
from aiproxy.chatgpt import ChatGPTProxy
from aiproxy.anthropic_claude import ClaudeProxy
from aiproxy.gemini import GeminiProxy

logger = logging.getLogger("aiproxy")
logger.addHandler(logging.NullHandler())

# Get API Key from env
env_openai_api_key = os.getenv("OPENAI_API_KEY")
env_anthropic_api_key = os.getenv("ANTHROPIC_API_KEY")
env_google_api_key = os.getenv("GOOGLE_API_KEY")

# Get arguments
parser = argparse.ArgumentParser(description="AIProxy usage")
parser.add_argument("--host", type=str, default="127.0.0.1", required=False, help="hostname or ipaddress")
parser.add_argument("--port", type=int, default="8000", required=False, help="port number")
parser.add_argument("--openai_api_key", type=str, default=env_openai_api_key, required=False, help="OpenAI API Key")
parser.add_argument("--anthropic_api_key", type=str, default=env_anthropic_api_key, required=False, help="Anthropic API Key")
parser.add_argument("--google_api_key", type=str, default=env_google_api_key, required=False, help="Google API Key")
parser.add_argument("--connection_str", type=str, default="sqlite:///aiproxy.db", required=False, help="Database connection string")

args = parser.parse_args()

# Setup access log worker
worker = AccessLogWorker(connection_str=args.connection_str)

# Setup server application
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Start access log worker
    threading.Thread(target=worker.run, daemon=True).start()
    yield
    # Stop access log worker
    worker.queue_client.put(None)

app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)

# ChatGPT Proxy
chatgpt_proxy = ChatGPTProxy(
    api_key=args.openai_api_key,
    access_logger_queue=worker.queue_client
)
chatgpt_proxy.add_route(app)

# Proxy for Anthropic Claude
claude_proxy = ClaudeProxy(
    api_key=args.anthropic_api_key,
    access_logger_queue=worker.queue_client
)
claude_proxy.add_route(app)

# Proxy for Gemini on Google AI Studio (not Vertex AI)
gemini_proxy = GeminiProxy(
    api_key=args.google_api_key,
    access_logger_queue=worker.queue_client
)
gemini_proxy.add_route(app)

logger.info(f"Start AI Proxy version {__version__}")

uvicorn.run(app, host=args.host, port=args.port)
