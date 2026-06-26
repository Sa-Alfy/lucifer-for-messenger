import re
from telegram import Update
from telegram.ext import ContextTypes
from services.currency import convert_currency
from utils.decorators import rate_limit
from utils.cache import currency_cache, CURRENCY_TTL
from utils.logger import get_logger

logger = get_logger(__name__)


@rate_limit(seconds=5)
async def convert_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /convert 100 USD to BDT — Currency conversion.
    Uses frankfurter.dev API (100% free, no key, no signup).
    """
    if not context.args:
        await update.message.reply_text(
            "💱 <b>Currency Converter</b>\n\n"
            "Usage: <code>/convert &lt;amount&gt; &lt;FROM&gt; to &lt;TO&gt;</code>\n\n"
            "Examples:\n"
            "• <code>/convert 100 USD to BDT</code>\n"
            "• <code>/convert 50 EUR to GBP</code>\n"
            "• <code>/convert 1000 BDT to USD</code>",
            parse_mode="HTML",
        )
        return

    # Parse: /convert 100 USD to BDT
    text = " ".join(context.args).upper()
    
    # Try to match patterns like "100 USD TO BDT" or "100 USD BDT"
    match = re.match(r"([\d,.]+)\s*([A-Z]{3})\s*(?:TO|IN|->|=)?\s*([A-Z]{3})", text)
    
    if not match:
        await update.message.reply_text(
            "❌ Could not parse your input.\n\n"
            "Format: <code>/convert 100 USD to BDT</code>",
            parse_mode="HTML",
        )
        return

    amount_str = match.group(1).replace(",", "")
    from_currency = match.group(2)
    to_currency = match.group(3)

    try:
        amount = float(amount_str)
    except ValueError:
        await update.message.reply_text("❌ Invalid amount.")
        return

    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")

    # Check cache
    cache_key = f"{amount}_{from_currency}_{to_currency}"
    cached = currency_cache.get(cache_key)
    if cached:
        result = cached
    else:
        result = await convert_currency(amount, from_currency, to_currency)
        if result.get("success"):
            currency_cache.set(cache_key, result, CURRENCY_TTL)

    if result.get("success"):
        text = (
            f"💱 <b>Currency Conversion</b>\n\n"
            f"💵 {result['amount']:,.2f} {result['from']}\n"
            f"   ⬇️\n"
            f"💰 <b>{result['result']:,.2f} {result['to']}</b>\n\n"
            f"📊 Rate: 1 {result['from']} = {result['rate']:.4f} {result['to']}"
        )
        await update.message.reply_text(text, parse_mode="HTML")
    else:
        await update.message.reply_text(
            f"❌ Conversion failed.\n\n<b>Reason:</b> {result.get('error')}",
            parse_mode="HTML",
        )


@rate_limit(seconds=3)
async def bdt_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /bdt [amount] — Quick USD to BDT conversion.
    Default: 1 USD if no amount given.
    """
    amount = 1.0
    if context.args:
        try:
            amount = float(context.args[0].replace(",", ""))
        except ValueError:
            await update.message.reply_text("❌ Invalid amount. Example: <code>/bdt 100</code>", parse_mode="HTML")
            return

    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")

    # Check cache
    cache_key = f"{amount}_USD_BDT"
    cached = currency_cache.get(cache_key)
    if cached:
        result = cached
    else:
        result = await convert_currency(amount, "USD", "BDT")
        if result.get("success"):
            currency_cache.set(cache_key, result, CURRENCY_TTL)

    if result.get("success"):
        text = (
            f"🇺🇸🇧🇩 <b>USD → BDT Quick Rate</b>\n\n"
            f"💵 {result['amount']:,.2f} USD\n"
            f"   ⬇️\n"
            f"💰 <b>{result['result']:,.2f} BDT</b>\n\n"
            f"📊 Rate: 1 USD = {result['rate']:.2f} BDT"
        )
        await update.message.reply_text(text, parse_mode="HTML")
    else:
        await update.message.reply_text(
            f"❌ Could not fetch rate.\n\n<b>Reason:</b> {result.get('error')}",
            parse_mode="HTML",
        )
