"""
tests/test_phase8_hardening.py — Hardening.

Tests:
  - URL allowlist: adversarial cases against services.downloader.is_supported_url
  - yt-dlp freshness: pure logic in services.ytdlp_freshness (age calculation,
    staleness threshold, graceful degradation for non-date versions)
  - Task registry: register_task adds/removes tasks; wait_for_shutdown respects timeout

All tests run with no live external services — no real DB, Redis, or network calls.

Style notes:
  - AsyncMock / MagicMock / patch from unittest.mock, consistent with existing tests.
  - Fake* fixtures from conftest are not needed here — all code under test is pure.
  - pytest.mark.asyncio for async tests, matching the pattern in test_phase2_webhook.py.
"""

import asyncio
import sys
from datetime import date, timedelta
from types import ModuleType
from unittest.mock import MagicMock, patch

import pytest


# ── Shared helper: mock yt_dlp at module level ────────────────────────────────
# services/downloader.py does `import yt_dlp` at the top level, so we can't
# just import is_supported_url without yt_dlp being available.  The function
# itself doesn't USE yt_dlp — it's pure Python — so we inject a stub module
# into sys.modules and re-import downloader each time, isolated per class.

def _get_is_supported_url():
    """
    Return is_supported_url with yt_dlp stubbed out.

    Uses sys.modules injection so the top-level `import yt_dlp` in downloader.py
    resolves without error even when yt_dlp is not installed.
    """
    stub = ModuleType("yt_dlp")
    stub.YoutubeDL = MagicMock()
    stub.utils = MagicMock()
    stub.utils.DownloadError = Exception

    # Remove any cached version of the module so we get a fresh import
    sys.modules.pop("services.downloader", None)
    with patch.dict(sys.modules, {"yt_dlp": stub}):
        from services.downloader import is_supported_url
        return is_supported_url


# ── URL allowlist: is_supported_url ──────────────────────────────────────────
# These tests are written adversarially, not just happy-path.
# The goal: if the allowlist logic regresses to a substring check (e.g.,
# `"tiktok.com" in domain` instead of exact/suffix match), tests catch it.

