"""
services/admin.py — Messenger-native admin controls (Phase 6a).

Claim flow, admin authorization, feature-flag toggling, user blocking,
and quick stats for in-chat admin commands and quick replies.
"""

import hmac

from config import settings

ADMIN_CLAIM_MAX_ATTEMPTS = 5
ADMIN_CLAIM_WINDOW_SECONDS = 3600


async def is_admin_claim_rate_limited(redis, psid: str) -> bool:
    key = f"admin_claim_attempts:{psid}"
    count = await redis.incr(key)
    if count == 1:
        await redis.expire(key, ADMIN_CLAIM_WINDOW_SECONDS)
    return count > ADMIN_CLAIM_MAX_ATTEMPTS


async def claim_admin(pool, psid: str, provided_secret: str) -> bool:
    if not settings.admin_bootstrap_secret or not provided_secret:
        return False
    if not hmac.compare_digest(provided_secret, settings.admin_bootstrap_secret):
        return False
    async with pool.acquire() as conn:
        await conn.execute("UPDATE users SET is_admin = true WHERE psid = $1", psid)
    return True


async def is_admin(pool, psid: str) -> bool:
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT is_admin FROM users WHERE psid = $1", psid)
    return bool(row and row["is_admin"])


async def list_flags(pool) -> list[dict]:
    async with pool.acquire() as conn:
        rows = await conn.fetch("SELECT key, enabled FROM feature_flags ORDER BY key")
    return [dict(row) for row in rows]


async def toggle_flag(pool, key: str) -> bool:
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "UPDATE feature_flags SET enabled = NOT enabled, updated_at = now() "
            "WHERE key = $1 RETURNING enabled",
            key,
        )
    if row is None:
        raise ValueError(f"Unknown flag '{key}'")
    return row["enabled"]


async def set_block_status(pool, target_psid: str, blocked: bool) -> bool:
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "UPDATE users SET is_blocked = $1 WHERE psid = $2 RETURNING psid",
            blocked, target_psid,
        )
    return row is not None


async def get_stats_dict(pool) -> dict:
    async with pool.acquire() as conn:
        total_users = await conn.fetchval("SELECT COUNT(*) FROM users")
        new_today = await conn.fetchval(
            "SELECT COUNT(*) FROM users WHERE first_seen_at::date = CURRENT_DATE"
        )
        active_7d = await conn.fetchval(
            "SELECT COUNT(*) FROM users WHERE last_seen_at >= now() - interval '7 days'"
        )
        messages_today = await conn.fetchval(
            "SELECT COUNT(*) FROM processed_webhook_events "
            "WHERE processed_at::date = CURRENT_DATE"
        )
        blocked = await conn.fetchval("SELECT COUNT(*) FROM users WHERE is_blocked = true")
        admins = await conn.fetchval("SELECT COUNT(*) FROM users WHERE is_admin = true")
        persona_rows = await conn.fetch(
            "SELECT persona, COUNT(*) AS count FROM users GROUP BY persona ORDER BY count DESC"
        )
    return {
        "total_users": total_users,
        "new_today": new_today,
        "active_last_7_days": active_7d,
        "messages_today": messages_today,
        "blocked_users": blocked,
        "admin_users": admins,
        "persona_distribution": {row["persona"]: row["count"] for row in persona_rows},
    }


async def get_quick_stats(pool) -> str:
    stats = await get_stats_dict(pool)
    return (
        f"Bot stats\n"
        f"Total users: {stats['total_users']}\n"
        f"New today: {stats['new_today']}\n"
        f"Messages today: {stats['messages_today']}\n"
        f"Blocked users: {stats['blocked_users']}"
    )


async def list_users(
    pool, search: str | None, blocked_only: bool, page: int, page_size: int = 25
) -> dict:
    offset = (page - 1) * page_size
    conditions, params = [], []
    if search:
        conditions.append(f"psid ILIKE ${len(params) + 1}")
        params.append(f"%{search}%")
    if blocked_only:
        conditions.append("is_blocked = true")
    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    async with pool.acquire() as conn:
        total = await conn.fetchval(f"SELECT COUNT(*) FROM users {where}", *params)
        rows = await conn.fetch(
            f"SELECT psid, persona, message_count, last_seen_at, is_blocked, is_admin "
            f"FROM users {where} ORDER BY last_seen_at DESC "
            f"LIMIT ${len(params) + 1} OFFSET ${len(params) + 2}",
            *params, page_size, offset,
        )
    return {"total": total, "page": page, "page_size": page_size, "users": [dict(r) for r in rows]}
