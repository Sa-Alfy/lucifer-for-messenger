import os
import threading
import time
import requests
from http.server import HTTPServer, BaseHTTPRequestHandler
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
    ContextTypes,
)
from config import Config
from handlers.basic import start_command, handle_message, button_callback, back_to_start_callback, help_command, clear_history_command, developer_callback, nav_callback, result_action_callback
from handlers.image_gen import generate_image_command
from handlers.daraz_handler import find_deal_command, daraz_callback
from handlers.weather import weather_command
from handlers.tts import say_male_command, say_female_command
from handlers.debug import debug_command, toggle_api_command, what_type_command
from handlers.admin import admin_command, admin_callback
from handlers.persona import persona_command, persona_callback
from handlers.translate import translate_command
from handlers.voice_input import handle_voice_message
from handlers.qr import qr_command
from handlers.currency import convert_command, bdt_command
from handlers.quiz import quiz_command, quiz_answer_callback
from handlers.ocr import ocr_command
from handlers.download import download_command, download_callback
from handlers.news import news_command
from handlers.sticker import sticker_command
from handlers.games import play_command, stopgame_command, game_callback
from handlers.profile import profile_command
# ── New Feature Imports ──
from handlers.reminder import remind_command, reminder_callback, my_reminders_command
from handlers.vote import vote_command, vote_callback, poll_command, poll_callback
from handlers.ai_tools import explain_command, summarize_command, rewrite_command
from handlers.prayer import prayer_command
from handlers.mobile import mobile_command, mobile_callback
from services.reminder_service import reminder_store
from utils.logger import get_logger
from utils.decorators import enforce_moderation

logger = get_logger(__name__)


# ============================================================
# Health Check Server (Required for Koyeb / Cloud Hosting)
# ============================================================
class HealthCheckHandler(BaseHTTPRequestHandler):
    """Responds to any request with 200 OK."""

    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/plain")
        self.end_headers()
        self.wfile.write(b"Lucifer Bot is running!")

    def log_message(self, format, *args):
        pass


def start_health_server():
    """Starts the health check server in a background daemon thread."""
    port = int(os.environ.get("PORT", 8000))
    server = HTTPServer(("0.0.0.0", port), HealthCheckHandler)
    logger.info(f"Health check server started on port {port}")
    server.serve_forever()


def keep_alive_pinger():
    """Pings the service itself every 10 minutes to prevent Render from sleeping."""
    # Wait for the server to actually start
    time.sleep(10)
    
    url = os.environ.get("RENDER_EXTERNAL_URL")
    if not url:
        logger.warning("RENDER_EXTERNAL_URL environment variable not set. Self-pinging disabled.")
        return

    logger.info(f"Self-pinging service started for: {url}")
    while True:
        try:
            # Ping the health check endpoint
            response = requests.get(url, timeout=30)
            logger.info(f"Self-ping successful: {response.status_code}")
        except Exception as e:
            logger.error(f"Self-ping failed: {e}")
        
        # Wait for 10 minutes (600 seconds)
        time.sleep(600)


# ============================================================
# Global Error Handler
# ============================================================
async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    """Catches unhandled exceptions from any handler and notifies the user."""
    logger.error(f"Unhandled exception: {context.error}", exc_info=context.error)
    
    # Try to notify the user if possible
    if update and isinstance(update, Update) and update.effective_message:
        try:
            await update.effective_message.reply_text(
                "😔 Something went wrong while processing your request. Please try again."
            )
        except Exception:
            pass  # If even this fails, just log it


