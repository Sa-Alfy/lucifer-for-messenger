import os
import shutil
import tempfile
import yt_dlp
from utils.logger import get_logger

logger = get_logger(__name__)

# Telegram Bot API file size limit (50 MB)
TELEGRAM_MAX_BYTES = 50 * 1024 * 1024

# Check if ffmpeg is available on this system
FFMPEG_AVAILABLE = shutil.which("ffmpeg") is not None


def get_media_info(url: str) -> dict:
    """
    Extracts metadata and available formats from a URL without downloading.
    Returns a simplified info dict or an error dict.
    """
    ydl_opts = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "noplaylist": True,  # Only download single video, not playlists
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)

        if not info:
            return {"success": False, "error": "Could not extract info from this URL."}

        # Build simplified format list
        formats = info.get("formats", [])
        options = _build_download_options(formats)

        return {
            "success": True,
            "title": info.get("title", "Unknown"),
            "duration": info.get("duration", 0),
            "uploader": info.get("uploader", "Unknown"),
            "thumbnail": info.get("thumbnail"),
            "webpage_url": info.get("webpage_url", url),
            "options": options,
            "url": url,
        }

    except yt_dlp.utils.DownloadError as e:
        error_msg = str(e)
        if "is not a valid URL" in error_msg or "Unsupported URL" in error_msg:
            return {"success": False, "error": "This URL is not supported."}
        elif "Private video" in error_msg:
            return {"success": False, "error": "This video is private."}
        elif "Sign in" in error_msg or "age" in error_msg:
            return {"success": False, "error": "This video requires login/age verification."}
        else:
            logger.error(f"yt-dlp error: {e}")
            return {"success": False, "error": f"Download error: {error_msg[:150]}"}
    except Exception as e:
        logger.error(f"Media info error: {e}")
        return {"success": False, "error": f"Failed to fetch info: {str(e)[:150]}"}


def _build_download_options(formats: list) -> list:
    """
    Filters yt-dlp formats into clean, Telegram-friendly download options.
    Prioritizes pre-merged formats (no ffmpeg needed).
    """
    options = []
    
    # ── 1. Video options ──
    video_formats = {}
    
    for f in formats:
        vcodec = f.get("vcodec", "none")
        acodec = f.get("acodec", "none")
        height = f.get("height")
        filesize = f.get("filesize") or f.get("filesize_approx") or 0

        has_video = vcodec and vcodec != "none"
        has_audio = acodec and acodec != "none"

        # Look for pre-merged formats (has both video AND audio)
        if has_video and has_audio and height:
            if height not in video_formats or (filesize and filesize > video_formats[height]["filesize"]):
                video_formats[height] = {
                    "format_id": f["format_id"],
                    "height": height,
                    "filesize": filesize,
                    "ext": f.get("ext", "mp4"),
                    "type": "video",
                    "too_large": filesize > TELEGRAM_MAX_BYTES if filesize else False
                }

    # If ffmpeg is available, build merged streams for highest qualities
    if FFMPEG_AVAILABLE:
        best_audio_only = None
        for f in formats:
            acodec = f.get("acodec", "none")
            vcodec = f.get("vcodec", "none")
            if acodec and acodec != "none" and (not vcodec or vcodec == "none"):
                if not best_audio_only or (f.get("abr", 0) or 0) > (best_audio_only.get("abr", 0) or 0):
                    best_audio_only = f

        if best_audio_only:
            for f in formats:
                vcodec = f.get("vcodec", "none")
                acodec = f.get("acodec", "none")
                height = f.get("height")
                has_video = vcodec and vcodec != "none"
                has_audio = acodec and acodec != "none"
                
                # Video-only stream
                if has_video and not has_audio and height:
                    v_size = f.get("filesize") or f.get("filesize_approx") or 0
                    a_size = best_audio_only.get("filesize") or best_audio_only.get("filesize_approx") or 0
                    total_size = v_size + a_size
                    
                    # Only add if we don't have a pre-merged version of this height, 
                    # or if this merged version offers significantly better quality
                    if height not in video_formats or (total_size and total_size > video_formats[height]["filesize"] * 1.2):
                        video_formats[height] = {
                            "format_id": f"{f['format_id']}+{best_audio_only['format_id']}",
                            "height": height,
                            "filesize": total_size,
                            "ext": "mp4",
                            "type": "video",
                            "too_large": total_size > TELEGRAM_MAX_BYTES if total_size else False
                        }

    # Sort resolutions descending
    sorted_heights = sorted(video_formats.keys(), reverse=True)
    
    for h in sorted_heights:
        vf = video_formats[h]
        size_str = _format_size(vf["filesize"]) if vf["filesize"] else "Unknown Size"
        
        if vf["too_large"]:
            options.append({
                "label": f"🎬 {h}p Video ({size_str}) ⚠️ Too Large",
                "format_id": vf["format_id"],
                "type": "video",
                "ext": vf["ext"],
                "too_large": True
            })
        else:
            options.append({
                "label": f"🎬 {h}p Video ({size_str})",
                "format_id": vf["format_id"],
                "type": "video",
                "ext": vf["ext"],
                "too_large": False
            })

    # Always provide a guaranteed "Best Auto" fallback
    best_auto_format = "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best" if FFMPEG_AVAILABLE else "best[ext=mp4]/best"
    options.append({
        "label": "📥 Best Auto Video",
        "format_id": best_auto_format,
        "type": "video",
        "ext": "mp4",
        "too_large": False  # yt-dlp will evaluate at download time
    })

    # ── 2. Audio-only option ──
    best_audio = None
    for f in formats:
        vcodec = f.get("vcodec", "none")
        acodec = f.get("acodec", "none")
        if (acodec and acodec != "none") and (not vcodec or vcodec == "none"):
            abr = f.get("abr") or 0
            if not best_audio or abr > (best_audio.get("abr") or 0):
                best_audio = f

    if best_audio:
        size = best_audio.get("filesize") or best_audio.get("filesize_approx") or 0
        size_str = _format_size(size) if size else "Unknown Size"
        ext = "mp3" if FFMPEG_AVAILABLE else best_audio.get("ext", "m4a")
        options.append({
            "label": f"🎵 Audio Only ({size_str})",
            "format_id": "bestaudio/best",
            "type": "audio",
            "ext": ext,
            "too_large": False
        })
    elif any(f.get("acodec") and f.get("acodec") != "none" for f in formats):
        # Fallback if there's audio mixed in some streams but no discrete audio stream
        options.append({
            "label": "🎵 Audio Only (Auto)",
            "format_id": "bestaudio/best",
            "type": "audio",
            "ext": "mp3" if FFMPEG_AVAILABLE else "m4a",
            "too_large": False
        })

    return options


