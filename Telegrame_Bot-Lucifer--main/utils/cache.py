"""
Lightweight in-memory TTL cache for reducing redundant API calls.
Used by weather, news, currency, and prayer time services.
"""

import time
import threading
from utils.logger import get_logger

logger = get_logger(__name__)


class SimpleCache:
    """Thread-safe in-memory cache with per-key TTL."""

    def __init__(self):
        self._store = {}  # key -> (value, expire_time)
        self._lock = threading.Lock()

    def get(self, key: str):
        """Return cached value if it exists and hasn't expired, else None."""
        with self._lock:
            entry = self._store.get(key)
            if entry is None:
                return None
            value, expire_time = entry
            if time.time() > expire_time:
                del self._store[key]
                return None
            return value

    def set(self, key: str, value, ttl_seconds: int = 300):
        """Store a value with a TTL (time-to-live) in seconds."""
        with self._lock:
            self._store[key] = (value, time.time() + ttl_seconds)

    def invalidate(self, key: str):
        """Remove a specific key from the cache."""
        with self._lock:
            self._store.pop(key, None)

    def clear(self):
        """Clear the entire cache."""
        with self._lock:
            self._store.clear()

    def stats(self) -> dict:
        """Return cache statistics."""
        with self._lock:
            now = time.time()
            total = len(self._store)
            alive = sum(1 for _, (_, exp) in self._store.items() if exp > now)
            return {"total_keys": total, "alive_keys": alive, "expired_keys": total - alive}


# ── Global cache instances (one per domain for clean separation) ──
weather_cache = SimpleCache()   # TTL: 300s (5 min)
news_cache = SimpleCache()      # TTL: 600s (10 min)
currency_cache = SimpleCache()  # TTL: 120s (2 min)
prayer_cache = SimpleCache()    # TTL: 3600s (1 hr)
daraz_cache = SimpleCache()     # TTL: 600s (10 min)

# Default TTLs
WEATHER_TTL = 300
NEWS_TTL = 600
CURRENCY_TTL = 120
PRAYER_TTL = 3600
DARAZ_TTL = 600
