"""
Phase 6a admin controls — unit/integration tests for the self-verify checklist.
"""

import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost:5432/test")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")

from services.admin import (
    ADMIN_CLAIM_MAX_ATTEMPTS,
    claim_admin,
    get_quick_stats,
    is_admin_claim_rate_limited,
)
from services.event_processor import (
    handle_admin_command,
    handle_admin_quick_reply,
    process_messaging_event,
)


class FakeRedis:
    def __init__(self):
        self._data: dict[str, int] = {}
        self._ttl: dict[str, int] = {}

    async def incr(self, key: str) -> int:
        self._data[key] = self._data.get(key, 0) + 1
        return self._data[key]

    async def expire(self, key: str, seconds: int) -> None:
        self._ttl[key] = seconds


class FakeConn:
    def __init__(self, fetchrow_results=None, fetchval_results=None, fetch_results=None):
        self.fetchrow_results = list(fetchrow_results or [])
        self.fetchval_results = list(fetchval_results or [])
        self.fetch_results = list(fetch_results or [])
        self.executed: list[tuple] = []

    async def fetchrow(self, query, *args):
        if self.fetchrow_results:
            return self.fetchrow_results.pop(0)
        return None

    async def fetchval(self, query, *args):
        if self.fetchval_results:
            return self.fetchval_results.pop(0)
        return 0

    async def fetch(self, query, *args):
        if self.fetch_results:
            return self.fetch_results.pop(0)
        return []

    async def execute(self, query, *args):
        self.executed.append((query, args))


class FakeAcquire:
    def __init__(self, conn):
        self.conn = conn

    async def __aenter__(self):
        return self.conn

    async def __aexit__(self, *args):
        pass


class FakePool:
    def __init__(self, conn):
        self.conn = conn

    def acquire(self):
        return FakeAcquire(self.conn)


class FakeTransaction:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass


class FakeTxnConn(FakeConn):
    def transaction(self):
        return FakeTransaction()


@pytest.fixture
def bootstrap_secret(monkeypatch):
    monkeypatch.setattr("services.admin.settings.admin_bootstrap_secret", "super-secret-bootstrap")


@pytest.mark.asyncio
async def test_claim_success(bootstrap_secret):
    conn = FakeConn()
    pool = FakePool(conn)
    assert await claim_admin(pool, "psid1", "super-secret-bootstrap") is True
    assert "is_admin = true" in conn.executed[0][0]


@pytest.mark.asyncio
async def test_claim_wrong_secret_generic_message(bootstrap_secret):
    conn = FakeConn()
    pool = FakePool(conn)
    redis = FakeRedis()

    with patch("services.event_processor.send_text_message", new_callable=AsyncMock) as send:
        await handle_admin_command(pool, redis, "psid1", "/admin claim wrong-secret", None)
        send.assert_called_once_with("psid1", "Invalid or expired secret.")


@pytest.mark.asyncio
async def test_claim_success_message(bootstrap_secret):
    conn = FakeConn()
    pool = FakePool(conn)
    redis = FakeRedis()

    with patch("services.event_processor.send_text_message", new_callable=AsyncMock) as send:
        await handle_admin_command(
            pool, redis, "psid1", "/admin claim super-secret-bootstrap", None
        )
        send.assert_called_once_with("psid1", "You're now an admin.")


@pytest.mark.asyncio
async def test_claim_rate_limit_on_sixth_attempt(bootstrap_secret):
    redis = FakeRedis()
    conn = FakeConn()
    pool = FakePool(conn)

    for _ in range(ADMIN_CLAIM_MAX_ATTEMPTS):
        assert await is_admin_claim_rate_limited(redis, "psid1") is False

    assert await is_admin_claim_rate_limited(redis, "psid1") is True

    with patch("services.event_processor.send_text_message", new_callable=AsyncMock) as send:
        await handle_admin_command(
            pool, redis, "psid1", "/admin claim super-secret-bootstrap", None
        )
        send.assert_called_once_with("psid1", "Too many attempts — try again later.")


@pytest.mark.asyncio
async def test_non_admin_denied_for_admin_commands():
    conn = FakeConn(fetchrow_results=[{"is_admin": False}] * 3)
    pool = FakePool(conn)
    redis = FakeRedis()

    with patch("services.event_processor.send_text_message", new_callable=AsyncMock) as send:
        for text in ("/admin", "/admin stats", "/admin block victim123"):
            send.reset_mock()
            await handle_admin_command(pool, redis, "psid1", text, None)
            send.assert_called_once_with("psid1", "You're not authorized for admin commands.")


@pytest.mark.asyncio
async def test_admin_bare_command_shows_menu():
    conn = FakeConn(fetchrow_results=[{"is_admin": True}])
    pool = FakePool(conn)
    redis = FakeRedis()

    with patch("services.event_processor.send_quick_replies", new_callable=AsyncMock) as qr:
        await handle_admin_command(pool, redis, "admin_psid", "/admin", None)
        qr.assert_called_once()
        args = qr.call_args[0]
        assert args[0] == "admin_psid"
        assert args[1] == "Admin menu:"
        assert len(args[2]) == 2


