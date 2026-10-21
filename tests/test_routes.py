import httpx
import openai
import pytest
from mcp.shared.exceptions import McpError
from mcp.types import ErrorData

from tests.conftest import TOOL_NAMES

REQUEST = httpx.Request("POST", "https://example.com")


def test_root_serves_the_chat_page(make_client):
    r = make_client().get("/")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/html")
    assert "Ask about your live data" in r.text


def test_healthz(make_client):
    body = make_client(llm_model="anthropic:claude-sonnet-5").get("/healthz").json()
    assert body == {
        "status": "ok",
        "mcp_tools": len(TOOL_NAMES),
        "llm_model": "anthropic:claude-sonnet-5",
        "auth_required": False,
    }


def test_healthz_needs_no_key_even_when_auth_is_on(make_client):
    r = make_client(app_api_key="secret").get("/healthz")
    assert r.status_code == 200 and r.json()["auth_required"] is True


# ---------- auth ----------

@pytest.mark.parametrize("path, method", [("/chat", "post"), ("/tools", "get")])
@pytest.mark.parametrize(
    "headers, expected",
    [
        ({}, 401),
        ({"Authorization": "Bearer wrong"}, 401),
        ({"Authorization": "secret"}, 401),  # no Bearer scheme
        ({"Authorization": "Bearer secret"}, 200),
    ],
)
def test_key_is_enforced_when_set(make_client, path, method, headers, expected):
    client = make_client(app_api_key="secret")
    kwargs = {"json": {"message": "hi"}} if method == "post" else {}
    assert getattr(client, method)(path, headers=headers, **kwargs).status_code == expected


def test_401_says_what_to_send(make_client):
    r = make_client(app_api_key="secret").post("/chat", json={"message": "hi"})
    assert "APP_API_KEY" in r.json()["detail"]


@pytest.mark.parametrize("headers", [{}, {"Authorization": "Bearer anything"}])
def test_no_key_configured_means_open(make_client, headers):
    client = make_client(app_api_key="")
    assert client.post("/chat", json={"message": "hi"}, headers=headers).status_code == 200
    assert client.get("/tools", headers=headers).json() == {"tools": TOOL_NAMES}


# ---------- chat ----------

def test_chat_returns_reply_and_new_thread(make_client, stub_agent):
    r = make_client().post("/chat", json={"message": "hi"})
    body = r.json()
    assert r.status_code == 200 and body["reply"] == "hello"
    assert len(body["thread_id"]) == 36  # a fresh uuid4
    (inputs, config), = stub_agent.calls
    assert inputs["messages"][0].content == "hi"
    assert config == {"configurable": {"thread_id": body["thread_id"]}}


def test_chat_reuses_a_given_thread(make_client, stub_agent):
    r = make_client().post("/chat", json={"message": "hi", "thread_id": "t-1"})
    assert r.json()["thread_id"] == "t-1"
    assert stub_agent.calls[0][1]["configurable"]["thread_id"] == "t-1"


def test_chat_flattens_content_blocks(make_client, stub_agent):
    # Some providers return a list of blocks instead of a string.
    stub_agent.reply = [{"type": "text", "text": "a"}, {"type": "tool_use"}, {"type": "text", "text": "b"}]
    assert make_client().post("/chat", json={"message": "hi"}).json()["reply"] == "ab"


@pytest.mark.parametrize("body", [{}, {"message": ""}, {"message": "x" * 4001}])
def test_chat_validates_the_message(make_client, body):
    assert make_client().post("/chat", json=body).status_code == 422


def _status(status):
    return httpx.Response(status, request=REQUEST)


@pytest.mark.parametrize(
    "exc, expected",
    [
        (openai.AuthenticationError("x", response=_status(401), body=None),
         "rejected the API key for LLM_MODEL=openai:gpt-4o. Check OPENAI_API_KEY."),
        (openai.RateLimitError("x", response=_status(429), body=None), "rate limiting"),
        (ExceptionGroup("g", [ExceptionGroup("g", [
            httpx.HTTPStatusError("401", request=REQUEST, response=_status(401))])]),
         "Connect AI rejected the credentials (HTTP 401)"),
        (ExceptionGroup("g", [McpError(ErrorData(code=-1, message="Session terminated"))]),
         "CDATA_MCP_URL"),
        (KeyError("boom"), "The agent failed (KeyError). See the service logs."),
    ],
)
def test_chat_failures_become_actionable_502s(make_client, stub_agent, exc, expected):
    stub_agent.exc = exc
    r = make_client().post("/chat", json={"message": "hi"})
    assert r.status_code == 502
    assert expected in r.json()["detail"]
