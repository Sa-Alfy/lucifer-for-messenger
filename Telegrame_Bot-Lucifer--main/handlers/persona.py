from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from services.ai_chat import PERSONAS
from utils.logger import get_logger

logger = get_logger(__name__)

# Friendly labels for each persona
PERSONA_LABELS = {
    "default": "🧠 Default (Varsity Level AI)",
    "teacher": "👨‍🏫 Teacher (Patient & Clear)",
    "friend": "😎 Friend (Casual & Fun)",
    "coder": "💻 Coder (Senior Engineer)",
    "bangla_tutor": "🇧🇩 বাংলা শিক্ষক (Bangla Tutor)",
    "language_mentor": "🇩🇪 German Lehrer (A1-A2 Study)",
    "lucifer": "😈 Lucifer (Devilishly Honest)",
}


async def persona_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /persona — Show inline keyboard to switch AI personality.
    /persona <name> — Switch directly.
    """
    # If they gave a name directly: /persona coder
    if context.args:
        name = context.args[0].lower()
        if name in PERSONAS:
            context.user_data["persona"] = name
            label = PERSONA_LABELS.get(name, name)
            await update.message.reply_text(
                f"✅ Persona switched to: {label}\n\nStart chatting and I'll respond in this style!",
            )
            return
        else:
            available = ", ".join(f"<code>{k}</code>" for k in PERSONAS.keys())
            await update.message.reply_text(
                f"❌ Unknown persona <code>{name}</code>.\n\nAvailable: {available}",
                parse_mode="HTML",
            )
            return

    # No args — show the inline keyboard
    current = context.user_data.get("persona", "default")
    
    keyboard = []
    for key, label in PERSONA_LABELS.items():
        marker = " ✅" if key == current else ""
        keyboard.append([InlineKeyboardButton(f"{label}{marker}", callback_data=f"persona_{key}")])

    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        f"🎭 <b>Choose AI Persona</b>\n\nCurrent: {PERSONA_LABELS.get(current, current)}\n\n"
        "Each persona changes how I respond to your messages:",
        reply_markup=reply_markup,
        parse_mode="HTML",
    )


async def persona_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle persona button clicks."""
    query = update.callback_query
    await query.answer()

    # Extract persona name from callback data like "persona_coder"
    persona_name = query.data.replace("persona_", "")

    if persona_name in PERSONAS:
        context.user_data["persona"] = persona_name
        label = PERSONA_LABELS.get(persona_name, persona_name)
        await query.edit_message_text(
            f"✅ Persona switched to: {label}\n\nStart chatting and I'll respond in this style!"
        )
    else:
        await query.edit_message_text("❌ Unknown persona.")
