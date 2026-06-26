"""
Lightweight keyword-based intent detection for natural language queries.
Maps user messages to existing bot services without heavy NLP dependencies.
"""

import re
from utils.logger import get_logger

logger = get_logger(__name__)


# ── Intent Patterns ──────────────────────────────────────────────
# Each entry: (compiled_regex, intent_name, arg_extractor_function)
# arg_extractor returns a string that becomes the "args" for the handler

_INTENT_PATTERNS = [
    # Weather
    (re.compile(r"^(?:weather|আবহাওয়া|abohaowa)\s+(.+)$", re.IGNORECASE), "weather", lambda m: m.group(1).strip()),
    (re.compile(r"^(?:weather|আবহাওয়া)$", re.IGNORECASE), "weather_no_args", lambda m: ""),

    # Currency / USD Rate
    (re.compile(r"^(?:usd|dollar|ডলার)\s*(?:rate|রেট|price|দাম)?$", re.IGNORECASE), "bdt_rate", lambda m: ""),
    (re.compile(r"^(?:convert|রূপান্তর)\s+(.+)$", re.IGNORECASE), "convert", lambda m: m.group(1).strip()),

    # News
    (re.compile(r"^(?:news|খবর|সংবাদ|headlines?)(?:\s+(bd|bangladesh|বাংলাদেশ|world|বিশ্ব))?$", re.IGNORECASE), "news", lambda m: (m.group(1) or "").strip()),

    # Reminder
    (re.compile(r"^(?:remind\s*(?:me)?|মনে\s*করিয়ো|রিমাইন্ড)\s+(.+)$", re.IGNORECASE), "reminder", lambda m: m.group(1).strip()),

    # Prayer times
    (re.compile(r"^(?:prayer\s*(?:time)?s?|নামাজ(?:ের\s*সময়)?|salah|salat|namaz)\s*(.*)$", re.IGNORECASE), "prayer", lambda m: m.group(1).strip()),

    # Mobile offers
    (re.compile(r"^(?:offer|অফার|internet\s*(?:offer|pack)|ইন্টারনেট|recharge|রিচার্জ|mobile\s*offer)\s*(.*)$", re.IGNORECASE), "mobile_offer", lambda m: m.group(1).strip()),

    # Quick vote
    (re.compile(r"^(?:vote|ভোট)\s+(.+)$", re.IGNORECASE), "vote", lambda m: m.group(1).strip()),
]


def detect_intent(text: str):
    """
    Try to match user text against known intent patterns.
    
    Returns:
        (intent_name: str, extracted_args: str) if matched
        (None, None) if no match — falls through to AI chat
    """
    if not text:
        return None, None

    text = text.strip()

    # Skip if it looks like a command (starts with /)
    if text.startswith("/"):
        return None, None

    for pattern, intent_name, arg_extractor in _INTENT_PATTERNS:
        match = pattern.match(text)
        if match:
            args = arg_extractor(match)
            logger.info(f"Intent detected: {intent_name} (args: '{args}')")
            return intent_name, args

    return None, None
