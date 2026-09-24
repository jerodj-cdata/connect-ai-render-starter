import logging

from langchain.agents import create_agent
from langchain.chat_models import init_chat_model
from langchain_mcp_adapters.client import MultiServerMCPClient

from app.config import Settings
from app.errors import SetupError, describe_mcp_error

log = logging.getLogger("uvicorn.error")

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
    try:
        tools = await mcp.get_tools()
    except Exception as exc:
        message = describe_mcp_error(exc, settings.cdata_mcp_url)
        if message is None:
            raise
        raise SetupError(message) from None
    if not tools:
        log.warning(
            "%s exposes no tools; the agent cannot reach any data. If it is a "
            "Toolkit URL, enable some tools on the Toolkit.",
            settings.cdata_mcp_url,
        )

    try:
        llm = init_chat_model(settings.llm_model, temperature=0)
    except ImportError as exc:
        # The message names the pip package to install.
        raise SetupError(
            f"LLM_MODEL={settings.llm_model}: {exc} Add it to requirements.in."
        ) from None
    except ValueError as exc:
        raise SetupError(f"LLM_MODEL={settings.llm_model}: {exc}") from None

    agent = create_agent(
        llm, tools, system_prompt=SYSTEM_PROMPT, checkpointer=checkpointer
    )
    log.info(
        "Loaded %d tools from %s; model %s",
        len(tools), settings.cdata_mcp_url, settings.llm_model,
    )
    return agent, [t.name for t in tools]
