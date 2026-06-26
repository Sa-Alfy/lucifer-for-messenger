import httpx
from utils.logger import get_logger

logger = get_logger(__name__)

# Frankfurter API — 100% free, no key, no signup, no limits
API_BASE = "https://api.frankfurter.dev/v2"


async def convert_currency(amount: float, from_currency: str, to_currency: str) -> dict:
    """
    Convert currency using the Frankfurter API (European Central Bank data).
    Returns: {"success": True, "result": 8500.50, "rate": 85.005} or {"success": False, "error": "..."}
    """
    from_currency = from_currency.upper()
    to_currency = to_currency.upper()

    url = f"{API_BASE}/latest?base={from_currency}&symbols={to_currency}"

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(url)

        if response.status_code == 200:
            data = response.json()
            rates = data.get("rates", {})

            if to_currency in rates:
                rate = rates[to_currency]
                result = round(amount * rate, 2)
                return {
                    "success": True,
                    "amount": amount,
                    "from": from_currency,
                    "to": to_currency,
                    "rate": rate,
                    "result": result,
                }
            else:
                return {"success": False, "error": f"Currency '{to_currency}' not found."}

        elif response.status_code == 404:
            return {"success": False, "error": f"Currency '{from_currency}' is not supported."}
        else:
            return {"success": False, "error": f"API returned HTTP {response.status_code}"}

    except httpx.TimeoutException:
        return {"success": False, "error": "Currency API timed out."}
    except Exception as e:
        logger.error(f"Currency API error: {e}")
        return {"success": False, "error": f"Network error: {str(e)}"}


async def get_supported_currencies() -> list:
    """Returns a list of supported currency codes."""
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(f"{API_BASE}/currencies")
        if response.status_code == 200:
            return list(response.json().keys())
    except Exception:
        pass
    return []
