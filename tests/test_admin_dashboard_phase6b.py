"""
Phase 6b web admin dashboard — self-verify checklist tests.
"""

import logging
from unittest.mock import patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from handlers.admin_dashboard import (
    LOGIN_RATE_LIMIT_MAX,
    get_client_ip,
    is_login_rate_limited,
)
from tests.conftest import FakeConn, FakePool, FakeRedis
from utils.security import create_session_token, verify_session_token


@pytest.fixture
def admin_settings(monkeypatch):
    monkeypatch.setattr("handlers.admin_dashboard.settings.admin_dashboard_password", "dashboard-pass")
    monkeypatch.setattr("handlers.admin_dashboard.settings.admin_session_secret", "session-hmac-secret-key")
    monkeypatch.setattr("handlers.admin_dashboard.settings.env", "dev")


@pytest_asyncio.fixture
async def client(admin_settings):
    from main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


def _valid_session_cookie() -> dict:
    token = create_session_token("session-hmac-secret-key")
    return {"admin_session": token}


@pytest.mark.asyncio
async def test_admin_redirects_to_login_without_cookie(client):
    resp = await client.get("/admin", follow_redirects=False)
    assert resp.status_code == 303
    assert resp.headers["location"] == "/admin/login"


@pytest.mark.asyncio
async def test_wrong_password_redirects_with_error_no_cookie(client, fake_pool):
    with patch("handlers.admin_dashboard.get_pool", return_value=fake_pool), patch(
        "handlers.admin_dashboard.get_redis", return_value=FakeRedis()
    ):
        resp = await client.post(
            "/admin/login",
            data={"password": "wrong"},
            follow_redirects=False,
        )
    assert resp.status_code == 303
    assert resp.headers["location"] == "/admin/login?error=1"
    assert "admin_session" not in resp.cookies


@pytest.mark.asyncio
async def test_empty_password_config_fails_closed(client, monkeypatch, fake_pool):
    monkeypatch.setattr("handlers.admin_dashboard.settings.admin_dashboard_password", "")
    with patch("handlers.admin_dashboard.get_pool", return_value=fake_pool), patch(
        "handlers.admin_dashboard.get_redis", return_value=FakeRedis()
    ):
        resp = await client.post(
            "/admin/login",
            data={"password": "anything"},
            follow_redirects=False,
        )
    assert resp.status_code == 303
    assert "admin_session" not in resp.cookies


@pytest.mark.asyncio
async def test_correct_password_sets_cookie_and_redirects(client, fake_pool):
    with patch("handlers.admin_dashboard.get_pool", return_value=fake_pool), patch(
        "handlers.admin_dashboard.get_redis", return_value=FakeRedis()
    ):
        resp = await client.post(
            "/admin/login",
            data={"password": "dashboard-pass"},
            follow_redirects=False,
        )
    assert resp.status_code == 303
    assert resp.headers["location"] == "/admin"
    assert "admin_session" in resp.cookies
    assert verify_session_token(resp.cookies["admin_session"], "session-hmac-secret-key")


@pytest.mark.asyncio
async def test_login_rate_limit_on_sixth_attempt():
    redis = FakeRedis()
    ip = "203.0.113.42"
    for _ in range(LOGIN_RATE_LIMIT_MAX):
        assert await is_login_rate_limited(redis, ip) is False
    assert await is_login_rate_limited(redis, ip) is True


@pytest.mark.asyncio
async def test_login_rate_limit_uses_forwarded_ip(client, fake_pool):
    redis = FakeRedis()
    with patch("handlers.admin_dashboard.get_pool", return_value=fake_pool), patch(
        "handlers.admin_dashboard.get_redis", return_value=redis
    ):
        for i in range(6):
            resp = await client.post(
                "/admin/login",
                data={"password": "wrong"},
                headers={"X-Forwarded-For": "198.51.100.7"},
                follow_redirects=False,
            )
            if i < 5:
                assert resp.status_code == 303
            else:
                assert resp.status_code == 429


def test_get_client_ip_prefers_x_forwarded_for():
    from starlette.requests import Request

    scope = {
        "type": "http",
        "method": "GET",
        "path": "/",
        "headers": [(b"x-forwarded-for", b"198.51.100.7, 10.0.0.1")],
        "client": ("10.0.0.99", 12345),
    }
    request = Request(scope)
    assert get_client_ip(request) == "198.51.100.7"


