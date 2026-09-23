import base64
import os
from dataclasses import dataclass


def _required(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
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
    def mcp_auth_header(self) -> str:
        # Connect AI MCP uses HTTP Basic auth: base64("email:PAT")
        raw = f"{self.cdata_username}:{self.cdata_pat}".encode()
        return "Basic " + base64.b64encode(raw).decode()


def load_settings() -> Settings:
    return Settings(
        cdata_username=_required("CDATA_USERNAME"),
        cdata_pat=_required("CDATA_PAT"),
        cdata_mcp_url=os.environ.get("CDATA_MCP_URL", "https://mcp.cloud.cdata.com/mcp"),
        database_url=_required("DATABASE_URL"),
        llm_model=os.environ.get("LLM_MODEL", "openai:gpt-4o"),
        app_api_key=_required("APP_API_KEY"),
    )
