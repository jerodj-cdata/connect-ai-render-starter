import asyncio
import logging

import httpx
import pytest
from langchain_core.messages import ToolMessage
from langchain_core.tools import tool

import app.agent as agent_mod
from app.agent import TOOL_OUTPUT_MAX_CHARS, TruncateToolOutput, _truncate, build_agent
from app.errors import SetupError
from tests.conftest import MCP_URL, make_settings
from tests.fakes import FakeMCPClient, ScriptedModel

BIG_TABLE_LIST = "TABLE_NAME,TABLE_TYPE\r\n" + "".join(
    f"Table_{i:05},TABLE\r\n" for i in range(25_000)
)


# ---------- truncation ----------

def test_small_output_is_untouched():
    assert _truncate("short", "queryData") == "short"
    assert _truncate("x" * TOOL_OUTPUT_MAX_CHARS, "queryData") == "x" * TOOL_OUTPUT_MAX_CHARS


def test_large_output_is_cut_on_a_row_boundary_with_a_note():
    out = _truncate(BIG_TABLE_LIST, "getTables")
    kept, note = out.split("\n\n[Truncated:")
    assert len(kept) <= TOOL_OUTPUT_MAX_CHARS
    assert kept.endswith("TABLE\r")  # a whole row, not half a name
    assert f"of {len(BIG_TABLE_LIST):,} characters" in note
    assert "pass tableName to getTables" in note


def test_hint_for_other_tools():
    assert "WHERE" in _truncate("row\n" * 10_000, "queryData")


def _tool_message(content, **kw):
    return ToolMessage(content=content, tool_call_id="1", name="getTables", **kw)


def test_cap_handles_mcp_content_blocks():
    msg = _tool_message([
        {"type": "text", "text": BIG_TABLE_LIST},
        {"type": "image", "url": "x"},
    ])
    out = TruncateToolOutput._cap(msg, "getTables")
    assert "[Truncated:" in out.content[0]["text"]
    assert out.content[1] == {"type": "image", "url": "x"}


def test_cap_keeps_error_status_and_ignores_non_tool_messages():
    out = TruncateToolOutput._cap(_tool_message("x" * 50_000, status="error"), "queryData")
    assert out.status == "error" and "[Truncated:" in out.content
    assert TruncateToolOutput._cap("not a message", "x") == "not a message"


# ---------- build_agent ----------

@pytest.fixture
def fake_mcp(monkeypatch):
    FakeMCPClient.tools, FakeMCPClient.error = [], None
    monkeypatch.setattr(agent_mod, "MultiServerMCPClient", FakeMCPClient)
    return FakeMCPClient


@pytest.fixture
def fake_model(monkeypatch):
    model = ScriptedModel()
    monkeypatch.setattr(agent_mod, "init_chat_model", lambda *a, **k: model)
    return model


def _build(**settings):
    return asyncio.run(build_agent(make_settings(**settings), checkpointer=None))


def test_mcp_client_gets_basic_auth_and_url(fake_mcp, fake_model):
    _build()
    server = fake_mcp.last_config["cdata"]
    assert server["url"] == MCP_URL
    assert server["transport"] == "streamable_http"
    assert server["headers"]["Authorization"].startswith("Basic ")


def test_mcp_401_becomes_setup_error(fake_mcp, fake_model):
    req = httpx.Request("POST", MCP_URL)
    fake_mcp.error = ExceptionGroup("g", [httpx.HTTPStatusError(
        "401", request=req, response=httpx.Response(401, request=req))])
    with pytest.raises(SetupError, match="rejected the credentials"):
        _build()


def test_unexpected_mcp_error_propagates(fake_mcp, fake_model):
    fake_mcp.error = KeyError("boom")
    with pytest.raises(KeyError):
        _build()


def test_zero_tools_warns(fake_mcp, fake_model, caplog):
    with caplog.at_level(logging.WARNING, logger="uvicorn.error"):
        _build()
    assert "exposes no tools" in caplog.text


@pytest.mark.parametrize(
    "error, expected",
    [
        (ImportError("Unable to import langchain_google_genai."), "Add it to requirements.in"),
        (ValueError("Unsupported model_provider='nope'."), "Unsupported model_provider"),
    ],
)
def test_model_construction_errors_become_setup_errors(fake_mcp, monkeypatch, error, expected):
    def boom(*a, **k):
        raise error
    monkeypatch.setattr(agent_mod, "init_chat_model", boom)
    with pytest.raises(SetupError, match=expected):
        _build(llm_model="google_genai:gemini")


def test_truncation_is_wired_into_the_agent(fake_mcp, fake_model):
    # The cap must apply inside a real agent run, not just as a function.
    @tool
    def getTables() -> str:
        """List tables."""
        return BIG_TABLE_LIST

    fake_mcp.tools = [getTables]
    fake_model.tool_calls = ["getTables"]
    agent, names, _ = _build()
    assert names == ["getTables"]

    result = asyncio.run(agent.ainvoke({"messages": [("user", "list tables")]}))
    tool_msg = next(m for m in result["messages"] if isinstance(m, ToolMessage))
    assert len(tool_msg.content) < TOOL_OUTPUT_MAX_CHARS + 500
    assert "truncated=True" in result["messages"][-1].content
