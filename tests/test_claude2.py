import pytest
from datetime import datetime
import json
import os
from time import sleep
from typing import Union
from uuid import uuid4
import boto3
from botocore.exceptions import ClientError
from aiproxy import (
    AccessLog,
    RequestFilterBase,
    ResponseFilterBase
)
from aiproxy.accesslog import AccessLogWorker
from aiproxy.claude2 import Claude2Proxy, Claude2RequestItem, Claude2ResponseItem, Claude2StreamResponseItem

sqlite_conn_str = "sqlite:///aiproxy_test.db"
postgresql_conn_str = f"postgresql://{os.getenv('PSQL_USER')}:{os.getenv('PSQL_PASSWORD')}@{os.getenv('PSQL_HOST')}:{os.getenv('PSQL_PORT')}/{os.getenv('PSQL_DATABASE')}"

DB_CONNECTION_STR = sqlite_conn_str

# Filters for test
class OverwriteFilter(RequestFilterBase):
    async def filter(self, request_id: str, request_json: dict, request_headers: dict) -> Union[str, None]:
        request_model = request_json["model"]
        if not request_model.startswith("anthropic.claude-v2"):
            # Overwrite request_json
            request_json["model"] = "anthropic.claude-v100-twinturbo"


class ValueReturnFilter(RequestFilterBase):
    async def filter(self, request_id: str, request_json: dict, request_headers: dict) -> Union[str, None]:
        banned_user = ["uezo"]
        user = request_json.get("user")

        # Return string message to return response right after this filter ends (not to call ChatGPT)
        if not user:
            return "user is required"
        elif user in banned_user:
            return "you can't use this service"


class OverwriteResponseFilter(ResponseFilterBase):
    async def filter(self, request_id: str, response_json: dict) -> Union[dict, None]:
        response_json["completion"] = "Overwrite in filter"
        return response_json


# Test data
@pytest.fixture
def prompt_text() -> str:
    return "うなぎとあなごの違いは？"

@pytest.fixture
def prompt(prompt_text) -> list:
    return f'''Human: {prompt_text}\nAssistant: '''

@pytest.fixture
def request_json(prompt):
    return {
        "prompt": prompt,
        "max_tokens_to_sample": 200,
    }

@pytest.fixture
def request_headers():
    return {"user-agent": "Boto3/1.33.6 md/Botocore#1.33.6 ua/2.0 os/macos#22.6.0 md/arch#x86_64 lang/python#3.11.6 md/pyimpl#CPython cfg/retry-mode#legacy Botocore/1.33.6"}

@pytest.fixture
def response_json():
    return {'completion': ' うなぎとあなごの主な違いは以下の通りです。\n\n- 種類が違う。うなぎはウナギ科の魚類、あなごはアナゴ科の魚類である。\n\n- 生息場所が違う。うなぎは淡水や汽水域に生息するのに対し、あなごは海水域に生息する。 \n\n- 成長過程が違う。うなぎは淡水でシラスウナギやニホンウナギと呼ばれる稚魚期を過ごした後、海に下って成長する。一方、あな', 'stop_reason': 'max_tokens', 'stop': None}

@pytest.fixture
def response_headers_json():
    return {'date': 'Sun, 10 Dec 2023 03:37:16 GMT', 'content-type': 'application/json', 'content-length': '535', 'connection': 'keep-alive', 'x-amzn-requestid': '1df60217-446e-4e2c-bc7b-0e41029eff63', 'x-amzn-bedrock-invocation-latency': '9170', 'x-amzn-bedrock-output-token-count': '200', 'x-amzn-bedrock-input-token-count': '25'}

@pytest.fixture
def response_headers_stream_json():
    return {'date': 'Sun, 10 Dec 2023 03:38:46 GMT', 'content-type': 'application/vnd.amazon.eventstream', 'transfer-encoding': 'chunked', 'connection': 'keep-alive', 'x-amzn-requestid': 'bc5d2ef8-094e-4262-8368-52fbb4ac5dfc', 'x-amzn-bedrock-content-type': 'application/json'}

