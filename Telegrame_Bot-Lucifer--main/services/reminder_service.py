"""
Persistent reminder system backed by reminders.json.
Default timezone: Bangladesh Standard Time (UTC+6).
"""

import json
import os
import uuid
import asyncio
from datetime import datetime, timedelta, timezone
from utils.logger import get_logger

logger = get_logger(__name__)

REMINDERS_FILE = "reminders.json"

from utils.time_utils import BST


class ReminderStore:
    """File-backed reminder storage with async scheduling."""

    def __init__(self):
        self._reminders = {}  # id -> reminder dict
        self._timers = {}     # id -> asyncio.Task
        self._load()

    def _load(self):
        """Load reminders from disk."""
        if os.path.exists(REMINDERS_FILE):
            try:
                with open(REMINDERS_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self._reminders = data if isinstance(data, dict) else {}
            except Exception as e:
                logger.error(f"Failed to load reminders: {e}")
                self._reminders = {}

    def _save(self):
        """Persist reminders to disk."""
        try:
            with open(REMINDERS_FILE, "w", encoding="utf-8") as f:
                json.dump(self._reminders, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Failed to save reminders: {e}")

    def add(self, user_id: int, chat_id: int, text: str, trigger_time: datetime) -> str:
        """Add a new reminder and return its ID."""
        reminder_id = str(uuid.uuid4())[:8]
        self._reminders[reminder_id] = {
            "id": reminder_id,
            "user_id": user_id,
            "chat_id": chat_id,
            "text": text,
            "trigger_time": trigger_time.isoformat(),
            "created_at": datetime.now(BST).isoformat(),
            "status": "pending",
        }
        self._save()
        return reminder_id

    def get_user_reminders(self, user_id: int) -> list:
        """Get all pending reminders for a user."""
        return [
            r for r in self._reminders.values()
            if r["user_id"] == user_id and r["status"] == "pending"
        ]

    def delete(self, reminder_id: str) -> bool:
        """Delete a reminder and cancel its timer."""
        if reminder_id in self._reminders:
            self._reminders[reminder_id]["status"] = "cancelled"
            self._save()
            # Cancel the timer if running
            task = self._timers.pop(reminder_id, None)
            if task and not task.done():
                task.cancel()
            return True
        return False

    def mark_done(self, reminder_id: str):
        """Mark a reminder as delivered."""
        if reminder_id in self._reminders:
            self._reminders[reminder_id]["status"] = "done"
            self._save()
            self._timers.pop(reminder_id, None)

    def schedule(self, reminder_id: str, app):
        """Schedule a single reminder to fire at its trigger time."""
        reminder = self._reminders.get(reminder_id)
        if not reminder or reminder["status"] != "pending":
            return

        trigger_time = datetime.fromisoformat(reminder["trigger_time"])
        now = datetime.now(BST)

        # Ensure trigger_time is timezone-aware
        if trigger_time.tzinfo is None:
            trigger_time = trigger_time.replace(tzinfo=BST)

        delay = (trigger_time - now).total_seconds()

        if delay <= 0:
            # Already past — fire immediately
            delay = 1

        async def _fire():
            try:
                await asyncio.sleep(delay)
                await app.bot.send_message(
                    chat_id=reminder["chat_id"],
                    text=(
                        f"⏰ <b>Reminder!</b>\n\n"
                        f"📝 {reminder['text']}\n\n"
                        f"<i>Set at {reminder['created_at'][:16].replace('T', ' ')}</i>"
                    ),
                    parse_mode="HTML",
                )
                self.mark_done(reminder_id)
                logger.info(f"Reminder {reminder_id} fired for user {reminder['user_id']}")
            except asyncio.CancelledError:
                pass
            except Exception as e:
                logger.error(f"Failed to fire reminder {reminder_id}: {e}")

        task = asyncio.create_task(_fire())
        self._timers[reminder_id] = task

    def schedule_all(self, app):
        """Schedule all pending reminders (called on bot startup)."""
        pending = [r for r in self._reminders.values() if r["status"] == "pending"]
        count = 0
        for reminder in pending:
            trigger_time = datetime.fromisoformat(reminder["trigger_time"])
            if trigger_time.tzinfo is None:
                trigger_time = trigger_time.replace(tzinfo=BST)
            now = datetime.now(BST)

            # Skip reminders that are way too old (> 24h past)
            if (now - trigger_time).total_seconds() > 86400:
                self._reminders[reminder["id"]]["status"] = "expired"
                continue

            self.schedule(reminder["id"], app)
            count += 1

        self._save()
        logger.info(f"Restored {count} pending reminders from disk.")


def parse_natural_time(text: str) -> tuple:
    """
    Parse natural language time expressions.
    Returns (timedelta, cleaned_text) or (None, original_text).
    
    Supports:
    - "in 30 minutes to call mom" -> (timedelta(minutes=30), "call mom")
    - "in 2 hours check email" -> (timedelta(hours=2), "check email")
    - "5 min take medicine" -> (timedelta(minutes=5), "take medicine")
    """
    import re

    patterns = [
        # "in X minutes/hours to <text>"
        (r"(?:in\s+)?(\d+)\s*(?:min(?:ute)?s?|মিনিট)\s*(?:to\s+|পরে\s+)?(.+)", "minutes"),
        (r"(?:in\s+)?(\d+)\s*(?:hr|hour|ঘণ্টা)s?\s*(?:to\s+|পরে\s+)?(.+)", "hours"),
        (r"(?:in\s+)?(\d+)\s*(?:sec(?:ond)?s?|সেকেন্ড)\s*(?:to\s+|পরে\s+)?(.+)", "seconds"),
    ]

    for pattern, unit in patterns:
        match = re.match(pattern, text, re.IGNORECASE)
        if match:
            amount = int(match.group(1))
            remainder = match.group(2).strip()
            if unit == "minutes":
                return timedelta(minutes=amount), remainder
            elif unit == "hours":
                return timedelta(hours=amount), remainder
            elif unit == "seconds":
                return timedelta(seconds=amount), remainder

    return None, text


# ── Global singleton ──
reminder_store = ReminderStore()
