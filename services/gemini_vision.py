"""
services/gemini_vision.py — Google Gemini vision wrapper for photo understanding.

Uses the stable generate_content API (client.aio.models.generate_content),
NOT the beta Interactions API (client.interactions.create).

Scope for this phase: single-turn only.  Image replies are NOT stored in Redis
chat history — each photo is understood in isolation with no prior context.
This is intentional and documented; the history integration is Phase 4 work.

The system instruction is passed via GenerateContentConfig so it is cleanly
separated from the user content (not folded into the messages list).
"""

from google import genai
from google.genai import types

from config import settings
from utils.logger import get_logger

logger = get_logger(__name__)

# ── Model ─────────────────────────────────────────────────────────────────────

GEMINI_VISION_MODEL = "gemini-2.5-flash"

# ── Client (module-level singleton) ───────────────────────────────────────────

_gemini_client: genai.Client | None = None


def _get_client() -> genai.Client:
    """Lazily initialise the Gemini client so import-time failures are avoided."""
    global _gemini_client
    if _gemini_client is None:
        _gemini_client = genai.Client(api_key=settings.gemini_api_key)
    return _gemini_client


# ── Public API ────────────────────────────────────────────────────────────────

async def describe_image(
    system_prompt: str,
    prompt: str,
    image_bytes: bytes,
    mime_type: str,
) -> str:
    """
    Send an image to Gemini and return a text description.

    Uses the stable generate_content API.  The system_prompt is passed as a
    GenerateContentConfig system_instruction rather than a user message so the
    model treats it as a behavioural constraint, not part of the conversation.

    Args:
        system_prompt: The active persona's system text.
        prompt:        The user's text prompt accompanying the image (e.g.
                       "What's in this photo?" or a user-supplied caption).
        image_bytes:   Raw image bytes.
        mime_type:     MIME type of the image (e.g. "image/jpeg", "image/png").

    Returns:
        The model's textual description / answer.
    """
    logger.debug(
        "Gemini vision call: model=%s mime_type=%s bytes=%d",
        GEMINI_VISION_MODEL,
        mime_type,
        len(image_bytes),
    )

    response = await _get_client().aio.models.generate_content(
        model=GEMINI_VISION_MODEL,
        contents=[
            prompt,
            types.Part.from_bytes(data=image_bytes, mime_type=mime_type),
        ],
        config=types.GenerateContentConfig(system_instruction=system_prompt),
    )

    logger.debug("Gemini vision reply received.")
    return response.text
