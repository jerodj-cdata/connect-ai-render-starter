import pytest

from app.config import load_settings
from app.errors import SetupError

REQUIRED = {
    "CDATA_USERNAME": "user@example.com",
    "CDATA_PAT": "pat",
    "DATABASE_URL": "postgresql://localhost/agent",
    "OPENAI_API_KEY": "sk-test",
}


@pytest.fixture
def env(monkeypatch):
    for name, value in REQUIRED.items():
        monkeypatch.setenv(name, value)
    return monkeypatch


def test_defaults(env):
    s = load_settings()
    assert s.llm_model == "openai:gpt-4o"
    assert s.cdata_mcp_url == "https://mcp.cloud.cdata.com/mcp"
    assert s.app_api_key == ""


@pytest.mark.parametrize("name", ["CDATA_USERNAME", "CDATA_PAT", "DATABASE_URL"])
def test_missing_required_variable_is_named(env, name):
    env.delenv(name)
    with pytest.raises(SetupError, match=f"Missing required environment variable: {name}"):
        load_settings()


def test_whitespace_only_counts_as_missing(env):
    env.setenv("CDATA_PAT", "  \n")
    with pytest.raises(SetupError, match="CDATA_PAT"):
        load_settings()


def test_values_are_stripped(env):
    # A PAT pasted into Render with a trailing newline must still authenticate.
    env.setenv("CDATA_PAT", "pat\n")
    env.setenv("CDATA_MCP_URL", " https://example.com/mcp ")
    env.setenv("LLM_MODEL", "openai:gpt-4o\n")
    s = load_settings()
    assert (s.cdata_pat, s.cdata_mcp_url, s.llm_model) == (
        "pat", "https://example.com/mcp", "openai:gpt-4o",
    )


def test_mcp_auth_header_is_basic_email_pat(env):
    # base64("user@example.com:pat")
    assert load_settings().mcp_auth_header == "Basic dXNlckBleGFtcGxlLmNvbTpwYXQ="


@pytest.mark.parametrize("model", ["gpt-4o", "openai:", ":gpt-4o"])
def test_malformed_llm_model(env, model):
    env.setenv("LLM_MODEL", model)
    with pytest.raises(SetupError, match="must look like provider:model"):
        load_settings()


def test_missing_provider_key_names_the_variable(env):
    env.setenv("LLM_MODEL", "anthropic:claude-sonnet-5")
    with pytest.raises(SetupError, match="needs ANTHROPIC_API_KEY"):
        load_settings()


def test_only_the_selected_providers_key_is_required(env):
    env.delenv("OPENAI_API_KEY")
    env.setenv("LLM_MODEL", "anthropic:claude-sonnet-5")
    env.setenv("ANTHROPIC_API_KEY", "sk-ant")
    s = load_settings()
    assert (s.llm_provider, s.llm_key_var) == ("anthropic", "ANTHROPIC_API_KEY")


@pytest.mark.parametrize("raw, days", [(None, 30), ("7", 7), (" 90 ", 90), ("0", 0)])
def test_retention_days(env, raw, days):
    if raw is not None:
        env.setenv("CONVERSATION_RETENTION_DAYS", raw)
    assert load_settings().retention_days == days


@pytest.mark.parametrize("raw", ["-1", "thirty", "1.5"])
def test_invalid_retention_days(env, raw):
    env.setenv("CONVERSATION_RETENTION_DAYS", raw)
    with pytest.raises(SetupError, match="CONVERSATION_RETENTION_DAYS.*whole number"):
        load_settings()


def test_unknown_provider_skips_the_key_check(env):
    # Providers outside LLM_API_KEYS are left to init_chat_model to validate.
    env.setenv("LLM_MODEL", "ollama:qwen3")
    s = load_settings()
    assert s.llm_key_var is None


@pytest.mark.parametrize("raw, expected", [
    (None, True), ("true", True), ("0", False), (" OFF ", False), ("yes", True),
])
def test_suggest_followups_flag(env, raw, expected):
    if raw is not None:
        env.setenv("SUGGEST_FOLLOWUPS", raw)
    assert load_settings().suggest_followups is expected


def test_invalid_suggest_followups_flag(env):
    env.setenv("SUGGEST_FOLLOWUPS", "maybe")
    with pytest.raises(SetupError, match="SUGGEST_FOLLOWUPS='maybe' must be true or false"):
        load_settings()
