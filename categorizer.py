# -*- coding: utf-8 -*-
import re

# ── Hardcoded defaults (used as fallback & for initial DB seeding) ─────────
# Ordered list: more specific rules first
CATEGORY_RULES = [
    ('Payment / Refund', [
        'PAYMENT THANK YOU', 'PAYMENT-', 'BILL PAY', 'REFUND', 'REVERSAL', 'CREDIT ADJ'
    ]),
    ('Food Delivery', [
        'LINE MAN', 'LINEPAY*PF_LINE MAN', 'LPTH*PF_LM', 'FOODPANDA', 'ROBINHOOD',
        'GRAB FOOD', 'GRABFOOD', 'SHOPEEFOOD', 'LINE MAN WONGNAI'
    ]),
    ('Streaming & Entertainment', [
        'NETFLIX', 'SPOTIFY', 'YOUTUBE PREMIUM', 'DISNEY+', 'HBO MAX', 'APPLE TV',
        'AMAZON PRIME', 'DEEZER', 'JOOX', 'TRUE VISIONS', 'VIMEO'
    ]),
    ('Tech Subscriptions', [
        'OPENAI', 'CHATGPT', 'GITHUB', 'MIDJOURNEY', 'RACKNERD', 'DROPBOX',
        'GOOGLE ONE', 'ADOBE', 'MICROSOFT', 'NOTION', 'FIGMA', 'CANVA', 'DIGITALOCEAN',
        'AWS', 'LINODE', 'VULTR', 'CLOUDFLARE'
    ]),
    ('Health & Beauty', [
        'CLINIC', 'FITNESS', 'EVOLVE', 'HAIRDOCTOR', 'HOSPITAL', 'PHARMACY',
        'SALON', 'SPA', 'WATSONS', 'BOOTS', 'GUARDIAN', 'DENTAL', 'MEDILAB',
        'HEALTH', 'BEAUTY', 'SKIN', 'PORNKASEM', 'SOMBOON', 'BIOTHALASSO'
    ]),
    ('Telecom & Utilities', [
        'AIS SERVICES', 'AMP*AIS', 'TRUE SERVICE', 'OMISE*TRUE', 'DTAC',
        'TRUE MOVE', 'NT ', 'CAT TELECOM', 'TOT ', 'INTERNET', 'ELECTRICITY',
        'WATER', 'GAS BILL', 'MEA ', 'PEA ', 'MWA'
    ]),
    ('Fuel & Automotive', [
        'PTTST', 'PTT ', 'BANGCHAK', 'SHELL', 'CALTEX', 'ESSO', 'CHEVRON',
        'PETROL', 'FUEL', 'OIL', 'CAR WASH', 'PARKING', 'HIGHWAY'
    ]),
    ('Groceries & Supermarket', [
        'LOTUS HYPER', "LOTUS'S", 'TMN LOTUS', 'TOPS-', 'TOPS ', 'BIG C',
        'MAKRO', 'VILLA MARKET', 'GOURMET MARKET', 'FOODLAND', 'RIMPING',
        'CENTRAL FOOD', 'TOPS MARKET', 'SUPERMARKET', 'GROCERY'
    ]),
    ('Convenience Store', [
        '7-11', '7-ELEVEN', 'SEVEN ELEVEN', 'LAWSON', 'FAMILY MART', 'TMN 7-11'
    ]),
    ('Food & Dining', [
        'FAST FOOD', 'GRILL', 'BONCHON', 'TALIEW', 'TANA CURRY', 'LONGEST GRILL',
        'RESTAURANT', 'BISTRO', 'EATERY', 'KITCHEN', 'CANTEEN', 'DINER',
        'PIZZA', 'SUSHI', 'RAMEN', 'BURGER', 'BBQ', 'STEAK', 'SEAFOOD',
        'NOODLE', 'BUFFET', 'CAFE', 'COFFEE', 'BAKERY', 'DESSERT', 'TEA',
        'MCDONALD', 'KFC', 'BURGER KING', 'SUBWAY', 'STARBUCKS', 'AMAZON COFFEE',
        'INTER', 'CHICKEN', 'RICE FISH', 'CRAB'
    ]),
    ('Shopping & E-Commerce', [
        'LAZADA', 'WWW.2C2P.COM*LAZADA', '2C2P *LAZADA', 'SHOPEE', 'AMAZON',
        'WWW.2C2P', 'CENTRAL', 'ROBINSON', 'THE MALL', 'EMQUARTIER',
        'TERMINAL21', 'ICONSIAM', 'FASHIONISLAND', 'FASHION ISLAND',
        'ZARA', 'H&M', 'UNIQLO', 'NIKE', 'ADIDAS', 'SEPHORA', 'LAZADA LIMITED'
    ]),
    ('Transport & Ride-Hailing', [
        'WWW.GRAB.COM', 'GRAB', 'BTS', 'MRT', 'AIRPORT RAIL LINK',
        'TAXI', 'BOLT', 'UBER', 'LIMOUSINE', 'MINIBUS', 'BUS', 'FERRY',
        'THAI AIRWAYS', 'AIRASIA', 'LION AIR', 'NOKAIR', 'BANGKOK AIR'
    ]),
    ('Travel & Accommodation', [
        'HOTEL', 'RESORT', 'HOSTEL', 'AGODA', 'BOOKING.COM', 'AIRBNB',
        'KLOOK', 'TRIPADVISOR', 'EXPEDIA', 'TRAVELOKA'
    ]),
]

