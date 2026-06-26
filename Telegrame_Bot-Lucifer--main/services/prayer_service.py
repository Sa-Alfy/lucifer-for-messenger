"""
Prayer times service using the free Aladhan API.
Default location: Dhaka, Bangladesh.
"""

import httpx
from utils.logger import get_logger
from utils.cache import prayer_cache, PRAYER_TTL

logger = get_logger(__name__)

ALADHAN_API = "https://api.aladhan.com/v1/timingsByCity"

# Prayer name translations
PRAYER_NAMES = {
    "Fajr": "ফজর",
    "Sunrise": "সূর্যোদয়",
    "Dhuhr": "যোহর",
    "Asr": "আসর",
    "Maghrib": "মাগরিব",
    "Isha": "ইশা",
}

PRAYER_EMOJIS = {
    "Fajr": "🌅",
    "Sunrise": "☀️",
    "Dhuhr": "🌤️",
    "Asr": "🌇",
    "Maghrib": "🌆",
    "Isha": "🌙",
}


async def get_prayer_times(city: str = "Dhaka", country: str = "Bangladesh") -> dict:
    """
    Fetch prayer times from Aladhan API with caching.
    Returns dict: {"success": True, "timings": {...}, "date": "...", "city": "..."}
    """
    cache_key = f"{city.lower()}_{country.lower()}"
    cached = prayer_cache.get(cache_key)
    if cached:
        return cached

    params = {
        "city": city,
        "country": country,
        "method": 1,  # University of Islamic Sciences, Karachi (common for South Asia)
    }

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(ALADHAN_API, params=params)

        if response.status_code == 200:
            data = response.json()
            if data.get("code") == 200:
                timings = data["data"]["timings"]
                date_info = data["data"]["date"]["readable"]

                # Extract only the main prayers
                result = {
                    "success": True,
                    "timings": {
                        k: timings[k] for k in PRAYER_NAMES.keys() if k in timings
                    },
                    "date": date_info,
                    "city": city,
                    "country": country,
                }
                prayer_cache.set(cache_key, result, PRAYER_TTL)
                return result

        return {"success": False, "error": f"API returned status {response.status_code}"}

    except httpx.TimeoutException:
        return {"success": False, "error": "Prayer times API timed out."}
    except Exception as e:
        logger.error(f"Prayer times error: {e}")
        return {"success": False, "error": f"Network error: {str(e)}"}
