"""
services/event_processor.py — Per-event processing pipeline.

This module is the central routing hub: it validates, deduplicates, and
dispatches every inbound Messenger event to the correct handler.

Pipeline:
  1. Ignore echo events (bot's own sent messages) — prevents reply loops.
  2. Ignore non-message events (delivery/read receipts) — nothing to do.
  3. Atomically record the event as processed AND upsert the user row in a
     single transaction.  The upsert RETURNS persona so we avoid a second query.
  4. Extend the user's 24-hour messaging window in Redis.
  5. If there is audio but no text: check voice_input flag; if enabled,
     transcribe via Groq Whisper and let the transcribed text flow into the
     normal pipeline (commands + AI reply).
  6. Route ADMIN_ and HELP_ quick-reply payloads before command/text handling.
  7. Check if text matches a registered command (dispatch table).
     Every command handler catches its own exceptions and sends its own reply.
  8. Gate on the ai_chat feature flag (maintenance bypass).
  9. Gate on per-user rate limit (burst protection).
 10. Require text or an image attachment; reject anything else with a notice.
 11. Generate an AI reply via Groq with Tool Calling enabled.  If Groq decides
     to call a tool (weather, currency, image gen, translate), the tool is
     executed directly and the formatted result sent to the user — no second
     Groq round-trip.  Normal text replies are sent as usual.

Command dispatch table:
  /persona   — switch active persona (no AI call)
  /image     — generate image via HF FLUX.1-schnell + upload to Supabase
  /ocr       — extract text from a photo via Gemini vision
  /translate — translate text via Groq
  /explain   — explain text via Groq
  /summarize — summarize text via Groq
  /rewrite   — rewrite text via Groq
  /weather   — current weather via OpenWeatherMap
  /currency  — currency conversion via Frankfurter (ECB rates)
  /download  — download a video from TikTok/Twitter/Instagram/Facebook/Reddit
  /help      — interactive Quick Reply menu for non-technical users
  /menu      — alias for /help
  help       — plain-text alias for /help

Idempotency design:
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

from services.admin import (
    claim_admin,
    get_quick_stats,
    is_admin,
    is_admin_claim_rate_limited,
    list_flags,
    set_block_status,
    toggle_flag,
)
from services.ai_tools import run_ai_tool
from services.chat_history import append_history, get_history
from services.currency import convert_currency
from services.downloader import DownloaderError, download_video
from services.feature_flags import is_feature_enabled
from services.gemini_vision import describe_image
from services.groq_client import get_groq_reply, transcribe_audio
from services.image_gen import generate_image
from services.messaging_window import mark_user_active
from services.messenger_api import send_image_url, send_quick_replies, send_text_message, send_video_url
from services.ocr import extract_text
from services.personas import DEFAULT_PERSONA, PERSONAS
from services.rate_limit import is_rate_limited
from services.storage import upload_image, upload_video
from services.translate import translate_text
from services.weather import get_weather
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


async def handle_weather_command(pool, redis, psid: str, text: str, image_url: str | None) -> None:
    """Look up current weather for a city via OpenWeatherMap."""
    async with pool.acquire() as conn:
        if not await is_feature_enabled(conn, "weather"):
            await send_text_message(psid, "Weather lookups are temporarily disabled.")
            return

    parts = text.strip().split(maxsplit=1)
    if len(parts) < 2 or not parts[1].strip():
        await send_text_message(psid, "Usage: /weather <city>")
        return

    city = parts[1].strip()
    try:
        summary = await get_weather(redis, city)
        await send_text_message(psid, summary)
    except ValueError as exc:
        await send_text_message(psid, str(exc))
    except Exception:
        logger.exception("Weather lookup failed for psid=%s", psid)
        await send_text_message(
            psid, "Sorry, I couldn't fetch the weather — try again in a moment."
        )


async def handle_currency_command(pool, redis, psid: str, text: str, image_url: str | None) -> None:
    """Convert currency using Frankfurter ECB reference rates."""
    async with pool.acquire() as conn:
        if not await is_feature_enabled(conn, "currency"):
            await send_text_message(psid, "Currency conversion is temporarily disabled.")
            return

    parts = text.strip().split()
    if len(parts) != 4:
        await send_text_message(psid, "Usage: /currency <amount> <from> <to>")
        return

    try:
        amount = float(parts[1])
    except ValueError:
        await send_text_message(psid, "Usage: /currency <amount> <from> <to>")
        return

    from_currency = parts[2]
    to_currency = parts[3]

    try:
        result = await convert_currency(amount, from_currency, to_currency)
        message = (
            f"{result['amount']} {result['from']} = {result['result']} {result['to']}\n"
            f"Rate: 1 {result['from']} = {result['rate']:.4f} {result['to']}\n"
            f"(ECB daily reference rate for {result['date']} — not live market FX)"
        )
        await send_text_message(psid, message)
    except httpx.HTTPStatusError:
        await send_text_message(
            psid,
            f"I don't recognize that currency code — check '{from_currency}' and '{to_currency}'.",
        )
    except Exception:
        logger.exception("Currency conversion failed for psid=%s", psid)
        await send_text_message(
            psid, "Sorry, currency conversion failed — try again in a moment."
        )


# ── Download command ──────────────────────────────────────────────────────────

async def handle_download_command(pool, redis, psid: str, text: str, image_url: str | None) -> None:
    """
    Download a video from a supported platform and deliver it as a Messenger video attachment.

    Supported: TikTok, Twitter/X, Instagram, Facebook, Reddit.
    Not supported: YouTube (requires a JS runtime — see services/downloader.py).

    This handler does NOT need its own BackgroundTasks wrapping — every command
    already runs inside the background task that process_messaging_event was
    dispatched into, so this is already off the webhook critical path.
    """
    async with pool.acquire() as conn:
        if not await is_feature_enabled(conn, "downloader"):
            await send_text_message(psid, "Media downloads are temporarily disabled.")
            return

    parts = text.strip().split(maxsplit=1)
    if len(parts) < 2 or not parts[1].strip():
        await send_text_message(
            psid,
            "Usage: /download <url>  (TikTok, Twitter/X, Instagram, Facebook, or Reddit)",
        )
        return

    url = parts[1].strip()
    # Acknowledge immediately — downloads can take 10–30 s and users need feedback.
    await send_text_message(psid, "Got it — working on that, give me a moment.")

    try:
        video_bytes = await download_video(url)
        hosted_url = await upload_video(video_bytes)
        await send_video_url(psid, hosted_url)
    except DownloaderError as exc:
        await send_text_message(psid, str(exc))
    except Exception:
        logger.exception("Download failed for psid=%s url=%s", psid, url)
        await send_text_message(psid, "Sorry, that download failed — try again in a moment.")


# ── Admin commands and quick replies ──────────────────────────────────────────

FLAG_DISPLAY_NAMES = {
    "ai_chat": "AI Chat",
    "image_gen": "Image Gen",
    "downloader": "Downloader",
    "ocr": "OCR",
    "translate": "Translate",
    "voice_input": "Voice Input",
    "weather": "Weather",
    "currency": "Currency",
    "daraz": "Daraz",
}


async def _send_admin_menu(psid: str) -> None:
    await send_quick_replies(psid, "Admin menu:", [
        ("Toggle Flags", "ADMIN_FLAGS_MENU"),
        ("View Stats", "ADMIN_STATS"),
    ])


async def _send_flags_menu(pool, psid: str) -> None:
    flags = await list_flags(pool)
    options = [
        (
            f"{'ON' if f['enabled'] else 'OFF'} "
            f"{FLAG_DISPLAY_NAMES.get(f['key'], f['key'])}",
            f"ADMIN_TOGGLE:{f['key']}",
        )
        for f in flags
    ]
    await send_quick_replies(psid, "Tap a feature to toggle it:", options)


async def handle_admin_quick_reply(pool, psid: str, payload: str) -> None:
    if not await is_admin(pool, psid):
        return
    if payload == "ADMIN_FLAGS_MENU":
        await _send_flags_menu(pool, psid)
    elif payload == "ADMIN_STATS":
        await send_text_message(psid, await get_quick_stats(pool))
    elif payload.startswith("ADMIN_TOGGLE:"):
        flag_key = payload.split(":", 1)[1]
        try:
            new_state = await toggle_flag(pool, flag_key)
            await send_text_message(
                psid,
                f"{FLAG_DISPLAY_NAMES.get(flag_key, flag_key)} is now "
                f"{'ON' if new_state else 'OFF'}.",
            )
        except ValueError:
            await send_text_message(psid, "Unknown flag.")
        await _send_flags_menu(pool, psid)


async def handle_admin_command(pool, redis, psid: str, text: str, image_url: str | None) -> None:
    parts = text.strip().split(maxsplit=2)
    sub = parts[1].lower() if len(parts) > 1 else None

    if sub == "claim":
        secret = parts[2] if len(parts) > 2 else ""
        if await is_admin_claim_rate_limited(redis, psid):
            await send_text_message(psid, "Too many attempts — try again later.")
            return
        if await claim_admin(pool, psid, secret):
            await send_text_message(psid, "You're now an admin.")
        else:
            await send_text_message(psid, "Invalid or expired secret.")
        return

    if not await is_admin(pool, psid):
        await send_text_message(psid, "You're not authorized for admin commands.")
        return

    if sub is None:
        await _send_admin_menu(psid)
    elif sub == "stats":
        await send_text_message(psid, await get_quick_stats(pool))
    elif sub == "block" and len(parts) > 2:
        ok = await set_block_status(pool, parts[2], True)
        await send_text_message(
            psid,
            f"Blocked {parts[2]}." if ok else "No user found with that PSID.",
        )
    elif sub == "unblock" and len(parts) > 2:
        ok = await set_block_status(pool, parts[2], False)
        await send_text_message(
            psid,
            f"Unblocked {parts[2]}." if ok else "No user found with that PSID.",
        )
    else:
        await send_text_message(
            psid,
            "Usage: /admin | /admin stats | /admin block <psid> | /admin unblock <psid>",
        )


# ── Help / Menu quick-reply handler ───────────────────────────────────────────

# Each entry: (button label shown to user, quick-reply payload, usage hint sent on tap)
HELP_MENU_ITEMS: list[tuple[str, str, str]] = [
    ("🌦️ Weather",      "HELP_WEATHER",  "Type the city name you want weather for:"),
    ("💱 Currency",     "HELP_CURRENCY", "Type: /currency <amount> <from> <to>\nExample: /currency 100 USD EUR"),
    ("🎨 Generate Image","HELP_IMAGE",   "Describe the image you want and I'll generate it!\nExample: /image a sunset over the mountains"),
    ("🌐 Translate",    "HELP_TRANSLATE","Type: /translate <language> <text>\nExample: /translate Bengali Hello, how are you?"),
    ("🎭 Change Persona","HELP_PERSONA", f"Available personas: default, teacher, friend, coder\nType: /persona <name>"),
    ("💡 Explain Text", "HELP_EXPLAIN",  "Type: /explain <text>\nExample: /explain What is quantum computing?"),
    ("📝 Summarize",    "HELP_SUMMARIZE","Type: /summarize <text> — I'll give you the key points."),
    ("✏️ Rewrite",      "HELP_REWRITE",  "Type: /rewrite <text> — I'll clean it up for you."),
]

HELP_PAYLOAD_HINTS: dict[str, str] = {
    item[1]: item[2] for item in HELP_MENU_ITEMS
}


async def handle_help_command(pool, redis, psid: str, text: str, image_url: str | None) -> None:
    """Send an interactive Quick Reply menu to guide non-technical users."""
    options = [(label, payload) for label, payload, _ in HELP_MENU_ITEMS]
    await send_quick_replies(
        psid,
        "Hey! Here's what I can do — tap something to get started 👇",
        options,
    )


async def handle_help_quick_reply(psid: str, payload: str) -> None:
    """Send the usage hint for a tapped Help menu button."""
    hint = HELP_PAYLOAD_HINTS.get(payload)
    if hint:
        await send_text_message(psid, hint)


# ── Command dispatch table ────────────────────────────────────────────────────

COMMAND_HANDLERS: dict[str, object] = {
    "/persona":   handle_persona_command,
    "/image":     handle_image_command,
    "/ocr":       handle_ocr_command,
    "/translate": handle_translate_command,
    "/explain":   handle_explain_command,
    "/summarize": handle_summarize_command,
    "/rewrite":   handle_rewrite_command,
    "/weather":   handle_weather_command,
    "/currency":  handle_currency_command,
    "/download":  handle_download_command,
    "/admin":     handle_admin_command,
    "/help":      handle_help_command,
    "/menu":      handle_help_command,
    "help":       handle_help_command,
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
    pool,
    redis,
    psid: str,
    persona_key: str,
    text: str | None,
    image_url: str | None,
) -> str:
    """
    Route to the correct AI backend and return a reply string.

    - Image present → Gemini (single-turn; NOT stored in history by design).
    - Text only     → Groq with Tool Calling enabled.
        • If Groq returns a tool_call dict, the appropriate service function
          is executed directly and the result is sent without a second Groq
          round-trip. This halves latency and saves tokens.
        • If Groq returns normal text, it is returned as usual.

    Any exception from either AI path is caught here and replaced with a
    stock apology so the user always gets a response.

    History storage:
      - Text turns: user message + assistant reply are both appended.
      - Image turns: "[photo]" is stored for the user turn to preserve the
        conversational flow, and the Gemini reply is stored as assistant turn.
      - Tool call turns: the formatted tool result is stored as the assistant
        reply so future turns have context of the tool interaction.
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
            await append_history(redis, psid, "user", text or "[photo]")
            await append_history(redis, psid, "assistant", reply)
            return reply

        # ── Text path: Groq with tool calling ────────────────────────────────
        history = await get_history(redis, psid)
        result = await get_groq_reply(system_prompt, history, text, use_tools=True)

        # ── Tool call dispatch ────────────────────────────────────────────────
        if isinstance(result, dict) and result.get("type") == "tool_call":
            fn_name = result["name"]
            args = result["args"]
            logger.info("Dispatching tool call: fn=%s psid=%s", fn_name, psid)
            tool_reply = await _dispatch_tool(pool, redis, psid, fn_name, args)
            await append_history(redis, psid, "user", text)
            await append_history(redis, psid, "assistant", tool_reply)
            return tool_reply

        # ── Normal text reply ─────────────────────────────────────────────────
        await append_history(redis, psid, "user", text)
        await append_history(redis, psid, "assistant", result)
        return result

    except Exception:
        logger.exception("AI generation failed for psid=%s", psid)
        return "Sorry, I'm having trouble thinking right now — try again in a moment."


