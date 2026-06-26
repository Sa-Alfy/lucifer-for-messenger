from telegram import Update
from telegram.ext import ContextTypes
from services.ai_chat import get_ai_response
from utils.decorators import rate_limit
from utils.logger import get_logger

logger = get_logger(__name__)


@rate_limit(seconds=10)
async def ocr_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /ocr — Reply to a photo to extract text from it.
    Uses Gemini Vision — no new API needed.
    """
    # Check if the command is a reply to a photo
    replied = update.message.reply_to_message
    
    if not replied or not replied.photo:
        await update.message.reply_text(
            "📄 <b>OCR — Text Extraction</b>\n\n"
            "Reply to a photo with <code>/ocr</code> to extract text from it.\n\n"
            "Steps:\n"
            "1. Send a photo (or find one in chat)\n"
            "2. Reply to that photo with <code>/ocr</code>\n"
            "3. I'll extract all visible text!",
            parse_mode="HTML",
        )
        return

    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    status_msg = await update.message.reply_text("📄 Extracting text from image...")

    try:
        # Download the highest resolution photo
        photo = replied.photo[-1]
        photo_file = await context.bot.get_file(photo.file_id)
        image_bytes = await photo_file.download_as_bytearray()

        # Use Vision AI with an OCR-specific prompt
        ocr_prompt = (
            "Extract ALL text visible in this image. "
            "Return ONLY the extracted text, preserving the original formatting as much as possible. "
            "If the text is in Bangla/Bengali, keep it in Bangla. "
            "If there is no text in the image, say 'No text found in this image.'"
        )

        result = await get_ai_response(ocr_prompt, image_bytes=bytes(image_bytes))

        response_text = f"📄 <b>Extracted Text:</b>\n\n{result}"
        
        # Safe send
        try:
            await status_msg.edit_text(response_text, parse_mode="HTML")
        except Exception:
            await status_msg.edit_text(response_text)

    except Exception as e:
        logger.error(f"OCR Error: {e}")
        await status_msg.edit_text(
            f"❌ OCR failed.\n\n<b>Reason:</b> <code>{e}</code>",
            parse_mode="HTML",
        )
