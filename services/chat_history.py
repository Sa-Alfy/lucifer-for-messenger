"""
services/chat_history.py — Redis-backed sliding conversation window.

Design choices:
  - One Redis list per user (key: "chat_history:{psid}").
  - Every entry is a JSON-encoded {"role": ..., "content": ...} dict so it can
    be passed directly to the Groq messages list without any transformation.
  - LTRIM keeps the list at most HISTORY_MAX_ENTRIES long.  Older turns are
    dropped from the left, which is the correct direction (oldest first).
  - EXPIRE resets the TTL on every write: if a user is inactive for
    HISTORY_TTL_SECONDS their history key vanishes automatically — no cron job.
  - Image turns are stored as "[photo]" on the user side so the model has some
    context that a photo occurred without the full image payload being stored.
"""

import json

from utils.logger import get_logger

logger = get_logger(__name__)

# ── Configuration ─────────────────────────────────────────────────────────────

HISTORY_MAX_ENTRIES = 20                   # keep last 10 user+assistant pairs
HISTORY_TTL_SECONDS = 7 * 24 * 60 * 60    # 7 days of inactivity clears history


# ── Public API ────────────────────────────────────────────────────────────────

async def append_history(redis, psid: str, role: str, content: str) -> None:
    """
    Append a single message turn to the user's conversation history.

    The list is trimmed to HISTORY_MAX_ENTRIES after every write and the TTL
    is refreshed so idle users' history eventually expires on its own.

    Args:
        redis:   Initialised redis.asyncio.Redis client (decode_responses=True).
        psid:    The user's Page-Scoped ID — used as the Redis key suffix.
        role:    "user" or "assistant" — passed through to the AI messages list.
        content: The message text to store.
    """
    key = f"chat_history:{psid}"
    await redis.rpush(key, json.dumps({"role": role, "content": content}))
    # Trim to the last N entries (negative indices count from the right).
    await redis.ltrim(key, -HISTORY_MAX_ENTRIES, -1)
    # Reset inactivity TTL on every message.
    await redis.expire(key, HISTORY_TTL_SECONDS)
    logger.debug("History appended: psid=%s role=%s", psid, role)


async def get_history(redis, psid: str) -> list[dict]:
    """
    Retrieve the full conversation history for a user as a list of message dicts.

    Returns an empty list for users with no history (new users or after TTL
    expiry) — never raises.

    Args:
        redis: Initialised redis.asyncio.Redis client (decode_responses=True).
        psid:  The user's Page-Scoped ID.

    Returns:
        List of {"role": str, "content": str} dicts, oldest first.
    """
    key = f"chat_history:{psid}"
    raw: list[str] = await redis.lrange(key, 0, -1)
    return [json.loads(item) for item in raw]