@pytest.mark.asyncio
async def test_flags_menu_shows_nine_buttons():
    flags = [
        {"key": "ai_chat", "enabled": True},
        {"key": "currency", "enabled": True},
        {"key": "daraz", "enabled": False},
        {"key": "downloader", "enabled": True},
        {"key": "image_gen", "enabled": True},
        {"key": "ocr", "enabled": True},
        {"key": "translate", "enabled": True},
        {"key": "voice_input", "enabled": True},
        {"key": "weather", "enabled": True},
    ]
    conn = FakeConn(
        fetchrow_results=[{"is_admin": True}],
        fetch_results=[flags],
    )
    pool = FakePool(conn)

    with patch("services.event_processor.send_quick_replies", new_callable=AsyncMock) as qr:
        await handle_admin_quick_reply(pool, "admin_psid", "ADMIN_FLAGS_MENU")
        options = qr.call_args[0][2]
        assert len(options) == 9


@pytest.mark.asyncio
async def test_toggle_flag_confirms_and_reshows_menu():
    admin_conn = FakeConn(
        fetchrow_results=[
            {"is_admin": True},
            {"enabled": False},
        ],
        fetch_results=[
            [
                {"key": "ai_chat", "enabled": False},
                {"key": "daraz", "enabled": False},
            ]
        ],
    )
    pool = FakePool(admin_conn)

    with (
        patch("services.event_processor.send_text_message", new_callable=AsyncMock) as send,
        patch("services.event_processor.send_quick_replies", new_callable=AsyncMock) as qr,
    ):
        await handle_admin_quick_reply(pool, "admin_psid", "ADMIN_TOGGLE:ai_chat")
        send.assert_called_once_with("admin_psid", "AI Chat is now OFF.")
        qr.assert_called_once()


@pytest.mark.asyncio
async def test_stats_returns_formatted_counts():
    conn = FakeConn(fetchval_results=[10, 2, 7, 5, 1, 0], fetch_results=[[]])
    pool = FakePool(conn)
    stats = await get_quick_stats(pool)
    assert "Total users: 10" in stats
    assert "New today: 2" in stats
    assert "Messages today: 5" in stats
    assert "Blocked users: 1" in stats


@pytest.mark.asyncio
async def test_block_and_unblock_commands():
    conn = FakeConn(
        fetchrow_results=[
            {"is_admin": True},
            {"psid": "victim"},
            {"is_admin": True},
            {"psid": "victim"},
        ]
    )
    pool = FakePool(conn)
    redis = FakeRedis()

    with patch("services.event_processor.send_text_message", new_callable=AsyncMock) as send:
        await handle_admin_command(pool, redis, "admin", "/admin block victim", None)
        assert send.call_args[0][1] == "Blocked victim."

        await handle_admin_command(pool, redis, "admin", "/admin unblock victim", None)
        assert send.call_args[0][1] == "Unblocked victim."


@pytest.mark.asyncio
async def test_blocked_user_silent_drop():
    txn_conn = FakeTxnConn(
        fetchrow_results=[
            {"event_id": "mid1"},
            {"persona": "default", "is_blocked": True},
        ]
    )

    pool = MagicMock()
    pool.acquire.return_value = FakeAcquire(txn_conn)

    redis = FakeRedis()
    event = {
        "sender": {"id": "blocked_psid"},
        "message": {"mid": "mid1", "text": "hello"},
    }

    with (
        patch("services.event_processor.is_feature_enabled", new_callable=AsyncMock, return_value=True),
        patch("services.event_processor.mark_user_active", new_callable=AsyncMock) as active,
        patch("services.event_processor.send_text_message", new_callable=AsyncMock) as send,
    ):
        await process_messaging_event(pool, redis, event)
        active.assert_not_called()
        send.assert_not_called()


@pytest.mark.asyncio
async def test_non_admin_quick_reply_payload_silently_ignored():
    conn = FakeConn(fetchrow_results=[{"is_admin": False}])
    pool = FakePool(conn)

    with (
        patch("services.event_processor.send_text_message", new_callable=AsyncMock) as send,
        patch("services.event_processor.send_quick_replies", new_callable=AsyncMock) as qr,
    ):
        await handle_admin_quick_reply(pool, "psid1", "ADMIN_TOGGLE:ai_chat")
        send.assert_not_called()
        qr.assert_not_called()


@pytest.mark.asyncio
async def test_claim_does_not_log_secret(bootstrap_secret, caplog):
    import logging

    conn = FakeConn()
    pool = FakePool(conn)
    redis = FakeRedis()

    with caplog.at_level(logging.INFO):
        with patch("services.event_processor.send_text_message", new_callable=AsyncMock):
            await handle_admin_command(
                pool, redis, "psid1", "/admin claim super-secret-bootstrap", None
            )

    for record in caplog.records:
        if record.levelno <= logging.DEBUG:
            assert "super-secret-bootstrap" not in record.getMessage()
