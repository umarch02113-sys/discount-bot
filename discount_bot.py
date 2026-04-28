"""
PAKISTAN CLOTHING DISCOUNT BOT — GitHub Actions Version
STRICT: Scrapes MEN'S collection URLs only — Trousers & T-Shirts — L/XL — Fresh deals only
"""

import requests
from bs4 import BeautifulSoup
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import re, os, json
from datetime import datetime

# ── CONFIG ────────────────────────────────────
ALERT_EMAIL        = os.environ.get("ALERT_EMAIL",        "your@email.com")
GMAIL_SENDER       = os.environ.get("GMAIL_SENDER",       "your.gmail@gmail.com")
GMAIL_APP_PASSWORD = os.environ.get("GMAIL_APP_PASSWORD", "xxxx xxxx xxxx xxxx")

TROUSER_LIMIT = 1500
SHIRT_LIMIT   = 1000
CACHE_FILE    = "price_cache.json"

# ── 12 SITES — MEN'S SPECIFIC COLLECTION URLS ONLY ──
# Each site lists ONLY the men's trouser and t-shirt collection URLs.
# Bot scrapes ONLY these pages — women/kids collections are never touched.
SITES = [
    {
        "name": "Outfitters",
        "collections": [
            "https://outfitters.com.pk/collections/men-trousers",
            "https://outfitters.com.pk/collections/men-t-shirts",
        ]
    },
    {
        "name": "Engine",
        "collections": [
            "https://engine.com.pk/collections/men-trousers",
            "https://engine.com.pk/collections/men-t-shirts",
        ]
    },
    {
        "name": "Breakout",
        "collections": [
            "https://www.breakout.com.pk/collections/men-trouser-chinos",
            "https://www.breakout.com.pk/collections/men-tees",
        ]
    },
    {
        "name": "FITTED",
        "collections": [
            "https://fittedshop.com/collections/bottoms",
            "https://fittedshop.com/collections/t-shirts",
        ]
    },
    {
        "name": "Mad Official Store",
        "collections": [
            "https://madofficialstore.shop/collections/trousers",
            "https://madofficialstore.shop/collections/t-shirts",
        ]
    },
    {
        "name": "Ismail's Clothing",
        "collections": [
            "https://www.ismailsclothing.com/collections/men-trousers",
            "https://www.ismailsclothing.com/collections/men-t-shirts",
        ]
    },
    {
        "name": "Turbo Brands",
        "collections": [
            "https://turbobrandsfactory.com/collections/trouser-collection",
            "https://turbobrandsfactory.com/collections/tees",
        ]
    },
    {
        "name": "Salt by Gul Ahmed",
        "collections": [
            "https://www.gulahmedshop.com/collections/salt-western-wear-men-casual-trousers",
            "https://www.gulahmedshop.com/collections/salt-western-wear-men-t-shirts",
        ]
    },
    {
        "name": "Diners",
        "collections": [
            "https://diners.com.pk/collections/men-trousers",
            "https://diners.com.pk/collections/men-t-shirts",
        ]
    },
    {
        "name": "Cougar Clothing",
        "collections": [
            "https://cougar.com.pk/collections/men-trousers",
            "https://cougar.com.pk/collections/men-t-shirts",
        ]
    },
    {
        "name": "FUROR Jeans",
        "collections": [
            "https://furorjeans.com/collections/men-trousers",
            "https://furorjeans.com/collections/men-tees",
        ]
    },
    {
        "name": "elo (Export Leftovers)",
        "collections": [
            "https://www.exportleftovers.com/collections/mens-jeans-trousers-shorts",
            "https://www.exportleftovers.com/collections/mens-tees",
        ]
    },
]

# ── KEYWORDS ──────────────────────────────────
# Since we scrape men's URLs directly, these are just a secondary safety check

TROUSER_WORDS = [
    "trouser", "trousers", "chino", "chinos", "pant", "pants",
    "cargo", "jogger", "denim", "jeans", "khaki", "tapered",
    "straight", "slim", "loose", "wide leg", "cotton bottom",
]

TSHIRT_WORDS = [
    "t-shirt", "tshirt", "t shirt", "tee", "polo",
    "graphic", "printed", "crew neck", "round neck",
    "half sleeve", "basic", "dry fit", "dri-fit",
]

# Hard reject — catches mislabelled items even in men's collections
REJECT_WORDS = [
    "women", "woman", "ladies", "lady", "girl", "female",
    "kids", "kid", "boys", "boy", "children", "child",
    "baby", "infant", "junior", "teen",
    "jacket", "coat", "hoodie", "sweater", "sweatshirt",
    "shirt",   # catches "formal shirt", "casual shirt" — NOT t-shirts
    "shorts", "underwear", "boxer", "socks", "shoe", "shoes",
    "bag", "cap", "belt", "perfume", "scarf", "muffler",
    "kurta", "dupatta", "kameez", "shalwar", "frock",
]
# Exception: "t-shirt" contains "shirt" so we handle that carefully below

