"""Describe what the agent is doing, for the chat page and API callers."""
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage

WRITE_TOOLS = {"execute_insert", "execute_update", "executeProcedure"}


def describe_step(name: str, args: dict | None) -> str:
    """A short, human-readable label for one Connect AI tool call."""
    args = args or {}
    catalog = args.get("catalogName")
    table = args.get("tableName")
    in_catalog = f" in {catalog}" if catalog else ""
    if name == "getInstructions":
        return f"Loading {args.get('driverName') or 'driver'} SQL instructions"
    if name == "getCatalogs":
        return "Listing connections"
    if name == "getSchemas":
        return f"Listing schemas{in_catalog}"
    if name == "getTables":
        return f"Listing tables{in_catalog}" + (f" matching {table}" if table else "")
    if name == "getColumns":
        return f"Inspecting columns of {table or 'a table'}{in_catalog}"
    if name == "queryData":
        return "Running a SQL query"
    if name in ("getProcedures", "getProcedureParameters"):
        return f"Looking up stored procedures{in_catalog}"
    if name in WRITE_TOOLS:
        return f"Writing data ({name})"
    return f"Calling {name}"


def current_turn(messages: list[BaseMessage]) -> list[BaseMessage]:
    """The messages after the last user message: this request's work only."""
    for i in range(len(messages) - 1, -1, -1):
        if isinstance(messages[i], HumanMessage):
            return messages[i + 1:]
    return messages


def queries_in(messages: list[BaseMessage]) -> list[dict]:
    """Every SQL query run in `messages`, with whether it succeeded."""
    failed = {
        m.tool_call_id for m in messages
        if isinstance(m, ToolMessage) and m.status == "error"
    }
    return [
        {"sql": call["args"].get("query", ""), "ok": call["id"] not in failed}
        for m in messages if isinstance(m, AIMessage)
        for call in m.tool_calls if call["name"] == "queryData"
    ]
