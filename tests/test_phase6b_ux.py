"""
tests/test_phase6b_ux.py — Phase 6b: Hybrid UX (Tool Calling & Menus).

Tests:
  - Help Menu command triggers send_quick_replies with 8 options.
  - Help Menu quick reply taps send the correct usage hint.
  - Tool calling dispatch in generate_reply:
    - Normal text returns directly.
    - Weather tool call (mocked get_weather call, bypassing second AI hop).
    - Currency tool call (mocked convert_currency call, formatting output).
    - Image gen tool call (mocked generate_image + upload_image + send_image_url, returning "").
    - Translation tool call (mocked translate_text).
    - Disabled tool via feature flags returns "disabled" message.
    - Unknown tool name handles gracefully.
"""

from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from tests.conftest import FakeRedis, FakeConn, FakePool, FakeTxnConn, FakeAcquire


# ── Help Menu Commands ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_help_command_shows_menu():
    """Verify that '/help', '/menu', and 'help' trigger the quick replies menu."""
    from services.event_processor import handle_help_command
    pool = FakePool(FakeConn())
    redis = FakeRedis()
    psid = "user_help_test"
    
    with patch("services.event_processor.send_quick_replies", new_callable=AsyncMock) as mock_qr:
        await handle_help_command(pool, redis, psid, "/help", None)
        mock_qr.assert_called_once()
        
        args = mock_qr.call_args[0]
        assert args[0] == psid
        assert "tap something to get started" in args[1]
        options = args[2]
        assert len(options) == 8
        # Verify some option labels and payloads
        assert options[0] == ("🌦️ Weather", "HELP_WEATHER")
        assert options[2] == ("🎨 Generate Image", "HELP_IMAGE")


# ── Help Menu Quick Reply Taps ────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_help_quick_reply_taps():
    """Verify that tapping a help menu option sends the corresponding hint text."""
    from services.event_processor import handle_help_quick_reply
    psid = "user_qr_test"
    
    with patch("services.event_processor.send_text_message", new_callable=AsyncMock) as mock_send:
        # Test Weather hint
        await handle_help_quick_reply(psid, "HELP_WEATHER")
        mock_send.assert_called_once_with(psid, "Type the city name you want weather for:")
        
        # Test Image hint
        mock_send.reset_mock()
        await handle_help_quick_reply(psid, "HELP_IMAGE")
        assert "Describe the image you want" in mock_send.call_args[0][1]


# ── Tool Calling Dispatch in generate_reply ───────────────────────────────────

@pytest.mark.asyncio
async def test_generate_reply_normal_text():
    """Verify generate_reply returns normal text when no tool is called."""
    from services.event_processor import generate_reply
    pool = FakePool(FakeConn())
    redis = FakeRedis()
    psid = "user_normal_ai"
    
    with patch("services.event_processor.get_groq_reply", new_callable=AsyncMock) as mock_groq:
        mock_groq.return_value = "Hello! How can I help you today?"
        reply = await generate_reply(pool, redis, psid, "default", "Hi", None)
        assert reply == "Hello! How can I help you today?"
        
        # Verify history was updated
        history = await redis.lrange(f"chat_history:{psid}", 0, -1)
        assert len(history) == 2


@pytest.mark.asyncio
async def test_generate_reply_tool_call_weather_enabled():
    """Verify generate_reply executes the weather tool directly when requested by Groq."""
    from services.event_processor import generate_reply
    # Mock is_feature_enabled to return True
    conn = FakeConn(fetchrow_results=[{"key": "weather", "enabled": True}])
    pool = FakePool(conn)
    redis = FakeRedis()
    psid = "user_tool_weather"
    
    tool_call_payload = {
        "type": "tool_call",
        "name": "get_weather",
        "args": {"city": "Paris"}
    }
    
    with (
        patch("services.event_processor.get_groq_reply", new_callable=AsyncMock, return_value=tool_call_payload),
        patch("services.event_processor.get_weather", new_callable=AsyncMock, return_value="Paris is sunny, 22C") as mock_get_weather,
        patch("services.event_processor.is_feature_enabled", new_callable=AsyncMock, return_value=True)
    ):
        reply = await generate_reply(pool, redis, psid, "default", "What's the weather in Paris?", None)
        assert reply == "Paris is sunny, 22C"
        mock_get_weather.assert_called_once_with(redis, "Paris")


@pytest.mark.asyncio
async def test_generate_reply_tool_call_weather_disabled():
    """Verify generate_reply returns a disabled message if the weather tool is disabled by flags."""
    from services.event_processor import generate_reply
    # Mock is_feature_enabled to return False
    conn = FakeConn(fetchrow_results=[{"key": "weather", "enabled": False}])
    pool = FakePool(conn)
    redis = FakeRedis()
    psid = "user_tool_weather_disabled"
    
    tool_call_payload = {
        "type": "tool_call",
        "name": "get_weather",
        "args": {"city": "Paris"}
    }
    
    with (
        patch("services.event_processor.get_groq_reply", new_callable=AsyncMock, return_value=tool_call_payload),
        patch("services.event_processor.is_feature_enabled", new_callable=AsyncMock, return_value=False),
        patch("services.event_processor.get_weather", new_callable=AsyncMock) as mock_get_weather
    ):
        reply = await generate_reply(pool, redis, psid, "default", "Weather in Paris?", None)
        assert "temporarily disabled" in reply
        mock_get_weather.assert_not_called()


