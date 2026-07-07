"""
services/currency.py — Currency conversion via Frankfurter (ECB reference rates).

No API key required. Uses ECB daily reference rates — not live market FX.
"""

import httpx

from utils.logger import get_logger

logger = get_logger(__name__)

FRANKFURTER_API_URL = "https://api.frankfurter.app/latest"


async def convert_currency(amount: float, from_currency: str, to_currency: str) -> dict:
    """
    Convert *amount* from *from_currency* to *to_currency* using Frankfurter.

    Args:
        amount:         Amount to convert.
        from_currency:  Source currency code (e.g. "USD").
        to_currency:    Target currency code (e.g. "EUR").

    Returns:
        Dict with keys: amount, from, to, result, rate, date.

    Raises:
        httpx.HTTPStatusError: Invalid or unsupported currency codes.
    """
    from_code = from_currency.upper()
    to_code = to_currency.upper()

    logger.debug("Currency conversion: amount=%s from=%s to=%s", amount, from_code, to_code)

    async with httpx.AsyncClient(timeout=10, follow_redirects=True) as client:
        resp = await client.get(
            FRANKFURTER_API_URL,
            params={
                "amount": amount,
                "from": from_code,
                "to": to_code,
            },
        )
        resp.raise_for_status()
        data = resp.json()

    converted = data["rates"][to_code]
    rate = converted / amount if amount else 0

    return {
        "amount": amount,
        "from": from_code,
        "to": to_code,
        "result": round(converted, 2),
        "rate": rate,
        "date": data["date"],
    }
