"""
services/weather.py — OpenWeatherMap weather lookup with Redis caching.

Uses the classic 2.5 weather endpoint only (not One Call).
Responses are cached in Redis for 10 minutes to reduce API quota usage.
"""

import httpx

from config import settings
from utils.logger import get_logger

logger = get_logger(__name__)

WEATHER_API_URL = "https://api.openweathermap.org/data/2.5/weather"
CACHE_TTL_SECONDS = 600

WEATHER_EMOJIS = {
    "01d": "☀️", "01n": "🌙",
    "02d": "⛅", "02n": "☁️",
    "03d": "☁️", "03n": "☁️",
    "04d": "☁️", "04n": "☁️",
    "09d": "🌧️", "09n": "🌧️",
    "10d": "🌦️", "10n": "🌧️",
    "11d": "⛈️", "11n": "⛈️",
    "13d": "❄️", "13n": "❄️",
    "50d": "🌫️", "50n": "🌫️",
}


def _format_weather(data: dict) -> str:
    """Build a human-readable weather summary from OpenWeatherMap JSON."""
    icon_code = data["weather"][0].get("icon", "01d")
    emoji = WEATHER_EMOJIS.get(icon_code, "🌍")
    city = data["name"]
    country = data["sys"]["country"]
    description = data["weather"][0]["description"].title()
    temp = data["main"]["temp"]
    feels_like = data["main"]["feels_like"]
    humidity = data["main"]["humidity"]
    wind_speed = data["wind"]["speed"]

    return (
        f"{city}, {country}\n"
        f"{emoji} {description}\n"
        f"Temperature: {temp:.0f}°C (feels like {feels_like:.0f}°C)\n"
        f"Humidity: {humidity}% | Wind: {wind_speed} m/s"
    )


async def get_weather(redis, city: str) -> str:
    """
    Return a weather summary string for *city*, using Redis cache when available.

    Args:
        redis: Initialised redis.asyncio.Redis client (decode_responses=True).
        city:  City name to look up.

    Returns:
        Formatted weather summary string.

    Raises:
        ValueError: City not found (404) or API key not configured.
        httpx.HTTPStatusError: Other non-2xx API responses.
    """
    cache_key = f"weather_cache:{city.lower()}"
    cached = await redis.get(cache_key)
    if cached:
        logger.debug("Weather cache hit: city=%s", city)
        return cached

    if not settings.openweather_api_key:
        raise ValueError("Weather service is not configured.")

    logger.debug("Weather cache miss: city=%s", city)

    async with httpx.AsyncClient(timeout=10, follow_redirects=True) as client:
        resp = await client.get(
            WEATHER_API_URL,
            params={
                "q": city,
                "appid": settings.openweather_api_key,
                "units": "metric",
            },
        )
        if resp.status_code == 404:
            raise ValueError(
                f"I couldn't find a city called '{city}' — check the spelling?"
            )
        resp.raise_for_status()
        data = resp.json()

    summary = _format_weather(data)
    await redis.set(cache_key, summary, ex=CACHE_TTL_SECONDS)
    logger.debug("Weather cached: city=%s", city)
    return summary
