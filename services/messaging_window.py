"""
services/messaging_window.py — Redis-backed 24-hour messaging window tracker.

Facebook Messenger enforces a 24-hour window: a page may only send standard
messages to a user within 24 hours of the user's last inbound message.
Attempting to send outside that window fails with a specific API error.

This module tracks per-user activity in Redis so Phase 3+ code can check
before sending proactive or cross-window messages.

Key design choices:
  - Redis (not in-memory): survives process restarts and works across multiple
    Render instances if we ever scale horizontally.
  - TTL is set by Redis, not application code — no cron job needed, the key
    naturally expires after 24 hours of inactivity.
  - mark_user_active resets the TTL on every call (SETEX semantics via ex=),
    so the window slides correctly: it's always 24h from the *last* message.
"""

WINDOW_SECONDS = 24 * 60 * 60  # 86 400 — matches Facebook's standard window


async def mark_user_active(redis, psid: str) -> None:
    """
    Record that the user sent a message now, resetting their 24-hour window.

    Must be called every time a real inbound message is processed — not on
    echoes, delivery receipts, or read receipts.

    Args:
        redis: The initialised redis.asyncio.Redis client.
        psid:  The user's Page-Scoped ID.
    """
    await redis.set(f"messaging_window:{psid}", "1", ex=WINDOW_SECONDS)


async def is_within_window(redis, psid: str) -> bool:
    """
    Return True if the user sent a message within the last 24 hours.

    Not called anywhere in Phase 2 — the echo bot always replies immediately
    within the window. Exposed here so Phase 3+ proactive / scheduled logic
    can check window status before attempting sends.

    Args:
        redis: The initialised redis.asyncio.Redis client.
        psid:  The user's Page-Scoped ID.
    """
    return await redis.exists(f"messaging_window:{psid}") == 1
