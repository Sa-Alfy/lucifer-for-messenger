import requests
from config import Config
from utils.logger import get_logger

logger = get_logger(__name__)

# Map OpenWeatherMap icon codes to emojis
WEATHER_EMOJIS = {
    "01d": "☀️", "01n": "🌙",   # clear sky
    "02d": "⛅", "02n": "☁️",   # few clouds
    "03d": "☁️", "03n": "☁️",   # scattered clouds
    "04d": "☁️", "04n": "☁️",   # broken clouds
    "09d": "🌧️", "09n": "🌧️",  # shower rain
    "10d": "🌦️", "10n": "🌧️",  # rain
    "11d": "⛈️", "11n": "⛈️",   # thunderstorm
    "13d": "❄️", "13n": "❄️",   # snow
    "50d": "🌫️", "50n": "🌫️",  # mist/fog
}


def get_weather(city: str) -> dict:
    """Fetch complete weather information from OpenWeatherMap."""
    api_key = Config.OPENWEATHERMAP_API_KEY
    if not api_key:
        return {"success": False, "error": "OpenWeatherMap API Key is not configured in .env"}

    url = f"http://api.openweathermap.org/data/2.5/weather?q={city}&appid={api_key}&units=metric"

    try:
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            data = response.json()
            icon_code = data["weather"][0].get("icon", "01d")
            emoji = WEATHER_EMOJIS.get(icon_code, "🌍")

            return {
                "success": True,
                "temp": data["main"]["temp"],
                "feels_like": data["main"]["feels_like"],
                "humidity": data["main"]["humidity"],
                "wind_speed": data["wind"]["speed"],
                "description": data["weather"][0]["description"].title(),
                "icon_code": icon_code,
                "emoji": emoji,
                "city": data["name"],
                "country": data["sys"]["country"],
            }
        elif response.status_code == 404:
            return {"success": False, "error": f"City '{city}' not found."}
        elif response.status_code == 401:
            return {"success": False, "error": "Invalid OpenWeatherMap API Key."}
        else:
            return {"success": False, "error": f"API returned HTTP {response.status_code}"}
    except Exception as e:
        logger.error(f"Weather API error: {e}")
        return {"success": False, "error": "Network error occurred."}
