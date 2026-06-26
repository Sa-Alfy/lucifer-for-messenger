import json
import re
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from services.ai_chat import get_ai_response
from utils.decorators import rate_limit
from utils.logger import get_logger

logger = get_logger(__name__)


@rate_limit(seconds=10)
async def quiz_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /quiz <topic> — AI generates a multiple-choice quiz question.
    Uses existing Groq AI — no new API needed.
    """
    if not context.args:
        await update.message.reply_text(
            "🧩 <b>AI Quiz Game</b>\n\n"
            "Usage: <code>/quiz &lt;topic&gt;</code>\n\n"
            "Examples:\n"
            "• <code>/quiz science</code>\n"
            "• <code>/quiz bangladesh history</code>\n"
            "• <code>/quiz programming</code>\n"
            "• <code>/quiz math</code>\n\n"
            "📊 Your score is tracked per session!",
            parse_mode="HTML",
        )
        return

    topic = " ".join(context.args)

    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")

    # Ask AI to generate a quiz question in JSON format
    prompt = (
        f"Generate a multiple-choice quiz question about: {topic}\n\n"
        "You MUST respond with ONLY valid JSON in this exact format, nothing else:\n"
        '{"question": "What is ...?", "options": ["A) ...", "B) ...", "C) ...", "D) ..."], "correct": 0, "explanation": "..."}\n\n'
        "Rules:\n"
        "- 'correct' is the 0-based index of the correct answer\n"
        "- Make it interesting and educational\n"
        "- The question should be medium difficulty\n"
        "- Keep the explanation under 50 words\n"
        "- Respond with ONLY the JSON object, no extra text"
    )

    response = await get_ai_response(prompt)

    try:
        # Try to extract JSON from the response (handle cases where AI adds text around JSON)
        json_match = re.search(r'\{[^{}]*\}', response, re.DOTALL)
        if not json_match:
            raise ValueError("No JSON found in response")
        
        quiz_data = json.loads(json_match.group())

        question = quiz_data["question"]
        options = quiz_data["options"]
        correct_idx = int(quiz_data["correct"])
        explanation = quiz_data.get("explanation", "")

        # Store quiz data for answer checking
        context.user_data["current_quiz"] = {
            "correct": correct_idx,
            "explanation": explanation,
            "question": question,
        }

        # Build inline keyboard with answer buttons
        keyboard = []
        for i, option in enumerate(options):
            keyboard.append([InlineKeyboardButton(option, callback_data=f"quiz_{i}")])

        reply_markup = InlineKeyboardMarkup(keyboard)

        # Get current score
        score = context.user_data.get("quiz_score", 0)
        total = context.user_data.get("quiz_total", 0)

        await update.message.reply_text(
            f"🧩 <b>Quiz: {topic.title()}</b>\n"
            f"📊 Score: {score}/{total}\n\n"
            f"❓ {question}",
            reply_markup=reply_markup,
            parse_mode="HTML",
        )

    except (json.JSONDecodeError, KeyError, ValueError) as e:
        logger.error(f"Quiz parse error: {e}, response: {response[:200]}")
        await update.message.reply_text(
            "❌ Failed to generate quiz. Please try again or use a different topic.",
        )


async def quiz_answer_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle quiz answer button clicks."""
    query = update.callback_query
    await query.answer()

    quiz = context.user_data.get("current_quiz")
    if not quiz:
        await query.edit_message_text("⚠️ This quiz has expired. Use <code>/quiz &lt;topic&gt;</code> to start a new one!", parse_mode="HTML")
        return

    # Extract chosen answer index
    chosen = int(query.data.replace("quiz_", ""))
    correct = quiz["correct"]
    explanation = quiz.get("explanation", "")

    # Update score
    total = context.user_data.get("quiz_total", 0) + 1
    context.user_data["quiz_total"] = total

    if chosen == correct:
        score = context.user_data.get("quiz_score", 0) + 1
        context.user_data["quiz_score"] = score
        result_text = (
            f"✅ <b>Correct!</b>\n\n"
            f"💡 {explanation}\n\n"
            f"📊 Score: {score}/{total} ({int(score/total*100)}%)\n\n"
            f"Use <code>/quiz &lt;topic&gt;</code> for another question!"
        )
    else:
        score = context.user_data.get("quiz_score", 0)
        result_text = (
            f"❌ <b>Wrong!</b>\n\n"
            f"💡 {explanation}\n\n"
            f"📊 Score: {score}/{total} ({int(score/total*100)}%)\n\n"
            f"Use <code>/quiz &lt;topic&gt;</code> to try again!"
        )

    # Clear the current quiz
    context.user_data.pop("current_quiz", None)

    await query.edit_message_text(result_text, parse_mode="HTML")
