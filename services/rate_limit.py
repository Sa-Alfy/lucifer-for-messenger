"""
services/rate_limit.py — Per-user Redis sliding-window request throttle.

Purpose: prevent a single user (or a runaway reply loop) from exhausting the
daily Groq API quota.  This is independent of Groq's own rate limiting — both
layers can coexist.

Algorithm:
  On each call, INCR the user's counter key.  If it's a brand-new key (count
  returned 1), set its TTL to RATE_LIMIT_WINDOW_SECONDS.  This gives a fixed
  window (not a strict sliding window), but it is simple, O(1) in Redis, and
  accurate enough for burst protection at this scale.

  A true sliding window (sorted-set timestamps in Redis) would eliminate the
  burst ambiguity at window boundaries, at the cost of 2–3 Redis operations
  per request and more key-management code.  The fixed-window approach is
  sufficient for single-page-bot traffic: the worst-case burst a user can
  achieve is 2× the limit in the first second of a new window, which is an
  acceptable tradeoff at this scale.  Revisit if quota overage on the Groq
  side becomes a real operational problem.
"""

from utils.logger import get_logger

logger = get_logger(__name__)

# ── Configuration ─────────────────────────────────────────────────────────────

RATE_LIMIT_WINDOW_SECONDS = 60   # Reset counter every 60 seconds
RATE_LIMIT_MAX_REQUESTS = 8      # Max messages per user per window


# ── Public API ────────────────────────────────────────────────────────────────

async def is_rate_limited(redis, psid: str) -> bool:
    """
    Increment the request counter for this user and return True if they have
    exceeded RATE_LIMIT_MAX_REQUESTS within the current window.

    The first INCR for a new key also sets the TTL — counter resets
    automatically after RATE_LIMIT_WINDOW_SECONDS with no cron job.

    Args:
        redis: Initialised redis.asyncio.Redis client (decode_responses=True).
        psid:  The user's Page-Scoped ID.

    Returns:
        True  → caller should send the rate-limit message and skip AI.
        False → request is within limits; proceed.
    """
    key = f"rate_limit:{psid}"
    count = await redis.incr(key)
    if count == 1:
        # First request in this window — arm the expiry.
        await redis.expire(key, RATE_LIMIT_WINDOW_SECONDS)
    limited = count > RATE_LIMIT_MAX_REQUESTS
    if limited:
        logger.debug(
            "Rate limit hit: psid=%s count=%d limit=%d window=%ds",
            psid, count, RATE_LIMIT_MAX_REQUESTS, RATE_LIMIT_WINDOW_SECONDS,
        )
    return limited
