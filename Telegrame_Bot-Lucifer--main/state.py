import json
import os
from datetime import datetime

STATE_FILE = "state.json"

# Global state dictionary to hold the on/off status of our APIs
API_STATE = {
    "groq": True,
    "pollinations": True,
    "daraz": True,
}

# Simple user statistics (in-memory, persisted to state.json)
USER_STATS = {
    "unique_users": set(),
    "command_counts": {},
    "messages_today": 0,
    "last_reset_date": "",
}

# Moderation state
MODERATION_STATE = {
    "blocked_users": set(),
    "quiet_mode": False,
    "anti_spam": True,
}

FEATURE_FLAGS = {
    "ai_chat": True,
    "image_gen": True,
    "downloader": True,
    "news": True,
}

# ── Auto-save logic ──────────────────────────────────────────
_mutation_count = 0
_AUTO_SAVE_THRESHOLD = 10  # Save to disk every N mutations


def _maybe_save():
    """Auto-save state to disk after every N mutations."""
    global _mutation_count
    _mutation_count += 1
    if _mutation_count >= _AUTO_SAVE_THRESHOLD:
        save_state()
        _mutation_count = 0


def load_state():
    global API_STATE, USER_STATS, MODERATION_STATE, FEATURE_FLAGS
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r") as f:
                saved = json.load(f)
                # Load API state
                if "api_state" in saved:
                    API_STATE.update(saved["api_state"])
                elif any(k in saved for k in ["groq", "pollinations", "daraz"]):
                    # Backward compatibility with old format
                    for k in ["groq", "pollinations", "daraz"]:
                        if k in saved:
                            API_STATE[k] = saved[k]
                
                # Load Moderation state
                if "moderation" in saved:
                    mod = saved["moderation"]
                    MODERATION_STATE["blocked_users"] = set(mod.get("blocked_users", []))
                    MODERATION_STATE["quiet_mode"] = mod.get("quiet_mode", False)
                    MODERATION_STATE["anti_spam"] = mod.get("anti_spam", True)
                
                # Load Feature Flags
                if "feature_flags" in saved:
                    FEATURE_FLAGS.update(saved["feature_flags"])

                # Load stats
                if "stats" in saved:
                    stats = saved["stats"]
                    USER_STATS["unique_users"] = set(stats.get("unique_users", []))
                    USER_STATS["command_counts"] = stats.get("command_counts", {})
                    USER_STATS["messages_today"] = stats.get("messages_today", 0)
                    USER_STATS["last_reset_date"] = stats.get("last_reset_date", "")
        except Exception as e:
            print(f"Failed to load state: {e}")


def save_state():
    try:
        data = {
            "api_state": API_STATE,
            "feature_flags": FEATURE_FLAGS,
            "moderation": {
                "blocked_users": list(MODERATION_STATE["blocked_users"]),
                "quiet_mode": MODERATION_STATE["quiet_mode"],
                "anti_spam": MODERATION_STATE["anti_spam"],
            },
            "stats": {
                "unique_users": list(USER_STATS["unique_users"]),
                "command_counts": USER_STATS["command_counts"],
                "messages_today": USER_STATS["messages_today"],
                "last_reset_date": USER_STATS["last_reset_date"],
            },
        }
        with open(STATE_FILE, "w") as f:
            json.dump(data, f, indent=4)
    except Exception as e:
        print(f"Failed to save state: {e}")


def track_user(user_id: int):
    """Track a unique user."""
    USER_STATS["unique_users"].add(user_id)

    # Reset daily counter if it's a new day
    today = datetime.now().strftime("%Y-%m-%d")
    if USER_STATS["last_reset_date"] != today:
        USER_STATS["messages_today"] = 0
        USER_STATS["last_reset_date"] = today

    USER_STATS["messages_today"] += 1
    _maybe_save()


def track_command(command_name: str):
    """Track command usage."""
    USER_STATS["command_counts"][command_name] = (
        USER_STATS["command_counts"].get(command_name, 0) + 1
    )
    _maybe_save()


def get_stats_summary() -> str:
    """Returns a formatted stats string for the debug panel."""
    total_users = len(USER_STATS["unique_users"])
    messages_today = USER_STATS["messages_today"]

    # Top 5 most used commands
    sorted_cmds = sorted(
        USER_STATS["command_counts"].items(), key=lambda x: x[1], reverse=True
    )[:5]

    top_cmds = "\n".join(
        f"   • <code>{name}</code>: {count}" for name, count in sorted_cmds
    ) if sorted_cmds else "   No data yet"

    total_commands = sum(USER_STATS["command_counts"].values())

    return (
        f"👥 <b>Total Users:</b> <code>{total_users}</code>\n"
        f"📨 <b>Messages Today:</b> <code>{messages_today}</code>\n"
        f"📊 <b>Total Commands:</b> <code>{total_commands}</code>\n"
        f"🏆 <b>Top Commands:</b>\n{top_cmds}"
    )


# Load the state initially
load_state()
