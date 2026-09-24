import json

import httpx
import openai
import pytest

from tests.conftest import tool_step

SQL = "SELECT Name, Amount FROM [Salesforce1].[Salesforce].[Opportunity] LIMIT 5"


def stream(client, **body):
    r = client.post("/chat/stream", json={"message": "top deals?", **body})
    events = [json.loads(line) for line in r.text.splitlines() if line.strip()]
    return r, events


@pytest.fixture
def scripted(stub_agent):
    stub_agent.steps = [
        *tool_step("getTables", {"catalogName": "Salesforce1", "schemaName": "Salesforce"}, call_id="t1"),
        *tool_step("queryData", {"query": "SELECT nope"}, "Error: no table", status="error", call_id="q1"),
        *tool_step("queryData", {"query": SQL}, call_id="q2"),
    ]
    stub_agent.reply = "Northwind leads with $480K."
    return stub_agent


def test_events_in_order(make_client, scripted):
    r, events = stream(make_client(), thread_id="t-1")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("application/x-ndjson")
    assert [e["type"] for e in events] == [
        "start", "step", "step_done", "step", "step_done", "step", "step_done", "done", "suggestions",
    ]
    assert events[0] == {"type": "start", "thread_id": "t-1"}


def test_step_events_carry_labels_and_sql(make_client, scripted):
    _, events = stream(make_client())
    steps = [e for e in events if e["type"] == "step"]
    assert steps[0] == {"type": "step", "id": "t1", "tool": "getTables",
                        "label": "Listing tables in Salesforce1", "sql": None}
    assert [s["sql"] for s in steps[1:]] == ["SELECT nope", SQL]
    assert [e["ok"] for e in events if e["type"] == "step_done"] == [True, False, True]


def test_done_has_reply_and_queries(make_client, scripted):
    _, events = stream(make_client())
    done = next(e for e in events if e["type"] == "done")
    assert done["reply"] == "Northwind leads with $480K."
    assert done["queries"] == [{"sql": "SELECT nope", "ok": False}, {"sql": SQL, "ok": True}]
    assert done["thread_id"] == events[0]["thread_id"]


def test_a_plain_answer_streams_start_and_done(make_client, stub_agent):
    _, events = stream(make_client())
    assert [e["type"] for e in events] == ["start", "done", "suggestions"]
    assert events[1]["queries"] == []


def test_stream_requires_the_key_when_set(make_client, scripted):
    client = make_client(app_api_key="secret")
    assert client.post("/chat/stream", json={"message": "hi"}).status_code == 401
    r = client.post("/chat/stream", json={"message": "hi"}, headers={"Authorization": "Bearer secret"})
    assert r.status_code == 200


def test_invalid_message_is_rejected_before_streaming(make_client):
    assert make_client().post("/chat/stream", json={"message": ""}).status_code == 422


def test_failure_mid_run_ends_with_an_actionable_error(make_client, scripted):
    req = httpx.Request("POST", "https://api.openai.com")
    scripted.exc = openai.AuthenticationError("x", response=httpx.Response(401, request=req), body=None)
    scripted.fail_after_steps = True
    _, events = stream(make_client())
    assert [e["type"] for e in events][-1] == "error"
    assert "step" in [e["type"] for e in events]  # progress arrived before the failure
    assert "Check OPENAI_API_KEY" in events[-1]["detail"]
    assert not any(e["type"] == "done" for e in events)


def test_chat_json_reports_only_this_turns_queries(make_client, scripted):
    # The stub returns an earlier turn's "SELECT old" too, as the checkpointer would.
    body = make_client().post("/chat", json={"message": "top deals?"}).json()
    assert body["queries"] == [{"sql": "SELECT nope", "ok": False}, {"sql": SQL, "ok": True}]


def test_vendored_scripts_are_served(make_client):
    client = make_client()
    for path in ("/static/vendor/marked.umd.js", "/static/vendor/purify.min.js"):
        r = client.get(path)
        assert r.status_code == 200 and "javascript" in r.headers["content-type"]
    page = client.get("/").text
    assert "cdn.jsdelivr.net" not in page and "/static/vendor/purify.min.js" in page


# ---------- follow-up suggestions ----------

def test_suggestions_follow_the_answer(make_client, scripted, fake_llm):
    _, events = stream(make_client())
    assert events[-1] == {"type": "suggestions", "items": [
        "Which of those close this month?", "Break that down by stage",
        "How does that compare to last quarter?",
    ]}
    # The model saw the question, the answer, and only the SQL that worked.
    (system, human), = fake_llm.prompts
    assert "follow-up questions" in system.content
    assert "top deals?" in human.content and "Northwind leads" in human.content
    assert SQL in human.content and "SELECT nope" not in human.content


def test_suggestions_can_be_turned_off(make_client, scripted, fake_llm):
    _, events = stream(make_client(suggest_followups=False))
    assert events[-1]["type"] == "done" and fake_llm.prompts == []


@pytest.mark.parametrize("reply, exc", [
    ("Sure! Here are some ideas: ask about trends.", None),   # no list
    ("[]", None),                                              # empty list
    (None, RuntimeError("provider down")),
])
def test_failed_suggestions_leave_the_answer_alone(make_client, scripted, fake_llm, reply, exc):
    fake_llm.reply, fake_llm.exc = reply, exc
    _, events = stream(make_client())
    assert [e["type"] for e in events][-1] == "done"
    assert events[-1]["reply"] == "Northwind leads with $480K."


def test_no_suggestions_after_an_error(make_client, scripted, fake_llm):
    scripted.exc, scripted.fail_after_steps = RuntimeError("boom"), True
    _, events = stream(make_client())
    assert events[-1]["type"] == "error" and fake_llm.prompts == []


def test_chat_json_does_not_wait_for_suggestions(make_client, scripted, fake_llm):
    body = make_client().post("/chat", json={"message": "top deals?"}).json()
    assert "suggestions" not in body and fake_llm.prompts == []
