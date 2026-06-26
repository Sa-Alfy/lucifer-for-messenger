"""
Bangladesh Mobile Operator Offers — Static reference data.
Covers GP, Robi, Banglalink, Airtel, and Teletalk.
Updated with current best offers for internet, minutes, SMS, and combo packs.

Note: These are curated static offers. They should be periodically updated
to reflect the latest operator promotions.
"""

from utils.logger import get_logger

logger = get_logger(__name__)

# ── Operator Data ─────────────────────────────────────────────

OPERATORS = {
    "gp": {
        "name": "Grameenphone",
        "short": "GP",
        "emoji": "🟢",
        "color": "Green",
        "ussd_balance": "*566#",
        "ussd_internet": "*121*3#",
        "ussd_minutes": "*121*1#",
        "offers": {
            "internet": [
                {"name": "1GB 3 দিন", "price": "29 ৳", "dial": "*121*3*4*4#", "validity": "3 days"},
                {"name": "2GB 7 দিন", "price": "49 ৳", "dial": "*121*3*4*2#", "validity": "7 days"},
                {"name": "5GB 7 দিন", "price": "99 ৳", "dial": "*121*3*4*7#", "validity": "7 days"},
                {"name": "10GB 30 দিন", "price": "198 ৳", "dial": "*121*3*4*9#", "validity": "30 days"},
                {"name": "30GB 30 দিন", "price": "399 ৳", "dial": "*121*3*4*11#", "validity": "30 days"},
            ],
            "minutes": [
                {"name": "50 মিনিট GP-GP", "price": "29 ৳", "dial": "*121*1*3*1#", "validity": "3 days"},
                {"name": "100 মিনিট যেকোনো নম্বর", "price": "69 ৳", "dial": "*121*1*3*3#", "validity": "7 days"},
                {"name": "200 মিনিট যেকোনো", "price": "129 ৳", "dial": "*121*1*3*5#", "validity": "30 days"},
                {"name": "500 মিনিট যেকোনো", "price": "249 ৳", "dial": "*121*1*3*7#", "validity": "30 days"},
            ],
            "sms": [
                {"name": "100 SMS যেকোনো", "price": "19 ৳", "dial": "*121*2*3*1#", "validity": "7 days"},
                {"name": "300 SMS যেকোনো", "price": "39 ৳", "dial": "*121*2*3*2#", "validity": "30 days"},
            ],
            "combo": [
                {"name": "1GB + 50 মিনিট + 50 SMS", "price": "59 ৳", "dial": "*121*5*1#", "validity": "7 days"},
                {"name": "3GB + 100 মিনিট + 100 SMS", "price": "149 ৳", "dial": "*121*5*3#", "validity": "30 days"},
                {"name": "10GB + 300 মিনিট + 100 SMS", "price": "349 ৳", "dial": "*121*5*5#", "validity": "30 days"},
            ],
        },
    },
    "robi": {
        "name": "Robi Axiata",
        "short": "Robi",
        "emoji": "🔴",
        "color": "Red",
        "ussd_balance": "*222#",
        "ussd_internet": "*123*3#",
        "ussd_minutes": "*123*1#",
        "offers": {
            "internet": [
                {"name": "1GB 3 দিন", "price": "29 ৳", "dial": "*123*029#", "validity": "3 days"},
                {"name": "2GB 7 দিন", "price": "49 ৳", "dial": "*123*049#", "validity": "7 days"},
                {"name": "5GB 7 দিন", "price": "99 ৳", "dial": "*123*099#", "validity": "7 days"},
                {"name": "10GB 30 দিন", "price": "199 ৳", "dial": "*123*199#", "validity": "30 days"},
                {"name": "25GB 30 দিন", "price": "399 ৳", "dial": "*123*399#", "validity": "30 days"},
            ],
            "minutes": [
                {"name": "40 মিনিট Robi-Robi", "price": "22 ৳", "dial": "*123*022#", "validity": "3 days"},
                {"name": "100 মিনিট যেকোনো", "price": "59 ৳", "dial": "*123*059#", "validity": "7 days"},
                {"name": "250 মিনিট যেকোনো", "price": "138 ৳", "dial": "*123*138#", "validity": "30 days"},
            ],
            "sms": [
                {"name": "100 SMS যেকোনো", "price": "17 ৳", "dial": "*123*017#", "validity": "7 days"},
                {"name": "500 SMS যেকোনো", "price": "35 ৳", "dial": "*123*035#", "validity": "30 days"},
            ],
            "combo": [
                {"name": "1GB + 40 মিনিট + 40 SMS", "price": "49 ৳", "dial": "*123*3049#", "validity": "7 days"},
                {"name": "4GB + 150 মিনিট + 50 SMS", "price": "169 ৳", "dial": "*123*3169#", "validity": "30 days"},
            ],
        },
    },
    "banglalink": {
        "name": "Banglalink",
        "short": "BL",
        "emoji": "🟠",
        "color": "Orange",
        "ussd_balance": "*124#",
        "ussd_internet": "*121*3#",
        "ussd_minutes": "*121*1#",
        "offers": {
            "internet": [
                {"name": "1GB 3 দিন", "price": "19 ৳", "dial": "*121*3019#", "validity": "3 days"},
                {"name": "2GB 7 দিন", "price": "45 ৳", "dial": "*121*3045#", "validity": "7 days"},
                {"name": "5GB 7 দিন", "price": "89 ৳", "dial": "*121*3089#", "validity": "7 days"},
                {"name": "12GB 30 দিন", "price": "199 ৳", "dial": "*121*3199#", "validity": "30 days"},
                {"name": "30GB 30 দিন", "price": "349 ৳", "dial": "*121*3349#", "validity": "30 days"},
            ],
            "minutes": [
                {"name": "50 মিনিট BL-BL", "price": "19 ৳", "dial": "*121*1019#", "validity": "3 days"},
                {"name": "100 মিনিট যেকোনো", "price": "55 ৳", "dial": "*121*1055#", "validity": "7 days"},
                {"name": "300 মিনিট যেকোনো", "price": "139 ৳", "dial": "*121*1139#", "validity": "30 days"},
            ],
            "sms": [
                {"name": "100 SMS যেকোনো", "price": "15 ৳", "dial": "*121*2015#", "validity": "7 days"},
                {"name": "500 SMS যেকোনো", "price": "30 ৳", "dial": "*121*2030#", "validity": "30 days"},
            ],
            "combo": [
                {"name": "1GB + 50 মিনিট", "price": "48 ৳", "dial": "*121*5048#", "validity": "7 days"},
                {"name": "5GB + 200 মিনিট + 100 SMS", "price": "199 ৳", "dial": "*121*5199#", "validity": "30 days"},
            ],
        },
    },
    "airtel": {
        "name": "Airtel Bangladesh",
        "short": "Airtel",
        "emoji": "🔵",
        "color": "Blue",
        "ussd_balance": "*778#",
        "ussd_internet": "*121*3#",
        "ussd_minutes": "*121*1#",
        "offers": {
            "internet": [
                {"name": "1GB 3 দিন", "price": "29 ৳", "dial": "*121*3029#", "validity": "3 days"},
                {"name": "3GB 7 দিন", "price": "69 ৳", "dial": "*121*3069#", "validity": "7 days"},
                {"name": "10GB 30 দিন", "price": "189 ৳", "dial": "*121*3189#", "validity": "30 days"},
            ],
            "minutes": [
                {"name": "50 মিনিট Airtel", "price": "25 ৳", "dial": "*121*1025#", "validity": "3 days"},
                {"name": "150 মিনিট যেকোনো", "price": "79 ৳", "dial": "*121*1079#", "validity": "7 days"},
            ],
            "sms": [
                {"name": "100 SMS যেকোনো", "price": "15 ৳", "dial": "*121*2015#", "validity": "7 days"},
            ],
            "combo": [
                {"name": "2GB + 100 মিনিট", "price": "89 ৳", "dial": "*121*5089#", "validity": "7 days"},
            ],
        },
    },
    "teletalk": {
        "name": "Teletalk",
        "short": "TT",
        "emoji": "🟡",
        "color": "Yellow",
        "ussd_balance": "*152#",
        "ussd_internet": "*111*3#",
        "ussd_minutes": "*111*1#",
        "offers": {
            "internet": [
                {"name": "1GB 3 দিন", "price": "22 ৳", "dial": "*111*022#", "validity": "3 days"},
                {"name": "3GB 7 দিন", "price": "55 ৳", "dial": "*111*055#", "validity": "7 days"},
                {"name": "10GB 30 দিন", "price": "175 ৳", "dial": "*111*175#", "validity": "30 days"},
                {"name": "20GB 30 দিন", "price": "299 ৳", "dial": "*111*299#", "validity": "30 days"},
            ],
            "minutes": [
                {"name": "50 মিনিট TT-TT", "price": "18 ৳", "dial": "*111*1018#", "validity": "3 days"},
                {"name": "100 মিনিট যেকোনো", "price": "49 ৳", "dial": "*111*1049#", "validity": "7 days"},
            ],
            "sms": [
                {"name": "100 SMS যেকোনো", "price": "12 ৳", "dial": "*111*2012#", "validity": "7 days"},
            ],
            "combo": [
                {"name": "2GB + 80 মিনিট + 50 SMS", "price": "79 ৳", "dial": "*111*5079#", "validity": "7 days"},
            ],
        },
    },
}

