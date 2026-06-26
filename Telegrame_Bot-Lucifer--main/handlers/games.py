from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from services.ai_chat import GAME_PROMPTS
from utils.logger import get_logger

logger = get_logger(__name__)

GAME_LABELS = {
    "word_chain": "📖 Word Chain (শব্দের খেলা)",
    "antakshari": "🎤 Bangla Antakshari (অন্ত্যাক্ষরী)",
    "haat_bazaar": "🛍️ Haat-Bazaar Bargaining (হাট-বাজার)"
}

async def play_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /play — Show inline keyboard to select a game.
    """
    current_game = context.user_data.get("active_game")
    
    msg_text = "🎲 <b>AI Interactive Games</b>\n\nChoose a game to play with me! If you win rounds, you'll earn points for the future Leaderboard! 🏆"
    if current_game:
        # Show that they are already in a game
        label = GAME_LABELS.get(current_game, current_game)
        msg_text = f"🎲 <b>AI Interactive Games</b>\n\nYou are currently playing: <b>{label}</b>\n\nSelect a new game to switch, or click '🛑 Stop Game' to exit to normal chat."

    keyboard = []
    for key, label in GAME_LABELS.items():
        marker = " ✅" if key == current_game else ""
        keyboard.append([InlineKeyboardButton(f"{label}{marker}", callback_data=f"game_{key}")])
        
    if current_game:
        keyboard.append([InlineKeyboardButton("🛑 Stop Game", callback_data="game_stop")])

    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        text=msg_text,
        reply_markup=reply_markup,
        parse_mode="HTML"
    )

async def game_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle game selection button clicks."""
    query = update.callback_query
    await query.answer()

    action = query.data.replace("game_", "")
    
    if action == "stop":
        context.user_data.pop("active_game", None)
        context.user_data.pop("chat_history", None) # Clear memory so AI forgets the strict game rules
        await query.edit_message_text(
            "🛑 <b>Game Stopped!</b>\n\nYou have returned to the normal AI chat. Type /play if you want to start another game.",
            parse_mode="HTML"
        )
        return
        
    if action in GAME_PROMPTS:
        context.user_data["active_game"] = action
        context.user_data.pop("chat_history", None) # Clear memory for a fresh game start
        label = GAME_LABELS.get(action, action)
        
        intro_text = f"🎮 <b>Starting: {label}</b>\n\n"
        if action == "word_chain":
            intro_text += "Rules: Let's play Word Chain in Bengali! Say a word to start, and I'll reply with a word starting with the last letter of yours."
        elif action == "antakshari":
            intro_text += "Rules: Start singing a Bangla song, and I'll reply with a song that starts with the last letter of yours!"
        elif action == "haat_bazaar":
            intro_text += "Welcome to the Bazaar! Send me a message saying 'কি বিক্রি করছেন?' (What are you selling?) to start bargaining!"
            
        intro_text += "\n\n<i>(Type /stopgame when you want to quit)</i>"

        await query.edit_message_text(intro_text, parse_mode="HTML")
    else:
        await query.edit_message_text("❌ Unknown game.")

async def stopgame_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Exit the current game."""
    if "active_game" in context.user_data:
        context.user_data.pop("active_game")
        context.user_data.pop("chat_history", None)
        await update.message.reply_text("🛑 <b>Game Stopped!</b>\n\nYou are back to normal chat mode.", parse_mode="HTML")
    else:
        await update.message.reply_text("You are not currently playing any games! Type /play to see the list.")
