import os
import asyncio
import functools
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from services.downloader import get_media_info, download_media, cleanup_download, _format_size
from utils.decorators import rate_limit, api_enabled
from utils.logger import get_logger

logger = get_logger(__name__)


def _format_duration(seconds: int) -> str:
    """Format seconds into H:MM:SS or M:SS."""
    if not seconds:
        return "Unknown"
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    secs = seconds % 60
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


@rate_limit(seconds=5)
@api_enabled("downloader")
async def download_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /download <url> — Fetch info and show quality options.
    Supports YouTube, Instagram, TikTok, Facebook, Twitter, Reddit, and 1000+ sites.
    """
    if not context.args:
        await update.message.reply_text(
            "📥 <b>Media Downloader</b>\n\n"
            "Usage: <code>/download &lt;URL&gt;</code>\n\n"
            "Supported sites:\n"
            "• YouTube, Instagram, TikTok\n"
            "• Facebook, Twitter/X, Reddit\n"
            "• And 1000+ more!\n\n"
            "Example:\n"
            "<code>/download https://youtube.com/watch?v=dQw4w9WgXcQ</code>",
            parse_mode="HTML",
        )
        return

    url = " ".join(context.args)

    # Quick URL validation
    if not url.startswith(("http://", "https://", "www.")):
        await update.message.reply_text("❌ Please provide a valid URL starting with http:// or https://")
        return

    if url.startswith("www."):
        url = "https://" + url

    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    status_msg = await update.message.reply_text("🔍 Fetching media info...")

    # Fetch info in a thread (yt-dlp is blocking)
    loop = asyncio.get_running_loop()
    info = await loop.run_in_executor(None, get_media_info, url)

    if not info.get("success"):
        await status_msg.edit_text(
            f"❌ Failed to fetch media.\n\n<b>Reason:</b>\n<pre>{info.get('error')}</pre>",
            parse_mode="HTML",
        )
        return

    options = info.get("options", [])
    if not options:
        await status_msg.edit_text("❌ No downloadable formats found for this URL.")
        return

    # Store info for the callback
    context.user_data["dl_url"] = url
    context.user_data["dl_options"] = {str(i): opt for i, opt in enumerate(options)}

    # Build the info text
    title = info.get("title", "Unknown")[:60]
    duration = _format_duration(info.get("duration"))
    uploader = info.get("uploader", "Unknown")

    info_text = (
        f"📥 <b>Media Found!</b>\n\n"
        f"📌 <b>Title:</b> {title}\n"
        f"👤 <b>Source:</b> {uploader}\n"
        f"⏱️ <b>Duration:</b> {duration}\n\n"
        f"Choose quality to download:"
    )

    # Build inline keyboard
    keyboard = []
    for i, opt in enumerate(options):
        if opt.get("too_large"):
            keyboard.append([InlineKeyboardButton(f"❌ {opt['label']}", callback_data=f"dl_{i}")])
        else:
            keyboard.append([InlineKeyboardButton(opt["label"], callback_data=f"dl_{i}")])

    keyboard.append([InlineKeyboardButton("🚫 Cancel", callback_data="dl_cancel")])
    reply_markup = InlineKeyboardMarkup(keyboard)

    await status_msg.edit_text(info_text, reply_markup=reply_markup, parse_mode="HTML")


async def download_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle download quality selection button clicks."""
    query = update.callback_query
    await query.answer()

    # Handle cancel
    if query.data == "dl_cancel":
        await query.edit_message_text("🚫 Download cancelled.")
        context.user_data.pop("dl_url", None)
        context.user_data.pop("dl_options", None)
        return

    # Get the selected option
    option_idx = query.data.replace("dl_", "")
    dl_options = context.user_data.get("dl_options", {})
    selected = dl_options.get(option_idx)
    url = context.user_data.get("dl_url")

    if not selected or not url:
        await query.edit_message_text(
            "⚠️ Download session expired. Please use <code>/download &lt;url&gt;</code> again.",
            parse_mode="HTML",
        )
        return

    # Check if format is too large
    if selected.get("too_large"):
        await query.answer("❌ This format exceeds Telegram's 50MB limit. Choose a lower quality.", show_alert=True)
        return

    format_id = selected["format_id"]
    media_type = selected["type"]
    ext = selected["ext"]

    # Update message to show download progress
    await query.edit_message_text(
        f"⬇️ <b>Downloading...</b>\n\n"
        f"🎯 Quality: {selected['label']}\n"
        f"⏳ Please wait, this may take a moment...",
        parse_mode="HTML",
    )

    # Show upload action
    if media_type == "audio":
        await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="upload_voice")
    else:
        await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="upload_video")

    # Download in a thread
    loop = asyncio.get_running_loop()
    result = await loop.run_in_executor(
        None, functools.partial(download_media, url, format_id, media_type)
    )

    tmp_dir = result.get("tmp_dir")

    try:
        if not result.get("success"):
            await query.edit_message_text(
                f"❌ Download failed.\n\n<b>Reason:</b>\n<pre>{result.get('error')}</pre>",
                parse_mode="HTML",
            )
            return

        file_path = result["path"]
        file_size = result.get("file_size", 0)
        title = result.get("title", "download")
        size_str = _format_size(file_size)

        # Update status
        await query.edit_message_text(
            f"📤 <b>Uploading to Telegram...</b>\n\n"
            f"📦 Size: {size_str}\n"
            f"⏳ Almost done...",
            parse_mode="HTML",
        )

        # Send the file
        with open(file_path, "rb") as f:
            if media_type == "audio":
                await context.bot.send_audio(
                    chat_id=update.effective_chat.id,
                    audio=f,
                    title=title,
                    caption=f"🎵 {title}\n📦 {size_str}",
                )
            else:
                # Try sending as video first, fall back to document
                try:
                    await context.bot.send_video(
                        chat_id=update.effective_chat.id,
                        video=f,
                        caption=f"🎬 {title}\n📦 {size_str}",
                        supports_streaming=True,
                    )
                except Exception:
                    # If video send fails (format not supported), send as document
                    f.seek(0)
                    await context.bot.send_document(
                        chat_id=update.effective_chat.id,
                        document=f,
                        caption=f"📥 {title}\n📦 {size_str}",
                    )

        # Success — update the status message
        await query.edit_message_text(
            f"✅ <b>Download Complete!</b>\n\n"
            f"📌 {title}\n"
            f"📦 {size_str}",
            parse_mode="HTML",
        )

    except Exception as e:
        logger.error(f"Upload error: {e}")
        await query.edit_message_text(
            f"❌ Failed to upload.\n\n<b>Reason:</b>\n<pre>{str(e)[:150]}</pre>",
            parse_mode="HTML",
        )

    finally:
        # Always clean up temp files
        if tmp_dir:
            # Small delay for Windows file locks
            await asyncio.sleep(0.5)
            cleanup_download(tmp_dir)

        # Clear stored data
        context.user_data.pop("dl_url", None)
        context.user_data.pop("dl_options", None)
