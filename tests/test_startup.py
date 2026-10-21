"""The real startup path: settings, Postgres, checkpointer, agent build.

Only the MCP server and the chat model are faked; Postgres is real.
"""
import uuid

import pytest
from fastapi.testclient import TestClient
from langchain_core.tools import tool

import app.agent as agent_mod
import app.main as main
from app.errors import SetupError
from tests.fakes import FakeMCPClient, ScriptedModel


@tool
def getCatalogs() -> str:
    """List connections."""
    return "TABLE_CATALOG\r\nSalesforce1"


@pytest.fixture
def boot(monkeypatch):
    """boot(**env) -> a TestClient running the real lifespan."""
    FakeMCPClient.tools, FakeMCPClient.error = [getCatalogs], None
    monkeypatch.setattr(agent_mod, "MultiServerMCPClient", FakeMCPClient)
    monkeypatch.setattr(agent_mod, "init_chat_model", lambda *a, **k: ScriptedModel())
    base = {
        "CDATA_USERNAME": "user@example.com",
        "CDATA_PAT": "pat",
        "OPENAI_API_KEY": "sk-test",
        "APP_API_KEY": "",
    }

    def _boot(**env):
        for name, value in {**base, **env}.items():
            monkeypatch.setenv(name, value)
        return TestClient(main.app)
    return _boot


def test_missing_settings_stop_startup(boot):
    with pytest.raises(SetupError, match="DATABASE_URL"):
        with boot():
            pass


def test_unreachable_postgres_stops_startup_fast(boot):
    client = boot(DATABASE_URL="postgresql://agent:agent@127.0.0.1:1/agent")
    with pytest.raises(SetupError, match=r"Could not connect to Postgres.*docker compose up -d db"):
        with client:
            pass


@pytest.mark.db
def test_boots_and_remembers_conversations(boot, database_url):
    with boot(DATABASE_URL=database_url) as client:
        health = client.get("/healthz").json()
        assert health["mcp_tools"] == 1 and health["auth_required"] is False

        thread = f"test-{uuid.uuid4()}"
        first = client.post("/chat", json={"message": "hi", "thread_id": thread}).json()
        second = client.post("/chat", json={"message": "again", "thread_id": thread}).json()
        other = client.post("/chat", json={"message": "hi"}).json()

    # ScriptedModel reports how many user messages it saw: history comes from
    # the Postgres checkpointer, and threads are kept apart.
    assert first["reply"].startswith("humans=1")
    assert second["reply"].startswith("humans=2")
    assert other["reply"].startswith("humans=1")


@tool
def queryData(query: str) -> str:
    """Run SQL."""
    return "Name,Amount\r\nNorthwind,480000"


@pytest.mark.db
def test_stream_from_a_real_agent(boot, database_url, monkeypatch):
    # The real create_agent graph and checkpointer, so the stream's node and
    # message shapes are LangGraph's own, not a stub's.
    FakeMCPClient.tools = [getCatalogs, queryData]
    model = ScriptedModel()
    model.tool_calls = ["getCatalogs", ("queryData", {"query": "SELECT Name FROM t"})]
    monkeypatch.setattr(agent_mod, "init_chat_model", lambda *a, **k: model)
    with boot(DATABASE_URL=database_url) as client:
        r = client.post("/chat/stream", json={"message": "top deals?"})
    import json
    events = [json.loads(line) for line in r.text.splitlines()]
    assert [e["type"] for e in events] == ["start", "step", "step_done", "step", "step_done", "done"]
    assert [e["label"] for e in events if e["type"] == "step"] == ["Listing connections", "Running a SQL query"]
    assert events[-1]["queries"] == [{"sql": "SELECT Name FROM t", "ok": True}]
    assert events[-1]["reply"].startswith("humans=1")


@pytest.mark.db
def test_retention_runs_at_startup(boot, database_url, caplog):
    import logging
    import psycopg
    thread = f"stale-{uuid.uuid4()}"
    with boot(DATABASE_URL=database_url) as client:
        client.post("/chat", json={"message": "hi", "thread_id": thread})
    with psycopg.connect(database_url, autocommit=True) as pg:
        pg.execute("UPDATE checkpoints SET checkpoint = jsonb_set(checkpoint, '{ts}', "
                   "'\"2020-01-01T00:00:00+00:00\"') WHERE thread_id = %s", (thread,))
    with caplog.at_level(logging.INFO, logger="uvicorn.error"):
        with boot(DATABASE_URL=database_url, CONVERSATION_RETENTION_DAYS="30") as client:
            client.get("/healthz")
            for _ in range(50):  # the cleanup task runs just after startup
                with psycopg.connect(database_url) as pg:
                    left = pg.execute("SELECT count(*) FROM checkpoints WHERE thread_id = %s",
                                      (thread,)).fetchone()[0]
                if not left:
                    break
                import time; time.sleep(0.1)
    assert left == 0
    assert "idle for over 30 days" in caplog.text


@pytest.mark.db
def test_bad_mcp_credentials_stop_startup(boot, database_url):
    import httpx
    req = httpx.Request("POST", "https://mcp.cloud.cdata.com/mcp")
    FakeMCPClient.error = ExceptionGroup("g", [httpx.HTTPStatusError(
        "401", request=req, response=httpx.Response(401, request=req))])
    with pytest.raises(SetupError, match="Connect AI rejected the credentials"):
        with boot(DATABASE_URL=database_url):
            pass
