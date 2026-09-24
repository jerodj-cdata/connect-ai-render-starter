import base64
import os
from dataclasses import dataclass

from app.errors import SetupError

# API key variable for each provider requirements.txt installs. To add one,
# add its langchain-<provider> package to requirements.in and a line here.
LLM_API_KEYS = {
    "openai": "OPENAI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
}


def _env(name: str, default: str = "") -> str:
    # Strip: a value pasted into Render with a trailing newline otherwise
    # breaks auth in ways that are hard to spot.
    return os.environ.get(name, default).strip()


def _required(name: str) -> str:
    value = _env(name)
    if not value:
        raise SetupError(f"Missing required environment variable: {name}")
    return value


@dataclass(frozen=True)
class Settings:
    cdata_username: str
    cdata_pat: str
    cdata_mcp_url: str
    database_url: str
    llm_model: str
    app_api_key: str

    @property
    def llm_provider(self) -> str:
        return self.llm_model.split(":", 1)[0]

    @property
    def llm_key_var(self) -> str | None:
        return LLM_API_KEYS.get(self.llm_provider)

    @property
    def mcp_auth_header(self) -> str:
        # Connect AI MCP uses HTTP Basic auth: base64("email:PAT")
        raw = f"{self.cdata_username}:{self.cdata_pat}".encode()
        return "Basic " + base64.b64encode(raw).decode()


def _check_llm(model: str) -> None:
    provider, sep, name = model.partition(":")
    if not (sep and provider and name):
        raise SetupError(
            f"LLM_MODEL={model!r} must look like provider:model, "
            "e.g. openai:gpt-4o or anthropic:claude-sonnet-5"
        )
    key_var = LLM_API_KEYS.get(provider)
    if key_var and not _env(key_var):
        raise SetupError(
            f"LLM_MODEL={model} needs {key_var}, which is not set. Set it, or "
            "point LLM_MODEL at a provider you have a key for."
        )


def load_settings() -> Settings:
    settings = Settings(
        cdata_username=_required("CDATA_USERNAME"),
        cdata_pat=_required("CDATA_PAT"),
        cdata_mcp_url=_env("CDATA_MCP_URL", "https://mcp.cloud.cdata.com/mcp"),
        database_url=_required("DATABASE_URL"),
        llm_model=_env("LLM_MODEL", "openai:gpt-4o"),
        app_api_key=_required("APP_API_KEY"),
    )
    _check_llm(settings.llm_model)
    return settings
