"""
Prayer times handler — fetches and displays daily prayer times.
Default: Dhaka, Bangladesh.
"""

from telegram import Update
from telegram.ext import ContextTypes
from services.prayer_service import get_prayer_times, PRAYER_NAMES, PRAYER_EMOJIS
from utils.decorators import rate_limit
from utils.logger import get_logger
from state import track_command

logger = get_logger(__name__)


@rate_limit(seconds=5)
async def prayer_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /prayer [city] — Show today's prayer times.
    Default: Dhaka
    """
    track_command("prayer")

    city = "Dhaka"
    country = "Bangladesh"

    if context.args:
        city = " ".join(context.args)

    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    status_msg = await update.message.reply_text(f"🕌 Fetching prayer times for {city}...")

    result = await get_prayer_times(city, country)

    if result.get("success"):
        timings = result["timings"]
        text = (
            f"🕌 <b>Prayer Times — {result['city']}</b>\n"
            f"📅 {result['date']}\n"
            f"━━━━━━━━━━━━━━━━━━━━\n\n"
        )

        for eng_name, bn_name in PRAYER_NAMES.items():
            time_val = timings.get(eng_name, "N/A")
            emoji = PRAYER_EMOJIS.get(eng_name, "🕐")
            text += f"{emoji} <b>{bn_name}</b> ({eng_name}): <code>{time_val}</code>\n"

        text += (
            f"\n━━━━━━━━━━━━━━━━━━━━\n"
            f"<i>📍 Location: {result['city']}, {result['country']}\n"
            f"💡 Use /prayer [city] for other cities</i>"
        )

        await status_msg.edit_text(text, parse_mode="HTML")
    else:
        await status_msg.edit_text(
            f"❌ Could not fetch prayer times.\n\n<b>Reason:</b> {result.get('error')}",
            parse_mode="HTML",
        )
