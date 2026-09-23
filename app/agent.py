from langchain.chat_models import init_chat_model
from langchain_mcp_adapters.client import MultiServerMCPClient
from langgraph.prebuilt import create_react_agent

from app.config import Settings

SYSTEM_PROMPT = """\
You are a business data assistant with live access to enterprise systems
through CData Connect AI.

- Explore before querying: list catalogs, schemas, and tables, and inspect
  columns before writing SQL.
- Keep result sets small: select only needed columns and always use LIMIT.
- Never create, update, or delete records unless the user explicitly asks
  and confirms the exact change.
- In every answer, say which source and table the data came from.
"""


async def build_agent(settings: Settings, checkpointer):
    mcp = MultiServerMCPClient(
        {
            "cdata": {
                "transport": "streamable_http",
                "url": settings.cdata_mcp_url,
                "headers": {"Authorization": settings.mcp_auth_header},
            }
        }
    )
    tools = await mcp.get_tools()
    llm = init_chat_model(settings.llm_model, temperature=0)
    agent = create_react_agent(
        llm, tools, prompt=SYSTEM_PROMPT, checkpointer=checkpointer
    )
    return agent, [t.name for t in tools]
