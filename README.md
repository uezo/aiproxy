# 🦉 AIProxy

🦉 **AIProxy** is a Python library that serves as a reverse proxy for the ChatGPT API. It provides enhanced features like monitoring, logging, and filtering requests and responses. This library is especially useful for developers and administrators who need detailed oversight and control over the interaction with ChatGPT API.

- ✅ Streaming support: Logs every bit of request and response data with token count – never miss a beat! 💓
- ✅ Custom monitoring: Tailor-made for logging any specific info you fancy. Make it your own! 🔍
- ✅ Custom filtering: Flexibly blocks access based on specific info or sends back your own responses. Be in control! 🛡️
- ✅ Multiple AI Services: Supports ChatGPT (OpenAI and Azure OpenAI Service), Claude2 on AWS Bedrock, and is extensible by yourself! 🤖
- ✅ Express dashboard: We provide template for [Apache Superset](https://superset.apache.org) that's ready to use right out of the box – get insights quickly and efficiently!  📊


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
proxy = ChatGPTProxy(api_key=YOUR_API_KEY, access_logger_queue=worker.queue_client)
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
    worker.queue_client.put(None)

app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
proxy.add_route(app, "/chat/completions")
```

Run with uvicorn with some params if you need.

```sh
$ uvicorn run:app --host 0.0.0.0 --port 8080
```

To use Azure OpenAI, instantiate `ChatGPTProxy` with `AsyncAzureOpenAI`.

```python
azure_client = openai.AsyncAzureOpenAI(
    api_key = "YOUR_API_KEY",
    api_version = "2023-10-01-preview",
    azure_endpoint = "https://{DEPLOYMENT_ID}.openai.azure.com/"
)

proxy = ChatGPTProxy(async_client=azure_client, access_logger_queue=worker.queue_client)
```

To use Claude2 on AWS Bedrock, instantiate `Claude2Proxy`.

```python
from aiproxy.claude2 import Claude2Proxy
claude_proxy = Claude2Proxy(
    aws_access_key_id="YOUR_AWS_ACCESS_KEY_ID",
    aws_secret_access_key="YOUR_AWS_SECRET_ACCESS_KEY",
    region_name="your-bedrock-region",
    access_logger_queue=worker.queue_client
)
claude_proxy.add_route(app, "/model/anthropic.claude-v2")
```

Client side. We test API with boto3.

```python
import boto3
import json
# Make client with dummy creds
session = boto3.Session(aws_access_key_id="dummy", aws_secret_access_key="dummy",)
bedrock = session.client(service_name="bedrock-runtime", region_name="private", endpoint_url="http://127.0.0.1:8000")
# Call API
response = bedrock.invoke_model(
    modelId="anthropic.claude-v2",
    body=json.dumps({"prompt": "Human: うなぎとあなごの違いは？\nAssistant: ", "max_tokens_to_sample": 100})
)
# Show response
print(json.loads(response["body"].read()))
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

`request_id` is included in HTTP response headers as `x-aiproxy-request-id`.

NOTE: **Response** filter doesn't work when `stream=True`.


## 📊 Dashboard

We provide an Apache Superset template as our express dashboard. Please follow the steps below to set up.

![🦉AIProxy dashboard powered by Apache Superset](https://uezo.blob.core.windows.net/github/aiproxy/dashboard.png)

Install Superset.

```sh
$ pip install apache-superset
```

Get dashboard.zip from release page and extract it to the same directory as aiproxy.db.

https://github.com/uezo/aiproxy/releases/tag/v0.3.0


Set required environment variables.

```sh
$ export SUPERSET_CONFIG_PATH=$(pwd)/dashboard/superset_config.py
$ export FLASK_APP=superset
```

Make database.

```sh
$ superset db upgrade
```

Create admin user. Change username and password as you like.

```sh
$ superset fab create-admin --username admin --firstname AIProxyAdmin --lastname AIProxyAdmin --email admin@localhost --password admin
```

Initialize Superset.

```sh
$ superset init
```

Import 🦉AIProxy dashboard template. Execute this command in the same directory as aiproxy.db. If you execute from a different location, open the Database connections page in the Superset after completing these steps and modify the database connection string to the absolute path.

```sh
$ superset import-directory dashboard/resources
```

Start Superset.

```sh
$ superset run -p 8088
```

Open and customize the dashboard to your liking, including the metrics you want to monitor and their conditions.👍

http://localhost:8088

📕 Superset official docs: https://superset.apache.org/docs/intro


## 💡 Tips

- CORS: Configure CORS if you call API from web apps. https://fastapi.tiangolo.com/tutorial/cors/
- Retry: 🦉AIProxy does not retry when API returns 5xx error because the OpenAI official client library retries. Sett `max_retries` to `ChatGPTProxy` if you call 🦉AIProxy from general HTTP client library.

```python
proxy = ChatGPTProxy(
    api_key=args.openai_api_key,
    access_logger_queue=worker.queue_client,
    max_retries=2   # OpenAI's default is 2
)
```

- Database: You can use other RDBMS that is supported by SQLAlchemy. You can use them by just changing connection string. (and, install client libraries required.)

Example for PostgreSQL🐘

```sh
$ pip install psycopg2-binary
```

```python
# connection_str = "sqlite:///aiproxy.db"
connection_str = f"postgresql://{USER}:{PASSWORD}@{HOST}:{PORT}/{DATABASE}"

worker = AccessLogWorker(connection_str=connection_str)
```


## 🛟 Support

For support, questions, or contributions, please open an issue in the GitHub repository. Please contact me directly when you need an enterprise or business support😊.


## ⚖️ License

**🦉AIProxy** is released under the [Apache License v2](LICENSE).

Made with ❤️ by Uezo, the representive of Unagiken.
