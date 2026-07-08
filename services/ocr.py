"""
services/ocr.py — OCR via Gemini vision.

No new vision dependency is introduced here.  This module is a thin adapter
that calls the existing describe_image function with an OCR-specific system
prompt, instructing the model to act purely as an OCR engine rather than as a
conversational assistant.

Design note:
  OCR and image description share the same Gemini client and model (gemini-2.5-flash).
  Using a dedicated system prompt here keeps the two use-cases cleanly separated
  while avoiding code duplication.
"""

from services.gemini_vision import describe_image
from utils.logger import get_logger

logger = get_logger(__name__)

# ── System prompt ─────────────────────────────────────────────────────────────

OCR_SYSTEM_PROMPT = (
    "You are an OCR tool. Extract and return only the literal text visible in "
    "the image, with no commentary, no formatting instructions, and no preamble. "
    "If there is no text in the image, reply with exactly: (no text found)"
)


# ── Public API ────────────────────────────────────────────────────────────────

async def extract_text(image_bytes: bytes, mime_type: str) -> str:
    """
    Extract text from an image using Gemini vision.

    Reuses the describe_image function with an OCR-specific system
    prompt.  No new AI dependency is added.

    Args:
        image_bytes: Raw image bytes (any format Gemini accepts).
        mime_type:   MIME type of the image, e.g. "image/jpeg".

    Returns:
        The raw text found in the image, or a "(no text found)" notice.

    Raises:
        Any exception from Gemini — callers are expected to catch and convert
        to a user-facing error message.
    """
    logger.debug("OCR requested: mime_type=%s bytes=%d", mime_type, len(image_bytes))
    result = await describe_image(
        OCR_SYSTEM_PROMPT,
        "Extract all text from this image.",
        image_bytes,
        mime_type,
    )
    logger.debug("OCR complete.")
    return result or "No text found in that image."
