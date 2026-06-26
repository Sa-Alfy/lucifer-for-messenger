"""
Mobile operator offers handler — button-based operator and offer type selection.
Covers GP, Robi, Banglalink, Airtel, and Teletalk.
"""

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from services.mobile_offers import OPERATORS, OFFER_TYPE_LABELS, format_offer_card
from utils.decorators import rate_limit
from utils.logger import get_logger
from state import track_command

logger = get_logger(__name__)


@rate_limit(seconds=3)
async def mobile_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /offers — Show Bangladesh mobile operator selection.
    """
    track_command("offers")

    keyboard = []
    for key, op in OPERATORS.items():
        keyboard.append([InlineKeyboardButton(
            f"{op['emoji']} {op['name']}",
            callback_data=f"mob_{key}"
        )])

    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        "📱 <b>Mobile Operator Offers</b>\n\n"
        "বাংলাদেশের সকল অপারেটরের সেরা অফার দেখুন!\n"
        "Choose your operator:",
        reply_markup=reply_markup,
        parse_mode="HTML",
    )


async def mobile_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle mobile offer button clicks."""
    query = update.callback_query
    await query.answer()

    data = query.data

    # Back to operator list
    if data == "mob_back":
        keyboard = []
        for key, op in OPERATORS.items():
            keyboard.append([InlineKeyboardButton(
                f"{op['emoji']} {op['name']}",
                callback_data=f"mob_{key}"
            )])
        reply_markup = InlineKeyboardMarkup(keyboard)

        await query.edit_message_text(
            "📱 <b>Mobile Operator Offers</b>\n\n"
            "বাংলাদেশের সকল অপারেটরের সেরা অফার দেখুন!\n"
            "Choose your operator:",
            reply_markup=reply_markup,
            parse_mode="HTML",
        )
        return

    # Show offer type for an operator: mob_gp
    if data.startswith("mob_") and "_" not in data[4:]:
        operator = data.replace("mob_", "")
        op = OPERATORS.get(operator)
        if not op:
            await query.edit_message_text("❌ Operator not found.")
            return

        keyboard = []
        for offer_type, label in OFFER_TYPE_LABELS.items():
            keyboard.append([InlineKeyboardButton(
                label,
                callback_data=f"mobt_{operator}_{offer_type}"
            )])
        keyboard.append([InlineKeyboardButton("🔙 Back", callback_data="mob_back")])
        reply_markup = InlineKeyboardMarkup(keyboard)

        await query.edit_message_text(
            f"{op['emoji']} <b>{op['name']}</b>\n\n"
            f"কোন ধরনের অফার দেখতে চান?\n"
            f"Select offer category:",
            reply_markup=reply_markup,
            parse_mode="HTML",
        )
        return

    # Show specific offers: mobt_gp_internet
    if data.startswith("mobt_"):
        parts = data.replace("mobt_", "").split("_", 1)
        if len(parts) != 2:
            return
        operator, offer_type = parts

        text = format_offer_card(operator, offer_type)

        keyboard = [
            [InlineKeyboardButton("🔙 Back to categories", callback_data=f"mob_{operator}")],
            [InlineKeyboardButton("🔙 All Operators", callback_data="mob_back")],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await query.edit_message_text(
            text,
            reply_markup=reply_markup,
            parse_mode="HTML",
        )