@pytest.fixture
def chunks_json():
    return [
        {'completion': ' ', 'stop_reason': None, 'stop': None},
        {'completion': 'うなぎとあなごの主な違いは', 'stop_reason': None, 'stop': None},
        {'completion': '以下の通りです。\n\n- 種類が異', 'stop_reason': None, 'stop': None},
        {'completion': 'なる\n    - うなぎはウナ', 'stop_reason': None, 'stop': None},
        {'completion': 'ギ目ウナギ科の魚', 'stop_reason': None, 'stop': None},
        {'completion': '\n    - あなごはアナゴ目アナ', 'stop_reason': None, 'stop': None},
        {'completion': 'ゴ科の魚', 'stop_reason': None, 'stop': None},
        {'completion': '\n- 生息場所が異なる', 'stop_reason': None, 'stop': None},
        {'completion': '\n    - うなぎは川や湖、湿地など', 'stop_reason': None, 'stop': None},
        {'completion': 'の淡水に生息\n    - あなご', 'stop_reason': None, 'stop': None},
        {'completion': 'は海に生息\n- 体型が異なる\n   ', 'stop_reason': None, 'stop': None},
        {'completion': ' - うなぎは円筒形で体が', 'stop_reason': None, 'stop': None},
        {'completion': '細長い\n    - あなご', 'stop_reason': None, 'stop': None},
        {'completion': 'は側扁した体', 'stop_reason': None, 'stop': None},
        {'completion': '型をしている\n- 食', 'stop_reason': None, 'stop': None},
        {'completion': 'べ方が異なる\n    - うな', 'stop_reason': 'max_tokens', 'stop': None, 'amazon-bedrock-invocationMetrics': {'inputTokenCount': 25, 'outputTokenCount': 200, 'invocationLatency': 6858, 'firstByteLatency': 1824}}
    ]


def test_request_item_to_accesslog(prompt_text, request_json, request_headers):
    request_id = str(uuid4())
    item = Claude2RequestItem(request_id, request_json, request_headers)

    accesslog = item.to_accesslog(AccessLog)

    assert accesslog.request_id == request_id
    assert isinstance(accesslog.created_at, datetime)
    assert accesslog.direction == "request"
    assert accesslog.content == prompt_text
    assert accesslog.function_call is None
    assert accesslog.tool_calls is None
    assert accesslog.raw_body == json.dumps(request_json, ensure_ascii=False)
    assert accesslog.raw_headers == json.dumps(request_headers, ensure_ascii=False)
    assert accesslog.model == "anthropic.claude-v2"


def test_request_item_to_from_json(prompt, request_json, request_headers):
    request_id = str(uuid4())
    item = Claude2RequestItem(request_id, request_json, request_headers)

    item_json = item.to_json()
    item_dict = json.loads(item_json)

    assert item_dict["type"] == Claude2RequestItem.__name__
    assert item_dict["request_id"] == request_id
    assert item_dict["request_json"] == request_json
    assert item_dict["request_headers"] == request_headers

    item_restore = Claude2RequestItem.from_json(item_json)

    assert item_restore.request_id == request_id
    assert item_restore.request_json == request_json
    assert item_restore.request_headers == request_headers    


def test_response_item_to_accesslog(response_json, response_headers_json):
    request_id = str(uuid4())
    item = Claude2ResponseItem(request_id, response_json, response_headers_json, 1.0, 2.0, 200)

    accesslog = item.to_accesslog(AccessLog)

    assert accesslog.request_id == request_id
    assert isinstance(accesslog.created_at, datetime)
    assert accesslog.direction == "response"
    assert accesslog.status_code == 200
    assert accesslog.content == response_json["completion"]
    assert accesslog.function_call is None
    assert accesslog.tool_calls is None
    assert accesslog.raw_body == json.dumps(response_json, ensure_ascii=False)
    assert accesslog.raw_headers == json.dumps(response_headers_json, ensure_ascii=False)
    assert accesslog.model == "anthropic.claude-v2"
    assert accesslog.prompt_tokens == response_headers_json["x-amzn-bedrock-input-token-count"]
    assert accesslog.completion_tokens == response_headers_json["x-amzn-bedrock-output-token-count"]
    assert accesslog.request_time == item.duration
    assert accesslog.request_time_api == item.duration_api


