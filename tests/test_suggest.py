import asyncio

import pytest
from langchain_core.messages import AIMessage

import app.suggest as suggest
from app.suggest import parse_suggestions, suggest_followups


@pytest.mark.parametrize("text, expected", [
    ('["A?", "B?", "C?"]', ["A?", "B?", "C?"]),
    ('```json\n["A?", "B?"]\n```', ["A?", "B?"]),
    ('Here you go:\n["A?", "B?"]\nHope that helps.', ["A?", "B?"]),
    ('<think>they want ["no", "not these"]</think>["A?"]', ["A?"]),
    ('["A?", "B?", "C?", "D?"]', ["A?", "B?", "C?"]),           # capped at 3
    ('["A?", "A?", "  B?\\n "]', ["A?", "B?"]),                 # deduped, whitespace tidied
    ('["A?", 42, null, ""]', ["A?"]),                           # non-strings dropped
    ('["' + "x" * 121 + '", "B?"]', ["B?"]),                    # too long
    ('{"questions": ["A?"]}', ["A?"]),                           # list inside an object
    ("no list here", []),
    ('["unterminated', []),
    ("", []),
    (None, []),
])
def test_parse_suggestions(text, expected):
    assert parse_suggestions(text) == expected


class LLM:
    def __init__(self, content=None, exc=None, delay=0):
        self.content, self.exc, self.delay = content, exc, delay

    async def ainvoke(self, messages):
        await asyncio.sleep(self.delay)
        if self.exc:
            raise self.exc
        return AIMessage(content=self.content)


def run(llm):
    return asyncio.run(suggest_followups(llm, "q", "a", [{"sql": "SELECT 1", "ok": True}]))


def test_content_blocks_are_read():
    assert run(LLM(content=[{"type": "text", "text": '["A?"]'}])) == ["A?"]


def test_provider_errors_give_no_suggestions():
    assert run(LLM(exc=RuntimeError("down"))) == []


def test_slow_models_are_cut_off(monkeypatch):
    monkeypatch.setattr(suggest, "TIMEOUT_SECONDS", 0.05)
    assert run(LLM(content='["A?"]', delay=1)) == []
