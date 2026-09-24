import logging
import secrets
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

import psycopg
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from langchain_core.messages import HumanMessage
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from psycopg.conninfo import conninfo_to_dict
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool
from pydantic import BaseModel, Field

from app.agent import build_agent
from app.config import load_settings
from app.errors import SetupError, describe_llm_error, describe_mcp_error

log = logging.getLogger("uvicorn.error")
CHAT_PAGE = Path(__file__).parent / "static" / "index.html"


async def _check_database(url: str) -> None:
    # Fail fast with the real reason. Otherwise the pool retries quietly and
    # startup dies 30 seconds later with an uninformative PoolTimeout.
    try:
        host = conninfo_to_dict(url).get("host", "localhost")
        conn = await psycopg.AsyncConnection.connect(url, connect_timeout=10)
    except psycopg.Error as exc:
        reason = str(exc).strip().splitlines()[-1] if str(exc).strip() else type(exc).__name__
        raise SetupError(
            f"Could not connect to Postgres ({reason}). Check DATABASE_URL; "
            "locally, start the database with `docker compose up -d db`."
        ) from None
    await conn.close()
    log.info("Connected to Postgres at %s", host)


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        settings = load_settings()
        await _check_database(settings.database_url)
    except SetupError as exc:
        log.error("Startup failed: %s", exc)
        raise
    pool = AsyncConnectionPool(
        conninfo=settings.database_url,
        max_size=10,
        open=False,
        kwargs={"autocommit": True, "prepare_threshold": 0, "row_factory": dict_row},
    )
    async with pool:
        checkpointer = AsyncPostgresSaver(pool)
        await checkpointer.setup()  # creates checkpoint tables on first boot
        try:
            agent, tool_names = await build_agent(settings, checkpointer)
        except SetupError as exc:
            log.error("Startup failed: %s", exc)
            raise
        app.state.settings = settings
        app.state.agent = agent
        app.state.tool_names = tool_names
        yield


app = FastAPI(title="Connect AI Agent on Render", lifespan=lifespan)


# auto_error=False so a missing header returns 401, not FastAPI's default 403.
bearer = HTTPBearer(auto_error=False, description="Paste the APP_API_KEY value")


def require_api_key(
    request: Request,
    creds: HTTPAuthorizationCredentials | None = Depends(bearer),
) -> None:
    expected = request.app.state.settings.app_api_key
    supplied = creds.credentials if creds else ""
    if not secrets.compare_digest(supplied, expected):
        raise HTTPException(status_code=401, detail="Unauthorized: send APP_API_KEY as a bearer token")


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    thread_id: str | None = None


class ChatResponse(BaseModel):
    thread_id: str
    reply: str


def _text(content) -> str:
    # Some model providers return a list of content blocks instead of a string.
    if isinstance(content, str):
        return content
    return "".join(
        block.get("text", "") for block in content if isinstance(block, dict)
    )


@app.get("/", include_in_schema=False)
async def root():
    return FileResponse(CHAT_PAGE)


@app.get("/healthz")
async def healthz(request: Request):
    return {
        "status": "ok",
        "mcp_tools": len(request.app.state.tool_names),
        "llm_model": request.app.state.settings.llm_model,
    }


@app.get("/tools", dependencies=[Depends(require_api_key)])
async def tools(request: Request):
    return {"tools": request.app.state.tool_names}


@app.post("/chat", response_model=ChatResponse, dependencies=[Depends(require_api_key)])
async def chat(body: ChatRequest, request: Request):
    settings = request.app.state.settings
    thread_id = body.thread_id or str(uuid.uuid4())
    try:
        result = await request.app.state.agent.ainvoke(
            {"messages": [HumanMessage(content=body.message)]},
            config={"configurable": {"thread_id": thread_id}},
        )
    except Exception as exc:
        # Errors inside a tool (bad SQL, unknown table) never reach here: the
        # MCP adapter returns them to the model, which can correct itself.
        # What does reach here is a failure the operator has to fix.
        detail = describe_mcp_error(exc, settings.cdata_mcp_url) or describe_llm_error(
            exc, settings.llm_model, settings.llm_key_var
        )
        log.exception("Chat request failed: %s", detail or "unexpected error")
        raise HTTPException(
            status_code=502,
            detail=detail or f"The agent failed ({type(exc).__name__}). See the service logs.",
        ) from None
    return ChatResponse(thread_id=thread_id, reply=_text(result["messages"][-1].content))
