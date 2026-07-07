"""
tests/test_phase5_utilities.py — Phase 5: Utility Tools.

Tests:
  - Weather lookup (cache hit, cache miss, OpenWeather API call, 404 error, missing API key)
  - Currency conversion (Frankfurter API call, success path, HTTP status error)
"""

from unittest.mock import AsyncMock, MagicMock, patch
import pytest
import httpx
from tests.conftest import FakeRedis


# ── Weather ───────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_weather_cache_hit():
    """Verify get_weather returns cached response directly without calling API."""
    from services.weather import get_weather
    redis = FakeRedis()
    await redis.set("weather_cache:dhaka", "Cached Weather Data", ex=600)
    
    with patch("httpx.AsyncClient") as mock_client:
        result = await get_weather(redis, "Dhaka")
        assert result == "Cached Weather Data"
        mock_client.assert_not_called()


@pytest.mark.asyncio
async def test_get_weather_cache_miss_success():
    """Verify get_weather calls API on cache miss, caches result, and returns formatted text."""
    from services.weather import get_weather
    redis = FakeRedis()
    
    mock_weather_data = {
        "name": "Dhaka",
        "sys": {"country": "BD"},
        "weather": [{"description": "clear sky", "icon": "01d"}],
        "main": {"temp": 30.5, "feels_like": 34.2, "humidity": 70},
        "wind": {"speed": 4.5}
    }
    
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = mock_weather_data
    mock_resp.raise_for_status = MagicMock()
    
    mock_client = MagicMock()
    mock_client.get = AsyncMock(return_value=mock_resp)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    
    with patch("httpx.AsyncClient", return_value=mock_client):
        result = await get_weather(redis, "Dhaka")
        
        assert "Dhaka, BD" in result
        assert "☀️ Clear Sky" in result
        assert "Temperature: 30°C" in result
        assert "Humidity: 70%" in result
        
        # Verify it was cached
        cached = await redis.get("weather_cache:dhaka")
        assert cached == result


@pytest.mark.asyncio
async def test_get_weather_city_not_found():
    """Verify get_weather raises ValueError with a clean message on 404."""
    from services.weather import get_weather
    redis = FakeRedis()
    
    mock_resp = MagicMock()
    mock_resp.status_code = 404
    
    mock_client = MagicMock()
    mock_client.get = AsyncMock(return_value=mock_resp)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    
    with patch("httpx.AsyncClient", return_value=mock_client):
        with pytest.raises(ValueError, match="I couldn't find a city called 'Atlantis'"):
            await get_weather(redis, "Atlantis")


@pytest.mark.asyncio
async def test_get_weather_missing_api_key():
    """Verify get_weather raises ValueError when openweather_api_key is missing/empty."""
    from services.weather import get_weather
    from config import settings
    redis = FakeRedis()
    
    with patch.object(settings, "openweather_api_key", ""):
        with pytest.raises(ValueError, match="Weather service is not configured"):
            await get_weather(redis, "Dhaka")


# ── Currency ──────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_convert_currency_success():
    """Verify convert_currency calls Frankfurter, does math, and returns dict."""
    from services.currency import convert_currency
    
    mock_currency_data = {
        "amount": 100.0,
        "base": "USD",
        "date": "2026-06-27",
        "rates": {"EUR": 92.5}
    }
    
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = mock_currency_data
    mock_resp.raise_for_status = MagicMock()
    
    mock_client = MagicMock()
    mock_client.get = AsyncMock(return_value=mock_resp)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    
    with patch("httpx.AsyncClient", return_value=mock_client):
        result = await convert_currency(100.0, "USD", "EUR")
        
        assert result["amount"] == 100.0
        assert result["from"] == "USD"
        assert result["to"] == "EUR"
        assert result["result"] == 92.5
        assert result["rate"] == 0.925
        assert result["date"] == "2026-06-27"
        
        mock_client.get.assert_called_once_with(
            "https://api.frankfurter.app/latest",
            params={"amount": 100.0, "from": "USD", "to": "EUR"}
        )


@pytest.mark.asyncio
async def test_convert_currency_invalid_codes():
    """Verify convert_currency raises HTTPStatusError on invalid currency code."""
    from services.currency import convert_currency
    
    mock_resp = MagicMock()
    mock_resp.status_code = 400
    mock_resp.raise_for_status.side_effect = httpx.HTTPStatusError(
        message="Bad Request",
        request=MagicMock(),
        response=mock_resp
    )
    
    mock_client = MagicMock()
    mock_client.get = AsyncMock(return_value=mock_resp)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    
    with patch("httpx.AsyncClient", return_value=mock_client):
        with pytest.raises(httpx.HTTPStatusError):
            await convert_currency(100.0, "XYZ", "EUR")
