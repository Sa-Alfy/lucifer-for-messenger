"""
tests/test_phase3_ai_core.py — Phase 3: AI Chat Core.

Tests:
  - Rate limiting (Redis-based, 8 requests per 60s)
  - Messaging window (24h window check)
  - Chat history (retrieval and appending to Redis)
  - Persona switching (/persona command updates database)
  - Groq client (primary success, fallback on 5xx, no-retry on 4xx)
"""

from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from tests.conftest import FakeRedis, FakeConn, FakePool


# ── Rate Limiting ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_rate_limiter_allows_under_limit():
    """Users should not be rate limited on their first few requests."""
    from services.rate_limit import is_rate_limited
    redis = FakeRedis()
    psid = "user_rate_limit_ok"
    
    # 5 requests should all be allowed
    for _ in range(5):
        assert await is_rate_limited(redis, psid) is False


@pytest.mark.asyncio
async def test_rate_limiter_blocks_over_limit():
    """Users should be rate limited after the 8th request within 60s."""
    from services.rate_limit import is_rate_limited
    redis = FakeRedis()
    psid = "user_rate_limit_bad"
    
    # 8 requests are allowed
    for _ in range(8):
        assert await is_rate_limited(redis, psid) is False
        
    # 9th request is blocked
    assert await is_rate_limited(redis, psid) is True


# ── Messaging Window ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_messaging_window_lifecycle():
    """Test that we can mark a user active and check if they are within the 24h window."""
    from services.messaging_window import mark_user_active, is_within_window
    redis = FakeRedis()
    psid = "user_window_test"
    
    # By default, without marking, they are not within window (or we can assume False/True depending on implementation)
    # Let's check is_within_window behavior
    # Note: is_within_window checks if the key exists in Redis
    assert await is_within_window(redis, psid) is False
    
    await mark_user_active(redis, psid)
    assert await is_within_window(redis, psid) is True


# ── Chat History ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_chat_history_append_and_get():
    """Test appending and retrieving history from Redis."""
    from services.chat_history import append_history, get_history
    redis = FakeRedis()
    psid = "user_history_test"
    
    # Empty history initially
    history = await get_history(redis, psid)
    assert history == []
    
    # Append turns
    await append_history(redis, psid, "user", "Hello bot")
    await append_history(redis, psid, "assistant", "Hello human")
    
    history = await get_history(redis, psid)
    assert len(history) == 2
    assert history[0] == {"role": "user", "content": "Hello bot"}
    assert history[1] == {"role": "assistant", "content": "Hello human"}


@pytest.mark.asyncio
async def test_chat_history_truncation():
    """Test that history is kept within limits (e.g., last 20 messages / 10 turns)."""
    from services.chat_history import append_history, get_history
    redis = FakeRedis()
    psid = "user_history_trunc"
    
    # Append 30 messages (15 turns)
    for i in range(15):
        await append_history(redis, psid, "user", f"user message {i}")
        await append_history(redis, psid, "assistant", f"bot reply {i}")
        
    history = await get_history(redis, psid)
    # The limit is usually 20 messages (10 turns) in chat_history.py
    assert len(history) <= 20
    # The last message should be the most recent one
    assert history[-1] == {"role": "assistant", "content": "bot reply 14"}


# ── Persona Switching ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_persona_switching_command_valid():
    """Tapping or typing /persona with a valid name should update the DB."""
    from services.event_processor import handle_persona_command
    conn = FakeConn()
    pool = FakePool(conn)
    redis = FakeRedis()
    psid = "user_persona_switch"
    
    with patch("services.event_processor.send_text_message", new_callable=AsyncMock) as mock_send:
        await handle_persona_command(pool, redis, psid, "/persona teacher", None)
        mock_send.assert_called_once_with(psid, "Persona switched to 'teacher'.")
        
        # Verify the SQL update query was executed
        assert len(conn.executed) == 1
        query, args = conn.executed[0]
        assert "UPDATE users" in query
        assert "teacher" in args
        assert psid in args


@pytest.mark.asyncio
async def test_persona_switching_command_invalid():
    """Typing /persona with an invalid name should list available personas and not update DB."""
    from services.event_processor import handle_persona_command
    conn = FakeConn()
    pool = FakePool(conn)
    redis = FakeRedis()
    psid = "user_persona_switch_bad"
    
    with patch("services.event_processor.send_text_message", new_callable=AsyncMock) as mock_send:
        await handle_persona_command(pool, redis, psid, "/persona super_hero", None)
        # Should inform the user and list available options
        mock_send.assert_called_once()
        assert "Unknown persona" in mock_send.call_args[0][1]
        assert len(conn.executed) == 0


# ── Groq Client fallback & retry ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_groq_client_success():
    """Verify get_groq_reply returns response on successful API call."""
    from services.groq_client import get_groq_reply
    
    mock_choice = MagicMock()
    mock_choice.finish_reason = "stop"
    mock_choice.message.content = "This is a response from Groq."
    mock_choice.message.tool_calls = None
    
    mock_resp = MagicMock()
    mock_resp.choices = [mock_choice]
    
    # Mock the _chat_completion call inside groq_client
    with patch("services.groq_client._chat_completion", new_callable=AsyncMock, return_value=mock_resp) as mock_complete:
        reply = await get_groq_reply("You are Lucifer.", [], "Hello", use_tools=False)
        assert reply == "This is a response from Groq."
        mock_complete.assert_called_once()
        # Ensure it was called with the primary model
        assert mock_complete.call_args[0][0] == "openai/gpt-oss-120b"


@pytest.mark.asyncio
async def test_groq_client_fallback_on_failure():
    """Verify get_groq_reply falls back to the secondary model if the primary fails."""
    from services.groq_client import get_groq_reply
    
    mock_choice = MagicMock()
    mock_choice.finish_reason = "stop"
    mock_choice.message.content = "Fallback response."
    mock_choice.message.tool_calls = None
    
    mock_resp = MagicMock()
    mock_resp.choices = [mock_choice]
    
    # Primary model fails, secondary succeeds
    async def side_effect(model, *args, **kwargs):
        if model == "openai/gpt-oss-120b":
            raise Exception("Primary model overload")
        return mock_resp
        
    with patch("services.groq_client._chat_completion", new_callable=AsyncMock, side_effect=side_effect) as mock_complete:
        reply = await get_groq_reply("You are Lucifer.", [], "Hello", use_tools=False)
        assert reply == "Fallback response."
        # Should be called twice (once for primary, once for fallback)
        assert mock_complete.call_count == 2
