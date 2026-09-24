"""Suggest follow-up questions after an answer.

A nice-to-have: it runs after the answer is delivered, and any failure (a slow
model, unparseable output, a provider error) means no suggestions, never a
failed chat.
"""
import asyncio
import json
import logging
import re

from langchain_core.messages import HumanMessage, SystemMessage

log = logging.getLogger("uvicorn.error")

MAX_SUGGESTIONS = 3
MAX_LENGTH = 120
TIMEOUT_SECONDS = 45

PROMPT = """\
You suggest follow-up questions for a business user chatting with an \
assistant that answers from live company systems (CRM, ERP, ticketing and \
more) by running SQL.

Given the user's question, the assistant's answer, and the SQL it ran, \
suggest 3 follow-up questions that:
- dig deeper into the same data: a breakdown, a trend over time, a \
comparison, or the records behind a number
- each take a different angle from the others
- are NOT already answered by the answer above; never ask for something it \
states, such as which item is largest when the answer already shows that
- can be answered from the same sources
- are phrased the way the user would ask them, in under 12 words

Reply with only a JSON array of 3 strings."""


def parse_suggestions(text: str) -> list[str]:
    """Pull a list of questions out of a model reply; [] if there isn't one."""
    text = re.sub(r"<think>.*?</think>", "", text or "", flags=re.S)
    start, end = text.find("["), text.rfind("]")
    if start < 0 or end <= start:
        return []
    try:
        items = json.loads(text[start:end + 1])
    except json.JSONDecodeError:
        return []
    if not isinstance(items, list):
        return []
    out = []
    for item in items:
        if isinstance(item, str):
            question = " ".join(item.split())
            if question and len(question) <= MAX_LENGTH and question not in out:
                out.append(question)
    return out[:MAX_SUGGESTIONS]


def _content(message) -> str:
    content = getattr(message, "content", "")
    if isinstance(content, list):  # content blocks
        return "".join(b.get("text", "") for b in content if isinstance(b, dict))
    return content if isinstance(content, str) else ""


async def suggest_followups(llm, question: str, reply: str, queries: list[dict]) -> list[str]:
    sql = "\n\n".join(q["sql"] for q in queries if q.get("ok")) or "(none)"
    context = (
        f"User question:\n{question}\n\n"
        f"Assistant answer:\n{reply[:3000]}\n\n"
        f"SQL that ran:\n{sql[:2000]}"
    )
    try:
        message = await asyncio.wait_for(
            llm.ainvoke([SystemMessage(PROMPT), HumanMessage(context)]),
            timeout=TIMEOUT_SECONDS,
        )
    except Exception as exc:  # includes TimeoutError
        log.warning("Skipping follow-up suggestions (%s)", type(exc).__name__)
        return []
    suggestions = parse_suggestions(_content(message))
    if not suggestions:
        log.warning("Skipping follow-up suggestions (no usable list in the reply)")
    return suggestions
