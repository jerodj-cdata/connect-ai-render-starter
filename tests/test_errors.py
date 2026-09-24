import anthropic
import httpx
import openai
import pytest
from mcp.shared.exceptions import McpError
from mcp.types import ErrorData

from app.errors import describe_llm_error, describe_mcp_error, root_cause

URL = "https://mcp.cloud.cdata.com/mcp"
REQUEST = httpx.Request("POST", URL)


def http_error(status):
    return httpx.HTTPStatusError(
        str(status), request=REQUEST, response=httpx.Response(status, request=REQUEST)
    )


def provider_error(cls, status):
    return cls("boom", response=httpx.Response(status, request=REQUEST), body=None)


def nested(exc):
    # How anyio delivers MCP transport failures.
    return ExceptionGroup("outer", [ExceptionGroup("inner", [exc])])


def test_root_cause_unwraps_nested_groups():
    inner = ValueError("real")
    assert root_cause(nested(inner)) is inner
    assert root_cause(inner) is inner


@pytest.mark.parametrize("status", [401, 403])
def test_mcp_rejected_credentials(status):
    msg = describe_mcp_error(nested(http_error(status)), URL)
    assert f"rejected the credentials (HTTP {status})" in msg
    assert "CDATA_USERNAME" in msg and "CDATA_PAT" in msg


def test_mcp_404_points_at_the_url():
    assert "Check CDATA_MCP_URL" in describe_mcp_error(http_error(404), URL)


def test_mcp_other_status():
    assert "returned HTTP 500" in describe_mcp_error(http_error(500), URL)


def test_mcp_session_terminated_means_bad_url():
    # The MCP SDK turns an HTTP 404 into this.
    exc = McpError(ErrorData(code=-1, message="Session terminated"))
    msg = describe_mcp_error(nested(exc), URL)
    assert "Session terminated" in msg and "CDATA_MCP_URL" in msg


def test_mcp_unreachable_host():
    exc = httpx.ConnectError("All connection attempts failed", request=REQUEST)
    msg = describe_mcp_error(nested(exc), URL)
    assert msg.startswith(f"Could not reach the Connect AI MCP server at {URL}")


def test_mcp_unrelated_error_is_not_described():
    assert describe_mcp_error(KeyError("x"), URL) is None


@pytest.mark.parametrize(
    "exc, expected",
    [
        (provider_error(openai.AuthenticationError, 401), "rejected the API key"),
        (provider_error(anthropic.AuthenticationError, 401), "rejected the API key"),
        (provider_error(openai.PermissionDeniedError, 403), "rejected the API key"),
        (provider_error(openai.NotFoundError, 404), "does not recognise"),
        (provider_error(openai.RateLimitError, 429), "rate limiting"),
        (provider_error(openai.InternalServerError, 500), "returned HTTP 500"),
    ],
)
def test_llm_errors(exc, expected):
    msg = describe_llm_error(exc, "openai:gpt-4o", "OPENAI_API_KEY")
    assert expected in msg
    assert "LLM_MODEL=openai:gpt-4o" in msg


def test_llm_bad_key_names_the_variable():
    exc = provider_error(openai.AuthenticationError, 401)
    assert "Check OPENAI_API_KEY" in describe_llm_error(exc, "openai:gpt-4o", "OPENAI_API_KEY")
    assert "the provider's API key" in describe_llm_error(exc, "ollama:x", None)


def test_llm_non_http_error_is_not_described():
    assert describe_llm_error(KeyError("x"), "openai:gpt-4o", "OPENAI_API_KEY") is None
