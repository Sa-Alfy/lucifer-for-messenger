"""
Contextual AI reply tools — /explain, /summarize, /rewrite.
Must be used by replying to a message.
"""

from telegram import Update
from telegram.ext import ContextTypes
from services.ai_chat import get_ai_response
from utils.decorators import rate_limit, api_enabled
from utils.format import prepare_telegram_html, clean_markdown_fallback
from utils.logger import get_logger
from state import track_command

logger = get_logger(__name__)


async def _process_reply_tool(update: Update, context: ContextTypes.DEFAULT_TYPE, tool_name: str, system_prompt: str, emoji: str):
    """
    Shared logic for all reply-based AI tools.
    Extracts reply text, sends to AI with focused prompt, displays result.
    """
    # Must be a reply to another message
    if not update.message.reply_to_message:
        await update.message.reply_text(
            f"{emoji} <b>{tool_name}</b>\n\n"
            f"Reply to any message with <code>/{tool_name.lower()}</code> to use this tool.\n\n"
            f"<i>Example: Reply to a message → type /{tool_name.lower()}</i>",
            parse_mode="HTML",
        )
        return

    # Get the text from the replied message
    original = update.message.reply_to_message
    target_text = original.text or original.caption or ""

    if not target_text:
        await update.message.reply_text("❌ The replied message has no text to process.")
        return

    if len(target_text) > 4000:
        target_text = target_text[:4000] + "..."

    track_command(tool_name.lower())

    # Typing indicator
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    status_msg = await update.message.reply_text(f"{emoji} Processing...")

    try:
        prompt = f"{system_prompt}\n\nText to process:\n\"\"\"\n{target_text}\n\"\"\""
        response = await get_ai_response(prompt)

        display = f"{emoji} <b>{tool_name}</b>\n\n{response}"

        try:
            await status_msg.edit_text(prepare_telegram_html(display), parse_mode="HTML")
        except Exception:
            try:
                await status_msg.edit_text(clean_markdown_fallback(display))
            except Exception:
                pass

    except Exception as e:
        logger.error(f"{tool_name} error: {e}")
        await status_msg.edit_text(f"❌ Failed to process: {str(e)[:100]}")


@rate_limit(seconds=10)
@api_enabled("ai_chat")
async def explain_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/explain — Reply to a message to get a simple explanation."""
    await _process_reply_tool(
        update, context,
        tool_name="Explain",
        system_prompt=(
            "You are an expert explainer. The user has replied to a message and wants you to explain it clearly. "
            "Break down complex topics into simple, easy-to-understand language. "
            "Use analogies if helpful. Keep it concise (under 200 words). "
            "Format for Telegram: no LaTeX, no markdown. Use emojis to structure."
        ),
        emoji="💡",
    )


@rate_limit(seconds=10)
@api_enabled("ai_chat")
async def summarize_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/summarize — Reply to a message to get a concise summary."""
    await _process_reply_tool(
        update, context,
        tool_name="Summarize",
        system_prompt=(
            "You are an expert summarizer. The user has replied to a message and wants a concise summary. "
            "Extract the key points and present them clearly. "
            "Keep the summary under 100 words. Use bullet points if there are multiple points. "
            "Format for Telegram: no LaTeX, no markdown. Use emojis."
        ),
        emoji="📋",
    )


@rate_limit(seconds=10)
@api_enabled("ai_chat")
async def rewrite_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/rewrite — Reply to a message to get a clearer, professional rewrite."""
    await _process_reply_tool(
        update, context,
        tool_name="Rewrite",
        system_prompt=(
            "You are a professional text editor. The user has replied to a message and wants it rewritten. "
            "Rewrite the text to be clearer, more professional, and better structured. "
            "Maintain the original meaning but improve readability and clarity. "
            "If the text is in Bengali, rewrite in Bengali. If English, rewrite in English. "
            "Format for Telegram: no LaTeX, no markdown."
        ),
        emoji="✍️",
    )
