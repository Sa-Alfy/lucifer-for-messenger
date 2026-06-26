import os
from dotenv import load_dotenv

# Load variables from .env
load_dotenv()


class Config:
    # Configuration constants
    TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
    GROQ_API_KEY = os.getenv("GROQ_API_KEY")
    IMAGE_GEN_KEY = os.getenv("IMAGE_GEN_KEY")
    OPENWEATHERMAP_API_KEY = os.getenv("OPENWEATHERMAP_API_KEY")
    ADMIN_ID = os.getenv("ADMIN_ID")
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")


# ── Startup Validation ──────────────────────────────────
_REQUIRED = {
    "TELEGRAM_BOT_TOKEN": Config.TELEGRAM_TOKEN,
}
_OPTIONAL = {
    "GROQ_API_KEY": (Config.GROQ_API_KEY, "AI Chat, Translation, Quiz, OCR, Voice"),
    "IMAGE_GEN_KEY": (Config.IMAGE_GEN_KEY, "AI Image Generation"),
    "OPENWEATHERMAP_API_KEY": (Config.OPENWEATHERMAP_API_KEY, "Weather"),
    "ADMIN_ID": (Config.ADMIN_ID, "Admin Debug Panel"),
    "GEMINI_API_KEY": (Config.GEMINI_API_KEY, "Vision AI (OCR, Photo Analysis)"),
}

for name, value in _REQUIRED.items():
    if not value:
        print(f"❌ CRITICAL: {name} is not set in .env! Bot cannot start.")

for name, (value, feature) in _OPTIONAL.items():
    if not value:
        print(f"⚠️  WARNING: {name} is not set — {feature} will not work.")