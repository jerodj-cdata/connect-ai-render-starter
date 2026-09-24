import contextlib
import os

import psycopg
import pytest
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from psycopg.conninfo import conninfo_to_dict, make_conninfo

import app.main as main
from app.config import Settings

# Every variable the app or the job reads. Cleared before each test so a
# developer's .env or shell never leaks into results.
APP_ENV_VARS = [
    "CDATA_USERNAME", "CDATA_PAT", "CDATA_MCP_URL", "CDATA_API_URL",
    "DATABASE_URL", "LLM_MODEL", "OPENAI_API_KEY", "OPENAI_BASE_URL",
    "ANTHROPIC_API_KEY", "APP_API_KEY", "CONVERSATION_RETENTION_DAYS", "SUGGEST_FOLLOWUPS",
    "CDATA_SF_CATALOG",
    "DIGEST_LOOKAHEAD_DAYS", "SLACK_WEBHOOK_URL",
]

TOOL_NAMES = ["getCatalogs", "getTables", "getColumns", "queryData"]


def skip_or_fail(reason: str):
    """Skip locally, but fail in CI, where a skip would hide missing coverage."""
    if os.environ.get("CI"):
        pytest.fail(f"{reason} (CI is set, so this fails instead of skipping)")
    pytest.skip(reason)
MCP_URL = "https://mcp.cloud.cdata.com/mcp"


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for name in APP_ENV_VARS:
        monkeypatch.delenv(name, raising=False)


def make_settings(**overrides) -> Settings:
    values = dict(
        cdata_username="user@example.com",
        cdata_pat="pat",
        cdata_mcp_url=MCP_URL,
        database_url="postgresql://unused",
        llm_model="openai:gpt-4o",
        app_api_key="",
    )
    values.update(overrides)
    return Settings(**values)


def tool_step(name, args, result="ok", status="success", call_id=None):
    """The two messages one tool call produces: the model's call, the result."""
    call_id = call_id or f"call-{name}-{len(str(args))}"
    return [
        AIMessage(content="", tool_calls=[{"name": name, "args": args, "id": call_id}]),
        ToolMessage(content=result, tool_call_id=call_id, name=name, status=status),
    ]


class StubAgent:
    """Stands in for the LangGraph agent.

    Plays `steps` (messages from tool_step), then answers `reply`. `exc` is
    raised before any step, or after them if `fail_after_steps` is set.
    """

    def __init__(self):
        self.reply = "hello"
        self.steps = []
        self.exc = None
        self.fail_after_steps = False
        self.calls = []

    async def ainvoke(self, inputs, config):
        self.calls.append((inputs, config))
        if self.exc is not None:
            raise self.exc
        # Like the real agent with a checkpointer: the whole thread comes back.
        earlier = [HumanMessage("earlier question"), *tool_step("queryData", {"query": "SELECT old"})]
        return {"messages": [*earlier, *inputs["messages"], *self.steps, AIMessage(content=self.reply)]}

    async def astream(self, inputs, config, stream_mode):
        assert stream_mode == "updates"
        self.calls.append((inputs, config))
        if self.exc is not None and not self.fail_after_steps:
            raise self.exc
        for msg in self.steps:
            node = "tools" if isinstance(msg, ToolMessage) else "model"
            yield {node: {"messages": [msg]}}
        if self.exc is not None:
            raise self.exc
        yield {"model": {"messages": [AIMessage(content=self.reply)]}}


class FakeLLM:
    """The chat model as the suggestion code sees it: `reply` or raise `exc`."""

    def __init__(self):
        self.reply = '["Which of those close this month?", "Break that down by stage", "How does that compare to last quarter?"]'
        self.exc = None
        self.prompts = []

    async def ainvoke(self, messages):
        self.prompts.append(messages)
        if self.exc is not None:
            raise self.exc
        return AIMessage(content=self.reply)


@pytest.fixture
def stub_agent():
    return StubAgent()


@pytest.fixture
def fake_llm():
    return FakeLLM()


@pytest.fixture
def make_client(monkeypatch, stub_agent, fake_llm):
    """make_client(**settings) -> a TestClient whose startup is stubbed out."""
    stack = contextlib.ExitStack()

    def _make(**settings_overrides):
        @contextlib.asynccontextmanager
        async def lifespan(app):
            app.state.settings = make_settings(**settings_overrides)
            app.state.agent = stub_agent
            app.state.llm = fake_llm
            app.state.tool_names = TOOL_NAMES
            yield

        monkeypatch.setattr(main.app.router, "lifespan_context", lifespan)
        return stack.enter_context(TestClient(main.app))

    yield _make
    stack.close()


# ---------- Postgres ----------

DEFAULT_TEST_DB = "postgresql://agent:agent@localhost:5432/agent_test"


@pytest.fixture(scope="session")
def database_url():
    """A disposable database, created on first use. Skips if Postgres is down."""
    url = os.environ.get("TEST_DATABASE_URL", DEFAULT_TEST_DB)
    params = conninfo_to_dict(url)
    try:
        with psycopg.connect(url, connect_timeout=3):
            return url
    except psycopg.OperationalError as exc:
        if "does not exist" not in str(exc):
            skip_or_fail(f"Postgres not reachable ({str(exc).strip().splitlines()[-1]}); "
                         "start it with `docker compose up -d db`")
    # The database is missing: create it through the server's default db.
    admin = make_conninfo(url, dbname="postgres")
    with psycopg.connect(admin, autocommit=True) as conn:
        conn.execute(f'CREATE DATABASE "{params["dbname"]}"')
    return url
