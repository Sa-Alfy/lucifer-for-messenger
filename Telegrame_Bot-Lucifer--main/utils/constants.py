# ── Bot Constants ─────────────────────────────────────────────
MAX_HISTORY = 20  # Max messages per user in conversation memory

# ── Branding & Developer ──────────────────────────────────────
DEVELOPER_NAME = "Shariar Ahamed"
GITHUB_URL = "https://github.com/Sa-Alfy"
ASSET_PROFILE_PICTURE = "assets/profile picture.png"

# ── Model Registry (Source of Truth) ──────────────────────────

# Gemini Vision Models (Fallback order)
# Gemini 2.5 Flash is currently the latest active model in Apr 2026
GEMINI_VISION_MODELS = [
    "gemini-2.5-flash",
    "gemini-2.0-flash", 
    "gemini-flash-latest",
    "gemini-1.5-flash"
]

# Groq Chat Models (Fallback order)
# Llama 3.3 70B is currently the standard for high performance
# Llama 3.1 8B is a very fast and reliable fallback
GROQ_CHAT_MODELS = [
    "llama-3.3-70b-versatile",
    "llama-3.1-8b-instant"
]

# Hugging Face Image Generation Model
# Flux.1-schnell is currently the optimal free generator
FLUX_HF_MODEL = "black-forest-labs/FLUX.1-schnell"
FLUX_HF_ROUTER_URL = "https://router.huggingface.co/hf-inference/models/"
