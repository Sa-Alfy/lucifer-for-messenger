"""
services/downloader.py — yt-dlp video download wrapper (Phase 7).

Supported platforms (deliberate, narrow scope):
  TikTok, Twitter/X, Instagram, Facebook, Reddit.

YouTube is explicitly NOT supported — its current anti-bot/signature system
requires a JavaScript runtime (node/deno/bun) that isn't part of this
deployment.  Adding YouTube later means adding a JS runtime to the Render
build (likely a move to a custom Docker deploy) — that's a real, separate
decision, not an oversight here.

Async safety:
  yt-dlp's extract_info and download are both fully synchronous and
  CPU/IO-blocking.  Every call goes through run_in_executor so the event
  loop is never stalled.  This isn't just about the webhook ACK (already
  handled upstream by BackgroundTasks) — without this, a single slow
  download would stall every OTHER user's concurrent request too, since
  they all share one event loop.

Format selection:
  progressive-only (best[ext=mp4]/best).  No format string that requires
  merging separate video and audio streams — that needs ffmpeg, which is
  not installed here.

Size limits:
  Both the duration pre-check and the post-download size check are required.
  max_filesize in yt-dlp's options is metadata-based and not reliable enough
  alone.

Temp directory:
  Always removed in a finally block — success or failure, every path.
"""

import asyncio
import os
import shutil
import tempfile
from urllib.parse import urlparse

import yt_dlp

from utils.logger import get_logger

logger = get_logger(__name__)

# ── Allowlist ─────────────────────────────────────────────────────────────────
# Do NOT expand this list casually.  See module docstring before adding any domain.

ALLOWED_DOMAINS = {
    "tiktok.com", "www.tiktok.com",
    "twitter.com", "www.twitter.com", "x.com", "www.x.com",
    "instagram.com", "www.instagram.com",
    "facebook.com", "www.facebook.com", "fb.watch",
    "reddit.com", "www.reddit.com",
}

# ── Limits ────────────────────────────────────────────────────────────────────

MAX_DURATION_SECONDS = 600          # 10 minutes — tune as needed
MAX_FILE_SIZE_BYTES = 23 * 1024 * 1024  # stay under Messenger's 25 MB asset limit with margin


# ── Error type ────────────────────────────────────────────────────────────────

class DownloaderError(Exception):
    """
    User-facing download failure.

    The exception message IS the string sent back to the user, so keep
    wording friendly and avoid leaking internal details.
    """


# ── URL validation ────────────────────────────────────────────────────────────

def is_supported_url(url: str) -> bool:
    """Return True iff the URL's domain is in ALLOWED_DOMAINS."""
    domain = urlparse(url).netloc.lower()
    return any(domain == d or domain.endswith("." + d) for d in ALLOWED_DOMAINS)


# ── Sync workers (run in thread pool via run_in_executor) ─────────────────────

def _probe_sync(url: str) -> dict:
    """
    Extract metadata from *url* without downloading — sync, runs in thread pool.

    Returns the info dict from yt-dlp (contains 'duration', 'id', etc.).
    """
    opts = {"quiet": True, "no_warnings": True, "skip_download": True}
    with yt_dlp.YoutubeDL(opts) as ydl:
        return ydl.extract_info(url, download=False)


def _download_sync(url: str, out_dir: str) -> str:
    """
    Download the best progressive MP4 from *url* into *out_dir* — sync, runs in thread pool.

    Returns the local filesystem path to the downloaded file.

    Format selection: progressive-only (no ffmpeg merge step available).
    max_filesize is a best-effort, metadata-based hint — the real size check
    happens after download in the async wrapper.
    """
    opts = {
        "quiet": True,
        "no_warnings": True,
        "format": "best[ext=mp4]/best",
        "outtmpl": os.path.join(out_dir, "%(id)s.%(ext)s"),
        "max_filesize": MAX_FILE_SIZE_BYTES,
        "noplaylist": True,
    }
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=True)
        return ydl.prepare_filename(info)


# ── Public async API ──────────────────────────────────────────────────────────

async def download_video(url: str) -> bytes:
    """
    Validate, probe, and download a video from *url*.  Returns raw bytes.

    Raises:
        DownloaderError: For any user-facing failure (unsupported domain,
                         duration/size limit exceeded, private/dead link).

    The caller is responsible for uploading the bytes and sending the result.
    Temp files are always cleaned up here, regardless of outcome.
    """
    if not is_supported_url(url):
        raise DownloaderError(
            "I can only download from TikTok, Twitter/X, Instagram, Facebook, and Reddit right now — "
            "YouTube isn't supported due to platform restrictions."
        )

    loop = asyncio.get_running_loop()

    # Probe metadata first — cheap, gives us duration before we pay for the download.
    try:
        info = await loop.run_in_executor(None, _probe_sync, url)
    except Exception:
        logger.debug("yt-dlp probe failed for url=%s", url, exc_info=True)
        raise DownloaderError("I couldn't read that link — check it's a public video URL.")

    duration = info.get("duration") or 0
    if duration > MAX_DURATION_SECONDS:
        raise DownloaderError(
            f"That video is too long ({duration // 60} min) — I can only handle clips under "
            f"{MAX_DURATION_SECONDS // 60} minutes."
        )

    temp_dir = tempfile.mkdtemp(prefix="lucifer_dl_")
    try:
        filepath = await loop.run_in_executor(None, _download_sync, url, temp_dir)
        size = os.path.getsize(filepath)
        if size > MAX_FILE_SIZE_BYTES:
            raise DownloaderError(
                "That video is too large to send on Messenger (25 MB limit) — try a shorter clip."
            )
        logger.debug("Video downloaded: path=%s size=%d", filepath, size)
        with open(filepath, "rb") as f:
            return f.read()
    except yt_dlp.utils.DownloadError:
        logger.debug("yt-dlp download failed for url=%s", url, exc_info=True)
        raise DownloaderError(
            "I couldn't download that video — the link might be private, expired, or unsupported."
        )
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)  # always clean up, success or failure