REQUIRED_SIZES = {"L", "XL", "LARGE", "EXTRA LARGE", "EXTRA-LARGE"}

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
}

# ── CACHE ─────────────────────────────────────
def load_cache():
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE) as f:
                return json.load(f)
        except Exception:
            pass
    return {}

def save_cache(cache):
    with open(CACHE_FILE, "w") as f:
        json.dump(cache, f, indent=2)

# ── FILTERS ───────────────────────────────────
def should_reject(name):
    n = name.lower()
    # Allow t-shirt/tshirt/tee even though they contain "shirt"
    is_tshirt_name = any(w in n for w in ["t-shirt", "tshirt", "t shirt", "tee", "polo"])
    for word in REJECT_WORDS:
        if word == "shirt" and is_tshirt_name:
            continue   # don't reject "graphic t-shirt" because of "shirt"
        if word in n:
            return True
    return False

def is_trouser(name):
    if should_reject(name):
        return False
    n = name.lower()
    return any(w in n for w in TROUSER_WORDS)

def is_tshirt(name):
    if should_reject(name):
        return False
    n = name.lower()
    return any(w in n for w in TSHIRT_WORDS)

def has_l_or_xl(size_values):
    for v in size_values:
        if str(v).strip().upper() in REQUIRED_SIZES:
            return True
    return False

def extract_price(text):
    if not text: return None
    cleaned = re.sub(r'[^\d.]', '', text.replace(',', ''))
    try:
        val = float(cleaned)
        return val if val > 100 else None
    except ValueError:
        return None

# ── SCRAPE A SINGLE COLLECTION PAGE ───────────
def scrape_collection(collection_url):
    """
    Calls /products.json scoped to a specific collection.
    e.g. /collections/men-trousers/products.json
    This means ONLY products from that collection are returned.
    """
    # Convert collection URL to its products.json endpoint
    base    = collection_url.split("/collections/")[0]
    col_slug = collection_url.split("/collections/")[1].split("?")[0].rstrip("/")
    json_url = f"{base}/collections/{col_slug}/products.json?limit=250"

    products = []
    try:
        r = requests.get(json_url, headers=HEADERS, timeout=15)
        if r.status_code == 200:
            for item in r.json().get("products", []):
                title  = item.get("title", "")
                handle = item.get("handle", "")

                # Collect size values
                size_vals = []
                for opt in item.get("options", []):
                    if "size" in opt.get("name", "").lower():
                        size_vals.extend(opt.get("values", []))
                for v in item.get("variants", []):
                    for key in ["title", "option1", "option2", "option3"]:
                        val = v.get(key, "")
                        if val:
                            size_vals.append(str(val))

                # Only keep variants that are specifically L or XL size
                lxl_variants = []
                for v in item.get("variants", []):
                    v_size_vals = [
                        str(v.get("title", "")),
                        str(v.get("option1", "")),
                        str(v.get("option2", "")),
                        str(v.get("option3", "")),
                    ]
                    if has_l_or_xl(v_size_vals) and float(v.get("price") or 0) > 0:
                        lxl_variants.append(v)

                # Skip product entirely if no L/XL variant found
                if not lxl_variants:
                    continue

                # Price = cheapest among L/XL variants only
                min_price = min(float(v.get("price") or 0) for v in lxl_variants)

                # compare_at_price from L/XL variants
                compare = 0.0
                for v in lxl_variants:
                    cp = float(v.get("compare_at_price") or 0)
                    if cp > min_price:
                        compare = cp
                        break

                products.append({
                    "name":           title,
                    "price":          min_price,
                    "original_price": compare if compare > min_price else None,
                    "url":            f"{base}/products/{handle}",
                    "size_available": True,
                })
            print(f"    [{col_slug}] {len(products)} products via JSON")
            return products

    except Exception as e:
        print(f"    [JSON error for {col_slug}] {e}")

    # Fallback: HTML scrape
    try:
        r    = requests.get(collection_url, headers=HEADERS, timeout=15)
        soup = BeautifulSoup(r.text, 'html.parser')
        for sel in [".product-item__title", ".grid-item__title",
                    ".product__title", ".woocommerce-loop-product__title"]:
            tags = soup.select(sel)
            if not tags:
                continue
            for tag in tags:
                name = tag.get_text(strip=True)
                pt   = tag.find_next(class_=re.compile(r'price', re.I))
                if pt:
                    price = extract_price(pt.get_text(strip=True))
                    if price:
                        products.append({
                            "name": name, "price": price,
                            "original_price": None,
                            "url": collection_url,
                            "size_available": True,
                        })
            if products:
                break
        print(f"    [{col_slug}] {len(products)} products via HTML")
    except Exception as e:
        print(f"    [HTML error for {col_slug}] {e}")

    return products

