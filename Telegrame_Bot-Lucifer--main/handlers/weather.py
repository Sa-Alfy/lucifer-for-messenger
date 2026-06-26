import asyncio
from telegram import Update
from telegram.ext import ContextTypes
from services.weather import get_weather
from utils.decorators import rate_limit
from utils.cache import weather_cache, WEATHER_TTL
from utils.logger import get_logger

logger = get_logger(__name__)


@rate_limit(seconds=5)
async def weather_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler for the /weather command — rich weather display with caching."""
    if not context.args:
        await update.message.reply_text(
            "🌤️ Please provide a city name. Example: <code>/weather Dhaka</code>",
            parse_mode="HTML",
        )
        return

    city = " ".join(context.args)
    cache_key = city.lower().strip()
    
    # Check cache first
    cached = weather_cache.get(cache_key)
    if cached:
        result = cached
        logger.info(f"Weather cache hit for '{city}'")
    else:
        # Typing indicator
        await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
        status_msg = await update.message.reply_text(f"🔍 Checking weather for '{city}'...")

        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(None, get_weather, city)
        
        if result.get("success"):
            weather_cache.set(cache_key, result, WEATHER_TTL)

    if not cached:
        pass  # status_msg already exists
    else:
        status_msg = await update.message.reply_text("🔍 Loading...")

    if result.get("success"):
        emoji = result.get("emoji", "🌍")
        weather_text = (
            f"{emoji} <b>Weather in {result['city']}, {result['country']}</b>\n\n"
            f"🌡️ <b>Temperature:</b> {result['temp']}°C\n"
            f"🤔 <b>Feels Like:</b> {result['feels_like']}°C\n"
            f"☁️ <b>Condition:</b> {result['description']}\n"
            f"💧 <b>Humidity:</b> {result['humidity']}%\n"
            f"💨 <b>Wind Speed:</b> {result['wind_speed']} m/s"
        )
        await status_msg.edit_text(weather_text, parse_mode="HTML")
    else:
        await status_msg.edit_text(
            f"❌ Could not fetch weather.\n\n<b>Reason:</b> {result.get('error')}",
            parse_mode="HTML",
        )
