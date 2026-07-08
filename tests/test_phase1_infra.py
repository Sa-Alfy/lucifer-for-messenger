"""
tests/test_phase1_infra.py — Infrastructure Foundation.

Tests:
  - config: env vars load correctly via pydantic-settings
  - security: HMAC-SHA256 signature verification
  - messenger_api: text chunking logic
  - logger: get_logger returns named logger
"""

import hashlib
import hmac as _hmac

import pytest


# ── Config ────────────────────────────────────────────────────────────────────

def test_config_loads_from_env():
    """Settings should load without error when all required vars are set (bootstrapped in conftest)."""
    from config import settings
    assert settings.database_url.startswith("postgresql://")
    assert settings.redis_url.startswith("redis://")
    assert settings.fb_page_access_token == "test-page-token"
    assert settings.groq_api_key == "test-groq-key"


def test_config_openweather_key_set():
    from config import settings
    assert settings.openweather_api_key == "test-weather-key"


def test_config_admin_secret_set():
    from config import settings
    assert settings.admin_bootstrap_secret == "test-bootstrap-secret"


# ── Signature verification ─────────────────────────────────────────────────────

def _make_sig(secret: str, body: bytes) -> str:
    mac = _hmac.new(secret.encode(), body, hashlib.sha256)
    return f"sha256={mac.hexdigest()}"


def test_valid_signature_returns_true():
    """A correctly computed HMAC-SHA256 header should return True."""
    from utils.security import verify_fb_signature
    body = b'{"entry":[{"messaging":[{"message":{"text":"hi"}}]}]}'
    sig = _make_sig("test-app-secret", body)
    assert verify_fb_signature(body, sig, "test-app-secret") is True


def test_missing_signature_returns_false():
    """A None signature header should return False."""
    from utils.security import verify_fb_signature
    assert verify_fb_signature(b"body", None, "test-app-secret") is False


def test_malformed_signature_no_prefix_returns_false():
    """A header without 'sha256=' prefix should return False."""
    from utils.security import verify_fb_signature
    assert verify_fb_signature(b"body", "deadbeef", "test-app-secret") is False


def test_wrong_signature_returns_false():
    """A spoofed/incorrect signature should return False."""
    from utils.security import verify_fb_signature
    assert verify_fb_signature(b"body", "sha256=deadbeef", "test-app-secret") is False


def test_signature_wrong_body_returns_false():
    """Correct format but tampered body should not validate."""
    from utils.security import verify_fb_signature
    original_body = b'{"entry": "real"}'
    tampered_body = b'{"entry": "evil"}'
    sig = _make_sig("test-app-secret", original_body)
    assert verify_fb_signature(tampered_body, sig, "test-app-secret") is False


# ── Text chunker ──────────────────────────────────────────────────────────────

def test_chunk_short_text_is_single_chunk():
    """Text shorter than the limit should be returned as a single chunk."""
    from services.messenger_api import _chunk_text
    chunks = _chunk_text("Hello!", 2000)
    assert chunks == ["Hello!"]


def test_chunk_long_text_splits_correctly():
    """Text longer than the limit should be split into sequential chunks."""
    from services.messenger_api import _chunk_text
    text = "A" * 2500
    chunks = _chunk_text(text, 2000)
    assert len(chunks) == 2
    assert len(chunks[0]) == 2000
    assert len(chunks[1]) == 500


def test_chunk_empty_text_returns_list_with_empty_string():
    """Empty text must yield at least one chunk — Messenger rejects empty bodies."""
    from services.messenger_api import _chunk_text
    chunks = _chunk_text("", 2000)
    assert chunks == [""]


def test_chunk_exact_limit_is_single_chunk():
    """Text exactly at the limit should not be split."""
    from services.messenger_api import _chunk_text
    text = "B" * 2000
    chunks = _chunk_text(text, 2000)
    assert len(chunks) == 1
    assert chunks[0] == text


def test_chunk_three_parts():
    """Text at 2.5x the limit should produce exactly 3 chunks."""
    from services.messenger_api import _chunk_text
    text = "C" * 5000
    chunks = _chunk_text(text, 2000)
    assert len(chunks) == 3


# ── Logger ────────────────────────────────────────────────────────────────────

def test_get_logger_returns_named_logger():
    """get_logger should return a Python Logger with the given name."""
    import logging
    from utils.logger import get_logger
    log = get_logger("test.module")
    assert isinstance(log, logging.Logger)
    assert log.name == "test.module"


def test_get_logger_different_names_are_different():
    """Different module names should return distinct logger instances."""
    from utils.logger import get_logger
    log_a = get_logger("module.a")
    log_b = get_logger("module.b")
    assert log_a.name != log_b.name
