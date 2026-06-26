import os
import asyncio
from telegram import Update
from telegram.ext import ContextTypes
from services.tts import generate_speech
from utils.decorators import rate_limit
from utils.logger import get_logger

logger = get_logger(__name__)


@rate_limit(seconds=5)
async def say_command(update: Update, context: ContextTypes.DEFAULT_TYPE, voice_type: str = "male"):
    """
    Handler for /say and /say_as_girl commands.
    Generates and sends a voice message.
    """
    
    # 1. Check for text input
    if not context.args:
        help_text = (
            "🎙️ <b>Text to Speech</b>\n\n"
            "Usage:\n"
            "👨 <code>/say [text]</code> — Male Voice\n"
            "👩 <code>/say_as_girl [text]</code> — Female Voice\n\n"
            "Example: <code>/say_as_girl আমার নাম লুসিফার</code>"
        )
        await update.message.reply_text(help_text, parse_mode="HTML")
        return

    text = " ".join(context.args)
    
    # Show "Recording" action to the user
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="record_voice")
    
    audio_path = None
    try:
        # 2. Generate Audio
        audio_path = await generate_speech(text, voice_type)
        
        # 3. Send Voice Message
        with open(audio_path, 'rb') as voice:
            await update.message.reply_voice(
                voice=voice,
                caption=f"🎙️ {text[:60]}{'...' if len(text) > 60 else ''}",
            )
            
    except Exception as e:
        logger.error(f"TTS Error: {e}")
        await update.message.reply_text(
            f"❌ Failed to generate speech.\n\n<b>Reason:</b> <code>{e}</code>",
            parse_mode="HTML",
        )
    finally:
        # 4. Always clean up temp file, even on error
        if audio_path and os.path.exists(audio_path):
            try:
                await asyncio.sleep(0.1)
                os.remove(audio_path)
            except OSError:
                pass


async def say_male_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Specific wrapper for /say (Male)"""
    await say_command(update, context, "male")

async def say_female_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Specific wrapper for /say_as_girl (Female)"""
    await say_command(update, context, "female")
