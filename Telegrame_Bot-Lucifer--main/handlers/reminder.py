"""
Button-driven reminder system handler.
Supports quick time buttons, natural language input, and reminder management.
"""

from datetime import datetime, timedelta, timezone
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from services.reminder_service import reminder_store, parse_natural_time
from utils.time_utils import BST
from utils.decorators import rate_limit
from utils.logger import get_logger
from state import track_command

logger = get_logger(__name__)


@rate_limit(seconds=3)
async def remind_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /remind — Button-based reminder setup OR natural language.
    Examples:
        /remind              -> Show button flow
        /remind 30 min call  -> Set reminder in 30 minutes
    """
    track_command("remind")

    # If args provided, try natural language parsing
    if context.args:
        raw_text = " ".join(context.args)
        delta, reminder_text = parse_natural_time(raw_text)

        if delta and reminder_text:
            trigger_time = datetime.now(BST) + delta
            reminder_id = reminder_store.add(
                user_id=update.effective_user.id,
                chat_id=update.effective_chat.id,
                text=reminder_text,
                trigger_time=trigger_time,
            )
            reminder_store.schedule(reminder_id, context.application)

            total_minutes = int(delta.total_seconds() / 60)
            time_display = f"{total_minutes} মিনিট" if total_minutes < 60 else f"{total_minutes // 60} ঘণ্টা {total_minutes % 60} মিনিট"

            await update.message.reply_text(
                f"✅ <b>Reminder Set!</b>\n\n"
                f"📝 <b>Text:</b> {reminder_text}\n"
                f"⏰ <b>Time:</b> {time_display} পরে\n"
                f"🕐 <b>At:</b> {trigger_time.strftime('%I:%M %p')}\n\n"
                f"🆔 ID: <code>{reminder_id}</code>\n"
                f"<i>Use /myreminders to manage your reminders</i>",
                parse_mode="HTML",
            )
            return
        else:
            # Could not parse time — show help
            await update.message.reply_text(
                "❌ Could not understand the time.\n\n"
                "<b>Examples:</b>\n"
                "• <code>/remind 30 min call mom</code>\n"
                "• <code>/remind 2 hours check email</code>\n"
                "• Or use /remind without args for button menu",
                parse_mode="HTML",
            )
            return

    # No args — show button-based flow
    keyboard = [
        [
            InlineKeyboardButton("⏱️ 5 মিনিট", callback_data="rem_5"),
            InlineKeyboardButton("⏱️ 15 মিনিট", callback_data="rem_15"),
        ],
        [
            InlineKeyboardButton("⏱️ 30 মিনিট", callback_data="rem_30"),
            InlineKeyboardButton("⏱️ 1 ঘণ্টা", callback_data="rem_60"),
        ],
        [
            InlineKeyboardButton("⏱️ 2 ঘণ্টা", callback_data="rem_120"),
            InlineKeyboardButton("⏱️ 3 ঘণ্টা", callback_data="rem_180"),
        ],
        [
            InlineKeyboardButton("🚫 Cancel", callback_data="rem_cancel"),
        ],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        "⏰ <b>Set a Reminder</b>\n\n"
        "Choose how long from now:\n\n"
        "<i>Or use natural language:</i>\n"
        "<code>/remind 30 min take medicine</code>",
        reply_markup=reply_markup,
        parse_mode="HTML",
    )


async def reminder_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle reminder button clicks — time selection and management."""
    query = update.callback_query
    await query.answer()

    data = query.data

    # Cancel
    if data == "rem_cancel":
        await query.edit_message_text("🚫 Reminder cancelled.")
        context.user_data.pop("rem_pending_minutes", None)
        return

    # Delete a specific reminder
    if data.startswith("rem_del_"):
        reminder_id = data.replace("rem_del_", "")
        if reminder_store.delete(reminder_id):
            await query.edit_message_text(f"🗑️ Reminder <code>{reminder_id}</code> deleted.", parse_mode="HTML")
        else:
            await query.edit_message_text("❌ Reminder not found or already completed.")
        return

    # Time selection from button menu
    if data.startswith("rem_"):
        try:
            minutes = int(data.replace("rem_", ""))
        except ValueError:
            await query.edit_message_text("❌ Invalid selection.")
            return

        # Store the selected time and ask for reminder text
        context.user_data["rem_pending_minutes"] = minutes
        context.user_data["rem_awaiting_text"] = True

        time_display = f"{minutes} মিনিট" if minutes < 60 else f"{minutes // 60} ঘণ্টা"

        await query.edit_message_text(
            f"⏰ <b>Time selected:</b> {time_display} পরে\n\n"
            f"📝 Now type your reminder message:\n"
            f"<i>(Just send a text message with what you want to be reminded about)</i>",
            parse_mode="HTML",
        )
        return