async def post_init(application: Application):
    """Sets the Telegram Menu button commands and restores pending reminders."""
    commands = [
        ("start", "🏠 শুরু | Start Bot"),
        ("image", "🎨 ভাবো | AI Art"),
        ("find", "🛒 খুঁজো | Find Deals"),
        ("weather", "🌤️ আবহাওয়া | Weather"),
        ("say", "👨 বলো | Boy Voice"),
        ("translate", "🌐 অনুবাদ | Translate"),
        ("convert", "💱 রূপান্তর | Currency"),
        ("bdt", "🇺🇸🇧🇩 USD→BDT Rate"),
        ("news", "📰 খবর | Daily News"),
        ("prayer", "🕌 নামাজ | Prayer Times"),
        ("offers", "📱 অফার | Mobile Offers"),
        ("remind", "⏰ রিমাইন্ড | Reminder"),
        ("vote", "🗳️ ভোট | Quick Vote"),
        ("poll", "📊 পোল | Group Poll"),
        ("explain", "💡 ব্যাখ্যা | Explain"),
        ("quiz", "🧩 কুইজ | Quiz"),
        ("play", "🎲 খেলো | Games"),
        ("download", "📥 ডাউনলোড | Download"),
        ("me", "📊 প্রোফাইল | Profile"),
        ("help", "❓ সাহায্য | Help"),
    ]
    await application.bot.set_my_commands(commands)
    
    # Restore pending reminders from disk
    reminder_store.schedule_all(application)


