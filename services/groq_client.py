"""
services/groq_client.py — Groq async API wrapper with same-provider fallback
and OpenAI-compatible tool (function) calling.

Model notes (as of June 17, 2026):
  - llama-3.1-8b-instant and llama-3.3-70b-versatile are deprecated on Groq.
  - Primary model:  openai/gpt-oss-120b  (highest quality)
  - Fallback model: openai/gpt-oss-20b   (same provider, lower latency)

Retry policy:
  - Up to 2 attempts per model call, exponential back-off (1–4 s).
  - Only retries on transport errors or 5xx — not 400/401/403/429.
  - If the primary model itself raises after retries, get_groq_reply falls back
    to the lower model rather than immediately giving up.

Tool calling:
  - GROQ_TOOLS defines the functions exposed to the model (weather, currency,
    image gen, translation).
  - get_groq_reply returns either a plain str (normal chat) or a dict of the
    form {"type": "tool_call", "name": <fn>, "args": <dict>} when the model
    decides to call a tool.
  - Tool results are dispatched and formatted by event_processor — we do NOT
    send a second Groq request; the formatted tool output goes directly to the
    user, which halves latency and saves tokens.

max_completion_tokens is used instead of the deprecated max_tokens parameter.
"""

import json
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

# ── Tool Definitions (OpenAI-compatible schema) ───────────────────────────────
# These are the functions the model is allowed to call on the user's behalf.
# Keep descriptions concise but unambiguous — the model uses them to decide
# which tool to invoke and with which parameters.

GROQ_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": (
                "Get the current live weather for a specific city. "
                "Call this ONLY when the user explicitly asks for weather information "
                "in a specific place. Do NOT call this for casual mentions of weather."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "city": {
                        "type": "string",
                        "description": "The city name to look up, e.g. 'London' or 'Dhaka'.",
                    }
                },
                "required": ["city"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "convert_currency",
            "description": (
                "Convert an amount of money from one currency to another using "
                "ECB reference rates. Call this when the user asks to convert a "
                "specific amount between two currency codes."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "amount": {
                        "type": "number",
                        "description": "The numeric amount to convert, e.g. 100.",
                    },
                    "from_currency": {
                        "type": "string",
                        "description": "The source ISO 4217 currency code, e.g. 'USD'.",
                    },
                    "to_currency": {
                        "type": "string",
                        "description": "The target ISO 4217 currency code, e.g. 'EUR'.",
                    },
                },
                "required": ["amount", "from_currency", "to_currency"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "generate_image",
            "description": (
                "Generate an image from a text description using AI. "
                "Call this when the user asks to create, draw, or generate an image."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "prompt": {
                        "type": "string",
                        "description": "A detailed description of the image to generate.",
                    }
                },
                "required": ["prompt"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "translate_text",
            "description": (
                "Translate text into a specified target language. "
                "Call this when the user explicitly asks to translate something."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "language": {
                        "type": "string",
                        "description": "The target language name or code, e.g. 'Bengali' or 'fr'.",
                    },
                    "text": {
                        "type": "string",
                        "description": "The text to translate.",
                    },
                },
                "required": ["language", "text"],
            },
        },
    },
]

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
async def _chat_completion(model: str, messages: list[dict], tools: list[dict] | None = None):
    """
    POST a chat-completion request to Groq.  Retried by tenacity on transient
    failures; permanent errors are re-raised to the caller.

    When tools are provided, the model may respond with a tool_calls array
    instead of (or in addition to) a content string.
    """
    kwargs = dict(
        model=model,
        messages=messages,
        max_completion_tokens=600,
        temperature=0.7,
    )
    if tools:
        kwargs["tools"] = tools
        kwargs["tool_choice"] = "auto"

    return await _get_client().chat.completions.create(**kwargs)


# ── Public API ────────────────────────────────────────────────────────────────

async def get_groq_reply(
    system_prompt: str,
    history: list[dict],
    text: str,
    use_tools: bool = True,
) -> str | dict:
    """
    Generate a reply from Groq, trying the primary model first.

    When use_tools=True (default), the model is given access to the GROQ_TOOLS
    function schemas.  If the model decides to call a tool, this function
    returns a dict:
        {"type": "tool_call", "name": <function_name>, "args": <dict>}

    If the model replies with normal text, a plain str is returned.

    If the primary model raises after its retry budget, falls back to the
    GROQ_FALLBACK_MODEL.  Any failure at that stage is re-raised so the caller
    can catch it and return a stock error message to the user.

    Args:
        system_prompt: The persona system prompt to prepend.
        history:       Prior conversation turns (list of role/content dicts).
        text:          The user's current message.
        use_tools:     Whether to expose tools to the model (default: True).

    Returns:
        Plain str for normal chat, or a tool_call dict for tool invocations.
    """
    messages: list[dict] = [
        {"role": "system", "content": system_prompt},
        *history,
        {"role": "user", "content": text},
    ]
    tools = GROQ_TOOLS if use_tools else None

    try:
        resp = await _chat_completion(GROQ_PRIMARY_MODEL, messages, tools)
        logger.debug("Groq reply received via primary model.")
    except Exception:
        logger.warning(
            "Primary Groq model (%s) failed — falling back to %s.",
            GROQ_PRIMARY_MODEL,
            GROQ_FALLBACK_MODEL,
        )
        resp = await _chat_completion(GROQ_FALLBACK_MODEL, messages, tools)
        logger.debug("Groq reply received via fallback model.")

    choice = resp.choices[0]

    # ── Tool call response ────────────────────────────────────────────────────
    # The model has decided to call one of the exposed functions.
    # We return a structured dict; event_processor dispatches the real call.
    if choice.finish_reason == "tool_calls" and choice.message.tool_calls:
        tool_call = choice.message.tool_calls[0]
        fn_name = tool_call.function.name
        try:
            fn_args = json.loads(tool_call.function.arguments)
        except (json.JSONDecodeError, TypeError):
            fn_args = {}
        logger.info("Groq tool call: function=%s args=%s", fn_name, fn_args)
        return {"type": "tool_call", "name": fn_name, "args": fn_args}

    # ── Normal text response ──────────────────────────────────────────────────
    return choice.message.content


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
