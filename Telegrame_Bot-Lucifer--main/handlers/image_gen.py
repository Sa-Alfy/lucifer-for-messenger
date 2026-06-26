import os
import tempfile
import asyncio
import functools
from telegram import Update
from telegram.ext import ContextTypes
from services.image_gen import generate_image_bytes
from state import API_STATE, FEATURE_FLAGS
from utils.decorators import rate_limit, api_enabled
from utils.logger import get_logger
from handlers.basic import get_image_buttons
from utils.ux import ux_card

logger = get_logger(__name__)


@rate_limit(seconds=15)
@api_enabled("image_gen")
async def generate_image_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Generates an image when the user types /image <prompt>"""
    
    if not FEATURE_FLAGS.get("image_gen", True):
        await update.message.reply_text(
            "🎨 Image Generation is currently disabled by the Admin."
        )
        return
    
    # Check if the user provided a prompt
    if not context.args:
        await update.message.reply_text(
            "Please provide a prompt! Example: <code>/image a futuristic city</code>", 
            parse_mode="HTML"
        )
        return
        
    # Join ingredients into a single prompt string
    prompt = " ".join(context.args)
    
    # Save the prompt for the Retry functionality
    context.user_data["last_image_prompt"] = prompt
    
    # Send a placeholder message to show progress
    status_msg = await update.message.reply_text("⏳ <b>Lucifer:</b> Initiating generation...", parse_mode="HTML")
    
    # Visual feedback in Telegram (shows "uploading photo...")
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="upload_photo")
    
    try:
        # Step 2 update
        await status_msg.edit_text("🎨 <b>Lucifer:</b> Synthesizing pixels...", parse_mode="HTML")
        
        # We process the generation in a separate thread so the bot doesn't freeze
        loop = asyncio.get_running_loop()
        image_bytes = await loop.run_in_executor(
            None, 
            functools.partial(generate_image_bytes, prompt)
        )
        
        await status_msg.edit_text("📦 <b>Lucifer:</b> Finalizing artwork...", parse_mode="HTML")
        
        # Save the image bytes to a temporary file
        with tempfile.NamedTemporaryFile(delete=False, suffix=".jpg") as tmp:
            tmp.write(image_bytes)
            tmp_path = tmp.name
        
        # File handle is now FULLY released — safe to open and send on Windows
        with open(tmp_path, 'rb') as photo:
            await update.message.reply_photo(
                photo=photo,
                caption=ux_card(f"✨ <b>Prompt:</b> {prompt}", title="🎨 AI Generation"),
                reply_markup=get_image_buttons(),
                parse_mode="HTML"
            )
        
        # Safely delete the temp file — ignore if Windows still has a lock on it
        try:
            os.remove(tmp_path)
        except OSError:
            pass

        # Delete the "Generating..." status message
        await status_msg.delete()
        
    except Exception as e:
        logger.error(f"Image Gen Error: {e}")
        await update.message.reply_text(
            f"❌ Failed to generate image.\n\n<b>Reason:</b> <code>{e}</code>",
            parse_mode="HTML",
        )