def download_media(url: str, format_id: str, media_type: str = "video") -> dict:
    """
    Downloads media in the specified format.
    Returns {"success": True, "path": "/path/to/file", "title": "..."} or error.
    """
    # Create a temp directory for this download
    tmp_dir = tempfile.mkdtemp(prefix="lucifer_dl_")

    ydl_opts = {
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "outtmpl": os.path.join(tmp_dir, "%(title).50s.%(ext)s"),
        "format": format_id,
    }

    # For audio, try to extract and convert if ffmpeg available
    if media_type == "audio":
        if FFMPEG_AVAILABLE:
            ydl_opts["postprocessors"] = [{
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "192",
            }]
        else:
            ydl_opts["format"] = "bestaudio/best/bestvideo+bestaudio/best"

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)

        # Find the downloaded file
        downloaded_file = None
        for root, dirs, files in os.walk(tmp_dir):
            for file in files:
                filepath = os.path.join(root, file)
                if os.path.getsize(filepath) > 0:
                    downloaded_file = filepath
                    break

        if not downloaded_file:
            return {"success": False, "error": "Download completed but file not found.", "tmp_dir": tmp_dir}

        # Check file size
        file_size = os.path.getsize(downloaded_file)
        if file_size > TELEGRAM_MAX_BYTES:
            size_str = _format_size(file_size)
            return {
                "success": False,
                "error": f"File is {size_str} — exceeds Telegram's 50MB limit. Try a lower quality.",
                "tmp_dir": tmp_dir,
            }

        return {
            "success": True,
            "path": downloaded_file,
            "title": info.get("title", "download"),
            "file_size": file_size,
            "tmp_dir": tmp_dir,
        }

    except Exception as e:
        logger.error(f"Download error: {e}")
        return {"success": False, "error": f"Download failed: {str(e)[:150]}", "tmp_dir": tmp_dir}


def cleanup_download(tmp_dir: str):
    """Safely remove the temp download directory."""
    try:
        if tmp_dir and os.path.exists(tmp_dir):
            shutil.rmtree(tmp_dir, ignore_errors=True)
    except Exception:
        pass


def _format_size(size_bytes: int) -> str:
    """Human-readable file size."""
    if not size_bytes or size_bytes <= 0:
        return "Unknown"
    if size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.0f} KB"
    return f"{size_bytes / (1024 * 1024):.1f} MB"
