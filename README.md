# 🦉 AIProxy

🦉 **AIProxy** is a Python library that serves as a reverse proxy for the ChatGPT API. It provides enhanced features like monitoring, logging, and filtering requests and responses. This library is especially useful for developers and administrators who need detailed oversight and control over the interaction with ChatGPT API.

- ✅ Streaming support: Logs every bit of request and response data with token count – never miss a beat! 📊
- ✅ Custom monitoring: Tailor-made for logging any specific info you fancy. Make it your own! 🔍
- ✅ Custom filtering: Flexibly blocks access based on specific info or sends back your own responses. Be in control! 🛡️


## 🚀 Quick start

Install.

```sh
$ pip install aiproxy-python
```

Run.

```sh
$ python -m aiproxy [--host host] [--port port] [--openai_api_key OPENAI_API_KEY]
```

Use.

```python
import openai
client = openai.Client(base_url="http://127.0.0.1:8000/", api_key="YOUR_API_KEY")
resp = client.chat.completions.create(model="gpt-3.5-turbo", messages=[{"role": "user", "content": "hello!"}])
print(resp)
```

Enjoy😊🦉


## 🛠️ Custom entrypoint

To customize **🦉AIProxy**, make your custom entrypoint and configure logger and filters here.

```python
from contextlib import asynccontextmanager
import logging
from fastapi import FastAPI
from aiproxy import ChatGPTProxy, AccessLogWorker
import threading

# Setup logger
logger = logging.getLogger()
logger.setLevel(logging.INFO)
log_format = logging.Formatter("%(asctime)s %(levelname)8s %(message)s")
streamHandler = logging.StreamHandler()
streamHandler.setFormatter(log_format)
logger.addHandler(streamHandler)

# Setup access log worker
# worker = AccessLogWorker()
worker = CustomAccessLogWorker(accesslog_cls=CustomAccessLog)   # 🌟 Instantiate your custom access log worker

# Setup proxy for ChatGPT
proxy = ChatGPTProxy(api_key=YOUR_API_KEY, access_logger_queue=worker.log_queue)
proxy.add_filter(CustomRequestFilter1())     # 🌟 Set your custom filter(s)
proxy.add_filter(CustomRequestFilter2())     # 🌟 Set your custom filter(s)
proxy.add_filter(CustomResponseFilter())     # 🌟 Set your custom filter(s)

# Setup server application
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Start access log worker
    threading.Thread(target=worker.run, daemon=True).start()
    yield
    # Stop access log worker
    worker.log_queue.put(None)

app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
proxy.add_route(app, "/chat/completions")
```

Run with uvicorn with some params if you need.

```sh
$ uvicorn run:app --host 0.0.0.0 --port 8080
```


## 🔍 Monitoring

By default, see `accesslog` table in `aiproxy.db`. If you want to use other RDBMS like PostgreSQL, set SQLAlchemy-formatted connection string as `connection_str` argument when instancing `AccessLogWorker`.

And, you can make custom logger as below:

This is an example to add `user` column to request log. In this case, the customized log are stored into table named `customaccesslog`, the lower case of your custom access log class.

```python
from datetime import datetime
import json
import traceback
from sqlalchemy import Column, String
from aiproxy.accesslog import AccessLogBase, AccessLogWorker

class CustomAccessLog(AccessLogBase):
    user = Column(String)

class CustomAccessLogWorker(AccessLogWorker):
    def insert_request(self, request_id: str, request_json: dict, request_headers: dict):
        db = self.get_session()

        try:
            db.add(self.accesslog_cls(
                request_id=request_id,
                created_at=datetime.utcnow(),
                direction="request",
                user=request_json.get("user"),  # 🌟 new column
                content=request_json["messages"][-1]["content"],
                raw_body=json.dumps(request_json, ensure_ascii=False),
                raw_headers=json.dumps(request_headers),
                model=request_json.get("model")
            ))
            db.commit()
        
        except Exception as ex:
            logger.error(f"Error at insert_request: {ex}\n{traceback.format_exc()}")
        
        finally:
            db.close()

# Enable your custom accesslog
worker = CustomAccessLogWorker(accesslog_cls=CustomAccessLog)
```

NOTE: By default `AccessLog`, OpenAI API Key in the request headers is masked.


## 🛡️ Filtering

The filter receives all requests and responses, allowing you to view and modify their content. For example:

- Detect and protect from misuse: From unknown apps, unauthorized users, etc.
- Trigger custom actions: Doing something triggered by a request.

This is an example for custom request filter that protects the service from banned user. uezo will receive "you can't use this service" as the ChatGPT response.

```python
from typing import Union
from aiproxy import RequestFilterBase

class BannedUserFilter(RequestFilterBase):
    async def filter(self, request_id: str, request_json: dict, request_headers: dict) -> Union[str, None]:
        banned_user = ["uezo"]
        user = request_json.get("user")

        # Return string message to return response right after this filter ends (not to call ChatGPT)
        if not user:
            return "user is required"
        elif user in banned_user:
            return "you can't use this service"

# Enable this filter
proxy.add_filter(BannedUserFilter())
```

Try it.

```python
resp = client.chat.completions.create(model="gpt-3.5-turbo", messages=messages, user="uezo")
print(resp)
```
```sh
ChatCompletion(id='-', choices=[Choice(finish_reason='stop', index=0, message=ChatCompletionMessage(content="you can't use this service", role='assistant', function_call=None, tool_calls=None))], created=0, model='request_filter', object='chat.completion', system_fingerprint=None, usage=CompletionUsage(completion_tokens=0, prompt_tokens=0, total_tokens=0))
```

Another example is the model overwriter that forces the user to use GPT-3.5-Turbo.

```python
class ModelOverwriteFilter(RequestFilterBase):
    async def filter(self, request_id: str, request_json: dict, request_headers: dict) -> Union[str, None]:
        request_model = request_json["model"]
        if not request_model.startswith("gpt-3.5"):
            print(f"Change model from {request_model} -> gpt-3.5-turbo")
            # Overwrite request_json
            request_json["model"] = "gpt-3.5-turbo"
```

Lastly, `ReplayFilter` that retrieves content for a specific request_id from the histories. This is an exceptionally cool feature for developers to test AI-based applications.

```python
class ReplayFilter(RequestFilterBase):
    async def filter(self, request_id: str, request_json: dict, request_headers: dict) -> Union[str, None]:
        # Get request_id to replay from request header
        request_id = request_headers.get("x-aiproxy-replay")
        if not request_id:
            return
        
        db = worker.get_session()
        try:
            # Get and return the response content from histories
            r = db.query(AccessLog).where(AccessLog.request_id == request_id, AccessLog.direction == "response").first()
            if r:
                return r.content
            else:
                return "Record not found for {request_id}"
        
        except Exception as ex:
            logger.error(f"Error at ReplayFilter: {str(ex)}\n{traceback.format_exc()}")
            return "Error at getting response for {request_id}"
        
        finally:
            db.close()
```

NOTE: **Response** filter doesn't work when `stream=True`.


## 🛟 Support

For support, questions, or contributions, please open an issue in the GitHub repository. Please contact me directly when you need an enterprise or business support😊.


## ⚖️ License

**🦉AIProxy** is released under the [Apache License v2](LICENSE).

Made with ❤️ by Uezo, the representive of Unagiken.
