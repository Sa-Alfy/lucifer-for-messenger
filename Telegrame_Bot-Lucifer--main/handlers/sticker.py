import io
from PIL import Image
from telegram import Update
from telegram.ext import ContextTypes
from state import track_command
from services.image_gen import generate_image_bytes
from utils.decorators import rate_limit

def resize_for_sticker(image_bytes: bytes) -> io.BytesIO:
    """
    Resizes an image to exactly 512px on the longest side, as required by Telegram.
    Saves as .webp formato.
    """
    img = Image.open(io.BytesIO(image_bytes))
    
    # Calculate new dimensions
    width, height = img.size
    ratio = 512 / max(width, height)
    new_width = int(width * ratio)
    new_height = int(height * ratio)
    
    img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
    
    # Save as WebP
    out_io = io.BytesIO()
    img.save(out_io, format="WEBP")
    out_io.seek(0)
    return out_io

@rate_limit(15)
async def sticker_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Creates a Telegram sticker.
    From reply: /sticker (replied to a photo)
    From prompt: /sticker a happy cat
    """
    track_command("sticker")
    args = context.args
    
    # Did they reply to an image?
    is_reply = update.message.reply_to_message and update.message.reply_to_message.photo
    
    if not args and not is_reply:
        await update.message.reply_text(
            "🖼️ <b>How to make a Sticker:</b>\n\n"
            "1. Reply to any photo with <code>/sticker</code>\n"
            "2. Type <code>/sticker [prompt]</code> to generate a brand new one using AI!\n\n"
            "<i>(Example: /sticker a cute dog in space)</i>",
            parse_mode="HTML"
        )
        return

    msg = await update.message.reply_text("🖼️ Processing your sticker...", parse_mode="HTML")
    
    try:
        if is_reply:
            photo = update.message.reply_to_message.photo[-1]
            photo_file = await context.bot.get_file(photo.file_id)
            img_bytes = await photo_file.download_as_bytearray()
        else:
            prompt = " ".join(args)
            await msg.edit_text("🎨 Generating image using AI...")
            # Run image gen synchronously in background thread
            import asyncio
            loop = asyncio.get_event_loop()
            img_bytes = await loop.run_in_executor(None, lambda: generate_image_bytes(prompt))
            
        await msg.edit_text("⚙️ Converting to Telegram Sticker format...")
        
        # Resize to 512px max side and convert to webp
        sticker_io = resize_for_sticker(img_bytes)
        
        # Send
        await update.message.reply_sticker(sticker=sticker_io)
        await msg.delete()
        
    except Exception as e:
        await msg.edit_text(f"❌ Error creating sticker: {str(e)}")