CATEGORY_ICONS = {
    'Payment / Refund': '↩',
    'Food Delivery': '🛵',
    'Streaming & Entertainment': '🎬',
    'Tech Subscriptions': '💻',
    'Health & Beauty': '💊',
    'Telecom & Utilities': '📡',
    'Fuel & Automotive': '⛽',
    'Groceries & Supermarket': '🛒',
    'Convenience Store': '🏪',
    'Food & Dining': '🍽',
    'Shopping & E-Commerce': '🛍',
    'Transport & Ride-Hailing': '🚗',
    'Travel & Accommodation': '✈',
    'Other': '📌',
}

CATEGORY_COLORS = {
    'Payment / Refund': '#56cc9d',
    'Food Delivery': '#ff9f43',
    'Streaming & Entertainment': '#a29bfe',
    'Tech Subscriptions': '#74b9ff',
    'Health & Beauty': '#fd79a8',
    'Telecom & Utilities': '#81ecec',
    'Fuel & Automotive': '#ffeaa7',
    'Groceries & Supermarket': '#55efc4',
    'Convenience Store': '#00cec9',
    'Food & Dining': '#ff6b6b',
    'Shopping & E-Commerce': '#e17055',
    'Transport & Ride-Hailing': '#fdcb6e',
    'Travel & Accommodation': '#6c5ce7',
    'Other': '#b2bec3',
}


# ── DB-backed rules cache ───────────────────────────────────────────────────

_rules_cache = None  # list of (category, keyword) tuples, ordered by priority


def invalidate_rules_cache():
    global _rules_cache
    _rules_cache = None


def _load_rules():
    """Return ordered list of (category, keyword) from DB, falling back to hardcoded."""
    global _rules_cache
    if _rules_cache is not None:
        return _rules_cache

    try:
        from database import get_db
        db = get_db()
        try:
            rows = db.execute(
                'SELECT category, keyword FROM category_rules ORDER BY category_order, id'
            ).fetchall()
        finally:
            db.close()

        if rows:
            _rules_cache = [(r['category'], r['keyword']) for r in rows]
            return _rules_cache
    except Exception:
        pass

    # Fallback: flatten hardcoded rules
    _rules_cache = [(cat, kw) for cat, keywords in CATEGORY_RULES for kw in keywords]
    return _rules_cache


def _match_keyword(keyword: str, desc_upper: str) -> bool:
    """
    Match a keyword against an uppercased description.
    '*' acts as a wildcard (any characters), so 'GRAB*FOOD' matches 'GRAB EXPRESS FOOD'.
    Plain keywords are matched as substrings.
    """
    kw = keyword.upper().strip()
    if '*' in kw:
        parts = [re.escape(p) for p in kw.split('*')]
        pattern = '.*'.join(parts)
        return bool(re.search(pattern, desc_upper))
    return kw in desc_upper


def categorize(description: str) -> str:
    if not description:
        return 'Other'
    desc_upper = description.upper()
    for category, keyword in _load_rules():
        if _match_keyword(keyword, desc_upper):
            return category
    return 'Other'
