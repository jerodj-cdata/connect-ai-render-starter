import asyncio
import contextlib
import json
import logging
import secrets
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

import psycopg
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from fastapi.staticfiles import StaticFiles
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from psycopg.conninfo import conninfo_to_dict
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool
from pydantic import BaseModel, Field

from app.agent import build_agent
from app.config import load_settings
from app.errors import SetupError, describe_llm_error, describe_mcp_error
from app.retention import retention_loop
from app.steps import current_turn, describe_step, queries_in
from app.suggest import suggest_followups

log = logging.getLogger("uvicorn.error")
STATIC = Path(__file__).parent / "static"
CHAT_PAGE = STATIC / "index.html"


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
    if not settings.app_api_key:
        log.warning(
            "APP_API_KEY is not set: /chat and /tools accept requests without a "
            "key. Fine on localhost; set it anywhere the service is reachable."
        )
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
            agent, tool_names, llm = await build_agent(settings, checkpointer)
        except SetupError as exc:
            log.error("Startup failed: %s", exc)
            raise
        app.state.settings = settings
        app.state.agent = agent
        app.state.tool_names = tool_names
        app.state.llm = llm  # also used for follow-up suggestions
        cleanup = None
        if settings.retention_days:
            cleanup = asyncio.create_task(
                retention_loop(pool, checkpointer, settings.retention_days)
            )
        try:
            yield
        finally:
            if cleanup:
                cleanup.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await cleanup


app = FastAPI(title="Connect AI Agent on Render", lifespan=lifespan)
# The chat page's scripts (vendored, so it needs no CDN).
app.mount("/static", StaticFiles(directory=STATIC), name="static")


# auto_error=False so a missing header returns 401, not FastAPI's default 403.
bearer = HTTPBearer(auto_error=False, description="Paste the APP_API_KEY value")


def require_api_key(
    request: Request,
    creds: HTTPAuthorizationCredentials | None = Depends(bearer),
) -> None:
    expected = request.app.state.settings.app_api_key
    if not expected:
        return  # auth disabled for local development; warned at startup
    supplied = creds.credentials if creds else ""
    if not secrets.compare_digest(supplied, expected):
        raise HTTPException(status_code=401, detail="Unauthorized: send APP_API_KEY as a bearer token")


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    thread_id: str | None = None


class Query(BaseModel):
    sql: str
    ok: bool


class ChatResponse(BaseModel):
    thread_id: str
    reply: str
    queries: list[Query] = Field(
        default_factory=list, description="SQL the agent ran for this reply"
    )


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
        # Tells the chat page whether to ask for APP_API_KEY.
        "auth_required": bool(request.app.state.settings.app_api_key),
    }


@app.get("/tools", dependencies=[Depends(require_api_key)])
async def tools(request: Request):
    return {"tools": request.app.state.tool_names}


def _describe_failure(exc: Exception, settings) -> str:
    # Errors inside a tool (bad SQL, unknown table) never reach here: the MCP
    # adapter returns them to the model, which can correct itself. What does
    # reach here is a failure the operator has to fix.
    detail = describe_mcp_error(exc, settings.cdata_mcp_url) or describe_llm_error(
        exc, settings.llm_model, settings.llm_key_var
    )
    log.exception("Chat request failed: %s", detail or "unexpected error")
    return detail or f"The agent failed ({type(exc).__name__}). See the service logs."


def _run(body: ChatRequest):
    thread_id = body.thread_id or str(uuid.uuid4())
    inputs = {"messages": [HumanMessage(content=body.message)]}
    return thread_id, inputs, {"configurable": {"thread_id": thread_id}}


@app.post("/chat", response_model=ChatResponse, dependencies=[Depends(require_api_key)])
async def chat(body: ChatRequest, request: Request):
    thread_id, inputs, config = _run(body)
    try:
        result = await request.app.state.agent.ainvoke(inputs, config=config)
    except Exception as exc:
        raise HTTPException(
            status_code=502, detail=_describe_failure(exc, request.app.state.settings)
        ) from None
    turn = current_turn(result["messages"])  # the checkpointer returns the whole thread
    return ChatResponse(
        thread_id=thread_id,
        reply=_text(result["messages"][-1].content),
        queries=queries_in(turn),
    )


@app.post(
    "/chat/stream",
    dependencies=[Depends(require_api_key)],
    response_class=StreamingResponse,
    responses={200: {"content": {"application/x-ndjson": {}}}},
)
async def chat_stream(body: ChatRequest, request: Request):
    """Like /chat, but streams progress as newline-delimited JSON events.

    `step` (id, tool, label, sql) when a tool call starts; `step_done`
    (id, ok) when it returns; then `done` (thread_id, reply, queries), or
    `error` (detail) if the run fails. After `done`, a `suggestions` event
    (items) may follow with up to three follow-up questions.
    """
    thread_id, inputs, config = _run(body)
    agent, settings = request.app.state.agent, request.app.state.settings

    async def events():
        def line(event: dict) -> str:
            return json.dumps(event) + "\n"

        # Sent first so proxies see bytes at once instead of timing out.
        yield line({"type": "start", "thread_id": thread_id})
        turn, reply = [], ""
        try:
            async for chunk in agent.astream(inputs, config=config, stream_mode="updates"):
                for update in chunk.values():
                    for msg in (update or {}).get("messages", []):
                        turn.append(msg)
                        if isinstance(msg, AIMessage) and msg.tool_calls:
                            for call in msg.tool_calls:
                                yield line({
                                    "type": "step",
                                    "id": call["id"],
                                    "tool": call["name"],
                                    "label": describe_step(call["name"], call["args"]),
                                    "sql": call["args"].get("query") if call["name"] == "queryData" else None,
                                })
                        elif isinstance(msg, AIMessage):
                            reply = _text(msg.content)
                        elif isinstance(msg, ToolMessage):
                            yield line({
                                "type": "step_done",
                                "id": msg.tool_call_id,
                                "ok": msg.status != "error",
                            })
        except Exception as exc:
            yield line({"type": "error", "detail": _describe_failure(exc, settings)})
            return
        queries = queries_in(turn)
        yield line({"type": "done", "thread_id": thread_id, "reply": reply, "queries": queries})
        # After `done`, so suggestions never delay the answer.
        llm = getattr(request.app.state, "llm", None)
        if settings.suggest_followups and llm is not None and reply:
            items = await suggest_followups(llm, body.message, reply, queries)
            if items:
                yield line({"type": "suggestions", "items": items})

    return StreamingResponse(
        events(),
        media_type="application/x-ndjson",
        # Stop reverse proxies from buffering the stream.
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