async def _dispatch_tool(pool, redis, psid: str, fn_name: str, args: dict) -> str:
    """
    Execute the tool function requested by Groq and return a formatted string.

    This is a direct dispatch — no second Groq call is made. The formatted
    result is immediately usable as a user-facing reply.

    Unsupported tool names fall back to a generic error string rather than
    raising, to keep the pipeline resilient.
    """
    try:
        if fn_name == "get_weather":
            city = args.get("city", "")
            if not city:
                return "I need a city name to look up weather. Which city?"
            # Feature flag check
            async with pool.acquire() as conn:
                if not await is_feature_enabled(conn, "weather"):
                    return "Weather lookups are temporarily disabled."
            return await get_weather(redis, city)

        if fn_name == "convert_currency":
            amount = args.get("amount")
            from_c = args.get("from_currency", "").upper()
            to_c = args.get("to_currency", "").upper()
            if not (amount and from_c and to_c):
                return "I need an amount and two currency codes to convert. Try: /currency 100 USD EUR"
            async with pool.acquire() as conn:
                if not await is_feature_enabled(conn, "currency"):
                    return "Currency conversion is temporarily disabled."
            import httpx as _httpx
            try:
                result = await convert_currency(float(amount), from_c, to_c)
                return (
                    f"{result['amount']} {result['from']} = {result['result']} {result['to']}\n"
                    f"Rate: 1 {result['from']} = {result['rate']:.4f} {result['to']}\n"
                    f"(ECB daily reference rate for {result['date']} — not live market FX)"
                )
            except _httpx.HTTPStatusError:
                return f"I don't recognize that currency code — check '{from_c}' and '{to_c}'."

        if fn_name == "generate_image":
            prompt = args.get("prompt", "")
            if not prompt:
                return "I need a description to generate an image."
            async with pool.acquire() as conn:
                if not await is_feature_enabled(conn, "image_gen"):
                    return "Image generation is temporarily disabled."
            image_bytes = await generate_image(prompt)
            hosted_url = await upload_image(image_bytes)
            # Images need to be sent separately as attachments, not as text.
            # We send the image here and return an empty string so generate_reply
            # has nothing further to send as text.
            await send_image_url(psid, hosted_url)
            return ""  # image already sent above

        if fn_name == "translate_text":
            language = args.get("language", "")
            text_to_translate = args.get("text", "")
            if not (language and text_to_translate):
                return "I need a target language and the text to translate."
            async with pool.acquire() as conn:
                if not await is_feature_enabled(conn, "translate"):
                    return "Translation is temporarily disabled."
            return await translate_text(language, text_to_translate)

    except ValueError as exc:
        # Surface clean user-facing ValueError messages (e.g., city not found)
        return str(exc)
    except Exception:
        logger.exception("Tool dispatch failed: fn=%s psid=%s", fn_name, psid)
        return "Sorry, that didn't work — try again in a moment."

    # Unknown tool name — should not happen unless schema drifts
    logger.warning("Unknown tool name received from Groq: %s", fn_name)
    return "Sorry, I tried to use a feature that isn't available yet."


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
                "RETURNING persona, is_blocked",
                psid,
            )

            # Feature flag check happens inside the same connection.
            ai_chat_enabled = await is_feature_enabled(conn, "ai_chat")

    if user_row["is_blocked"]:
        logger.info("Blocked user message dropped silently: psid=%s mid=%s", psid, mid)
        return

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

    # ── Quick-reply taps (payload routing, not typed commands) ──────────────
    quick_reply_payload = message.get("quick_reply", {}).get("payload")
    if quick_reply_payload:
        if quick_reply_payload.startswith("ADMIN_"):
            await handle_admin_quick_reply(pool, psid, quick_reply_payload)
            return
        if quick_reply_payload.startswith("HELP_"):
            await handle_help_quick_reply(psid, quick_reply_payload)
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
    reply = await generate_reply(pool, redis, psid, persona_key, text, image_url)
    # Tool calls that generate images send the image themselves and return ""
    # — skip sending an empty text message in that case.
    if reply:
        await send_text_message(psid, reply)
    logger.info("Event processed and replied: mid=%s psid=%s", mid, psid)
