"""Live configuration for demos: rebuild the agent when .env changes.

compose.yaml mounts the project at /workspace, so the app can see .env change
on the host. When it does, the agent is rebuilt in place: no container
restart, and requests already running finish on the agent they started with.
Without the mount (on Render, say) none of this runs.

Polls instead of using file events, which don't cross the VM boundary on
Colima, and compares contents rather than mtimes, since editors that save by
replacing the file can leave the mtime looking unchanged through a mount.
"""

import asyncio
import hashlib
import importlib.util
import logging
import os
import time
from pathlib import Path
from urllib.parse import urlparse

from dotenv import dotenv_values

from app.agent import build_agent
from app.config import load_settings

log = logging.getLogger("uvicorn.error")

WORKSPACE = Path(os.environ.get("LIVE_WORKSPACE", "/workspace"))
ENV_FILE = WORKSPACE / ".env"
# compose.yaml sets these under `environment:`, which must keep winning over .env.
PINNED = {"DATABASE_URL", "WATCHFILES_FORCE_POLLING", "LIVE_WORKSPACE"}
GATEWAY_HOST = "cloud.cdata.com"


def describe(settings, tool_names) -> dict:
    """What the header shows: where model calls go and what the agent can touch.

    Never includes a key, only what kind of key it is.
    """
    provider = settings.llm_provider
    base_var = "ANTHROPIC_BASE_URL" if provider == "anthropic" else "OPENAI_BASE_URL"
    base_url = os.environ.get(base_var, "")
    key = os.environ.get(settings.llm_key_var or "", "")
    parsed = urlparse(base_url)
    if not base_url:
        via = {"anthropic": "Anthropic API", "openai": "OpenAI API"}.get(provider, provider)
    elif parsed.hostname == GATEWAY_HOST and parsed.path.startswith("/gateway"):
        via = "Connect AI LLM Gateway"
    else:
        via = parsed.hostname or base_url
    return {
        "via": via,
        "gateway": via == "Connect AI LLM Gateway",
        "key_kind": "virtual key" if key.startswith("cgw_") else "provider key",
        "model": settings.llm_model.split(":", 1)[-1],
        "tools": len(tool_names),
        "tool_names": list(tool_names),
        "read_only": not ({"execute_insert", "execute_update", "executeProcedure"} & set(tool_names)),
    }


def apply_env(values: dict, previous_keys: set[str]) -> set[str]:
    """Make os.environ match the file: set what it has, drop what it lost."""
    for key in previous_keys - values.keys() - PINNED:
        os.environ.pop(key, None)
    for key, value in values.items():
        if key not in PINNED and value is not None:
            os.environ[key] = value
    return set(values)


async def rebuild(app, checkpointer) -> None:
    """Swap in an agent built from the current environment, or keep the old one."""
    try:
        settings = load_settings()
        agent, tool_names, llm = await build_agent(settings, checkpointer)
    except Exception as exc:  # a bad edit must not take the app down
        app.state.live_error = str(exc)
        log.error("Reload from .env failed, keeping the previous agent: %s", exc)
        return
    publish(app, settings, agent, tool_names, llm)
    log.info("Reloaded from .env: %s", app.state.route)


def publish(app, settings, agent, tool_names, llm) -> None:
    """Make an agent the one requests use, along with what /status reports."""
    app.state.settings = settings
    app.state.agent = agent
    app.state.tool_names = tool_names
    app.state.llm = llm  # also used for follow-up suggestions
    app.state.route = describe(settings, tool_names)
    app.state.served_model = None
    app.state.live_error = None
    app.state.reloaded_at = time.time()


def switch_stage(stage: str) -> list[str]:
    """Run demo/stage.py's switch from inside the container; returns the diff."""
    path = WORKSPACE / "demo" / "stage.py"
    spec = importlib.util.spec_from_file_location("demo_stage", path)
    if spec is None or not path.exists():
        raise FileNotFoundError(f"{path} not found: is the project mounted at {WORKSPACE}?")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.switch(stage)


def _digest(path: Path) -> str | None:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return None


async def watch_env(app, checkpointer, interval: float = 0.5) -> None:
    digest = _digest(ENV_FILE)
    if digest is None:
        log.info("No %s: live reload is off", ENV_FILE)
        return
    keys = set(dotenv_values(ENV_FILE))
    log.info("Live reload on: watching %s", ENV_FILE)
    while True:
        await asyncio.sleep(interval)
        current = _digest(ENV_FILE)
        if current is None or current == digest:
            continue
        await asyncio.sleep(0.3)  # let a multi-step save finish
        current = _digest(ENV_FILE)
        if current is None:
            continue
        digest = current
        keys = apply_env(dotenv_values(ENV_FILE), keys)
        await rebuild(app, checkpointer)