def main():
    if not Config.TELEGRAM_TOKEN:
        logger.error("No token found in .env file!")
        return

    # Start the health check server in a background thread (for Koyeb/Render)
    health_thread = threading.Thread(target=start_health_server, daemon=True)
    health_thread.start()

    # Start self-pinger to keep Render awake
    pinger_thread = threading.Thread(target=keep_alive_pinger, daemon=True)
    pinger_thread.start()

    # Build the application and include the Menu setup
    app = Application.builder().token(Config.TELEGRAM_TOKEN).post_init(post_init).build()

    import re

    def create_universal_handler(commands: list, func):
        """
        Creates a handler that catches /command, !command, and /command@botname.
        Automatically fixes context.args for the original functions.
        """
        # Matches optional @botname, then / or !, then command, then optional @botname
        pattern = r"^(?:@\w+\s+)?[/\!](" + "|".join(commands) + r")(?:\s*@\w+)?(?:\s+|$)"
        compiled_pattern = re.compile(pattern, re.IGNORECASE)
        
        @enforce_moderation()
        async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
            if not update.message or not update.message.text:
                return
            
            # Populate args identically to CommandHandler but ignoring the prefixes/suffixes
            if context.args is None:
                match = compiled_pattern.match(update.message.text)
                if match:
                    args_text = update.message.text[match.end():].strip()
                    context.args = args_text.split() if args_text else []
                else:
                    context.args = []
                
            return await func(update, context)
            
        return MessageHandler(filters.Regex(compiled_pattern) & filters.ALL, wrapper)

    # --- 1 & 2. Universal Bilingual Command Handlers ---
    app.add_handler(create_universal_handler(["start", "শুরু"], start_command))
    app.add_handler(create_universal_handler(["help", "সাহায্য"], help_command))
    app.add_handler(create_universal_handler(["image", "ভাবো"], generate_image_command))
    app.add_handler(create_universal_handler(["find", "খুঁজো"], find_deal_command))
    app.add_handler(create_universal_handler(["weather", "আবহাওয়া"], weather_command))
    app.add_handler(create_universal_handler(["say", "বলো"], say_male_command))
    app.add_handler(create_universal_handler(["say_as_girl", "মেয়ের_মত_বলো"], say_female_command))
    app.add_handler(create_universal_handler(["translate", "অনুবাদ"], translate_command))
    app.add_handler(create_universal_handler(["convert", "রূপান্তর"], convert_command))
    app.add_handler(create_universal_handler(["qr", "কিউআর"], qr_command))
    app.add_handler(create_universal_handler(["quiz", "কুইজ"], quiz_command))
    app.add_handler(create_universal_handler(["ocr", "ওসিআর"], ocr_command))
    app.add_handler(create_universal_handler(["sticker", "স্টিকার"], sticker_command))
    app.add_handler(create_universal_handler(["news", "খবর"], news_command))
    app.add_handler(create_universal_handler(["persona", "ব্যক্তিত্ব"], persona_command))
    app.add_handler(create_universal_handler(["download", "ডাউনলোড"], download_command))
    app.add_handler(create_universal_handler(["play", "খেলো"], play_command))
    app.add_handler(create_universal_handler(["stopgame", "থামো"], stopgame_command))
    app.add_handler(create_universal_handler(["me", "আমি"], profile_command))
    app.add_handler(create_universal_handler(["clear", "মুছো"], clear_history_command))

    # --- NEW: Group Assistant Commands ---
    app.add_handler(create_universal_handler(["remind", "রিমাইন্ড"], remind_command))
    app.add_handler(create_universal_handler(["myreminders"], my_reminders_command))
    app.add_handler(create_universal_handler(["vote", "ভোট"], vote_command))
    app.add_handler(create_universal_handler(["poll", "পোল"], poll_command))
    app.add_handler(create_universal_handler(["explain", "ব্যাখ্যা"], explain_command))
    app.add_handler(create_universal_handler(["summarize", "সারাংশ"], summarize_command))
    app.add_handler(create_universal_handler(["rewrite", "পুনর্লিখন"], rewrite_command))
    app.add_handler(create_universal_handler(["prayer", "নামাজ"], prayer_command))
    app.add_handler(create_universal_handler(["offers", "অফার"], mobile_command))
    app.add_handler(create_universal_handler(["bdt"], bdt_command))

    # --- 3. UI & Callback Handlers ---
    # Daraz callback (pagination + more options)
    app.add_handler(CallbackQueryHandler(daraz_callback, pattern=r"^daraz:more:"))
    # Navigation & Category callback (Phase 1 Redesign)
    app.add_handler(CallbackQueryHandler(nav_callback, pattern=r"^nav_"))
    # Admin callback
    app.add_handler(CallbackQueryHandler(admin_callback, pattern=r"^admin_"))
    # Persona callback
    app.add_handler(CallbackQueryHandler(persona_callback, pattern=r"^persona_"))
    # Games callback
    app.add_handler(CallbackQueryHandler(game_callback, pattern=r"^game_"))
    # Quiz answer callback
    app.add_handler(CallbackQueryHandler(quiz_answer_callback, pattern=r"^quiz_"))
    # Download quality selection callback
    app.add_handler(CallbackQueryHandler(download_callback, pattern=r"^dl_"))
    # Reminder callbacks
    app.add_handler(CallbackQueryHandler(reminder_callback, pattern=r"^rem_"))
    # Vote callbacks
    app.add_handler(CallbackQueryHandler(vote_callback, pattern=r"^vote_"))
    # Poll callbacks
    app.add_handler(CallbackQueryHandler(poll_callback, pattern=r"^poll_"))
    # Mobile offers callbacks
    app.add_handler(CallbackQueryHandler(mobile_callback, pattern=r"^mob"))
    # Back to menu callback
    app.add_handler(CallbackQueryHandler(back_to_start_callback, pattern=r"^back_to_start$"))
    # Developer info callback
    app.add_handler(CallbackQueryHandler(developer_callback, pattern=r"^developer_info$"))
    # Generic help button callback
    app.add_handler(CallbackQueryHandler(button_callback, pattern=r"^help_"))
    # Result action callbacks (Phase 3 Standardization)
    app.add_handler(CallbackQueryHandler(result_action_callback, pattern=r"_(retry|edit|continue)$"))

    # --- 4. Voice Message Handler ---
    app.add_handler(MessageHandler(filters.VOICE | filters.AUDIO, handle_voice_message))

    # --- 5. Standard AI Message Handler (text + photos) ---
    app.add_handler(
        MessageHandler(
            (filters.TEXT | filters.PHOTO) & ~filters.COMMAND & ~filters.Regex(r"^/"),
            handle_message,
        )
    )

    # --- 6. Admin Debug Commands ---
    app.add_handler(CommandHandler("admin", admin_command))
    app.add_handler(CommandHandler("debug", debug_command))
    app.add_handler(CommandHandler("what_type", what_type_command))
    app.add_handler(
        MessageHandler(
            filters.Regex(r"^/debug_turn_(groq|pollinations|daraz)_(on|off)"),
            toggle_api_command,
        )
    )

    # --- 7. Global Error Handler ---
    app.add_error_handler(error_handler)

    logger.info("Lucifer is starting...")
    app.run_polling()


if __name__ == "__main__":
    main()