"""Against a real Connect AI account. Opt in:

    set -a; source .env; set +a
    RUN_LIVE_TESTS=1 pytest -m live

Needs CDATA_USERNAME and CDATA_PAT. The digest test also needs
CDATA_SF_CATALOG to name a real Salesforce connection. No LLM is called.
These pin down behaviour discovered by hand, so a Connect AI or connector
change that breaks the starter's assumptions shows up here.
"""
import asyncio
import datetime as dt
import importlib
import os

import pytest

import app.agent as agent_mod
import jobs.pipeline_digest
from app.agent import build_agent
from app.errors import SetupError
from tests.conftest import make_settings
from tests.fakes import ScriptedModel

# Read now: the autouse clean_env fixture clears these before each test.
LIVE = {k: os.environ.get(k, "").strip() for k in ("CDATA_USERNAME", "CDATA_PAT", "CDATA_SF_CATALOG")}

pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(os.environ.get("RUN_LIVE_TESTS") != "1", reason="set RUN_LIVE_TESTS=1"),
    pytest.mark.skipif(not (LIVE["CDATA_USERNAME"] and LIVE["CDATA_PAT"]),
                       reason="needs CDATA_USERNAME and CDATA_PAT"),
]


@pytest.fixture
def no_llm(monkeypatch):
    monkeypatch.setattr(agent_mod, "init_chat_model", lambda *a, **k: ScriptedModel())


def test_mcp_tools_load_with_real_credentials(no_llm):
    settings = make_settings(cdata_username=LIVE["CDATA_USERNAME"], cdata_pat=LIVE["CDATA_PAT"])
    _, names, _ = asyncio.run(build_agent(settings, checkpointer=None))
    assert {"getCatalogs", "getTables", "getColumns", "queryData"} <= set(names)


def test_a_bad_pat_is_reported_as_rejected_credentials(no_llm):
    settings = make_settings(cdata_username=LIVE["CDATA_USERNAME"], cdata_pat="not-a-real-pat")
    with pytest.raises(SetupError, match=r"rejected the credentials \(HTTP 401\)"):
        asyncio.run(build_agent(settings, checkpointer=None))


@pytest.fixture
def live_digest(monkeypatch):
    def _load(catalog):
        monkeypatch.setenv("CDATA_USERNAME", LIVE["CDATA_USERNAME"])
        monkeypatch.setenv("CDATA_PAT", LIVE["CDATA_PAT"])
        monkeypatch.setenv("CDATA_SF_CATALOG", catalog)
        return importlib.reload(jobs.pipeline_digest)
    yield _load
    monkeypatch.undo()
    importlib.reload(jobs.pipeline_digest)


def test_missing_catalog_still_arrives_as_http_200_with_no_schema(live_digest):
    # If this starts raising cdata_connect_ai.Error instead, the connector has
    # been fixed and the `cur.description is None` check can be simplified.
    d = live_digest("NoSuchCatalog_starter_test")
    with pytest.raises(SystemExit, match="no connection named 'NoSuchCatalog_starter_test'"):
        d.fetch_open_opportunities(dt.date.today())


@pytest.mark.skipif(not LIVE["CDATA_SF_CATALOG"], reason="needs CDATA_SF_CATALOG")
def test_digest_reads_open_opportunities(live_digest):
    d = live_digest(LIVE["CDATA_SF_CATALOG"])
    opps = d.fetch_open_opportunities(dt.date.today() + dt.timedelta(days=14))
    assert isinstance(opps, list)
    if opps:
        assert set(opps[0]) == {"Id", "Name", "StageName", "Amount", "CloseDate"}
