import datetime as dt
import importlib

import psycopg
import pytest
import requests

import jobs.pipeline_digest

OPPS = [
    {"Id": "006A", "Name": "Northwind", "StageName": "Negotiation", "Amount": 480000.0, "CloseDate": "2026-10-15"},
    {"Id": "006B", "Name": "Contoso", "StageName": "Proposal", "Amount": None, "CloseDate": "2026-10-28"},
]


@pytest.fixture
def load_digest(monkeypatch):
    """load_digest(**env) -> the module, re-imported under that environment."""
    def _load(**env):
        for name, value in env.items():
            monkeypatch.setenv(name, value)
        return importlib.reload(jobs.pipeline_digest)
    yield _load
    monkeypatch.undo()
    importlib.reload(jobs.pipeline_digest)  # leave a clean module behind


# ---------- configuration ----------

def test_catalog_defaults_to_salesforce1(load_digest):
    d = load_digest()
    assert d.CATALOG == "Salesforce1"
    assert "FROM [Salesforce1].[Salesforce].[Opportunity]" in d.QUERY


def test_blank_catalog_falls_back_to_default(load_digest):
    assert load_digest(CDATA_SF_CATALOG="  ").CATALOG == "Salesforce1"


def test_hyphenated_catalog_is_accepted(load_digest):
    # Connect AI connection names like this used to be rejected.
    d = load_digest(CDATA_SF_CATALOG="Salesforce-Prod")
    assert "[Salesforce-Prod].[Salesforce].[Opportunity]" in d.QUERY


# "]" alone is the character that could close the bracketed identifier, so
# test it without any other disallowed characters alongside.
@pytest.mark.parametrize("catalog", ["evil]", "a]b", "x];DROP TABLE y", "a b", "sf.prod", "sf'"])
def test_unsafe_catalog_is_rejected(load_digest, catalog):
    with pytest.raises(SystemExit, match="Invalid CDATA_SF_CATALOG"):
        load_digest(CDATA_SF_CATALOG=catalog)


def test_lookahead(load_digest):
    assert load_digest(DIGEST_LOOKAHEAD_DAYS=" 30 ").LOOKAHEAD_DAYS == 30
    assert load_digest(DIGEST_LOOKAHEAD_DAYS="").LOOKAHEAD_DAYS == 14


# ---------- fetching from Connect AI ----------

class FakeCursor:
    def __init__(self, rows, description):
        self.rows, self.description, self.executed = rows, description, []

    def execute(self, query, params):
        self.executed.append((query, params))

    def fetchall(self):
        return [tuple(r.values()) for r in self.rows]


class FakeConn:
    def __init__(self, cursor):
        self._cursor, self.closed = cursor, False

    def cursor(self):
        return self._cursor

    def close(self):
        self.closed = True


@pytest.fixture
def digest(load_digest, monkeypatch):
    d = load_digest(CDATA_USERNAME="user@example.com", CDATA_PAT="pat\n")
    calls = {}

    def connect(cursor=None, error=None):
        conn = FakeConn(cursor)

        def fake_connect(**kwargs):
            calls.update(kwargs)
            if error:
                raise error
            return conn
        monkeypatch.setattr(d.cdata_connect_ai, "connect", fake_connect)
        return conn

    d.test_connect, d.connect_kwargs = connect, calls
    return d


def test_fetch_returns_dicts_and_passes_the_cutoff(digest):
    cols = [(k, None, None, None, None, None, None) for k in OPPS[0]]
    cur = FakeCursor(OPPS, cols)
    conn = digest.test_connect(cur)
    assert digest.fetch_open_opportunities(dt.date(2026, 10, 1)) == OPPS
    assert cur.executed[0][1] == {"cutoff": "2026-10-01"}
    assert digest.connect_kwargs["password"] == "pat"  # stripped
    assert conn.closed


def test_missing_catalog_is_explained(digest):
    # Connect AI answers HTTP 200 with the error in the body; cdata-connect-ai
    # drops it and leaves no result schema.
    conn = digest.test_connect(FakeCursor([], None))
    with pytest.raises(SystemExit, match="no connection named 'Salesforce1'"):
        digest.fetch_open_opportunities(dt.date(2026, 10, 1))
    assert conn.closed


def test_rejected_credentials_are_explained(digest):
    import cdata_connect_ai

    class RaisingCursor(FakeCursor):
        def execute(self, query, params):
            raise cdata_connect_ai.OperationalError("API request failed with status code 401")

    digest.test_connect(RaisingCursor([], None))
    with pytest.raises(SystemExit, match="rejected the credentials, so the query never ran"):
        digest.fetch_open_opportunities(dt.date(2026, 10, 1))


def test_missing_credentials_exit_before_connecting(load_digest):
    d = load_digest()
    with pytest.raises(SystemExit, match="Missing required environment variable: CDATA_USERNAME"):
        d.fetch_open_opportunities(dt.date(2026, 10, 1))


# ---------- Slack ----------

def test_slack_is_skipped_without_a_webhook(digest, monkeypatch):
    monkeypatch.setattr(digest.requests, "post", lambda *a, **k: pytest.fail("posted"))
    digest.post_to_slack(OPPS, dt.date(2026, 10, 8))


def test_slack_message(digest, monkeypatch):
    monkeypatch.setenv("SLACK_WEBHOOK_URL", "https://hooks.example.com/x")
    sent = {}

    class Ok:
        def raise_for_status(self):
            pass

    def post(url, json, timeout):
        sent.update(url=url, text=json["text"])
        return Ok()
    monkeypatch.setattr(digest.requests, "post", post)
    digest.post_to_slack(OPPS, dt.date(2026, 10, 8))
    assert sent["url"] == "https://hooks.example.com/x"
    assert "2 open deals, $480,000 total" in sent["text"]
    assert "- Contoso (Proposal): $0, closes 2026-10-28" in sent["text"]  # None amount


def test_slack_failure_says_the_snapshot_was_saved(digest, monkeypatch):
    monkeypatch.setenv("SLACK_WEBHOOK_URL", "https://hooks.example.com/x")

    def post(*a, **k):
        raise requests.ConnectionError("down")
    monkeypatch.setattr(digest.requests, "post", post)
    with pytest.raises(SystemExit, match="Snapshot saved, but the Slack post failed"):
        digest.post_to_slack(OPPS, dt.date(2026, 10, 8))


# ---------- Postgres ----------

def test_unreachable_postgres_is_explained(load_digest):
    d = load_digest(DATABASE_URL="postgresql://agent:agent@127.0.0.1:1/agent")
    with pytest.raises(SystemExit, match="Could not connect to Postgres"):
        d.save_snapshot(dt.date(2026, 9, 24), OPPS)


@pytest.mark.db
def test_snapshot_is_saved_and_rerun_is_idempotent(load_digest, database_url):
    d = load_digest(DATABASE_URL=database_url)
    with psycopg.connect(database_url, autocommit=True) as pg:
        pg.execute("DROP TABLE IF EXISTS pipeline_snapshot")

    day = dt.date(2026, 9, 24)
    d.save_snapshot(day, OPPS)
    changed = [{**OPPS[0], "StageName": "Closed Won"}, OPPS[1]]
    d.save_snapshot(day, changed)  # same day again: update, not duplicate

    with psycopg.connect(database_url) as pg:
        rows = pg.execute(
            "SELECT opportunity_id, stage, amount, close_date FROM pipeline_snapshot ORDER BY 1"
        ).fetchall()
    assert rows == [
        ("006A", "Closed Won", 480000, dt.date(2026, 10, 15)),
        ("006B", "Proposal", None, dt.date(2026, 10, 28)),
    ]
