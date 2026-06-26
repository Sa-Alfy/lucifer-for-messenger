"""
services/event_processor.py — Per-event processing pipeline (Phase 4).

This module is the central routing hub: it validates, deduplicates, and
dispatches every inbound Messenger event to the correct handler.

Pipeline (Phase 4):
  1. Ignore echo events (bot's own sent messages) — prevents reply loops.
  2. Ignore non-message events (delivery/read receipts) — nothing to do.
  3. Atomically record the event as processed AND upsert the user row in a
     single transaction.  The upsert RETURNS persona so we avoid a second query.
  4. Extend the user's 24-hour messaging window in Redis.
  5. If there is audio but no text: check voice_input flag; if enabled,
     transcribe via Groq Whisper and let the transcribed text flow into the
     normal pipeline (commands + AI reply).
  6. Check if text matches a registered command (dispatch table).
     Every command handler catches its own exceptions and sends its own reply.
  7. Gate on the ai_chat feature flag (maintenance bypass).
  8. Gate on per-user rate limit (burst protection).
  9. Require text or an image attachment; reject anything else with a notice.
 10. Generate an AI reply (Groq for text, Gemini for images) and send it.

Command dispatch table (Phase 4):
  /persona   — switch active persona (no AI call)
  /image     — generate image via HF FLUX.1-schnell + upload to Supabase
  /ocr       — extract text from a photo via Gemini vision
  /translate — translate text via Groq
  /explain   — explain text via Groq
  /summarize — summarize text via Groq
  /rewrite   — rewrite text via Groq

Idempotency design (unchanged from Phase 2):
  The processed_webhook_events INSERT and the users UPSERT run inside a single
  transaction.  The INSERT uses ON CONFLICT DO NOTHING with RETURNING to detect
  duplicates atomically — if the INSERT returns no row, this event has already
  been processed and we exit immediately.

Error handling:
  Every command handler wraps its logic in try/except and sends an apologetic
  reply on failure.  generate_reply() catches AI backend failures internally.
  This function never propagates those exceptions upward.
"""

import httpx

from services.ai_tools import run_ai_tool
from services.chat_history import append_history, get_history
from services.feature_flags import is_feature_enabled
from services.gemini_vision import describe_image
from services.groq_client import get_groq_reply, transcribe_audio
from services.image_gen import generate_image
from services.messaging_window import mark_user_active
from services.messenger_api import send_image_url, send_text_message
from services.ocr import extract_text
from services.personas import DEFAULT_PERSONA, PERSONAS
from services.rate_limit import is_rate_limited
from services.storage import upload_image
from services.translate import translate_text
from utils.logger import get_logger

logger = get_logger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────────

MAX_IMAGE_BYTES = 15 * 1024 * 1024   # 15 MB — refuse anything larger
MAX_AUDIO_BYTES = 20 * 1024 * 1024   # 20 MB — Groq's practical limit


# ── Attachment extraction ─────────────────────────────────────────────────────

def _extract_first_image_url(attachments: list[dict]) -> str | None:
    """
    Return the URL of the first image attachment, or None if there isn't one.

    Only the first image is processed — handling multiple images in a single
    message is out of scope for this phase.
    """
    for att in attachments:
        if att.get("type") == "image":
            return att.get("payload", {}).get("url")
    return None


def _extract_first_audio_url(attachments: list[dict]) -> str | None:
    """
    Return the URL of the first audio attachment, or None if there isn't one.

    Messenger delivers voice messages with type "audio".
    """
    for att in attachments:
        if att.get("type") == "audio":
            return att.get("payload", {}).get("url")
    return None


# ── Download helpers ──────────────────────────────────────────────────────────

async def _download_image(url: str) -> tuple[bytes, str]:
    """
    Download an image from a Messenger CDN URL.

    Returns:
        (raw bytes, mime_type string)

    Raises:
        httpx.HTTPStatusError: Non-2xx response from the CDN.
        ValueError:            Image exceeds MAX_IMAGE_BYTES.
    """
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        content = resp.content
        if len(content) > MAX_IMAGE_BYTES:
            raise ValueError(
                f"Image size {len(content)} bytes exceeds {MAX_IMAGE_BYTES}-byte limit"
            )
        mime_type = resp.headers.get("content-type", "image/jpeg").split(";")[0]
        return content, mime_type


