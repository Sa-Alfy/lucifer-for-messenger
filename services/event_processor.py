"""
services/event_processor.py — Per-event processing pipeline (Phase 3).

This module is the central routing hub: it validates, deduplicates, and
dispatches every inbound Messenger event to the correct handler.

Pipeline (Phase 3):
  1. Ignore echo events (bot's own sent messages) — prevents reply loops.
  2. Ignore non-message events (delivery/read receipts) — nothing to do.
  3. Atomically record the event as processed AND upsert the user row in a
     single transaction.  The upsert RETURNS persona so we avoid a second query.
  4. Extend the user's 24-hour messaging window in Redis.
  5. Handle /persona commands (no AI call; just a DB write + ack).
  6. Gate on the ai_chat feature flag (maintenance bypass).
  7. Gate on per-user rate limit (burst protection).
  8. Require text or an image attachment; reject anything else with a notice.
  9. Generate an AI reply (Groq for text, Gemini for images).
 10. Send the reply.

Idempotency design (unchanged from Phase 2):
  The processed_webhook_events INSERT and the users UPSERT run inside a single
  transaction.  The INSERT uses ON CONFLICT DO NOTHING with RETURNING to detect
  duplicates atomically — if the INSERT returns no row, this event has already
  been processed and we exit immediately.

Error handling:
  Groq / Gemini failures are caught in generate_reply() and replaced with a
  user-facing apology.  This function never propagates those exceptions upward.
"""

import httpx

from services.chat_history import append_history, get_history
from services.feature_flags import is_feature_enabled
from services.gemini_vision import describe_image
from services.groq_client import get_groq_reply
from services.messaging_window import mark_user_active
from services.messenger_api import send_text_message
from services.personas import DEFAULT_PERSONA, PERSONAS
from services.rate_limit import is_rate_limited
from utils.logger import get_logger

logger = get_logger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────────

PERSONA_COMMAND_PREFIX = "/persona"
MAX_IMAGE_BYTES = 15 * 1024 * 1024  # 15 MB — refuse anything larger


# ── Helpers ───────────────────────────────────────────────────────────────────

def _extract_first_image_url(attachments: list[dict]) -> str | None:
    """
    Return the URL of the first image attachment, or None if there isn't one.

    Only the first image is processed — handling multiple images in a single
    message is Phase 4+ scope.
    """
    for att in attachments:
        if att.get("type") == "image":
            return att.get("payload", {}).get("url")
    return None


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


# ── Command handling ──────────────────────────────────────────────────────────

async def try_handle_command(pool, psid: str, text: str | None) -> str | None:
    """
    Check whether `text` is a bot command and, if so, handle it.

    Currently supports: /persona <name>

    Returns:
        A reply string if the text was a recognised command.
        None if the text is not a command (caller should proceed normally).
    """
    if not text or not text.strip().lower().startswith(PERSONA_COMMAND_PREFIX):
        return None

    parts = text.strip().split(maxsplit=1)
    if len(parts) < 2:
        return (
            f"Available personas: {', '.join(PERSONAS.keys())}. "
            f"Usage: /persona <name>"
        )

    requested = parts[1].strip().lower()
    if requested not in PERSONAS:
        return (
            f"Unknown persona '{requested}'. "
            f"Available: {', '.join(PERSONAS.keys())}"
        )

    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE users SET persona = $1 WHERE psid = $2",
            requested,
            psid,
        )

    logger.info("Persona changed: psid=%s persona=%s", psid, requested)
    return f"Persona switched to '{requested}'."


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
    image_url = _extract_first_image_url(message.get("attachments", []))

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

    # ── /persona command — handled before AI, no rate-limit consumed ─────────
    command_reply = await try_handle_command(pool, psid, text)
    if command_reply is not None:
        await send_text_message(psid, command_reply)
        return

    # ── Feature flag gate ─────────────────────────────────────────────────────
    if not ai_chat_enabled:
        await send_text_message(
            psid,
            "AI chat is temporarily disabled — back soon.",
        )
        return

    # ── Rate limit gate ───────────────────────────────────────────────────────
    if await is_rate_limited(redis, psid):
        await send_text_message(
            psid,
            "You're sending messages a bit fast — give me a few seconds.",
        )
        return

    # ── Content gate ─────────────────────────────────────────────────────────
    if not text and not image_url:
        await send_text_message(
            psid,
            "I can only read text and photos right now.",
        )
        return

    # ── Generate and send AI reply ────────────────────────────────────────────
    reply = await generate_reply(redis, psid, persona_key, text, image_url)
    await send_text_message(psid, reply)
    logger.info("Event processed and replied: mid=%s psid=%s", mid, psid)
