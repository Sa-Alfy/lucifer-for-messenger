"""
tests/conftest.py — Shared fakes, fixtures, and helpers for the Lucifer test suite.

All fakes are in-process (no external services required). The env vars are
set before any service module is imported so pydantic-settings doesn't raise
on startup.

Pattern used across all tests:
  - FakeRedis / FakeConn / FakePool / FakeTxnConn — in-memory implementations
    that track calls and return configurable values.
  - patch() on send_text_message / send_quick_replies / send_image_url to avoid
    real HTTP calls to the Facebook Graph API.
  - respx / unittest.mock for mocking outbound httpx calls to external APIs.
"""

import os

import pytest

# ── Bootstrap env before any service import ───────────────────────────────────
# These must be set before pydantic-settings reads them.
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost:5432/test")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("FB_PAGE_ACCESS_TOKEN", "test-page-token")
os.environ.setdefault("FB_APP_SECRET", "test-app-secret")
os.environ.setdefault("FB_VERIFY_TOKEN", "test-verify-token")
os.environ.setdefault("FB_PAGE_ID", "123456789")
os.environ.setdefault("GROQ_API_KEY", "test-groq-key")
os.environ.setdefault("GEMINI_API_KEY", "test-gemini-key")
os.environ.setdefault("HF_API_KEY", "test-hf-key")
os.environ.setdefault("SUPABASE_URL", "https://test.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_KEY", "test-service-key")
os.environ.setdefault("OPENWEATHER_API_KEY", "test-weather-key")
os.environ.setdefault("ADMIN_BOOTSTRAP_SECRET", "test-bootstrap-secret")


# ── Fake Redis ────────────────────────────────────────────────────────────────

class FakeRedis:
    """In-memory Redis fake supporting the subset of commands used in this project."""

    def __init__(self):
        self._store: dict = {}
        self._ttl: dict = {}

    async def get(self, key: str):
        return self._store.get(key)

    async def set(self, key: str, value, ex: int | None = None):
        self._store[key] = value
        if ex:
            self._ttl[key] = ex

    async def incr(self, key: str) -> int:
        self._store[key] = self._store.get(key, 0) + 1
        return self._store[key]

    async def expire(self, key: str, seconds: int) -> None:
        self._ttl[key] = seconds

    async def exists(self, key: str) -> int:
        return 1 if key in self._store else 0

    async def lpush(self, key: str, *values):
        lst = self._store.setdefault(key, [])
        for v in values:
            lst.insert(0, v)

    async def ltrim(self, key: str, start: int, end: int):
        lst = self._store.get(key, [])
        if end == -1:
            self._store[key] = lst[start:]
        else:
            self._store[key] = lst[start: end + 1]

    async def lrange(self, key: str, start: int, end: int) -> list:
        lst = self._store.get(key, [])
        if end == -1:
            return lst[start:]
        return lst[start: end + 1]

    async def rpush(self, key: str, *values):
        lst = self._store.setdefault(key, [])
        lst.extend(values)

    async def ping(self) -> bool:
        return True


# ── Fake Postgres ─────────────────────────────────────────────────────────────

class FakeConn:
    """
    Single-connection fake that replays pre-configured results in order.

    fetchrow_results: List of dicts/None returned by successive fetchrow() calls.
    fetchval_results: List of values returned by successive fetchval() calls.
    fetch_results:    List of lists returned by successive fetch() calls.
    executed:         All (query, args) passed to execute() — for assertion.
    """

    def __init__(
        self,
        fetchrow_results: list | None = None,
        fetchval_results: list | None = None,
        fetch_results: list | None = None,
    ):
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


class FakeTransaction:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass


class FakeTxnConn(FakeConn):
    """FakeConn that also supports .transaction() context manager."""

    def transaction(self):
        return FakeTransaction()


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


# ── Shared fixtures ───────────────────────────────────────────────────────────

@pytest.fixture
def fake_redis():
    return FakeRedis()


@pytest.fixture
def fake_conn():
    return FakeConn()


@pytest.fixture
def fake_pool(fake_conn):
    return FakePool(fake_conn)
