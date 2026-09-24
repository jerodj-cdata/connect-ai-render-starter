"""Delete conversations nobody has touched in a while.

Conversation history includes query results, so it holds enterprise data.
Keeping it only as long as it is useful limits what a database leak exposes.
"""
import asyncio
import logging

log = logging.getLogger("uvicorn.error")

# LangGraph's checkpoints table has no timestamp column; each checkpoint's
# JSON carries an ISO "ts". A thread's age is its newest checkpoint's.
STALE_THREADS = """
SELECT thread_id FROM checkpoints
GROUP BY thread_id
HAVING max((checkpoint->>'ts')::timestamptz) < now() - make_interval(days => %s)
"""


async def purge_stale_threads(pool, checkpointer, days: int) -> int:
    async with pool.connection() as conn:
        rows = await (await conn.execute(STALE_THREADS, (days,))).fetchall()
    for row in rows:
        await checkpointer.adelete_thread(row["thread_id"])
    return len(rows)


async def retention_loop(pool, checkpointer, days: int, every_seconds: int = 86_400) -> None:
    """Purge at startup, then once a day. Failures are logged, never fatal."""
    while True:
        try:
            deleted = await purge_stale_threads(pool, checkpointer, days)
            if deleted:
                log.info("Deleted %d conversations idle for over %d days", deleted, days)
        except Exception:
            log.exception("Conversation cleanup failed; will retry")
        await asyncio.sleep(every_seconds)
