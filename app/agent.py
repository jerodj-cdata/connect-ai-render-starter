import logging

from langchain.agents import create_agent
from langchain.agents.middleware import AgentMiddleware
from langchain.chat_models import init_chat_model
from langchain_core.messages import ToolMessage
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

# About 5K tokens. Listing every table in a large Salesforce org returns ~440K
# characters (~110K tokens): past a local model's context window, where Ollama
# silently drops the start of the prompt (the question), and costly on any
# hosted model.
TOOL_OUTPUT_MAX_CHARS = 20_000


def _truncate(text: str, tool_name: str) -> str:
    if len(text) <= TOOL_OUTPUT_MAX_CHARS:
        return text
    kept = text[:TOOL_OUTPUT_MAX_CHARS].rsplit("\n", 1)[0]  # end on a whole row
    hint = (
        "pass tableName to getTables to filter by name"
        if tool_name == "getTables"
        else "narrow the request with WHERE, fewer columns, or a smaller LIMIT"
    )
    return (
        f"{kept}\n\n[Truncated: showed {len(kept):,} of {len(text):,} characters "
        f"({text.count(chr(10)) + 1:,} lines in full). To see the rest, {hint}.]"
    )


class TruncateToolOutput(AgentMiddleware):
    """Cap every tool result at TOOL_OUTPUT_MAX_CHARS before the model sees it."""

    @staticmethod
    def _cap(result, tool_name: str):
        if not isinstance(result, ToolMessage):
            return result
        content = result.content
        if isinstance(content, str):
            content = _truncate(content, tool_name)
        else:  # MCP tools return a list of content blocks
            content = [
                {**b, "text": _truncate(b["text"], tool_name)}
                if isinstance(b, dict) and isinstance(b.get("text"), str)
                else b
                for b in content
            ]
        return result.model_copy(update={"content": content})

    def wrap_tool_call(self, request, handler):
        return self._cap(handler(request), request.tool_call["name"])

    async def awrap_tool_call(self, request, handler):
        return self._cap(await handler(request), request.tool_call["name"])


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
        llm,
        tools,
        system_prompt=SYSTEM_PROMPT,
        middleware=[TruncateToolOutput()],
        checkpointer=checkpointer,
    )
    log.info(
        "Loaded %d tools from %s; model %s",
        len(tools), settings.cdata_mcp_url, settings.llm_model,
    )
    return agent, [t.name for t in tools], llm
