"""Turn low-level failures into messages that say what to fix."""
import httpx
from mcp.shared.exceptions import McpError


class SetupError(RuntimeError):
    """A misconfiguration the operator can fix. The message says how."""


def root_cause(exc: BaseException) -> BaseException:
    # anyio wraps MCP transport failures in (sometimes nested) ExceptionGroups,
    # which bury the real HTTP error in the middle of a long traceback.
    while isinstance(exc, BaseExceptionGroup) and exc.exceptions:
        exc = exc.exceptions[0]
    return exc


def describe_mcp_error(exc: BaseException, url: str) -> str | None:
    exc = root_cause(exc)
    if isinstance(exc, httpx.HTTPStatusError):
        status = exc.response.status_code
        if status in (401, 403):
            return (
                f"Connect AI rejected the credentials (HTTP {status}) at {url}. "
                "Check that CDATA_USERNAME is your Connect AI login email and "
                "CDATA_PAT is a current Personal Access Token."
            )
        if status == 404:
            return f"No MCP server at {url} (HTTP 404). Check CDATA_MCP_URL."
        return f"The Connect AI MCP server at {url} returned HTTP {status}."
    if isinstance(exc, McpError):
        # The MCP SDK reports an HTTP 404 as "Session terminated", which is
        # usually a wrong URL rather than an expired session.
        return (
            f"The MCP server at {url} ended the session ({exc}). This usually "
            "means CDATA_MCP_URL is not a valid Connect AI MCP endpoint."
        )
    if isinstance(exc, httpx.TransportError):
        return (
            f"Could not reach the Connect AI MCP server at {url} "
            f"({type(exc).__name__}: {exc}). Check CDATA_MCP_URL and your network."
        )
    return None


def describe_llm_error(exc: BaseException, model: str, key_var: str | None) -> str | None:
    # The openai and anthropic SDKs both put the HTTP status on the exception.
    status = getattr(root_cause(exc), "status_code", None)
    if not isinstance(status, int):
        return None
    key = key_var or "the provider's API key"
    if status in (401, 403):
        return f"The LLM provider rejected the API key for LLM_MODEL={model}. Check {key}."
    if status == 404:
        return f"The LLM provider does not recognise LLM_MODEL={model}. Check the model name."
    if status == 429:
        return (
            f"The LLM provider is rate limiting LLM_MODEL={model}, or the account is "
            "out of quota. Check billing, or retry shortly."
        )
    return f"The LLM provider returned HTTP {status} for LLM_MODEL={model}."
