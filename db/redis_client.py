"""
db/redis_client.py — Redis async client with retry-on-startup.

Uses redis.asyncio.from_url (redis-py ≥ 5.0).
Same retry discipline as postgres.py — transient Render/Redis cold-start
failures should not kill the boot sequence.
"""

import redis.asyncio as aioredis
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    before_sleep_log,
)

from utils.logger import get_logger

logger = get_logger(__name__)

_client: aioredis.Redis | None = None


@retry(
    stop=stop_after_attempt(5),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    before_sleep=before_sleep_log(logger, 30),  # 30 = logging.WARNING
)
async def _create_client(url: str) -> aioredis.Redis:
    """Create and verify the Redis client; retried by tenacity on any exception."""
    client = aioredis.from_url(url, decode_responses=True)
    # Probe the connection immediately so a bad URL fails here, not at first use.
    await client.ping()
    return client


async def init_redis(url: str) -> None:
    """
    Initialise the global Redis client.
    Called once during application startup lifespan.
    Does NOT log the URL — it may contain credentials.
    """
    global _client
    logger.info("Redis: initialising client…")
    _client = await _create_client(url)
    logger.info("Redis: client ready.")


async def close_redis() -> None:
    """Gracefully close the Redis connection. Called during shutdown lifespan."""
    global _client
    if _client:
        await _client.aclose()
        _client = None
        logger.info("Redis: connection closed.")


async def ping() -> bool:
    """
    Health-check: PING the Redis server.
    Returns True on success, False on any exception — never raises.
    """
    try:
        await _client.ping()
        return True
    except Exception as exc:
        logger.warning("Redis ping failed: %s", exc)
        return False


def get_redis() -> aioredis.Redis:
    """
    Return the initialised client for use in request handlers.
    Raises RuntimeError immediately if init_redis() was never called — fail loud.
    """
    if _client is None:
        raise RuntimeError(
            "Redis client has not been initialised. "
            "Call db.redis_client.init_redis() during application startup."
        )
    return _client
