"""
services/messenger_api.py — Facebook Messenger Send API wrapper.

Graph API version is pinned to v25.0.  Bump deliberately — do not auto-upgrade.

Retry policy:
  - Retry on transport errors (network blips, timeouts) and 5xx server errors.
  - Never retry 4xx — bad token, blocked recipient, invalid payload are all
    permanent failures; retrying just burns rate-limit quota.

Long-text handling:
  - Messenger imposes a 2 000-character per-message limit.
  - _chunk_text splits long replies into sequential chunks sent one after
    another. The order is guaranteed because we await each send in a loop.

messaging_type is always RESPONSE for this project.  Do not introduce
MESSAGE_TAG or UPDATE without explicit cross-phase scoping.
"""

import httpx
from tenacity import (
    retry,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential,
)

from config import settings
from utils.logger import get_logger

logger = get_logger(__name__)

GRAPH_API_VERSION = "v25.0"
MAX_MESSAGE_LENGTH = 2000  # Messenger's per-message text character limit


# ── Retry predicate ──────────────────────────────────────────────────────────

def _is_retryable(exc: Exception) -> bool:
    """
    Return True only for errors that are worth retrying.

    Transport errors (connection reset, timeout) are transient by nature.
    5xx responses are server-side problems that may clear on their own.
    4xx responses are permanent: retrying will not fix a bad token or a
    blocked recipient, and will just waste time and burn rate-limit quota.
    """
    if isinstance(exc, httpx.TransportError):
        return True
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code >= 500
    return False


# ── Internal send primitive ──────────────────────────────────────────────────

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=8),
    retry=retry_if_exception(_is_retryable),
)
async def _post_message(page_id: str, access_token: str, payload: dict) -> dict:
    """
    POST a single Send API payload to the Graph API.

    Retried up to 3 times for transient/5xx failures (see _is_retryable).
    Raises on permanent 4xx — let the caller handle or log it.
    """
    url = f"https://graph.facebook.com/{GRAPH_API_VERSION}/{page_id}/messages"
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(
            url,
            params={"access_token": access_token},
            json=payload,
        )
        resp.raise_for_status()
        return resp.json()


# ── Text chunker ─────────────────────────────────────────────────────────────

def _chunk_text(text: str, limit: int) -> list[str]:
    """
    Split text into chunks of at most `limit` characters.

    Returns at least one chunk even when text is empty, so callers always
    have something to send (Messenger rejects an empty message body).
    """
    return [text[i : i + limit] for i in range(0, len(text), limit)] or [text]


# ── Public API ───────────────────────────────────────────────────────────────

async def send_text_message(psid: str, text: str) -> None:
    """
    Send a text reply to a Messenger user.

    Splits into multiple chunks if text exceeds MAX_MESSAGE_LENGTH.
    Chunks are sent sequentially (awaited in order) to preserve message order.

    Args:
        psid: The recipient's Page-Scoped ID.
        text: The reply text to send.
    """
    chunks = _chunk_text(text, MAX_MESSAGE_LENGTH)
    logger.info("Sending reply to psid=%s in %d chunk(s)", psid, len(chunks))

    for chunk in chunks:
        payload = {
            "recipient": {"id": psid},
            "messaging_type": "RESPONSE",
            "message": {"text": chunk},
        }
        await _post_message(
            settings.fb_page_id,
            settings.fb_page_access_token,
            payload,
        )

    logger.info("Reply sent successfully to psid=%s", psid)
