import secrets
import uuid
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Request
from langchain_core.messages import HumanMessage
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool
from pydantic import BaseModel, Field

from app.agent import build_agent
from app.config import load_settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = load_settings()
    pool = AsyncConnectionPool(
        conninfo=settings.database_url,
        max_size=10,
        open=False,
        kwargs={"autocommit": True, "prepare_threshold": 0, "row_factory": dict_row},
    )
    async with pool:
        checkpointer = AsyncPostgresSaver(pool)
        await checkpointer.setup()  # creates checkpoint tables on first boot
        agent, tool_names = await build_agent(settings, checkpointer)
        app.state.settings = settings
        app.state.agent = agent
        app.state.tool_names = tool_names
        yield


app = FastAPI(title="Connect AI Agent on Render", lifespan=lifespan)


def require_api_key(request: Request) -> None:
    expected = f"Bearer {request.app.state.settings.app_api_key}"
    supplied = request.headers.get("authorization", "")
    if not secrets.compare_digest(supplied, expected):
        raise HTTPException(status_code=401, detail="Unauthorized")


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


@app.get("/healthz")
async def healthz(request: Request):
    return {"status": "ok", "mcp_tools": len(request.app.state.tool_names)}


@app.get("/tools", dependencies=[Depends(require_api_key)])
async def tools(request: Request):
    return {"tools": request.app.state.tool_names}


@app.post("/chat", response_model=ChatResponse, dependencies=[Depends(require_api_key)])
async def chat(body: ChatRequest, request: Request):
    thread_id = body.thread_id or str(uuid.uuid4())
    result = await request.app.state.agent.ainvoke(
        {"messages": [HumanMessage(content=body.message)]},
        config={"configurable": {"thread_id": thread_id}},
    )
    return ChatResponse(thread_id=thread_id, reply=_text(result["messages"][-1].content))
