"""
services/translate.py — Translation via Groq.

Uses the same get_groq_reply wrapper as the main AI chat path, so the existing
retry logic, model fallback, and token limits all apply automatically.  No
scraping, no third-party translation library, no new dependency.
"""

from services.groq_client import get_groq_reply
from utils.logger import get_logger

logger = get_logger(__name__)


# ── Public API ────────────────────────────────────────────────────────────────

async def translate_text(target_language: str, text: str) -> str:
    """
    Translate *text* into *target_language* using Groq.

    The system prompt instructs the model to return only the translated text
    with no explanation or preamble, so the reply can be sent directly to the
    user without post-processing.

    Args:
        target_language: Human-readable language name, e.g. "Spanish", "French".
        text:            The text to translate.

    Returns:
        The translated text string.

    Raises:
        Any exception from Groq — callers are expected to catch and convert
        to a user-facing error message.
    """
    system_prompt = (
        f"You are a precise translator. Translate the user's message into "
        f"{target_language}. Return only the translation, no explanation."
    )
    logger.debug("Translation requested: target_language=%s", target_language)
    result = await get_groq_reply(system_prompt, [], text)
    logger.debug("Translation complete.")
    return result
