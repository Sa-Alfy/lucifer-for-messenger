from telegram import Update
from telegram.ext import ContextTypes
from services.ai_chat import get_ai_response
from utils.decorators import rate_limit
from utils.logger import get_logger

logger = get_logger(__name__)


@rate_limit(seconds=5)
async def translate_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /translate <text> — Auto-detect ANY language and translate.
    Supports all language pairs, not just Bangla↔English.
    Uses existing Groq AI — no new API needed.
    """
    if not context.args:
        await update.message.reply_text(
            "🌐 <b>Multi-Language Translation</b>\n\n"
            "Usage: <code>/translate &lt;text&gt;</code>\n\n"
            "I auto-detect the language!\n\n"
            "<b>Supported:</b>\n"
            "🇧🇩 Bangla ↔ English\n"
            "🇯🇵 Japanese ↔ Bangla/English\n"
            "🇪🇸 Spanish ↔ Bangla/English\n"
            "🇫🇷 French ↔ Bangla/English\n"
            "🇸🇦 Arabic ↔ Bangla/English\n"
            "🇨🇳 Chinese ↔ Bangla/English\n"
            "🇰🇷 Korean ↔ Bangla/English\n"
            "...and <b>any other language!</b>\n\n"
            "Examples:\n"
            "• <code>/translate আমি ভালো আছি</code>\n"
            "• <code>/translate Bonjour le monde</code>\n"
            "• <code>/translate こんにちは世界</code>",
            parse_mode="HTML",
        )
        return

    text = " ".join(context.args)

    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")

    # Use a specialized multi-language translation prompt
    prompt = (
        f"You are a professional translator. Translate the following text.\n\n"
        f"Rules:\n"
        f"1. First, detect the source language.\n"
        f"2. If the text is in Bangla/Bengali, translate to English.\n"
        f"3. If the text is in English, translate to Bangla/Bengali.\n"
        f"4. If the text is in ANY OTHER language (Japanese, Spanish, French, Arabic, Hindi, etc.), "
        f"translate to BOTH Bangla AND English.\n"
        f"5. Format your response as:\n"
        f"   - For 2-way: Just the translation\n"
        f"   - For 3-way: 'Bangla: ...\nEnglish: ...'\n"
        f"6. ONLY output the translation(s). No explanations, no extra text.\n\n"
        f"Text: {text}"
    )

    result = await get_ai_response(prompt)

    await update.message.reply_text(
        f"🌐 <b>Translation</b>\n\n"
        f"📝 <b>Original:</b> {text}\n\n"
        f"🔄 <b>Result:</b>\n{result}",
        parse_mode="HTML",
    )
