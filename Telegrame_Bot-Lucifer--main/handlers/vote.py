"""
Quick Vote & Poll system for group chats.
- Quick vote: 👍/👎 with real-time count updates
- Poll: Multi-option with auto-close after 1 hour
"""

import asyncio
import uuid
from datetime import datetime, timedelta, timezone
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from utils.decorators import rate_limit
from utils.logger import get_logger
from state import track_command

logger = get_logger(__name__)

BST = timezone(timedelta(hours=6))

# In-memory vote/poll storage (keyed by message_id)
_votes = {}   # msg_id -> {"question": str, "up": set(), "down": set(), "creator": int}
_polls = {}   # msg_id -> {"question": str, "options": [...], "votes": {option_idx: set()}, "closed": bool, "creator": int, "task": Task}


def _build_vote_text(vote_data: dict) -> str:
    """Build the vote display text."""
    up_count = len(vote_data["up"])
    down_count = len(vote_data["down"])
    total = up_count + down_count

    up_bar = "█" * min(up_count, 20) if up_count else ""
    down_bar = "█" * min(down_count, 20) if down_count else ""

    return (
        f"🗳️ <b>Quick Vote</b>\n\n"
        f"❓ {vote_data['question']}\n\n"
        f"👍 {up_count}  {up_bar}\n"
        f"👎 {down_count}  {down_bar}\n\n"
        f"📊 Total votes: {total}"
    )


