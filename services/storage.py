"""
services/storage.py — Supabase Storage upload helper.

Uploads raw PNG bytes to the 'generated-images' bucket and returns a
publicly accessible URL that the Messenger Send API can fetch directly.

Manual prerequisite:
  The 'generated-images' bucket must already exist in Supabase Storage and
  must be set to public access before this module is useful.  This is a
  one-time console action — not something the code creates at runtime.

Why httpx and not the Supabase Python client?
  The supabase-py Storage client is synchronous.  Using httpx directly keeps
  the whole upload path non-blocking and avoids an extra dependency.
"""

import uuid

import httpx

from config import settings
from utils.logger import get_logger

logger = get_logger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────────

SUPABASE_BUCKET = "generated-images"


# ── Public API ────────────────────────────────────────────────────────────────

async def upload_image(image_bytes: bytes) -> str:
    """
    Upload *image_bytes* (PNG) to Supabase Storage and return its public URL.

    A UUID-based filename is generated for every upload so collisions are
    essentially impossible and no key-management logic is required.

    Args:
        image_bytes: Raw PNG bytes to upload.

    Returns:
        A fully-qualified public URL string that Messenger can retrieve.

    Raises:
        httpx.HTTPStatusError: If Supabase returns a non-2xx response.
        httpx.TimeoutException: If the upload exceeds the 30-second timeout.
    """
    filename = f"{uuid.uuid4().hex}.png"
    upload_url = (
        f"{settings.supabase_url}/storage/v1/object/{SUPABASE_BUCKET}/{filename}"
    )
    headers = {
        "Authorization": f"Bearer {settings.supabase_service_key}",
        "Content-Type": "image/png",
    }

    logger.debug("Uploading image to Supabase Storage: bucket=%s file=%s", SUPABASE_BUCKET, filename)

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(upload_url, headers=headers, content=image_bytes)
        resp.raise_for_status()

    public_url = (
        f"{settings.supabase_url}/storage/v1/object/public/{SUPABASE_BUCKET}/{filename}"
    )
    logger.debug("Image uploaded successfully: url=%s", public_url)
    return public_url


# ── Video uploads ─────────────────────────────────────────────────────────────

DOWNLOADS_BUCKET = "downloads"


async def upload_video(video_bytes: bytes) -> str:
    """
    Upload *video_bytes* (MP4) to Supabase Storage and return its public URL.

    Manual prerequisite:
      The 'downloads' bucket must already exist in Supabase Storage and must
      be set to public access before this function is useful.  This is a
      one-time console action — not something the code creates at runtime.

    Timeout is 60 s (vs 30 s for images) because videos are significantly
    larger and upload times are proportionally longer.

    Args:
        video_bytes: Raw MP4 bytes to upload.

    Returns:
        A fully-qualified public URL string that Messenger can retrieve.

    Raises:
        httpx.HTTPStatusError: If Supabase returns a non-2xx response.
        httpx.TimeoutException: If the upload exceeds the 60-second timeout.
    """
    filename = f"{uuid.uuid4().hex}.mp4"
    upload_url = (
        f"{settings.supabase_url}/storage/v1/object/{DOWNLOADS_BUCKET}/{filename}"
    )
    headers = {
        "Authorization": f"Bearer {settings.supabase_service_key}",
        "Content-Type": "video/mp4",
    }

    logger.debug(
        "Uploading video to Supabase Storage: bucket=%s file=%s size=%d",
        DOWNLOADS_BUCKET, filename, len(video_bytes),
    )

    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(upload_url, headers=headers, content=video_bytes)
        resp.raise_for_status()

    public_url = (
        f"{settings.supabase_url}/storage/v1/object/public/{DOWNLOADS_BUCKET}/{filename}"
    )
    logger.debug("Video uploaded successfully: url=%s", public_url)
    return public_url