async def _download_audio(url: str) -> bytes:
    """
    Download a voice message from a Messenger CDN URL.

    Raises:
        httpx.HTTPStatusError: Non-2xx response from the CDN.
        ValueError:            Audio exceeds MAX_AUDIO_BYTES.
    """
    async with httpx.AsyncClient(timeout=20) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        content = resp.content
        if len(content) > MAX_AUDIO_BYTES:
            raise ValueError(
                f"Audio size {len(content)} bytes exceeds {MAX_AUDIO_BYTES}-byte limit"
            )
        return content


# ── Command handlers ──────────────────────────────────────────────────────────
# All handlers share the same signature:
#   async def handle_X(pool, redis, psid, text, image_url) -> None
# Each handler sends its own reply and catches its own exceptions — nothing
# propagates back to the caller.

async def handle_persona_command(pool, redis, psid: str, text: str, image_url: str | None) -> None:
    """Switch the user's active persona."""
    parts = text.strip().split(maxsplit=1)
    if len(parts) < 2:
        await send_text_message(
            psid,
            f"Available personas: {', '.join(PERSONAS.keys())}. Usage: /persona <name>",
        )
        return

    requested = parts[1].strip().lower()
    if requested not in PERSONAS:
        await send_text_message(
            psid,
            f"Unknown persona '{requested}'. Available: {', '.join(PERSONAS.keys())}",
        )
        return

    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE users SET persona = $1 WHERE psid = $2", requested, psid
        )
    logger.info("Persona changed: psid=%s persona=%s", psid, requested)
    await send_text_message(psid, f"Persona switched to '{requested}'.")


async def handle_image_command(pool, redis, psid: str, text: str, image_url: str | None) -> None:
    """Generate an image from a text prompt via HF FLUX.1-schnell."""
    async with pool.acquire() as conn:
        if not await is_feature_enabled(conn, "image_gen"):
            await send_text_message(psid, "Image generation is temporarily disabled.")
            return

    parts = text.strip().split(maxsplit=1)
    if len(parts) < 2 or not parts[1].strip():
        await send_text_message(psid, "Usage: /image <description>")
        return

    try:
        image_bytes = await generate_image(parts[1].strip())
        hosted_url = await upload_image(image_bytes)
        await send_image_url(psid, hosted_url)
    except Exception:
        logger.exception("Image generation failed for psid=%s", psid)
        await send_text_message(
            psid, "Sorry, I couldn't generate that image — try again in a moment."
        )


async def handle_ocr_command(pool, redis, psid: str, text: str, image_url: str | None) -> None:
    """Extract text from an attached image using Gemini vision."""
    async with pool.acquire() as conn:
        if not await is_feature_enabled(conn, "ocr"):
            await send_text_message(psid, "OCR is temporarily disabled.")
            return

    if not image_url:
        await send_text_message(psid, "Send a photo with the caption /ocr to extract its text.")
        return

    try:
        image_bytes, mime_type = await _download_image(image_url)
        extracted = await extract_text(image_bytes, mime_type)
        await send_text_message(psid, extracted or "No text found in that image.")
    except Exception:
        logger.exception("OCR failed for psid=%s", psid)
        await send_text_message(
            psid, "Sorry, I couldn't read that image — try again in a moment."
        )


async def handle_translate_command(pool, redis, psid: str, text: str, image_url: str | None) -> None:
    """Translate text into a specified language via Groq."""
    async with pool.acquire() as conn:
        if not await is_feature_enabled(conn, "translate"):
            await send_text_message(psid, "Translation is temporarily disabled.")
            return

    parts = text.strip().split(maxsplit=2)
    if len(parts) < 3:
        await send_text_message(psid, "Usage: /translate <language> <text>")
        return

    try:
        translated = await translate_text(parts[1], parts[2])
        await send_text_message(psid, translated)
    except Exception:
        logger.exception("Translation failed for psid=%s", psid)
        await send_text_message(
            psid, "Sorry, translation failed — try again in a moment."
        )