def _build_poll_text(poll_data: dict) -> str:
    """Build the poll display text."""
    text = f"📊 <b>Poll</b>\n\n❓ {poll_data['question']}\n\n"
    total_votes = sum(len(v) for v in poll_data["votes"].values())

    for idx, option in enumerate(poll_data["options"]):
        count = len(poll_data["votes"].get(idx, set()))
        percentage = int((count / total_votes * 100)) if total_votes > 0 else 0
        bar_len = max(1, percentage // 5)
        bar = "▓" * bar_len + "░" * (20 - bar_len) if total_votes > 0 else "░" * 20
        text += f"  {option}\n  {bar}  {count} ({percentage}%)\n\n"

    status = "🔴 Closed" if poll_data.get("closed") else "🟢 Active (auto-close in 1 hr)"
    text += f"📈 Total: {total_votes} votes | {status}"
    return text


# ─── QUICK VOTE ──────────────────────────────────────────

@rate_limit(seconds=10)
async def vote_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /vote <question> — Create a quick 👍/👎 vote.
    """
    track_command("vote")

    if not context.args:
        await update.message.reply_text(
            "🗳️ <b>Quick Vote</b>\n\n"
            "Usage: <code>/vote Should we have a meetup this Friday?</code>\n\n"
            "Everyone can vote 👍 or 👎!",
            parse_mode="HTML",
        )
        return

    question = " ".join(context.args)

    vote_data = {
        "question": question,
        "up": set(),
        "down": set(),
        "creator": update.effective_user.id,
    }

    keyboard = [
        [
            InlineKeyboardButton("👍 Yes", callback_data="vote_up"),
            InlineKeyboardButton("👎 No", callback_data="vote_down"),
        ],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    sent = await update.message.reply_text(
        _build_vote_text(vote_data),
        reply_markup=reply_markup,
        parse_mode="HTML",
    )

    _votes[sent.message_id] = vote_data


async def vote_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle 👍/👎 vote button clicks."""
    query = update.callback_query
    msg_id = query.message.message_id
    user_id = update.effective_user.id
    action = query.data  # "vote_up" or "vote_down"

    vote_data = _votes.get(msg_id)
    if not vote_data:
        await query.answer("⚠️ This vote has expired.", show_alert=True)
        return

    # Remove previous vote if switching
    vote_data["up"].discard(user_id)
    vote_data["down"].discard(user_id)

    if action == "vote_up":
        vote_data["up"].add(user_id)
        await query.answer("👍 Voted Yes!")
    else:
        vote_data["down"].add(user_id)
        await query.answer("👎 Voted No!")

    # Update the message with new counts
    keyboard = [
        [
            InlineKeyboardButton(f"👍 Yes ({len(vote_data['up'])})", callback_data="vote_up"),
            InlineKeyboardButton(f"👎 No ({len(vote_data['down'])})", callback_data="vote_down"),
        ],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    try:
        await query.edit_message_text(
            _build_vote_text(vote_data),
            reply_markup=reply_markup,
            parse_mode="HTML",
        )
    except Exception:
        pass  # Message not modified


# ─── POLL SYSTEM ──────────────────────────────────────────

@rate_limit(seconds=15)
async def poll_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /poll <question> | option1 | option2 | option3
    Creates a multi-option poll that auto-closes after 1 hour.
    """
    track_command("poll")

    if not context.args:
        await update.message.reply_text(
            "📊 <b>Create a Poll</b>\n\n"
            "Usage: <code>/poll Question | Option 1 | Option 2 | Option 3</code>\n\n"
            "Example:\n"
            "<code>/poll Best programming language? | Python | JavaScript | Rust | Go</code>\n\n"
            "📌 Polls auto-close after 1 hour.",
            parse_mode="HTML",
        )
        return

    raw = " ".join(context.args)
    parts = [p.strip() for p in raw.split("|")]

    if len(parts) < 3:
        await update.message.reply_text(
            "❌ Need at least 2 options.\n\n"
            "Format: <code>/poll Question | Option 1 | Option 2</code>",
            parse_mode="HTML",
        )
        return

    question = parts[0]
    options = parts[1:]

    if len(options) > 8:
        options = options[:8]  # Max 8 options

    poll_data = {
        "question": question,
        "options": options,
        "votes": {i: set() for i in range(len(options))},
        "closed": False,
        "creator": update.effective_user.id,
        "task": None,
    }

    # Build option buttons
    keyboard = []
    for i, option in enumerate(options):
        keyboard.append([InlineKeyboardButton(f"  {option}", callback_data=f"poll_{i}")])
    keyboard.append([InlineKeyboardButton("🔒 Close Poll", callback_data="poll_close")])
    reply_markup = InlineKeyboardMarkup(keyboard)

    sent = await update.message.reply_text(
        _build_poll_text(poll_data),
        reply_markup=reply_markup,
        parse_mode="HTML",
    )

    # Schedule auto-close after 1 hour
    async def auto_close():
        try:
            await asyncio.sleep(3600)  # 1 hour
            if sent.message_id in _polls and not _polls[sent.message_id]["closed"]:
                _polls[sent.message_id]["closed"] = True
                await context.bot.edit_message_text(
                    chat_id=update.effective_chat.id,
                    message_id=sent.message_id,
                    text=_build_poll_text(_polls[sent.message_id]),
                    parse_mode="HTML",
                )
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"Poll auto-close error: {e}")

    poll_data["task"] = asyncio.create_task(auto_close())
    _polls[sent.message_id] = poll_data


async def poll_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle poll option clicks and close button."""
    query = update.callback_query
    msg_id = query.message.message_id
    user_id = update.effective_user.id
    data = query.data

    poll_data = _polls.get(msg_id)
    if not poll_data:
        await query.answer("⚠️ This poll has expired.", show_alert=True)
        return

    # Close poll
    if data == "poll_close":
        if user_id != poll_data["creator"]:
            await query.answer("❌ Only the poll creator can close it.", show_alert=True)
            return
        poll_data["closed"] = True
        if poll_data.get("task") and not poll_data["task"].done():
            poll_data["task"].cancel()

        await query.edit_message_text(
            _build_poll_text(poll_data),
            parse_mode="HTML",
        )
        await query.answer("🔒 Poll closed!")
        return

    # Check if closed
    if poll_data["closed"]:
        await query.answer("🔒 This poll is closed.", show_alert=True)
        return

    # Vote on an option
    try:
        option_idx = int(data.replace("poll_", ""))
    except ValueError:
        return

    # Remove previous vote from all options
    for votes_set in poll_data["votes"].values():
        votes_set.discard(user_id)

    # Add new vote
    if option_idx in poll_data["votes"]:
        poll_data["votes"][option_idx].add(user_id)
        await query.answer(f"✅ Voted: {poll_data['options'][option_idx]}")

    # Rebuild buttons with counts
    keyboard = []
    for i, option in enumerate(poll_data["options"]):
        count = len(poll_data["votes"].get(i, set()))
        keyboard.append([InlineKeyboardButton(f"  {option} ({count})", callback_data=f"poll_{i}")])
    keyboard.append([InlineKeyboardButton("🔒 Close Poll", callback_data="poll_close")])
    reply_markup = InlineKeyboardMarkup(keyboard)

    try:
        await query.edit_message_text(
            _build_poll_text(poll_data),
            reply_markup=reply_markup,
            parse_mode="HTML",
        )
    except Exception:
        pass
