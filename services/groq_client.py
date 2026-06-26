"""
services/groq_client.py — Groq async API wrapper with same-provider fallback.

Model notes (as of June 17, 2026):
  - llama-3.1-8b-instant and llama-3.3-70b-versatile are deprecated on Groq.
  - Primary model:  openai/gpt-oss-120b  (highest quality)
  - Fallback model: openai/gpt-oss-20b   (same provider, lower latency)

Retry policy:
  - Up to 2 attempts per model call, exponential back-off (1–4 s).
  - Only retries on transport errors or 5xx — not 400/401/403/429.
  - If the primary model itself raises after retries, get_groq_reply falls back
    to the lower model rather than immediately giving up.

max_completion_tokens is used instead of the deprecated max_tokens parameter.
"""

import logging

from groq import AsyncGroq
from tenacity import (
    retry,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential,
)

from config import settings
from utils.logger import get_logger

logger = get_logger(__name__)

# ── Models ────────────────────────────────────────────────────────────────────

GROQ_PRIMARY_MODEL = "openai/gpt-oss-120b"
GROQ_FALLBACK_MODEL = "openai/gpt-oss-20b"

# ── Client (module-level singleton) ───────────────────────────────────────────

_client: AsyncGroq | None = None


def _get_client() -> AsyncGroq:
    """Lazily initialise the Groq client so import-time failures are avoided."""
    global _client
    if _client is None:
        _client = AsyncGroq(api_key=settings.groq_api_key)
    return _client


# ── Retry predicate ───────────────────────────────────────────────────────────

def _is_retryable(exc: Exception) -> bool:
    """
    Return True only for errors that are worth retrying automatically.

    Transient/server-side issues (5xx, network errors) may clear on their own.
    Client errors (4xx) are permanent for this call — retrying wastes quota.
    """
    response = getattr(exc, "response", None)
    status = getattr(response, "status_code", None)
    # No status (transport error) or a 5xx → retry.
    return status is None or status >= 500


# ── Core completion call (retried) ────────────────────────────────────────────

@retry(
    stop=stop_after_attempt(2),
    wait=wait_exponential(multiplier=1, min=1, max=4),
    retry=retry_if_exception(_is_retryable),
    reraise=True,
)
async def _chat_completion(model: str, messages: list[dict]):
    """
    POST a chat-completion request to Groq.  Retried by tenacity on transient
    failures; permanent errors are re-raised to the caller.
    """
    return await _get_client().chat.completions.create(
        model=model,
        messages=messages,
        max_completion_tokens=600,   # max_tokens is deprecated on Groq's API
        temperature=0.7,
    )


# ── Public API ────────────────────────────────────────────────────────────────

async def get_groq_reply(
    system_prompt: str,
    history: list[dict],
    text: str,
) -> str:
    """
    Generate a text reply from Groq, trying the primary model first.

    If the primary model raises after its retry budget, falls back to the
    GROQ_FALLBACK_MODEL.  Any failure at that stage is re-raised so the caller
    can catch it and return a stock error message to the user.

    Args:
        system_prompt: The persona system prompt to prepend.
        history:       Prior conversation turns (list of role/content dicts).
        text:          The user's current message.

    Returns:
        The assistant's reply string.
    """
    messages: list[dict] = [
        {"role": "system", "content": system_prompt},
        *history,
        {"role": "user", "content": text},
    ]

    try:
        resp = await _chat_completion(GROQ_PRIMARY_MODEL, messages)
        logger.debug("Groq reply received via primary model.")
    except Exception:
        logger.warning(
            "Primary Groq model (%s) failed — falling back to %s.",
            GROQ_PRIMARY_MODEL,
            GROQ_FALLBACK_MODEL,
        )
        resp = await _chat_completion(GROQ_FALLBACK_MODEL, messages)
        logger.debug("Groq reply received via fallback model.")

    return resp.choices[0].message.content


# ── Transcription ─────────────────────────────────────────────────────────────

TRANSCRIPTION_MODEL = "whisper-large-v3-turbo"


async def transcribe_audio(audio_bytes: bytes, filename: str = "voice.mp4") -> str:
    """
    Transcribe audio bytes to text using Groq Whisper.

    Reuses the module-level AsyncGroq client singleton — no extra client is
    created.  The filename extension hints the codec to Groq; Messenger voice
    messages arrive as .mp4/AAC.

    Args:
        audio_bytes: Raw audio bytes downloaded from Messenger.
        filename:    Filename passed to the API as a content-type hint.
                     Defaults to "voice.mp4" (Messenger's format).

    Returns:
        The transcribed text string.

    Raises:
        Any exception from Groq — callers are expected to catch and convert
        to a user-facing error message.
    """
    logger.debug(
        "Groq transcription started: model=%s bytes=%d", TRANSCRIPTION_MODEL, len(audio_bytes)
    )
    result = await _get_client().audio.transcriptions.create(
        file=(filename, audio_bytes),
        model=TRANSCRIPTION_MODEL,
        response_format="text",
    )
    # Groq may return either a plain str (response_format="text") or a
    # Transcription object — handle both to be safe.
    text = result if isinstance(result, str) else result.text
    logger.debug("Groq transcription complete: chars=%d", len(text))
    return text
