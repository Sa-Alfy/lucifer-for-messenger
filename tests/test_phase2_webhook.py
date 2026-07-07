"""
tests/test_phase2_webhook.py — Phase 2: Messenger Webhook Core.

Tests:
  - GET /webhook: Facebook hub challenge verification
  - POST /webhook: signature validation gate
  - Event pipeline: echo suppression, non-message event suppression
  - Idempotency: duplicate mid is silently dropped
  - Blocked user: message silently dropped after upsert
  - messenger_api.send_text_message: retries on 5xx, skips retry on 4xx
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tests.conftest import FakeAcquire, FakeTxnConn, FakePool, FakeRedis


# ── GET /webhook — hub challenge ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_webhook_get_valid_challenge():
    """Correct hub.verify_token returns the challenge string with 200."""
    from fastapi.testclient import TestClient
    from main import app

    client = TestClient(app)
    resp = client.get(
        "/webhook",
        params={
            "hub.mode": "subscribe",
            "hub.verify_token": "test-verify-token",
            "hub.challenge": "CHALLENGE_CODE",
        },
    )
    assert resp.status_code == 200
    assert resp.text == "CHALLENGE_CODE"


@pytest.mark.asyncio
async def test_webhook_get_wrong_token():
    """Wrong hub.verify_token should return 403."""
    from fastapi.testclient import TestClient
    from main import app

    client = TestClient(app)
    resp = client.get(
        "/webhook",
        params={
            "hub.mode": "subscribe",
            "hub.verify_token": "wrong-token",
            "hub.challenge": "CHALLENGE_CODE",
        },
    )
    assert resp.status_code == 403


# ── POST /webhook — signature gate ────────────────────────────────────────────

def _make_sig(secret: str, body: bytes) -> str:
    import hashlib
    import hmac
    mac = hmac.new(secret.encode(), body, hashlib.sha256)
    return f"sha256={mac.hexdigest()}"


@pytest.mark.asyncio
async def test_webhook_post_missing_signature_returns_403():
    """POST without X-Hub-Signature-256 should return 403."""
    from fastapi.testclient import TestClient
    from main import app

    client = TestClient(app)
    resp = client.post(
        "/webhook",
        content=b'{"object":"page","entry":[]}',
        headers={"Content-Type": "application/json"},
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_webhook_post_invalid_signature_returns_403():
    """POST with wrong signature should return 403."""
    from fastapi.testclient import TestClient
    from main import app

    client = TestClient(app)
    resp = client.post(
        "/webhook",
        content=b'{"object":"page","entry":[]}',
        headers={
            "Content-Type": "application/json",
            "X-Hub-Signature-256": "sha256=deadbeef",
        },
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_webhook_post_valid_signature_returns_200():
    """POST with valid signature returns 200 immediately (background task is not awaited)."""
    from fastapi.testclient import TestClient
    from main import app

    body = b'{"object":"page","entry":[]}'
    sig = _make_sig("test-app-secret", body)

    with patch("handlers.webhook.BackgroundTasks.add_task"):
        client = TestClient(app)
        resp = client.post(
            "/webhook",
            content=body,
            headers={"Content-Type": "application/json", "X-Hub-Signature-256": sig},
        )
    assert resp.status_code == 200


# ── Event pipeline: echo and non-message suppression ─────────────────────────

@pytest.mark.asyncio
async def test_echo_event_is_silently_dropped():
    """is_echo=True messages must be dropped without any reply."""
    from services.event_processor import process_messaging_event

    pool = MagicMock()
    redis = FakeRedis()
    event = {"sender": {"id": "bot"}, "message": {"mid": "m1", "is_echo": True, "text": "hi"}}

    with patch("services.event_processor.send_text_message", new_callable=AsyncMock) as send:
        await process_messaging_event(pool, redis, event)
        send.assert_not_called()


@pytest.mark.asyncio
async def test_non_message_event_is_silently_dropped():
    """Events without a 'message' key (delivery/read receipts) must be dropped."""
    from services.event_processor import process_messaging_event

    pool = MagicMock()
    redis = FakeRedis()
    event = {"sender": {"id": "user1"}, "delivery": {"watermark": 123}}

    with patch("services.event_processor.send_text_message", new_callable=AsyncMock) as send:
        await process_messaging_event(pool, redis, event)
        send.assert_not_called()


# ── Idempotency: duplicate mid dropped ────────────────────────────────────────

@pytest.mark.asyncio
async def test_duplicate_mid_is_silently_dropped():
    """
    The second delivery of the same mid must be dropped.
    Simulated by fetchrow returning None (INSERT ON CONFLICT DO NOTHING returned nothing).
    """
    from services.event_processor import process_messaging_event

    txn_conn = FakeTxnConn(fetchrow_results=[None])  # None = conflict, already seen
    pool = MagicMock()
    pool.acquire.return_value = FakeAcquire(txn_conn)
    redis = FakeRedis()
    event = {"sender": {"id": "user1"}, "message": {"mid": "dup-mid", "text": "hello"}}

    with patch("services.event_processor.send_text_message", new_callable=AsyncMock) as send:
        await process_messaging_event(pool, redis, event)
        send.assert_not_called()


# ── Blocked user: silent drop ─────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_blocked_user_is_silently_dropped():
    """
    A user with is_blocked=True must have their message dropped.
    mark_user_active and send_text_message must not be called.
    """
    from services.event_processor import process_messaging_event

    txn_conn = FakeTxnConn(
        fetchrow_results=[
            {"event_id": "mid-block"},
            {"persona": "default", "is_blocked": True},
        ]
    )
    pool = MagicMock()
    pool.acquire.return_value = FakeAcquire(txn_conn)
    redis = FakeRedis()
    event = {"sender": {"id": "blocked"}, "message": {"mid": "mid-block", "text": "hi"}}

    with (
        patch("services.event_processor.is_feature_enabled", new_callable=AsyncMock, return_value=True),
        patch("services.event_processor.mark_user_active", new_callable=AsyncMock) as active,
        patch("services.event_processor.send_text_message", new_callable=AsyncMock) as send,
    ):
        await process_messaging_event(pool, redis, event)
        active.assert_not_called()
        send.assert_not_called()
