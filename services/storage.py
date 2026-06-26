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
