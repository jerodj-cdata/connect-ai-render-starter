import asyncio
import logging

import pytest
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

from app.retention import purge_stale_threads, retention_loop

pytestmark = pytest.mark.db
CHECKPOINT_TABLES = ("checkpoints", "checkpoint_writes", "checkpoint_blobs")


async def _with_saver(url, fn):
    kwargs = {"autocommit": True, "prepare_threshold": 0, "row_factory": dict_row}
    async with AsyncConnectionPool(url, kwargs=kwargs, open=False) as pool:
        saver = AsyncPostgresSaver(pool)
        await saver.setup()
        return await fn(pool, saver)


async def _save_thread(saver, thread_id, ts):
    from langgraph.checkpoint.base import empty_checkpoint
    cp = {**empty_checkpoint(), "ts": ts, "channel_values": {"messages": ["x"]}}
    config = {"configurable": {"thread_id": thread_id, "checkpoint_ns": ""}}
    config = await saver.aput(config, cp, {"source": "input", "step": 0}, {"messages": 1})
    await saver.aput_writes(config, [("messages", "y")], task_id="t")


async def _rows(pool, thread_id):
    async with pool.connection() as conn:
        return {
            t: (await (await conn.execute(f"SELECT count(*) AS n FROM {t} WHERE thread_id = %s",
                                          (thread_id,))).fetchone())["n"]
            for t in CHECKPOINT_TABLES
        }


def test_deletes_only_threads_idle_past_the_limit(database_url):
    async def run(pool, saver):
        await _save_thread(saver, "old-thread", "2020-01-01T00:00:00+00:00")
        await _save_thread(saver, "recent-thread", "2099-01-01T00:00:00+00:00")
        # A thread with one stale and one recent checkpoint is still active.
        await _save_thread(saver, "mixed-thread", "2020-01-01T00:00:00+00:00")
        await _save_thread(saver, "mixed-thread", "2099-01-01T00:00:00+00:00")
        before = await _rows(pool, "old-thread")
        deleted = await purge_stale_threads(pool, saver, days=30)
        return before, deleted, [await _rows(pool, t) for t in ("old-thread", "recent-thread", "mixed-thread")]

    before, deleted, (old, recent, mixed) = asyncio.run(_with_saver(database_url, run))
    assert before["checkpoints"] and before["checkpoint_writes"]  # the fixture wrote rows
    assert deleted >= 1
    assert old == dict.fromkeys(CHECKPOINT_TABLES, 0)  # gone from every table
    assert recent["checkpoints"] and mixed["checkpoints"]


def test_loop_keeps_going_after_a_failure(database_url, caplog):
    class BrokenSaver:
        async def adelete_thread(self, thread_id):
            raise RuntimeError("boom")

    async def run(pool, saver):
        await _save_thread(saver, "old-thread-2", "2020-01-01T00:00:00+00:00")
        task = asyncio.create_task(retention_loop(pool, BrokenSaver(), days=30, every_seconds=0.05))
        await asyncio.sleep(0.2)
        alive = not task.done()
        task.cancel()
        return alive

    with caplog.at_level(logging.ERROR, logger="uvicorn.error"):
        assert asyncio.run(_with_saver(database_url, run)) is True
    assert caplog.text.count("Conversation cleanup failed") >= 2  # retried, never crashed