async def _handle_ai_tool(tool: str, pool, psid: str, text: str) -> None:
    """Shared implementation for explain / summarize / rewrite."""
    async with pool.acquire() as conn:
        if not await is_feature_enabled(conn, "ai_chat"):
            await send_text_message(psid, "AI tools are temporarily disabled.")
            return

    parts = text.strip().split(maxsplit=1)
    if len(parts) < 2 or not parts[1].strip():
        await send_text_message(psid, f"Usage: /{tool} <text>")
        return

    try:
        result = await run_ai_tool(tool, parts[1].strip())
        await send_text_message(psid, result)
    except Exception:
        logger.exception("%s failed for psid=%s", tool, psid)
        await send_text_message(psid, "Sorry, that didn't work — try again in a moment.")


async def handle_explain_command(pool, redis, psid: str, text: str, image_url: str | None) -> None:
    await _handle_ai_tool("explain", pool, psid, text)


async def handle_summarize_command(pool, redis, psid: str, text: str, image_url: str | None) -> None:
    await _handle_ai_tool("summarize", pool, psid, text)


async def handle_rewrite_command(pool, redis, psid: str, text: str, image_url: str | None) -> None:
    await _handle_ai_tool("rewrite", pool, psid, text)


# ── Command dispatch table ────────────────────────────────────────────────────

COMMAND_HANDLERS: dict[str, object] = {
    "/persona":   handle_persona_command,
    "/image":     handle_image_command,
    "/ocr":       handle_ocr_command,
    "/translate": handle_translate_command,
    "/explain":   handle_explain_command,
    "/summarize": handle_summarize_command,
    "/rewrite":   handle_rewrite_command,
}


async def try_handle_command(
    pool,
    redis,
    psid: str,
    text: str | None,
    image_url: str | None,
) -> bool:
    """
    Check whether *text* is a registered command and, if so, dispatch it.

    Returns:
        True  — a handler was found and called (caller should stop).
        False — not a command; caller should continue with AI chat.
    """
    if not text:
        return False

    first_word = text.strip().split(maxsplit=1)[0].lower()
    handler = COMMAND_HANDLERS.get(first_word)
    if handler is None:
        return False

    await handler(pool, redis, psid, text, image_url)
    return True


# ── AI reply generation ───────────────────────────────────────────────────────

async def generate_reply(
    redis,
    psid: str,
    persona_key: str,
    text: str | None,
    image_url: str | None,
) -> str:
    """
    Route to the correct AI backend and return a reply string.

    - Image present → Gemini (single-turn; NOT stored in history by design).
    - Text only     → Groq with full conversation history from Redis.

    Any exception from either AI path is caught here and replaced with a
    stock apology so the user always gets a response.

    History storage:
      - Text turns: user message + assistant reply are both appended.
      - Image turns: "[photo]" is stored for the user turn to preserve the
        conversational flow, and the Gemini reply is stored as assistant turn.
    """
    system_prompt = PERSONAS.get(persona_key, PERSONAS[DEFAULT_PERSONA])

    try:
        if image_url:
            image_bytes, mime_type = await _download_image(image_url)
            reply = await describe_image(
                system_prompt,
                text or "Describe this image.",
                image_bytes,
                mime_type,
            )
        else:
            history = await get_history(redis, psid)
            reply = await get_groq_reply(system_prompt, history, text)
    except Exception:
        logger.exception("AI generation failed for psid=%s", psid)
        return "Sorry, I'm having trouble thinking right now — try again in a moment."

    # Store conversation turn in Redis history.
    await append_history(redis, psid, "user", text or "[photo]")
    await append_history(redis, psid, "assistant", reply)
    return reply


# ── Event pipeline ────────────────────────────────────────────────────────────

