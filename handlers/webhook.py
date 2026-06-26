"""
handlers/webhook.py — GET and POST /webhook route handlers.

GET  /webhook  — Facebook webhook verification challenge.
POST /webhook  — Inbound event receiver.

Order of operations for POST (must not be changed):
  1. Read raw bytes  — must happen before JSON parsing.
  2. Verify signature  — against the raw bytes; reject 403 if invalid.
  3. Parse JSON  — only after signature is confirmed.
  4. Return 200  — immediately, before any processing begins.
  5. Background tasks  — process each event outside the request/response cycle.

Facebook retries any non-200 response and any request that times out.
Returning 200 quickly (step 4) before slow work (step 5) prevents spurious
retries that would re-deliver the same events.

Note on BackgroundTasks durability: if the process restarts between accepting
the 200 and the background task completing, that event is lost.  This is an
accepted trade-off for Phase 2 scale.  Flag in Phase 8 if a durable queue
becomes necessary — do not build one now.
"""

import json
import logging

from fastapi import APIRouter, BackgroundTasks, Request, Response
from fastapi.responses import PlainTextResponse

from config import settings
from db.postgres import get_pool
from db.redis_client import get_redis
from services.event_processor import process_messaging_event
from utils.security import verify_fb_signature

logger = logging.getLogger(__name__)

router = APIRouter(tags=["webhook"])


# ── GET /webhook — Facebook verification challenge ────────────────────────────

@router.get("/webhook")
async def verify_webhook(request: Request) -> PlainTextResponse:
    """
    Respond to Facebook's webhook verification handshake.

    Facebook sends:
      ?hub.mode=subscribe
      &hub.verify_token=<our configured token>
      &hub.challenge=<a random string we must echo back>

    Return the challenge string with 200 if the token matches our secret.
    Return 403 for anything else — wrong token, wrong mode, missing params.
    """
    mode = request.query_params.get("hub.mode")
    token = request.query_params.get("hub.verify_token")
    challenge = request.query_params.get("hub.challenge")

    if mode == "subscribe" and token == settings.fb_verify_token:
        logger.info("Webhook verification challenge accepted.")
        return PlainTextResponse(content=challenge, status_code=200)

    logger.warning(
        "Webhook verification failed: mode=%s token_match=%s",
        mode,
        token == settings.fb_verify_token,
    )
    return PlainTextResponse(content="Forbidden", status_code=403)


# ── POST /webhook — inbound event receiver ────────────────────────────────────

@router.post("/webhook")
async def receive_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
) -> Response:
    """
    Receive and queue inbound Messenger events for background processing.

    Returns 200 immediately after signature verification and JSON parsing.
    All database and Send API work happens in background tasks so Facebook
    sees a fast response and does not retry the request.

    Returns 403 (without touching the database) if the signature is missing
    or does not match.
    """
    # Step 1 — capture raw bytes (before any parsing)
    raw_body = await request.body()

    # Step 2 — verify signature against raw bytes
    signature = request.headers.get("X-Hub-Signature-256")
    if not verify_fb_signature(raw_body, signature, settings.fb_app_secret):
        logger.warning("Webhook signature verification failed — rejecting request.")
        return Response(status_code=403)

    # Step 3 — parse JSON (only after signature is confirmed)
    payload = json.loads(raw_body)
    logger.debug("Webhook payload received (full body at DEBUG only).")

    # Step 4 — enqueue each messaging event as a background task
    event_count = 0
    for entry in payload.get("entry", []):
        for messaging_event in entry.get("messaging", []):
            background_tasks.add_task(_safe_process, messaging_event)
            event_count += 1

    logger.info("Webhook received: %d event(s) queued for processing.", event_count)

    # Step 5 — return 200 immediately; background tasks run after response
    return Response(status_code=200)


# ── Background task wrapper ───────────────────────────────────────────────────

async def _safe_process(messaging_event: dict) -> None:
    """
    Wrap process_messaging_event so exceptions do not propagate to FastAPI.

    BackgroundTask exceptions that bubble up are swallowed silently by FastAPI.
    Catching them here and logging them ourselves gives us visibility.
    The 200 was already sent — there is nothing to roll back.
    """
    try:
        await process_messaging_event(get_pool(), get_redis(), messaging_event)
    except Exception:
        logger.exception(
            "Unhandled exception while processing messaging event: %s",
            # log only the mid if available, never full content
            messaging_event.get("message", {}).get("mid", "<no-mid>"),
        )
