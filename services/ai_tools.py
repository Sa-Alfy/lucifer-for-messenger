"""
services/ai_tools.py — Explain / summarize / rewrite text transformations.

Each tool is a single Groq call with a purpose-specific system prompt.  The
prompts are intentionally short and direct: they instruct the model clearly
without over-constraining the output style.

All three tools share the same get_groq_reply function, so the retry logic,
model fallback, and token limits from groq_client.py apply uniformly.
"""

from services.groq_client import get_groq_reply
from utils.logger import get_logger

logger = get_logger(__name__)

# ── Prompt table ──────────────────────────────────────────────────────────────

AI_TOOL_PROMPTS: dict[str, str] = {
    "explain": (
        "Explain the following clearly and simply, as if to someone unfamiliar "
        "with the topic:"
    ),
    "summarize": (
        "Summarize the following concisely, keeping only the key points:"
    ),
    "rewrite": (
        "Rewrite the following to be clearer and better written, keeping the "
        "original meaning:"
    ),
}


# ── Public API ────────────────────────────────────────────────────────────────

async def run_ai_tool(tool: str, text: str) -> str:
    """
    Run a named text-transformation tool against *text* and return the result.

    Args:
        tool: One of "explain", "summarize", or "rewrite".
        text: The user-supplied text to transform.

    Returns:
        The transformed text string.

    Raises:
        KeyError:  If *tool* is not a recognised key in AI_TOOL_PROMPTS.
        Any exception from Groq — callers are expected to catch and convert
        to a user-facing error message.
    """
    system_prompt = AI_TOOL_PROMPTS[tool]
    logger.debug("AI tool requested: tool=%s text_length=%d", tool, len(text))
    result = await get_groq_reply(system_prompt, [], text)
    logger.debug("AI tool complete: tool=%s", tool)
    return result