async def process_messaging_event(pool, redis, messaging_event: dict) -> None:
    """
    Process a single Messenger messaging event end-to-end.

    Args:
        pool:            asyncpg connection pool (from db.postgres.get_pool).
        redis:           redis.asyncio client (from db.redis_client.get_redis).
        messaging_event: A single dict from entry["messaging"] in the payload.
    """
    # ── Guard: ignore echoes of the bot's own sent messages ──────────────────
    if messaging_event.get("message", {}).get("is_echo"):
        logger.debug("Ignoring echo event — bot's own message, skipping.")
        return

    # ── Guard: ignore non-message events (delivery/read receipts, etc.) ──────
    message = messaging_event.get("message")
    if not message:
        logger.debug("No 'message' key in event — delivery/read receipt, skipping.")
        return

    psid = messaging_event["sender"]["id"]
    mid = message["mid"]
    text = message.get("text")
    attachments = message.get("attachments", [])
    image_url = _extract_first_image_url(attachments)
    audio_url = _extract_first_audio_url(attachments)

    logger.info("Webhook event received: mid=%s psid=%s", mid, psid)

    # ── Atomic idempotency gate + user upsert + feature flag (single conn) ───
    async with pool.acquire() as conn:
        async with conn.transaction():
            # Idempotency: INSERT returns nothing if mid was already seen.
            row = await conn.fetchrow(
                "INSERT INTO processed_webhook_events (event_id) VALUES ($1) "
                "ON CONFLICT (event_id) DO NOTHING RETURNING event_id",
                mid,
            )
            if row is None:
                logger.info(
                    "Duplicate event detected, skipping: mid=%s psid=%s", mid, psid
                )
                return

            # Upsert user; RETURNING persona means one query does two jobs.
            user_row = await conn.fetchrow(
                "INSERT INTO users (psid) VALUES ($1) "
                "ON CONFLICT (psid) DO UPDATE SET "
                "    last_seen_at  = now(), "
                "    message_count = users.message_count + 1 "
                "RETURNING persona",
                psid,
            )

            # Feature flag check happens inside the same connection.
            ai_chat_enabled = await is_feature_enabled(conn, "ai_chat")

    persona_key: str = user_row["persona"] or DEFAULT_PERSONA

    # ── Extend Redis messaging window ─────────────────────────────────────────
    await mark_user_active(redis, psid)

    # ── Voice input: transcribe audio before routing ──────────────────────────
    # A voice message with no text caption is transcribed first; the resulting
    # text then flows through the normal command router and AI chat path.
    # This means a spoken "/persona teacher" works exactly like a typed one,
    # and a spoken question gets a normal persona-aware AI reply.
    if audio_url and not text:
        async with pool.acquire() as conn:
            voice_enabled = await is_feature_enabled(conn, "voice_input")
        if not voice_enabled:
            await send_text_message(
                psid,
                "Voice messages are temporarily disabled — try typing instead.",
            )
            return
        try:
            audio_bytes = await _download_audio(audio_url)
            text = await transcribe_audio(audio_bytes)
            logger.info("Voice transcription complete: psid=%s chars=%d", psid, len(text))
        except Exception:
            logger.exception("Transcription failed for psid=%s", psid)
            await send_text_message(
                psid, "Sorry, I couldn't understand that voice message."
            )
            return

    # ── Command dispatch ──────────────────────────────────────────────────────
    if await try_handle_command(pool, redis, psid, text, image_url):
        return

    # ── Feature flag gate ─────────────────────────────────────────────────────
    if not ai_chat_enabled:
        await send_text_message(psid, "AI chat is temporarily disabled — back soon.")
        return

    # ── Rate limit gate ───────────────────────────────────────────────────────
    if await is_rate_limited(redis, psid):
        await send_text_message(
            psid, "You're sending messages a bit fast — give me a few seconds."
        )
        return

    # ── Content gate ──────────────────────────────────────────────────────────
    if not text and not image_url:
        await send_text_message(
            psid, "I can only read text, photos, and voice messages right now."
        )
        return

    # ── Generate and send AI reply ────────────────────────────────────────────
    reply = await generate_reply(redis, psid, persona_key, text, image_url)
    await send_text_message(psid, reply)
    logger.info("Event processed and replied: mid=%s psid=%s", mid, psid)
