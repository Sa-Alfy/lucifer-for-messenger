from datetime import datetime
from telegram import Update
from telegram.ext import ContextTypes
from state import track_command, USER_STATS
from utils.logger import get_logger

logger = get_logger(__name__)


async def profile_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /me — Shows the user's personal profile and statistics.
    Tracks messages sent, quiz performance, games played, active persona, and more.
    """
    track_command("me")
    user = update.effective_user

    # ── Gather User Data ──
    chat_history_len = len(context.user_data.get("chat_history", []))
    persona = context.user_data.get("persona", "default")
    quiz_score = context.user_data.get("quiz_score", 0)
    quiz_total = context.user_data.get("quiz_total", 0)
    game_points = context.user_data.get("game_points", 0)
    active_game = context.user_data.get("active_game")

    # Calculate quiz accuracy
    if quiz_total > 0:
        quiz_accuracy = int((quiz_score / quiz_total) * 100)
        quiz_display = f"{quiz_score}/{quiz_total} ({quiz_accuracy}% accuracy)"
    else:
        quiz_display = "No quizzes played yet"

    # Active game display
    GAME_NAMES = {
        "word_chain": "📖 Word Chain",
        "antakshari": "🎤 Antakshari",
        "haat_bazaar": "🛍️ Haat-Bazaar",
    }
    game_display = GAME_NAMES.get(active_game, "None") if active_game else "None"

    # Persona display
    PERSONA_NAMES = {
        "default": "🧠 Default",
        "teacher": "👨‍🏫 Teacher",
        "friend": "😎 Friend",
        "coder": "💻 Coder",
        "bangla_tutor": "🇧🇩 বাংলা শিক্ষক",
        "lucifer": "😈 Lucifer",
    }
    persona_display = PERSONA_NAMES.get(persona, persona)

    # User's membership status (based on total interactions)
    total_interactions = chat_history_len + quiz_total + game_points
    if total_interactions >= 100:
        rank = "💎 Diamond User"
    elif total_interactions >= 50:
        rank = "🥇 Gold User"
    elif total_interactions >= 20:
        rank = "🥈 Silver User"
    elif total_interactions >= 5:
        rank = "🥉 Bronze User"
    else:
        rank = "🆕 New User"

    # Build profile card
    profile_text = (
        f"📊 <b>Your Profile</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"👤 <b>Name:</b> {user.first_name}{(' ' + user.last_name) if user.last_name else ''}\n"
        f"🆔 <b>ID:</b> <code>{user.id}</code>\n"
        f"🏅 <b>Rank:</b> {rank}\n\n"

        f"🤖 <b>AI Chat</b>\n"
        f"   💬 Messages in memory: {chat_history_len}\n"
        f"   🎭 Active Persona: {persona_display}\n\n"

        f"🧩 <b>Quiz Performance</b>\n"
        f"   📊 {quiz_display}\n\n"

        f"🎲 <b>Games</b>\n"
        f"   🏆 Game Points: {game_points}\n"
        f"   🎮 Active Game: {game_display}\n\n"

        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"💡 <i>Use /clear to reset chat history, /persona to switch AI style</i>"
    )

    await update.message.reply_text(profile_text, parse_mode="HTML")
