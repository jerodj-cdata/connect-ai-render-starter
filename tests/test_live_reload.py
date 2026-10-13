"""Live reload: what the header reports, and swapping the agent on a .env change."""
import asyncio
import os

import pytest

from app import live
from app.errors import SetupError
from tests.conftest import TOOL_NAMES, make_settings

GATEWAY = "https://cloud.cdata.com/gateway/v1"
WRITE_TOOLS = TOOL_NAMES + ["execute_insert", "execute_update"]


@pytest.mark.parametrize(
    "env, expected",
    [
        ({"ANTHROPIC_API_KEY": "sk-ant-x"}, ("Anthropic API", False, "provider key")),
        ({"ANTHROPIC_BASE_URL": GATEWAY, "ANTHROPIC_API_KEY": "cgw_sk_x"},
         ("Connect AI LLM Gateway", True, "virtual key")),
        ({"ANTHROPIC_BASE_URL": "https://cloud.cdata.com/gateway", "ANTHROPIC_API_KEY": "cgw_sk_x"},
         ("Connect AI LLM Gateway", True, "virtual key")),
        ({"ANTHROPIC_BASE_URL": "http://192.168.0.230:4000/v1", "ANTHROPIC_API_KEY": "sk-x"},
         ("192.168.0.230", False, "provider key")),
    ],
)
def test_describe_route(monkeypatch, env, expected):
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    route = live.describe(make_settings(llm_model="anthropic:claude-sonnet-5-5"), TOOL_NAMES)
    assert (route["via"], route["gateway"], route["key_kind"]) == expected
    assert route["model"] == "claude-sonnet-5-5"
    assert "cgw_sk_x" not in str(route) and "sk-ant-x" not in str(route)


def test_describe_tools():
    assert live.describe(make_settings(), TOOL_NAMES)["read_only"] is True
    route = live.describe(make_settings(), WRITE_TOOLS)
    assert route["read_only"] is False and route["tools"] == len(WRITE_TOOLS)


def test_apply_env_sets_and_unsets_but_leaves_pinned(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_BASE_URL", GATEWAY)
    monkeypatch.setenv("DATABASE_URL", "postgresql://db/agent")
    keys = live.apply_env({"LLM_MODEL": "anthropic:x", "DATABASE_URL": "postgresql://localhost/agent"},
                          {"ANTHROPIC_BASE_URL", "LLM_MODEL", "DATABASE_URL"})
    assert "ANTHROPIC_BASE_URL" not in os.environ  # dropped from the file, so unset
    assert os.environ["LLM_MODEL"] == "anthropic:x"
    assert os.environ["DATABASE_URL"] == "postgresql://db/agent"  # compose's value wins
    assert keys == {"LLM_MODEL", "DATABASE_URL"}
    monkeypatch.delenv("LLM_MODEL")


def test_status_reports_route_and_served_model(make_client):
    client = make_client(llm_model="anthropic:claude-sonnet-5-5")
    body = client.get("/status").json()
    assert body["model"] == "claude-sonnet-5-5" and body["served_model"] is None
    assert body["tools"] == len(TOOL_NAMES) and body["error"] is None


def test_rebuild_swaps_the_agent(monkeypatch, make_client):
    client = make_client()
    app = client.app
    new_agent = object()

    async def fake_build(settings, checkpointer):
        return new_agent, WRITE_TOOLS, "llm"

    monkeypatch.setattr(live, "build_agent", fake_build)
    monkeypatch.setattr(live, "load_settings", lambda: make_settings(llm_model="anthropic:claude-haiku-5-5"))
    app.state.served_model = "old"
    asyncio.run(live.rebuild(app, checkpointer=None))
    assert app.state.agent is new_agent
    assert app.state.route["model"] == "claude-haiku-5-5" and app.state.route["read_only"] is False
    assert app.state.served_model is None


def test_failed_rebuild_keeps_the_old_agent(monkeypatch, make_client):
    client = make_client()
    app = client.app
    old_agent = app.state.agent

    def broken():
        raise SetupError("LLM_MODEL='x' must look like provider:model")

    monkeypatch.setattr(live, "load_settings", broken)
    asyncio.run(live.rebuild(app, checkpointer=None))
    assert app.state.agent is old_agent
    assert "provider:model" in app.state.live_error
