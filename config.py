"""
Config & Constants for Netflix Bot
"""

import os

# ── Bot Config ──
BOT_TOKEN = "8940659636:AAHLhiJVzyLnfRYEiF3CmhXCbv8x6pyBgC0"
BOT_USERNAME = "giabellshop_bot"  # without @

# ── Files ──
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
COOKIE_FILE = os.path.join(BASE_DIR, "cookie.txt")      # Single merged cookie pool
USER_FILE = os.path.join(BASE_DIR, "user.json")
GIFT_CODE_FILE = os.path.join(BASE_DIR, "giftcodes.json")

# ── Limits ──
DAILY_LIMIT = 5            # Everyone gets 5 uses/day
MAX_REF_BONUS = 5          # Max bonus from referrals
ADMIN_IDS = [7205689936]
GROUP_USERNAME = "sharenet1"  # @sharenet1

# ── NFToken API ──
NFTOKEN_API_URL = "https://android13.prod.ftl.netflix.com/graphql"
NFTOKEN_HEADERS = {
    "User-Agent": "com.netflix.mediaclient/63884 (Linux; U; Android 13; ro; M2007J3SG; Build/TQ1A.230205.001.A2; Cronet/143.0.7445.0)",
    "Accept": "multipart/mixed;deferSpec=20220824, application/graphql-response+json, application/json",
    "Content-Type": "application/json",
    "Origin": "https://www.netflix.com",
    "Referer": "https://www.netflix.com/",
}

# ── Currency Map ──
CURRENCY_MAP = {
    "US": "USD", "GB": "GBP", "CA": "CAD", "AU": "AUD",
    "BR": "BRL", "MX": "MXN", "AR": "ARS$", "CL": "CLP",
    "CO": "COP", "PE": "PEN", "VN": "VND", "TH": "THB",
    "MY": "MYR", "SG": "SGD", "PH": "PHP", "ID": "IDR",
    "IN": "INR", "JP": "JPY", "KR": "KRW", "TR": "TRY",
    "ZA": "ZAR", "NG": "NGN", "EG": "EGP", "SA": "SAR",
    "AE": "AED", "IL": "ILS", "PL": "PLN", "SE": "SEK",
    "NO": "NOK", "DK": "DKK", "CZ": "CZK", "HU": "HUF",
    "RO": "RON", "UA": "UAH", "FR": "EUR", "DE": "EUR",
    "IT": "EUR", "ES": "EUR", "NL": "EUR", "BE": "EUR",
    "AT": "EUR", "PT": "EUR", "FI": "EUR", "IE": "EUR",
    "GR": "EUR", "SK": "EUR", "SI": "EUR", "LT": "EUR",
    "LV": "EUR", "EE": "EUR", "HR": "EUR", "BG": "BGN",
    "CH": "CHF", "TW": "TWD", "HK": "HKD", "NZ": "NZD",
}
