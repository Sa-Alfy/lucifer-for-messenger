"""
services/feature_flags.py — Postgres-backed feature flag lookup.

Why direct Postgres and not a Redis cache?
  At current traffic levels, the query is a primary-key
  lookup that Postgres serves in under a millisecond.  Adding a Redis cache
  layer would mean managing invalidation logic with zero observable benefit.
  Cache it when metrics show it's actually a bottleneck — not before.

The connection is expected to be an already-acquired asyncpg connection so this
function can be called inside an existing transaction without nested pool
acquisitions.  See event_processor.py for usage.
"""

from utils.logger import get_logger

logger = get_logger(__name__)


async def is_feature_enabled(conn, key: str) -> bool:
    """
    Return True if the given feature flag is enabled in Postgres.

    A missing row is treated as disabled — the caller should always seed the
    table with a sensible default (see migrations/0001_init.sql).

    Args:
        conn: An asyncpg Connection (or compatible async DB connection).
        key:  The feature flag key, e.g. "ai_chat".

    Returns:
        True if the flag exists and is enabled, False otherwise.
    """
    row = await conn.fetchrow(
        "SELECT enabled FROM feature_flags WHERE key = $1",
        key,
    )
    enabled = bool(row and row["enabled"])
    logger.debug("Feature flag '%s' = %s", key, enabled)
    return enabled