@pytest.mark.asyncio
async def test_api_flags_requires_auth(client):
    resp = await client.get("/admin/api/flags")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_api_stats_with_session(client, fake_pool):
    conn = FakeConn(fetchval_results=[10, 2, 7, 5, 1, 0], fetch_results=[[{"persona": "default", "count": 10}]])
    pool = FakePool(conn)
    with patch("handlers.admin_dashboard.get_pool", return_value=pool):
        resp = await client.get("/admin/api/stats", cookies=_valid_session_cookie())
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_users"] == 10
    assert data["active_last_7_days"] == 7
    assert data["persona_distribution"] == {"default": 10}


@pytest.mark.asyncio
async def test_api_toggle_flag(client):
    conn = FakeConn(fetchrow_results=[{"enabled": False}])
    pool = FakePool(conn)
    with patch("handlers.admin_dashboard.get_pool", return_value=pool):
        resp = await client.post(
            "/admin/api/flags/ai_chat/toggle",
            cookies=_valid_session_cookie(),
        )
    assert resp.status_code == 200
    assert resp.json() == {"key": "ai_chat", "enabled": False}


@pytest.mark.asyncio
async def test_api_list_users_search_and_blocked(client):
    users = [
        {
            "psid": "blocked123",
            "persona": "default",
            "message_count": 3,
            "last_seen_at": None,
            "is_blocked": True,
            "is_admin": False,
        }
    ]
    conn = FakeConn(fetchval_results=[1], fetch_results=[users])
    pool = FakePool(conn)
    with patch("handlers.admin_dashboard.get_pool", return_value=pool):
        resp = await client.get(
            "/admin/api/users?search=blocked&blocked_only=true&page=1",
            cookies=_valid_session_cookie(),
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert data["users"][0]["psid"] == "blocked123"


@pytest.mark.asyncio
async def test_api_block_user(client):
    conn = FakeConn(fetchrow_results=[{"psid": "victim"}])
    pool = FakePool(conn)
    with patch("handlers.admin_dashboard.get_pool", return_value=pool):
        resp = await client.post(
            "/admin/api/users/victim/block",
            cookies=_valid_session_cookie(),
        )
    assert resp.status_code == 200
    assert resp.json()["is_blocked"] is True


@pytest.mark.asyncio
async def test_logout_clears_session(client, fake_pool):
    with patch("handlers.admin_dashboard.get_pool", return_value=fake_pool), patch(
        "handlers.admin_dashboard.get_redis", return_value=FakeRedis()
    ):
        await client.post(
            "/admin/login",
            data={"password": "dashboard-pass"},
            follow_redirects=False,
        )
        logout = await client.post("/admin/logout", follow_redirects=False)
        assert logout.status_code == 303

        after = await client.get("/admin", follow_redirects=False)
        assert after.status_code == 303
        assert after.headers["location"] == "/admin/login"


@pytest.mark.asyncio
async def test_login_does_not_log_secrets(caplog, client, fake_pool):
    with patch("handlers.admin_dashboard.get_pool", return_value=fake_pool), patch(
        "handlers.admin_dashboard.get_redis", return_value=FakeRedis()
    ):
        with caplog.at_level(logging.INFO):
            await client.post(
                "/admin/login",
                data={"password": "dashboard-pass"},
                follow_redirects=False,
            )
    for record in caplog.records:
        if record.levelno <= logging.DEBUG:
            msg = record.getMessage()
            assert "dashboard-pass" not in msg
            assert "session-hmac-secret-key" not in msg


@pytest.mark.asyncio
async def test_get_stats_dict_shared_by_quick_stats():
    from services.admin import get_quick_stats, get_stats_dict

    conn = FakeConn(fetchval_results=[5, 1, 3, 2, 0, 1], fetch_results=[[{"persona": "default", "count": 5}]])
    pool = FakePool(conn)

    stats_dict = await get_stats_dict(pool)
    text = await get_quick_stats(FakePool(FakeConn(
        fetchval_results=[5, 1, 3, 2, 0, 1],
        fetch_results=[[{"persona": "default", "count": 5}]],
    )))

    assert "Total users: 5" in text
    assert stats_dict["total_users"] == 5
    assert stats_dict["messages_today"] == 2
