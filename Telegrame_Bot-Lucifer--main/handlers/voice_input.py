import time
from telegram import Update
from telegram.ext import ContextTypes
from services.ai_chat import transcribe_voice, get_ai_response_stream
from utils.logger import get_logger
from utils.format import prepare_telegram_html, clean_markdown_fallback
from utils.constants import MAX_HISTORY
from utils.decorators import enforce_moderation, rate_limit

logger = get_logger(__name__)


@enforce_moderation()
@rate_limit(seconds=10)
async def handle_voice_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handles voice messages:
    1. Downloads the voice/audio file
    2. Transcribes it using Groq Whisper (free)
    3. Streams the AI response for faster UX
    """
    # ── Group Chat Handling ──
    is_group = update.effective_chat.type in ["group", "supergroup"]
    if is_group:
        # In groups, only process voice messages if it's a direct reply to the bot
        is_reply_to_bot = (
            update.message.reply_to_message 
            and update.message.reply_to_message.from_user.id == context.bot.id
        )
        if not is_reply_to_bot:
            return  # Ignore generic group voice messages

    # Let the user know we're processing
    status_msg = await update.message.reply_text("🎤 Listening to your voice message...")

    try:
        # 1. Download the voice message
        voice = update.message.voice or update.message.audio
        if not voice:
            await status_msg.edit_text("❌ Could not read the voice message.")
            return

        voice_file = await context.bot.get_file(voice.file_id)
        voice_bytes = await voice_file.download_as_bytearray()

        # 2. Transcribe with Whisper
        await status_msg.edit_text("📝 Transcribing your voice...")
        transcript = await transcribe_voice(bytes(voice_bytes))

        if not transcript or transcript.startswith("🔧"):
            await status_msg.edit_text(f"❌ Transcription failed.\n\n{transcript}")
            return

        # 3. Stream AI response for faster UX
        await status_msg.edit_text(f"🎤 You said: \"{transcript}\"\n\n🤔 Thinking...")

        # Get chat history and persona for continuity
        chat_history = context.user_data.get("chat_history", [])
        persona = context.user_data.get("persona", "default")

        accumulated = ""
        last_edit = ""
        last_update_time = time.time()

        async for chunk in get_ai_response_stream(
            transcript,
            chat_history=chat_history[-MAX_HISTORY:],
            persona=persona,
        ):
            accumulated += chunk

            current_time = time.time()
            if (current_time - last_update_time) > 0.8 and accumulated != last_edit:
                display_text = f"🎤 <b>You said:</b> \"{transcript}\"\n\n{accumulated} ▌"
                try:
                    last_edit = accumulated
                    last_update_time = current_time
                    await status_msg.edit_text(display_text, parse_mode="HTML")
                except Exception as e:
                    if "not modified" not in str(e).lower():
                        logger.error(f"Voice stream edit error: {e}")

        # Final response
        response = accumulated if accumulated else "🤔 I couldn't generate a response."
        final_text = f"🎤 <b>You said:</b> \"{transcript}\"\n\n{response}"

        try:
            await status_msg.edit_text(prepare_telegram_html(final_text), parse_mode="HTML")
        except Exception:
            try:
                await status_msg.edit_text(clean_markdown_fallback(final_text))
            except Exception:
                pass

        # 4. Update conversation memory
        chat_history.append({"role": "user", "content": transcript})
        chat_history.append({"role": "assistant", "content": response})
        context.user_data["chat_history"] = chat_history[-MAX_HISTORY:]

    except Exception as e:
        logger.error(f"Voice handler error: {e}")
        await status_msg.edit_text(f"❌ Failed to process voice message.\n\nReason: {str(e)}")
