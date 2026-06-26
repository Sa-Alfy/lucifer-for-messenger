import os
import tempfile
import qrcode
from telegram import Update
from telegram.ext import ContextTypes
from utils.decorators import rate_limit
from utils.logger import get_logger

logger = get_logger(__name__)


@rate_limit(seconds=5)
async def qr_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /qr <text or URL> — Generate a QR code image and send it.
    Uses the qrcode library (offline, no API needed).
    """
    if not context.args:
        await update.message.reply_text(
            "📱 <b>QR Code Generator</b>\n\n"
            "Usage: <code>/qr &lt;text or URL&gt;</code>\n\n"
            "Example:\n"
            "• <code>/qr https://github.com</code>\n"
            "• <code>/qr Hello, World!</code>",
            parse_mode="HTML",
        )
        return

    data = " ".join(context.args)

    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="upload_photo")

    try:
        # Generate QR code with custom styling
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_M,
            box_size=10,
            border=4,
        )
        qr.add_data(data)
        qr.make(fit=True)

        img = qr.make_image(fill_color="black", back_color="white")

        # Save to temp file
        with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as tmp:
            img.save(tmp)
            tmp_path = tmp.name

        # Send the QR code
        with open(tmp_path, "rb") as photo:
            await update.message.reply_photo(
                photo=photo,
                caption=f"📱 QR Code for:\n{data[:100]}",
            )

        # Cleanup
        try:
            os.remove(tmp_path)
        except OSError:
            pass

    except Exception as e:
        logger.error(f"QR Code Error: {e}")
        await update.message.reply_text(
            f"❌ Failed to generate QR code.\n\n<b>Reason:</b> <code>{e}</code>",
            parse_mode="HTML",
        )