async def handle_reminder_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """
    Check if user is in reminder text input mode.
    Called from handle_message before AI processing.
    Returns True if handled, False if not a reminder flow.
    """
    if not context.user_data.get("rem_awaiting_text"):
        return False

    minutes = context.user_data.pop("rem_pending_minutes", 30)
    context.user_data.pop("rem_awaiting_text", None)

    reminder_text = update.message.text.strip()
    
    # 🚨 FIX 2.7: Allow escape
    if reminder_text.lower() in ["cancel", "stop", "exit"] or reminder_text.startswith("/"):
        await update.message.reply_text("🚫 Reminder setup cancelled.")
        return True

    if not reminder_text:
        await update.message.reply_text("❌ Reminder text cannot be empty. Please try again with /remind")
        return True

    trigger_time = datetime.now(BST) + timedelta(minutes=minutes)
    reminder_id = reminder_store.add(
        user_id=update.effective_user.id,
        chat_id=update.effective_chat.id,
        text=reminder_text,
        trigger_time=trigger_time,
    )
    reminder_store.schedule(reminder_id, context.application)

    time_display = f"{minutes} মিনিট" if minutes < 60 else f"{minutes // 60} ঘণ্টা {minutes % 60} মিনিট"

    keyboard = [
        [InlineKeyboardButton("🗑️ Cancel this reminder", callback_data=f"rem_del_{reminder_id}")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        f"✅ <b>Reminder Set!</b>\n\n"
        f"📝 <b>Text:</b> {reminder_text}\n"
        f"⏰ <b>In:</b> {time_display}\n"
        f"🕐 <b>At:</b> {trigger_time.strftime('%I:%M %p')} BST\n\n"
        f"🆔 ID: <code>{reminder_id}</code>",
        reply_markup=reply_markup,
        parse_mode="HTML",
    )
    return True


@rate_limit(seconds=3)
async def my_reminders_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /myreminders — List all active reminders with delete buttons.
    """
    track_command("myreminders")

    reminders = reminder_store.get_user_reminders(update.effective_user.id)

    if not reminders:
        await update.message.reply_text(
            "📭 <b>No active reminders!</b>\n\n"
            "Use /remind to set one.",
            parse_mode="HTML",
        )
        return

    text = "⏰ <b>Your Active Reminders</b>\n\n"
    keyboard = []

    for r in reminders:
        trigger = datetime.fromisoformat(r["trigger_time"])
        if trigger.tzinfo is None:
            trigger = trigger.replace(tzinfo=BST)
        time_str = trigger.strftime("%I:%M %p")

        text += f"📝 {r['text']}\n"
        text += f"   🕐 {time_str} | 🆔 <code>{r['id']}</code>\n\n"
        keyboard.append([InlineKeyboardButton(f"🗑️ Delete: {r['text'][:25]}", callback_data=f"rem_del_{r['id']}")])

    reply_markup = InlineKeyboardMarkup(keyboard) if keyboard else None

    await update.message.reply_text(text, reply_markup=reply_markup, parse_mode="HTML")
