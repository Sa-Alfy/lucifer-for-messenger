"""
services/task_registry.py — In-flight asyncio.Task registry for graceful shutdown.

Why this exists:
  FastAPI's BackgroundTasks.add_task() queues coroutines but does not expose
  the underlying asyncio.Task objects, so there is no way to await them during
  shutdown.  This module replaces the add_task() call with asyncio.create_task()
  and registers every task in a module-level set, allowing the lifespan shutdown
  to wait for all in-flight work to complete before closing the DB pool and Redis
  client.

What this solves:
  A clean SIGTERM (Render deploy) can now drain in-flight tasks before tearing
  down connections.  Without this, a background task mid-download or mid-AI-call
  would have its DB/Redis connection closed underneath it, producing confusing
  connection-closed errors rather than a clean finish or a clean log entry.

What this does NOT solve:
  A SIGKILL after the grace period, or a hard crash, still loses in-flight work.
  This is not a durable queue.  That trade-off is explicitly accepted — see the
  webhook event receiver documentation for the rationale.

Thread safety:
  All callers run on the same asyncio event loop (single-threaded), so no
  locking is required.
"""

import asyncio

from utils.logger import get_logger

logger = get_logger(__name__)

_in_flight: set[asyncio.Task] = set()


def register_task(coro) -> asyncio.Task:
    """
    Schedule *coro* as an asyncio.Task and register it for shutdown tracking.

    The task is automatically removed from the registry when it finishes
    (success, exception, or cancellation).

    Args:
        coro: An awaitable coroutine object.

    Returns:
        The created asyncio.Task.
    """
    task = asyncio.create_task(coro)
    _in_flight.add(task)
    task.add_done_callback(_in_flight.discard)
    return task


async def wait_for_shutdown(timeout: float) -> None:
    """
    Wait for all in-flight tasks to finish, up to *timeout* seconds.

    Called during lifespan shutdown BEFORE closing DB and Redis connections,
    so any task that is mid-query gets to finish cleanly.

    Logs how many tasks were pending and whether any exceeded the timeout.
    Does not cancel timed-out tasks — we let the process exit naturally after
    the lifespan completes, and the event loop cleanup handles them.

    Args:
        timeout: Maximum seconds to wait.  90s is the default — enough for a
                 yt-dlp probe + download of a long-ish video on a slow connection.
                 See main.py for the rationale.
    """
    pending = list(_in_flight)
    if not pending:
        logger.info("Shutdown: no in-flight tasks — proceeding immediately.")
        return

    logger.info(
        "Shutdown: waiting for %d in-flight task(s) (timeout=%.0fs)…",
        len(pending),
        timeout,
    )
    done, still_pending = await asyncio.wait(pending, timeout=timeout)

    if still_pending:
        logger.warning(
            "Shutdown: %d task(s) did not finish within %.0fs — proceeding anyway.  "
            "Work may be incomplete.",
            len(still_pending),
            timeout,
        )
    else:
        logger.info(
            "Shutdown: all %d in-flight task(s) finished cleanly.",
            len(done),
        )