OFFER_TYPE_LABELS = {
    "internet": "🌐 ইন্টারনেট",
    "minutes": "📞 মিনিট",
    "sms": "💬 SMS",
    "combo": "📦 কম্বো প্যাক",
}

def get_operator_list() -> list:
    """Return list of operator keys."""
    return list(OPERATORS.keys())

def get_operator_offers(operator: str, offer_type: str = None) -> dict:
    """Get offers for a specific operator, optionally filtered by type."""
    op = OPERATORS.get(operator)
    if not op:
        return None
    if offer_type:
        return op["offers"].get(offer_type, [])
    return op["offers"]

def format_offer_card(operator: str, offer_type: str) -> str:
    """Format offers of a specific type for display."""
    op = OPERATORS.get(operator)
    if not op:
        return "❌ Operator not found."

    offers = op["offers"].get(offer_type, [])
    if not offers:
        return "❌ No offers found for this category."

    type_label = OFFER_TYPE_LABELS.get(offer_type, offer_type)
    text = (
        f"{op['emoji']} <b>{op['name']}</b>\n"
        f"{type_label}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
    )

    for offer in offers:
        text += (
            f"📌 <b>{offer['name']}</b>\n"
            f"   💰 {offer['price']}  |  📅 {offer['validity']}\n"
            f"   📱 Dial: <code>{offer['dial']}</code>\n\n"
        )

    text += (
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"📱 Balance: <code>{op['ussd_balance']}</code>\n"
        f"🌐 Internet: <code>{op['ussd_internet']}</code>\n"
        f"📞 Minutes: <code>{op['ussd_minutes']}</code>"
    )

    return text