class TestIsSupportedUrl:
    """Adversarial and happy-path tests for the domain allowlist."""

    def _check(self, url: str) -> bool:
        is_supported_url = _get_is_supported_url()
        return is_supported_url(url)

    # ── Happy path — expected True ────────────────────────────────────────

    def test_tiktok_bare_domain(self):
        assert self._check("https://tiktok.com/video/123") is True

    def test_tiktok_www_subdomain(self):
        assert self._check("https://www.tiktok.com/video/123") is True

    def test_twitter_bare_domain(self):
        assert self._check("https://twitter.com/status/123") is True

    def test_twitter_www_subdomain(self):
        assert self._check("https://www.twitter.com/status/123") is True

    def test_x_com(self):
        assert self._check("https://x.com/status/123") is True

    def test_x_com_www(self):
        assert self._check("https://www.x.com/status/123") is True

    def test_instagram(self):
        assert self._check("https://instagram.com/p/abc123/") is True

    def test_instagram_www(self):
        assert self._check("https://www.instagram.com/p/abc123/") is True

    def test_facebook_bare(self):
        assert self._check("https://facebook.com/video/123") is True

    def test_facebook_www(self):
        assert self._check("https://www.facebook.com/video/123") is True

    def test_fb_watch(self):
        assert self._check("https://fb.watch/abc123/") is True

    def test_reddit_bare(self):
        assert self._check("https://reddit.com/r/test/comments/abc/") is True

    def test_reddit_www(self):
        assert self._check("https://www.reddit.com/r/test/comments/abc/") is True

    # ── Case insensitivity ────────────────────────────────────────────────

    def test_uppercase_domain_is_accepted(self):
        """urlparse netloc is lowercased in is_supported_url — TIKTOK.COM should work."""
        assert self._check("https://TIKTOK.COM/video/123") is True

    def test_mixed_case_domain(self):
        assert self._check("https://TikTok.com/video/123") is True

    # ── Adversarial: substring / suffix attacks ───────────────────────────

    def test_suffix_attack_tiktok_in_domain(self):
        """
        eviltiktok.com must be rejected.
        endswith(".tiktok.com") is False; == "tiktok.com" is False.
        """
        assert self._check("https://eviltiktok.com/video/123") is False

    def test_suffix_attack_domain_ends_with_but_extra_prefix(self):
        """
        notatiktok.com must be rejected — not a subdomain of tiktok.com.
        """
        assert self._check("https://notatiktok.com/video/123") is False

    def test_fake_subdomain_real_domain_in_path(self):
        """
        evil.com/tiktok.com should be rejected — tiktok.com is in the path, not the domain.
        """
        assert self._check("https://evil.com/tiktok.com/video/123") is False

    def test_tiktok_as_subdomain_of_evil(self):
        """
        tiktok.com.evil.com is a subdomain of evil.com, not of tiktok.com.
        endswith(".tiktok.com") → "tiktok.com.evil.com".endswith(".tiktok.com") is False.
        """
        assert self._check("https://tiktok.com.evil.com/video/123") is False

    def test_tiktok_subdomain_of_evil_reversed(self):
        """
        evil.tiktok.com.attacker.net should be rejected.
        """
        assert self._check("https://evil.tiktok.com.attacker.net/video/123") is False

    def test_lookalike_domain_unicode(self):
        """
        A homograph attack domain (tîktok.com) must be rejected.
        urlparse returns the IDN form in netloc, which won't match the ASCII allowlist.
        """
        assert self._check("https://tîktok.com/video/123") is False

    # ── Adversarial: missing or wrong scheme ──────────────────────────────

    def test_no_scheme_returns_false(self):
        """
        Without a scheme, urlparse places the whole string in 'path', not 'netloc'.
        netloc is empty → allowlist check fails.  This is the correct behaviour.
        """
        assert self._check("tiktok.com/video/123") is False

    def test_schemeless_double_slash(self):
        """
        //tiktok.com/video is scheme-relative; urlparse puts domain in netloc.
        This should be accepted (netloc == "tiktok.com").
        Document the actual behaviour so any future change is visible.
        """
        from urllib.parse import urlparse
        parsed_netloc = urlparse("//tiktok.com/video").netloc
        is_supported_url = _get_is_supported_url()
        result = is_supported_url("//tiktok.com/video")
        # If urlparse populates netloc, it should pass; document the actual value.
        # The assertion checks the behaviour is consistent with the parser.
        assert result == (parsed_netloc.lower() in {"tiktok.com", "www.tiktok.com"} or
                          any(parsed_netloc.lower() == d or parsed_netloc.lower().endswith("." + d)
                              for d in {"tiktok.com", "www.tiktok.com"}))

    def test_empty_url_returns_false(self):
        assert self._check("") is False

    def test_ftp_scheme_but_valid_domain(self):
        """ftp:// scheme is unusual but urlparse still extracts netloc correctly."""
        assert self._check("ftp://tiktok.com/video/123") is True

    # ── Adversarial: port in netloc ───────────────────────────────────────

    def test_port_in_url(self):
        """
        http://tiktok.com:8080/video — urlparse includes :8080 in netloc.
        "tiktok.com:8080" != "tiktok.com" and doesn't endswith ".tiktok.com".
        This should return False — document the actual behaviour.

        If the project later decides to strip ports, this test will catch the
        change in behaviour and force a conscious decision.
        """
        from urllib.parse import urlparse
        netloc = urlparse("http://tiktok.com:8080/video").netloc
        is_supported_url = _get_is_supported_url()
        result = is_supported_url("http://tiktok.com:8080/video")
        # netloc is "tiktok.com:8080", which doesn't match — so False is expected.
        # This test documents the known limitation; if someone fixes it, the
        # test changes to assert True and validates the fix.
        assert result is False  # port breaks the exact-match; document this

    # ── Explicitly rejected domains ───────────────────────────────────────

    def test_youtube_is_rejected(self):
        """YouTube is explicitly not supported — see module docstring."""
        assert self._check("https://youtube.com/watch?v=abc123") is False

    def test_youtube_youtu_be_shortlink_rejected(self):
        assert self._check("https://youtu.be/abc123") is False

    def test_completely_random_domain_rejected(self):
        assert self._check("https://example.com/video/123") is False

    def test_google_rejected(self):
        assert self._check("https://google.com/video") is False

    def test_credentials_in_url(self):
        """
        http://user:pass@tiktok.com/video — urlparse netloc is "user:pass@tiktok.com",
        which does NOT match "tiktok.com" in the allowlist.  This returns False.

        This is actually the safer outcome: URLs with embedded credentials are
        unusual for video sharing links.  Document the behaviour so any future
        change (e.g. stripping userinfo before the domain check) is visible.
        """
        from urllib.parse import urlparse
        netloc = urlparse("http://user:pass@tiktok.com/video").netloc
        # netloc is "user:pass@tiktok.com" — not "tiktok.com"
        assert netloc == "user:pass@tiktok.com"  # verify our assumption
        assert self._check("http://user:pass@tiktok.com/video") is False