# ── CHECK ONE SITE ────────────────────────────
def check_site(site):
    all_products = []
    print(f"\nChecking: {site['name']}")

    for url in site["collections"]:
        prods = scrape_collection(url)
        # Tag each product with which collection type it came from
        col_type = "trouser" if any(w in url for w in ["trouser", "chino", "pant", "bottom"]) else "tshirt"
        for p in prods:
            p["_col_type"] = col_type
        all_products.extend(prods)

    # Deduplicate by name
    seen, unique = set(), []
    for p in all_products:
        if p["name"] not in seen:
            seen.add(p["name"])
            unique.append(p)

    print(f"  Total unique products: {len(unique)}")

    deals = []
    for p in unique:
        name  = p["name"]
        price = p["price"]

        # Skip if no L or XL
        if not p.get("size_available", False):
            continue

        # Secondary keyword check (safety net for mislabelled items)
        col_type = p.get("_col_type", "")
        if col_type == "trouser":
            if should_reject(name):
                print(f"  REJECTED: {name}")
                continue
            if price < TROUSER_LIMIT:
                deals.append({**p, "category": "Trouser", "emoji": "👖",
                              "limit": TROUSER_LIMIT, "site": site["name"]})
                print(f"  TROUSER DEAL: {name} — Rs {price:.0f}")

        elif col_type == "tshirt":
            if should_reject(name):
                print(f"  REJECTED: {name}")
                continue
            if price < SHIRT_LIMIT:
                deals.append({**p, "category": "T-Shirt", "emoji": "👕",
                              "limit": SHIRT_LIMIT, "site": site["name"]})
                print(f"  T-SHIRT DEAL: {name} — Rs {price:.0f}")

    print(f"  Qualifying deals: {len(deals)}")
    return deals

# ── FRESH DEALS ONLY ──────────────────────────
def filter_fresh(all_deals, cache):
    fresh = []
    for d in all_deals:
        key   = f"{d['site']}::{d['name']}"
        prev  = cache.get(key)
        if prev is None or d["price"] < float(prev):
            fresh.append(d)
            note = "first time" if prev is None else f"dropped from Rs {prev:.0f}"
            print(f"  FRESH: {d['name']} @ Rs {d['price']:.0f} ({note})")
        cache[key] = d["price"]
    return fresh

