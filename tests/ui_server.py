"""The real app with a stub agent, served by uvicorn for the browser tests.

UI_STUB_API_KEY sets APP_API_KEY (empty: no key, like local development).
The agent streams two tool steps (the second a SQL query) before answering;
follow-up suggestions arrive SUGGEST_DELAY seconds after the answer.
Messages containing "break" fail after the first step, like a rejected
OpenAI key.
"""
import asyncio
import contextlib
import json
import os

import httpx
import openai
from langchain_core.messages import AIMessage, ToolMessage

import app.main as main
from tests.conftest import TOOL_NAMES, make_settings, tool_step

SQL = "SELECT Name, StageName, Amount FROM [Salesforce1].[Salesforce].[Opportunity] LIMIT 2"
# SQL comes from the model, so treat it as hostile: it must show as text.
HOSTILE_SQL = """SELECT '<img src=x onerror="document.title='XSS-SQL'">' AS x"""
STEP_DELAY = 0.4  # long enough for a test to see a step while it runs
SUGGEST_DELAY = 1.0


def followups_for(question):
    return [f"More about {question}", "Break that down by stage", "Compare to last quarter"]


class LLM:
    async def ainvoke(self, messages):
        await asyncio.sleep(SUGGEST_DELAY)
        question = messages[1].content.split("\n")[1]
        return AIMessage(content=json.dumps(followups_for(question)))

REPLY = """Top deals from `[Salesforce1].[Salesforce].[Opportunity]`:

| Name | Stage | Amount |
| --- | --- | ---: |
| Northwind renewal | Negotiation | $480,000 |
| Contoso expansion | Proposal | $325,000 |

**Two** deals are open. <img src=x onerror="document.title='XSS'">"""


class Agent:
    async def astream(self, inputs, config, stream_mode):
        text = inputs["messages"][0].content
        sql = HOSTILE_SQL if "hostile" in text else SQL
        steps = [
            *tool_step("getTables", {"catalogName": "Salesforce1", "schemaName": "Salesforce"}),
            *tool_step("queryData", {"query": sql}),
        ]
        for i, msg in enumerate(steps):
            await asyncio.sleep(STEP_DELAY)
            yield {"tools" if isinstance(msg, ToolMessage) else "model": {"messages": [msg]}}
            if "break" in text and i == 1:
                response = httpx.Response(401, request=httpx.Request("POST", "https://api.openai.com"))
                raise openai.AuthenticationError("bad key", response=response, body=None)
        yield {"model": {"messages": [AIMessage(content=REPLY)]}}


@contextlib.asynccontextmanager
async def lifespan(app):
    app.state.settings = make_settings(app_api_key=os.environ.get("UI_STUB_API_KEY", ""))
    app.state.tool_names = TOOL_NAMES
    app.state.agent = Agent()
    app.state.llm = LLM()
    yield


main.app.router.lifespan_context = lifespan
app = main.app