def test_stream_response_item_to_accesslog(chunks_json, response_headers_stream_json, request_json):
    request_id = str(uuid4())
    chunks = []
    content = ""
    for c in chunks_json:
        chunks.append(Claude2StreamResponseItem(request_id, c))
        content += c.get("completion", "")

    last_chunk = Claude2StreamResponseItem(request_id, response_headers=response_headers_stream_json, duration=1.0, duration_api=2.0, request_json=request_json, status_code=200)
    accesslog = last_chunk.to_accesslog(chunks, AccessLog)

    assert accesslog.request_id == request_id
    assert isinstance(accesslog.created_at, datetime)
    assert accesslog.direction == "response"
    assert accesslog.status_code == 200
    assert accesslog.content == content
    assert accesslog.function_call is None
    assert accesslog.tool_calls is None
    assert accesslog.raw_body == json.dumps(chunks_json, ensure_ascii=False)
    assert accesslog.raw_headers == json.dumps(response_headers_stream_json, ensure_ascii=False)
    assert accesslog.model == "anthropic.claude-v2"
    assert accesslog.prompt_tokens > 0
    assert accesslog.completion_tokens > 0
    assert accesslog.request_time == last_chunk.duration
    assert accesslog.request_time_api == last_chunk.duration_api


@pytest.fixture
def worker():
    return AccessLogWorker(connection_str=DB_CONNECTION_STR)

@pytest.fixture
def claude2_proxy(worker):
    return Claude2Proxy(access_logger_queue=worker.queue_client)

@pytest.fixture
def db(worker):
    return worker.get_session()

@pytest.fixture
def boto3_client():
    session = boto3.Session(
        aws_access_key_id="aws_access_key_id",
        aws_secret_access_key="aws_secret_access_key",
    )

    return session.client(
        service_name="bedrock-runtime", 
        region_name="private",
        endpoint_url="http://127.0.0.1:8000",
    )

@pytest.mark.asyncio
async def test_request_filter_overwrite(claude2_proxy, request_json, request_headers):
    request_id = str(uuid4())
    request_json["model"] = "anthropic.claude-v3"

    claude2_proxy.add_filter(OverwriteFilter())
    await claude2_proxy.filter_request(request_id, request_json, request_headers, False)

    assert request_json["model"] == "anthropic.claude-v100-twinturbo"


@pytest.mark.asyncio
async def test_request_filter_valuereturn(claude2_proxy, request_json, request_headers):
    request_id = str(uuid4())

    claude2_proxy.add_filter(ValueReturnFilter())

    ret = await claude2_proxy.filter_request(request_id, request_json, request_headers, False)
    assert json.loads(ret.body.decode())["completion"] == "user is required"

    request_json["user"] = "uezo"
    ret = await claude2_proxy.filter_request(request_id, request_json, request_headers, False)
    assert json.loads(ret.body.decode())["completion"] == "you can't use this service"

    request_json["user"] = "unagi"
    ret = await claude2_proxy.filter_request(request_id, request_json, request_headers, False)
    assert ret == request_json


@pytest.mark.asyncio
async def test_request_filter_valuereturn_stream(claude2_proxy, request_json, request_headers):
    request_id = str(uuid4())

    claude2_proxy.add_filter(ValueReturnFilter())

    ret = await claude2_proxy.filter_request(request_id, request_json, request_headers, False)
    assert json.loads(ret.body.decode())["completion"] == "user is required"

    request_json["user"] = "uezo"
    ret = await claude2_proxy.filter_request(request_id, request_json, request_headers, False)
    assert json.loads(ret.body.decode())["completion"] == "you can't use this service"

    request_json["user"] = "unagi"
    ret = await claude2_proxy.filter_request(request_id, request_json, request_headers, False)
    assert ret == request_json


@pytest.mark.asyncio
async def test_response_filter_valuereturn(claude2_proxy, response_json):
    request_id = str(uuid4())

    claude2_proxy.add_filter(OverwriteResponseFilter())

    ret = await claude2_proxy.filter_response(request_id, response_json)

    assert ret["completion"] == "Overwrite in filter"