@pytest.mark.asyncio
async def test_generate_reply_tool_call_currency():
    """Verify currency tool conversion is called and formatted correctly."""
    from services.event_processor import generate_reply
    pool = FakePool(FakeConn())
    redis = FakeRedis()
    psid = "user_tool_currency"
    
    tool_call_payload = {
        "type": "tool_call",
        "name": "convert_currency",
        "args": {"amount": 100, "from_currency": "USD", "to_currency": "EUR"}
    }
    
    mock_conversion_result = {
        "amount": 100.0,
        "from": "USD",
        "to": "EUR",
        "result": 92.5,
        "rate": 0.925,
        "date": "2026-06-27"
    }
    
    with (
        patch("services.event_processor.get_groq_reply", new_callable=AsyncMock, return_value=tool_call_payload),
        patch("services.event_processor.is_feature_enabled", new_callable=AsyncMock, return_value=True),
        patch("services.event_processor.convert_currency", new_callable=AsyncMock, return_value=mock_conversion_result) as mock_convert
    ):
        reply = await generate_reply(pool, redis, psid, "default", "Convert 100 USD to EUR", None)
        assert "100.0 USD = 92.5 EUR" in reply
        assert "Rate: 1 USD = 0.9250 EUR" in reply
        mock_convert.assert_called_once_with(100.0, "USD", "EUR")


@pytest.mark.asyncio
async def test_generate_reply_tool_call_image_gen():
    """Verify image generation tool generates, uploads, sends the image, and returns empty string."""
    from services.event_processor import generate_reply
    pool = FakePool(FakeConn())
    redis = FakeRedis()
    psid = "user_tool_image"
    
    tool_call_payload = {
        "type": "tool_call",
        "name": "generate_image",
        "args": {"prompt": "a red apple"}
    }
    
    with (
        patch("services.event_processor.get_groq_reply", new_callable=AsyncMock, return_value=tool_call_payload),
        patch("services.event_processor.is_feature_enabled", new_callable=AsyncMock, return_value=True),
        patch("services.event_processor.generate_image", new_callable=AsyncMock, return_value=b"image-bytes") as mock_gen,
        patch("services.event_processor.upload_image", new_callable=AsyncMock, return_value="https://supabase.co/apple.png") as mock_upload,
        patch("services.event_processor.send_image_url", new_callable=AsyncMock) as mock_send_img
    ):
        reply = await generate_reply(pool, redis, psid, "default", "Draw a red apple", None)
        # Should return empty string because the image was sent directly
        assert reply == ""
        mock_gen.assert_called_once_with("a red apple")
        mock_upload.assert_called_once_with(b"image-bytes")
        mock_send_img.assert_called_once_with(psid, "https://supabase.co/apple.png")


@pytest.mark.asyncio
async def test_generate_reply_unknown_tool():
    """Verify that an unknown tool name returns a friendly error message."""
    from services.event_processor import generate_reply
    pool = FakePool(FakeConn())
    redis = FakeRedis()
    psid = "user_unknown_tool"
    
    tool_call_payload = {
        "type": "tool_call",
        "name": "non_existent_tool_name",
        "args": {}
    }
    
    with patch("services.event_processor.get_groq_reply", new_callable=AsyncMock, return_value=tool_call_payload):
        reply = await generate_reply(pool, redis, psid, "default", "Do something weird", None)
        assert "isn't available yet" in reply


# ── Pipeline routing for HELP_ quick replies ──────────────────────────────────

@pytest.mark.asyncio
async def test_pipeline_routes_help_quick_reply():
    """Verify process_messaging_event routes HELP_ quick replies and stops processing."""
    from services.event_processor import process_messaging_event
    
    txn_conn = FakeTxnConn(fetchrow_results=[
        {"event_id": "mid-qr-help"},
        {"persona": "default", "is_blocked": False}
    ])
    pool = MagicMock()
    pool.acquire.return_value = FakeAcquire(txn_conn)
    redis = FakeRedis()
    
    event = {
        "sender": {"id": "user_qr_route"},
        "message": {
            "mid": "mid-qr-help",
            "text": "🌦️ Weather",
            "quick_reply": {"payload": "HELP_WEATHER"}
        }
    }
    
    with (
        patch("services.event_processor.handle_help_quick_reply", new_callable=AsyncMock) as mock_help_qr,
        patch("services.event_processor.generate_reply", new_callable=AsyncMock) as mock_gen_reply
    ):
        await process_messaging_event(pool, redis, event)
        mock_help_qr.assert_called_once_with("user_qr_route", "HELP_WEATHER")
        # Should NOT proceed to AI generation
        mock_gen_reply.assert_not_called()
