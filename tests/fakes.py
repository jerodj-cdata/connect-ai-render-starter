"""Offline stand-ins for the MCP client and the chat model."""
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult


class FakeMCPClient:
    """Replaces MultiServerMCPClient. Class attributes set the behaviour."""

    tools: list = []
    error: BaseException | None = None
    last_config: dict | None = None

    def __init__(self, config):
        FakeMCPClient.last_config = config

    async def get_tools(self):
        if FakeMCPClient.error is not None:
            raise FakeMCPClient.error
        return FakeMCPClient.tools


class ScriptedModel(BaseChatModel):
    """A chat model that calls each tool in `tool_calls` once, then answers.

    `tool_calls` holds tool names, or (name, args) pairs. Calls already
    answered in this turn are skipped. The final answer reports what it saw,
    so tests can assert on the conversation the agent actually built:
    "humans=<n> last_tool_chars=<n> truncated=<bool>".
    """

    tool_calls: list = []

    @property
    def _llm_type(self) -> str:
        return "scripted"

    def bind_tools(self, tools, **kwargs):
        return self

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        # Only this turn's tool results count, so each turn replays the script.
        last_human = max(i for i, m in enumerate(messages) if isinstance(m, HumanMessage))
        done = {m.name for m in messages[last_human:] if isinstance(m, ToolMessage)}
        script = [c if isinstance(c, tuple) else (c, {}) for c in self.tool_calls]
        pending = [(n, a) for n, a in script if n not in done]
        if pending:
            name, args = pending[0]
            msg = AIMessage(content="", tool_calls=[{"name": name, "args": args, "id": f"call-{name}-{last_human}"}])
        else:
            tools = [m for m in messages if isinstance(m, ToolMessage)]
            last = str(tools[-1].content) if tools else ""
            humans = sum(isinstance(m, HumanMessage) for m in messages)
            msg = AIMessage(
                content=f"humans={humans} last_tool_chars={len(last)} "
                f"truncated={'[Truncated:' in last}"
            )
        return ChatResult(generations=[ChatGeneration(message=msg)])