# ── yt-dlp freshness: pure logic ──────────────────────────────────────────────

class TestYtdlpFreshness:
    """Tests for services.ytdlp_freshness — all pure logic, no real yt-dlp needed."""

    def test_fresh_version_is_not_stale(self):
        """A version released 30 days ago is well within the 90-day threshold."""
        recent = (date.today() - timedelta(days=30)).strftime("%Y.%m.%d")
        with patch("importlib.metadata.version", return_value=recent):
            from services.ytdlp_freshness import get_ytdlp_info
            result = get_ytdlp_info()
        assert result["is_stale"] is False
        assert result["age_days"] == 30
        assert result["error"] is None

    def test_stale_version_is_flagged(self):
        """A version 100 days old should be marked stale (threshold is 90)."""
        old = (date.today() - timedelta(days=100)).strftime("%Y.%m.%d")
        with patch("importlib.metadata.version", return_value=old):
            from services.ytdlp_freshness import get_ytdlp_info
            result = get_ytdlp_info()
        assert result["is_stale"] is True
        assert result["age_days"] == 100

    def test_exactly_at_threshold_is_stale(self):
        """90 days old is >= 90, so it should be marked stale."""
        at_threshold = (date.today() - timedelta(days=90)).strftime("%Y.%m.%d")
        with patch("importlib.metadata.version", return_value=at_threshold):
            from services.ytdlp_freshness import get_ytdlp_info
            result = get_ytdlp_info()
        assert result["is_stale"] is True

    def test_one_day_before_threshold_is_not_stale(self):
        """89 days is < 90, so not stale."""
        almost = (date.today() - timedelta(days=89)).strftime("%Y.%m.%d")
        with patch("importlib.metadata.version", return_value=almost):
            from services.ytdlp_freshness import get_ytdlp_info
            result = get_ytdlp_info()
        assert result["is_stale"] is False

    def test_nonstandard_version_degrades_gracefully(self):
        """
        A git-installed dev version like '2026.06.09.dev0+g...' should not raise.
        The implementation parses only the first three components, so this should
        still work for the date prefix.
        """
        with patch("importlib.metadata.version", return_value="2026.06.09.dev0+gabcdef"):
            from services.ytdlp_freshness import get_ytdlp_info
            result = get_ytdlp_info()
        # "2026.06.09.dev0+gabcdef" — first three parts are 2026, 06, 09 → valid date
        assert result["version"] == "2026.06.09.dev0+gabcdef"
        assert result["release_date"] == "2026-06-09"
        assert result["error"] is None

    def test_completely_non_date_version_degrades(self):
        """
        A version string like 'dev' should produce error=..., is_stale=False.
        Never raise — failing soft is correct for an advisory signal.
        """
        with patch("importlib.metadata.version", return_value="dev"):
            from services.ytdlp_freshness import get_ytdlp_info
            result = get_ytdlp_info()
        assert result["is_stale"] is False
        assert result["release_date"] is None
        assert result["age_days"] is None
        assert result["error"] is not None

    def test_package_not_found_degrades(self):
        """If yt-dlp is not installed, return is_stale=False with error, never raise."""
        import importlib.metadata
        with patch("importlib.metadata.version", side_effect=importlib.metadata.PackageNotFoundError("yt-dlp")):
            from services.ytdlp_freshness import get_ytdlp_info
            result = get_ytdlp_info()
        assert result["version"] is None
        assert result["is_stale"] is False
        assert result["error"] is not None

    def test_stale_threshold_is_reported(self):
        """The response always includes the threshold value for display purposes."""
        with patch("importlib.metadata.version", return_value="2026.01.01"):
            from services.ytdlp_freshness import get_ytdlp_info
            result = get_ytdlp_info()
        assert result["stale_threshold_days"] == 90

    def test_version_string_is_returned(self):
        """The raw version string from importlib.metadata is echoed back."""
        with patch("importlib.metadata.version", return_value="2026.06.09"):
            from services.ytdlp_freshness import get_ytdlp_info
            result = get_ytdlp_info()
        assert result["version"] == "2026.06.09"

    def test_two_component_version_degrades(self):
        """A two-part version string ('2026.06') cannot be parsed as a date."""
        with patch("importlib.metadata.version", return_value="2026.06"):
            from services.ytdlp_freshness import get_ytdlp_info
            result = get_ytdlp_info()
        assert result["is_stale"] is False
        assert result["error"] is not None


