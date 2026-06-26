"""
services/image_gen.py — Hugging Face FLUX.1-schnell image generation wrapper.

Model: black-forest-labs/FLUX.1-schnell (Apache 2.0 — commercial use permitted).
Do NOT switch to FLUX.1-dev; it carries a non-commercial licence restriction.

Async safety:
  The Hugging Face InferenceClient is a synchronous library.  Calling it directly
  inside an async function would block the entire event loop for the full generation
  time (typically 5–20 s).  Every call is therefore dispatched via
  asyncio.get_running_loop().run_in_executor(None, ...) which moves it to a thread
  in the default ThreadPoolExecutor, leaving the event loop free to serve other
  requests while the image is being generated.
"""

import asyncio
import io

from huggingface_hub import InferenceClient

from config import settings
from utils.logger import get_logger

logger = get_logger(__name__)

# ── Model ─────────────────────────────────────────────────────────────────────

IMAGE_MODEL = "black-forest-labs/FLUX.1-schnell"

# ── Client (module-level singleton) ───────────────────────────────────────────

# Lazily initialised on first use so an empty HF_API_KEY at import time doesn't
# raise until the feature is actually invoked.
_hf_client: InferenceClient | None = None


def _get_client() -> InferenceClient:
    """Return the module-level InferenceClient, creating it on first call."""
    global _hf_client
    if _hf_client is None:
        _hf_client = InferenceClient(api_key=settings.hf_api_key)
    return _hf_client


# ── Sync worker (runs in thread pool) ────────────────────────────────────────

def _generate_sync(prompt: str):
    """
    Blocking image generation call — must never be awaited directly.

    Returns a PIL.Image.Image object as returned by the HF client's
    text_to_image method.
    """
    logger.debug("HF image generation started: model=%s", IMAGE_MODEL)
    image = _get_client().text_to_image(prompt, model=IMAGE_MODEL)
    logger.debug("HF image generation finished.")
    return image


# ── Public async API ──────────────────────────────────────────────────────────

async def generate_image(prompt: str) -> bytes:
    """
    Generate an image from *prompt* and return raw PNG bytes.

    Runs the blocking HF client in a thread pool via run_in_executor so the
    event loop is never stalled during generation.

    Args:
        prompt: Natural-language description of the desired image.

    Returns:
        PNG-encoded image as a bytes object.

    Raises:
        Any exception from the HF API — callers are expected to catch and
        convert to a user-facing error message.
    """
    loop = asyncio.get_running_loop()
    image = await loop.run_in_executor(None, _generate_sync, prompt)

    buf = io.BytesIO()
    image.save(buf, format="PNG")
    return buf.getvalue()
