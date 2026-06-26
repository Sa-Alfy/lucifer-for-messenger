import time
from functools import wraps
from telegram import Update
from telegram.ext import ContextTypes
from state import API_STATE, MODERATION_STATE, FEATURE_FLAGS
from utils.admin_guard import is_admin


def rate_limit(seconds: int = 15):
    """
    Decorator: Per-user cooldown to prevent spamming expensive API calls.
    Usage: @rate_limit(seconds=30)
    """
    def decorator(func):
        @wraps(func)
        async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
            user_id = update.effective_user.id
            key = f"_cooldown_{func.__name__}"
            
            last_used = context.user_data.get(key, 0)
            now = time.time()
            remaining = seconds - (now - last_used)
            
            if remaining > 0:
                await update.message.reply_text(
                    f"⏳ Please wait <b>{int(remaining)}s</b> before using this again.",
                    parse_mode="HTML"
                )
                return
            
            context.user_data[key] = now
            return await func(update, context, *args, **kwargs)
        return wrapper
    return decorator


def adaptive_rate_limit(base_seconds: int = 10, max_seconds: int = 120, escalation: float = 2.0, decay_after: int = 60):
    """
    Decorator: Adaptive per-user cooldown.
    - First violation: base_seconds cooldown
    - Each subsequent rapid use multiplies cooldown by escalation factor
    - Cooldown resets after decay_after seconds of no usage
    - Max cooldown capped at max_seconds
    """
    def decorator(func):
        @wraps(func)
        async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
            user_id = update.effective_user.id
            key_last = f"_adaptive_last_{func.__name__}"
            key_violations = f"_adaptive_violations_{func.__name__}"

            last_used = context.user_data.get(key_last, 0)
            violations = context.user_data.get(key_violations, 0)
            now = time.time()
            idle_time = now - last_used

            # Decay violations if user has been idle long enough
            if idle_time > decay_after and violations > 0:
                violations = 0
                context.user_data[key_violations] = 0

            # Calculate current cooldown based on violations
            current_cooldown = min(base_seconds * (escalation ** violations), max_seconds)
            remaining = current_cooldown - idle_time

            if remaining > 0 and last_used > 0:
                # Increment violations
                context.user_data[key_violations] = violations + 1
                await update.message.reply_text(
                    f"⏳ Slow down! Wait <b>{int(remaining)}s</b> before using this again.\n"
                    f"{'⚠️ Repeated spam will increase your cooldown!' if violations < 3 else '🚫 You are on extended cooldown.'}",
                    parse_mode="HTML"
                )
                return

            context.user_data[key_last] = now
            return await func(update, context, *args, **kwargs)
        return wrapper
    return decorator


def require_args(help_message: str):
    """
    Decorator: Auto-reply with help text if no arguments are provided.
    Usage: @require_args("Please provide a prompt! Example: /image sunset")
    """
    def decorator(func):
        @wraps(func)
        async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
            if not context.args:
                await update.message.reply_text(help_message, parse_mode="Markdown")
                return
            return await func(update, context, *args, **kwargs)
        return wrapper
    return decorator


def api_enabled(api_name: str):
    """
    Decorator: Check if an API/feature is enabled in global state before running.
    Checks API_STATE first (for backwards compatibility), then FEATURE_FLAGS.
    """
    FRIENDLY_NAMES = {
        "groq": "🤖 AI Chat",
        "pollinations": "🎨 Image Generation",
        "daraz": "🛒 Daraz Deal Finder",
        "ai_chat": "💬 AI Tools",
        "downloader": "📥 Downloader",
        "news": "📰 News"
    }
    def decorator(func):
        @wraps(func)
        async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
            is_enabled = API_STATE.get(api_name, True) if api_name in API_STATE else FEATURE_FLAGS.get(api_name, True)
            
            if not is_enabled:
                name = FRIENDLY_NAMES.get(api_name, api_name.capitalize())
                await update.message.reply_text(
                    f"{name} is currently disabled by the Admin. Please try again later."
                )
                return
            return await func(update, context, *args, **kwargs)
        return wrapper
    return decorator

def enforce_moderation():
    """
    Decorator: Apply global moderation checks.
    - Blocks users entirely if they are in 'blocked_users'.
    - Checks for quiet mode.
    """
    def decorator(func):
        @wraps(func)
        async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
            if not update.effective_user:
                return await func(update, context, *args, **kwargs)
                
            user_id = update.effective_user.id
            if is_admin(user_id):
                return await func(update, context, *args, **kwargs)

            # Block check
            if user_id in MODERATION_STATE.get("blocked_users", set()):
                # Silent drop for blocked users
                return
                
            # Quiet Mode check
            if MODERATION_STATE.get("quiet_mode", False):
                # Process only if specifically mentioned or button press
                is_callback = update.callback_query is not None
                text = ""
                if update.message and update.message.text:
                    text = update.message.text
                elif update.message and update.message.caption:
                    text = update.message.caption
                    
                is_mention = context.bot.username and f"@{context.bot.username}" in text
                
                if not (is_callback or is_mention):
                    return # Silently ignore
            
            # Anti-Spam check
            if MODERATION_STATE.get("anti_spam", True):
                key = f"_global_antispam_{user_id}"
                last = context.user_data.get(key, 0)
                now = time.time()
                if now - last < 1.0:
                    return  # Silent drop — too fast
                context.user_data[key] = now
                
            return await func(update, context, *args, **kwargs)
        return wrapper
    return decorator