# ── Task registry: unit tests ─────────────────────────────────────────────────
# These test the pure asyncio logic in services.task_registry without
# starting a real HTTP server.  The registry is module-level state, so we
# reset _in_flight between tests.

class TestTaskRegistry:
    """Tests for services.task_registry — register_task and wait_for_shutdown."""

    def _reset_registry(self):
        """Clear the module-level _in_flight set between tests."""
        import services.task_registry as reg
        reg._in_flight.clear()

    @pytest.mark.asyncio
    async def test_register_task_returns_asyncio_task(self):
        """register_task wraps a coroutine in asyncio.create_task."""
        self._reset_registry()
        from services.task_registry import register_task

        async def noop():
            pass

        task = register_task(noop())
        assert isinstance(task, asyncio.Task)
        await task  # let it finish cleanly

    @pytest.mark.asyncio
    async def test_register_task_is_tracked_while_running(self):
        """Task appears in _in_flight while it is executing."""
        self._reset_registry()
        import services.task_registry as reg
        from services.task_registry import register_task

        ready = asyncio.Event()
        finish = asyncio.Event()

        async def long_task():
            ready.set()
            await finish.wait()

        task = register_task(long_task())
        await ready.wait()  # task has started and is blocked

        assert task in reg._in_flight

        finish.set()
        await task  # let it complete

    @pytest.mark.asyncio
    async def test_task_removed_from_registry_when_done(self):
        """Task is removed from _in_flight automatically via done_callback."""
        self._reset_registry()
        import services.task_registry as reg
        from services.task_registry import register_task

        async def noop():
            pass

        task = register_task(noop())
        await task  # wait for completion
        # Give the done_callback a tick to fire
        await asyncio.sleep(0)

        assert task not in reg._in_flight

    @pytest.mark.asyncio
    async def test_wait_for_shutdown_no_tasks_returns_immediately(self):
        """wait_for_shutdown with empty registry completes without delay."""
        self._reset_registry()
        from services.task_registry import wait_for_shutdown

        # Should complete essentially instantly
        await asyncio.wait_for(wait_for_shutdown(30.0), timeout=2.0)

    @pytest.mark.asyncio
    async def test_wait_for_shutdown_waits_for_tasks(self):
        """wait_for_shutdown blocks until all tasks complete."""
        self._reset_registry()
        from services.task_registry import register_task, wait_for_shutdown
        import services.task_registry as reg

        done_flag = asyncio.Event()

        async def slow_task():
            await asyncio.sleep(0.05)
            done_flag.set()

        register_task(slow_task())
        assert len(reg._in_flight) == 1

        await wait_for_shutdown(timeout=5.0)
        assert done_flag.is_set()
        assert len(reg._in_flight) == 0

    @pytest.mark.asyncio
    async def test_wait_for_shutdown_respects_timeout(self):
        """
        wait_for_shutdown with a very short timeout should log a warning
        and return even if tasks are still running.  The tasks are NOT
        cancelled — the test verifies we don't hang.
        """
        self._reset_registry()
        from services.task_registry import register_task, wait_for_shutdown
        import services.task_registry as reg

        still_running = asyncio.Event()

        async def hung_task():
            still_running.set()
            await asyncio.sleep(10)  # much longer than our timeout

        task = register_task(hung_task())
        await still_running.wait()

        # Timeout is 0.1s — should return quickly even though task is not done
        await asyncio.wait_for(wait_for_shutdown(timeout=0.1), timeout=2.0)

        # Task was NOT cancelled by wait_for_shutdown (by design)
        assert not task.done()

        # Clean up: cancel the task ourselves so it doesn't pollute other tests
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