def test_post_content(prompt_text, request_json, request_headers, boto3_client, db):
    body = json.dumps(request_json)
    response = boto3_client.invoke_model(
        modelId="anthropic.claude-v2",
        body=body
    )

    comp_resp = response["body"]._raw_stream.json()
    headers = response["ResponseMetadata"]["HTTPHeaders"]
    request_id = headers.get("x-aiproxy-request-id")

    assert request_id is not None
    assert "うなぎ" in comp_resp["completion"]

    # Wait for processing queued items
    sleep(2.0)

    db_request = db.query(AccessLog).where(AccessLog.request_id == request_id, AccessLog.direction == "request").first()
    db_resonse = db.query(AccessLog).where(AccessLog.request_id == request_id, AccessLog.direction == "response").first()

    assert db_request.content == prompt_text
    assert db_resonse.content == comp_resp["completion"]
    assert db_resonse.status_code == response["ResponseMetadata"]["HTTPStatusCode"]


def test_post_content_apierror(prompt_text, request_json, request_headers, boto3_client, db):
    with pytest.raises(ClientError) as apisterr:
        request_json["extrakey"] = "extravalue"
        body = json.dumps(request_json)
        boto3_client.invoke_model(
            modelId="anthropic.claude-v2",
            body=body
        )
    
    api_resp = apisterr.value.response

    assert api_resp["ResponseMetadata"]["HTTPStatusCode"] == 400

    headers = api_resp["ResponseMetadata"]["HTTPHeaders"]
    request_id = headers.get("x-aiproxy-request-id")

    assert request_id is not None

    # Wait for processing queued items
    sleep(2.0)

    db_request = db.query(AccessLog).where(AccessLog.request_id == request_id, AccessLog.direction == "request").first()
    db_resonse = db.query(AccessLog).where(AccessLog.request_id == request_id, AccessLog.direction == "error").first()

    assert db_request.content == prompt_text
    assert str(api_resp["ResponseMetadata"]["HTTPStatusCode"]) in db_resonse.content
    assert db_resonse.status_code == api_resp["ResponseMetadata"]["HTTPStatusCode"]


def test_post_content_stream(prompt_text, request_json, request_headers, boto3_client, db):
    body = json.dumps(request_json)
    response = boto3_client.invoke_model_with_response_stream(
        modelId="anthropic.claude-v2",
        body=body
    )

    headers = response["ResponseMetadata"]["HTTPHeaders"]
    request_id = headers.get("x-aiproxy-request-id")
    assert request_id is not None

    content = ""
    stream = response.get("body")
    if stream:
        for event in stream:
            chunk = event.get("chunk")
            if chunk:
                content += json.loads(chunk.get("bytes").decode())["completion"]

    # Wait for processing queued items
    sleep(2.0)

    db_request = db.query(AccessLog).where(AccessLog.request_id == request_id, AccessLog.direction == "request").first()
    db_resonse = db.query(AccessLog).where(AccessLog.request_id == request_id, AccessLog.direction == "response").first()

    assert db_request.content == prompt_text
    assert db_resonse.content == content
    assert db_resonse.status_code == response["ResponseMetadata"]["HTTPStatusCode"]


def test_post_content_stream_apierror(prompt_text, request_json, request_headers, boto3_client, db):
    with pytest.raises(ClientError) as apisterr:
        request_json["extrakey"] = "extravalue"
        body = json.dumps(request_json)
        boto3_client.invoke_model_with_response_stream(
            modelId="anthropic.claude-v2",
            body=body
        )
    
    api_resp = apisterr.value.response

    assert api_resp["ResponseMetadata"]["HTTPStatusCode"] == 400

    headers = api_resp["ResponseMetadata"]["HTTPHeaders"]
    request_id = headers.get("x-aiproxy-request-id")

    assert request_id is not None

    # Wait for processing queued items
    sleep(2.0)

    db_request = db.query(AccessLog).where(AccessLog.request_id == request_id, AccessLog.direction == "request").first()
    db_resonse = db.query(AccessLog).where(AccessLog.request_id == request_id, AccessLog.direction == "error").first()

    assert db_request.content == prompt_text
    assert "x-amzn-errortype" in json.loads(db_resonse.raw_headers)
    assert db_resonse.status_code == api_resp["ResponseMetadata"]["HTTPStatusCode"]
