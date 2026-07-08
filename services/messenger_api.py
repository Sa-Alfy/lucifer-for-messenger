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
MESSAGE_TAG or UPDATE without explicit architectural scoping.
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


async def send_quick_replies(psid: str, text: str, options: list[tuple[str, str]]) -> None:
    """
    Send a text message with tappable quick-reply buttons.

    Titles are truncated to 20 characters — Messenger truncates longer labels.
    At most 13 quick replies are sent (Messenger's hard cap per message).
    """
    quick_replies = [
        {"content_type": "text", "title": title[:20], "payload": payload}
        for title, payload in options[:13]
    ]
    payload = {
        "recipient": {"id": psid},
        "messaging_type": "RESPONSE",
        "message": {"text": text, "quick_replies": quick_replies},
    }
    await _post_message(settings.fb_page_id, settings.fb_page_access_token, payload)


async def send_image_url(psid: str, image_url: str) -> None:
    """
    Send an image to a Messenger user via a hosted URL.

    Messenger's Send API fetches the image from *image_url* itself — raw bytes
    are never passed through the API.  is_reusable=True lets Messenger cache the
    attachment so Messenger can serve the cached copy for subsequent sends
    without re-fetching the original URL.

    Args:
        psid:      The recipient's Page-Scoped ID.
        image_url: A publicly accessible URL to a PNG/JPEG image.
    """
    payload = {
        "recipient": {"id": psid},
        "messaging_type": "RESPONSE",
        "message": {
            "attachment": {
                "type": "image",
                "payload": {"url": image_url, "is_reusable": True},
            }
        },
    }
    logger.info("Sending image to psid=%s url=%s", psid, image_url)
    await _post_message(settings.fb_page_id, settings.fb_page_access_token, payload)
    logger.info("Image sent successfully to psid=%s", psid)


async def send_video_url(psid: str, video_url: str) -> None:
    """
    Send a video to a Messenger user via a hosted URL.

    Messenger's Send API fetches the video from *video_url* itself — raw bytes
    are never passed through the API.  is_reusable=True lets Messenger cache the
    attachment so Messenger can serve the cached copy for subsequent sends
    without re-fetching the original URL.

    Args:
        psid:      The recipient's Page-Scoped ID.
        video_url: A publicly accessible URL to an MP4 video.
    """
    payload = {
        "recipient": {"id": psid},
        "messaging_type": "RESPONSE",
        "message": {
            "attachment": {
                "type": "video",
                "payload": {"url": video_url, "is_reusable": True},
            }
        },
    }
    logger.info("Sending video to psid=%s url=%s", psid, video_url)
    await _post_message(settings.fb_page_id, settings.fb_page_access_token, payload)
    logger.info("Video sent successfully to psid=%s", psid)
