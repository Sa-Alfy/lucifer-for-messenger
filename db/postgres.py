"""
db/postgres.py — asyncpg connection pool with retry-on-startup.

Supabase and Render cold starts can both produce transient connection failures.
tenacity retries up to 5 times with exponential backoff before raising,
which prevents a single flaky network tick from killing the whole boot sequence.
"""

import asyncpg
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    before_sleep_log,
)

from utils.logger import get_logger

logger = get_logger(__name__)

_pool: asyncpg.Pool | None = None


@retry(
    stop=stop_after_attempt(5),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    before_sleep=before_sleep_log(logger, 30),  # 30 = logging.WARNING
)
async def _create_pool(dsn: str) -> asyncpg.Pool:
    """Attempt to create the asyncpg pool; retried by tenacity on any exception."""
    return await asyncpg.create_pool(dsn, min_size=1, max_size=10)


async def init_pool(dsn: str) -> None:
    """
    Initialise the global pool.
    Called once during application startup lifespan.
    Logs success WITHOUT echoing the DSN (it contains credentials).
    """
    global _pool
    logger.info("Postgres: initialising connection pool…")
    _pool = await _create_pool(dsn)
    logger.info("Postgres: pool ready.")


async def close_pool() -> None:
    """Gracefully close the pool. Called during application shutdown lifespan."""
    global _pool
    if _pool:
        await _pool.close()
        _pool = None
        logger.info("Postgres: pool closed.")


async def ping() -> bool:
    """
    Health-check: run a trivial query to confirm the pool is live.
    Returns True on success, False on any exception — never raises.
    """
    try:
        async with _pool.acquire() as conn:
            await conn.fetchval("SELECT 1")
        return True
    except Exception as exc:
        logger.warning("Postgres ping failed: %s", exc)
        return False


def get_pool() -> asyncpg.Pool:
    """
    Return the initialised pool for use in request handlers.
    Raises RuntimeError immediately if init_pool() was never called — fail loud.
    """
    if _pool is None:
        raise RuntimeError(
            "Postgres pool has not been initialised. "
            "Call db.postgres.init_pool() during application startup."
        )
    return _pool