# ── APPLE-STYLE EMAIL ─────────────────────────
def send_email(deals):
    trousers = [d for d in deals if d["category"] == "Trouser"]
    shirts   = [d for d in deals if d["category"] == "T-Shirt"]
    n        = len(deals)
    lowest   = min(d["price"] for d in deals)
    now      = datetime.now().strftime("%B %d, %Y")

    def deal_row(d):
        badge, was = "", ""
        if d.get("original_price") and d["original_price"] > d["price"]:
            pct   = int((1 - d["price"] / d["original_price"]) * 100)
            badge = (f"<span style='display:inline-block;background:#e8f5e9;color:#2e7d32;"
                     f"font-size:10px;font-weight:700;padding:2px 8px;border-radius:20px;"
                     f"margin-left:8px;'>{pct}% off</span>")
            was   = (f"<div style='font-size:12px;color:#aaa;text-decoration:line-through;"
                     f"margin-top:1px;'>Was Rs {d['original_price']:,.0f}</div>")
        return (
            f"<tr>"
            f"<td style='padding:16px 0;border-bottom:1px solid #f0f0f0;'>"
            f"<div style='font-size:15px;font-weight:600;color:#1d1d1f;'>{d['emoji']} {d['name']}{badge}</div>"
            f"<div style='font-size:12px;color:#86868b;margin-top:3px;'>"
            f"{d['site']} &nbsp;&middot;&nbsp; Men&#39;s {d['category']} &nbsp;&middot;&nbsp; L / XL in stock"
            f"</div></td>"
            f"<td style='padding:16px 0 16px 16px;border-bottom:1px solid #f0f0f0;"
            f"text-align:right;white-space:nowrap;vertical-align:middle;'>"
            f"<div style='font-size:18px;font-weight:700;color:#1d1d1f;'>Rs {d['price']:,.0f}</div>"
            f"{was}</td>"
            f"<td style='padding:16px 0 16px 12px;border-bottom:1px solid #f0f0f0;"
            f"text-align:right;vertical-align:middle;'>"
            f"<a href='{d['url']}' style='display:inline-block;background:#0071e3;color:#fff;"
            f"font-size:12px;font-weight:600;padding:8px 18px;border-radius:980px;"
            f"text-decoration:none;white-space:nowrap;'>Shop</a></td></tr>"
        )

    def section_block(label, items):
        if not items: return ""
        rows = "".join(deal_row(d) for d in items)
        return (
            f"<div style='margin-bottom:32px;'>"
            f"<div style='font-size:12px;font-weight:600;color:#86868b;letter-spacing:0.06em;"
            f"text-transform:uppercase;margin-bottom:10px;'>{label}</div>"
            f"<table style='width:100%;border-collapse:collapse;'>{rows}</table>"
            f"</div>"
        )

    html = (
        "<!DOCTYPE html><html><body style='margin:0;padding:0;background:#f5f5f7;"
        "font-family:-apple-system,BlinkMacSystemFont,\"Helvetica Neue\",Arial,sans-serif;'>"
        "<table width='100%' cellpadding='0' cellspacing='0'><tr>"
        "<td align='center' style='padding:40px 16px;'>"
        "<table width='600' cellpadding='0' cellspacing='0' style='max-width:600px;width:100%;'>"
        "<tr><td style='background:#fff;border-radius:18px 18px 0 0;padding:36px 36px 24px;'>"
        "<div style='font-size:11px;font-weight:600;color:#86868b;letter-spacing:0.08em;"
        "text-transform:uppercase;margin-bottom:6px;'>Fresh Discount Alert</div>"
        f"<div style='font-size:28px;font-weight:700;color:#1d1d1f;line-height:1.2;margin-bottom:6px;'>"
        f"{n} new deal{'s' if n > 1 else ''} just dropped</div>"
        f"<div style='font-size:14px;color:#86868b;'>{now} &nbsp;&middot;&nbsp; "
        f"Lowest: <strong style='color:#1d1d1f;'>Rs {lowest:,.0f}</strong></div>"
        "<div style='margin-top:18px;'>"
        f"<span style='background:#f5f5f7;border-radius:980px;font-size:11px;color:#515154;padding:5px 12px;margin-right:6px;'>Men only</span>"
        f"<span style='background:#f5f5f7;border-radius:980px;font-size:11px;color:#515154;padding:5px 12px;margin-right:6px;'>Trouser &lt; Rs {TROUSER_LIMIT:,}</span>"
        f"<span style='background:#f5f5f7;border-radius:980px;font-size:11px;color:#515154;padding:5px 12px;margin-right:6px;'>T-Shirt &lt; Rs {SHIRT_LIMIT:,}</span>"
        f"<span style='background:#f5f5f7;border-radius:980px;font-size:11px;color:#515154;padding:5px 12px;'>L &amp; XL only</span>"
        "</div></td></tr>"
        "<tr><td style='background:#fff;padding:0 36px;'><div style='height:1px;background:#f0f0f0;'></div></td></tr>"
        "<tr><td style='background:#fff;border-radius:0 0 18px 18px;padding:28px 36px 36px;'>"
        + section_block("Trousers", trousers)
        + section_block("T-Shirts", shirts)
        + "</td></tr>"
        "<tr><td style='padding:20px 0 0;text-align:center;'>"
        "<div style='font-size:11px;color:#adadb0;line-height:1.8;'>"
        "Only fresh price drops &mdash; no repeat alerts<br>"
        "Monitoring 12 stores every 6 hours &bull; GitHub Actions"
        "</div></td></tr>"
        "</table></td></tr></table></body></html>"
    )

    msg = MIMEMultipart("alternative")
    msg["Subject"] = (f"{'1 new deal' if n == 1 else f'{n} new deals'} — from Rs {lowest:,.0f} | Discount Bot")
    msg["From"] = GMAIL_SENDER
    msg["To"]   = ALERT_EMAIL
    msg.attach(MIMEText(html, "html"))
    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(GMAIL_SENDER, GMAIL_APP_PASSWORD)
            server.sendmail(GMAIL_SENDER, ALERT_EMAIL, msg.as_string())
        print(f"\n  Email sent to {ALERT_EMAIL}")
    except Exception as e:
        print(f"\n  Email failed: {e}")

# ── MAIN ──────────────────────────────────────
print("=" * 60)
print(f"Discount Bot  {datetime.now().strftime('%Y-%m-%d %H:%M')}")
print(f"Men Trouser < Rs {TROUSER_LIMIT:,} | T-Shirt < Rs {SHIRT_LIMIT:,} | L/XL | Fresh only")
print(f"Stores: {len(SITES)}")
print("=" * 60)

cache     = load_cache()
all_deals = []
for site in SITES:
    all_deals.extend(check_site(site))

print(f"\nTotal qualifying: {len(all_deals)}")
fresh = filter_fresh(all_deals, cache)
save_cache(cache)
print(f"Fresh drops: {len(fresh)}")
print("-" * 60)

if fresh:
    send_email(fresh)
else:
    print("No new discounts. No email sent.")
print("-" * 60)
