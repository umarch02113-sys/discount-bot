"""
PAKISTAN CLOTHING DISCOUNT BOT — GitHub Actions Version
STRICT FILTER: Men's Trousers & T-Shirts ONLY — L/XL — Fresh discounts only
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

TROUSER_LIMIT = 2000
SHIRT_LIMIT   = 1500
CACHE_FILE    = "price_cache.json"

# ── 11 SITES ──────────────────────────────────
SITES = [
    {"name": "Outfitters",        "base": "https://outfitters.com.pk"},
    {"name": "Engine",            "base": "https://engine.com.pk"},
    {"name": "Breakout",          "base": "https://www.breakout.com.pk"},
    {"name": "FITTED",            "base": "https://fittedshop.com"},
    {"name": "Mad Official Store","base": "https://madofficialstore.shop"},
    {"name": "Ismail's Clothing", "base": "https://www.ismailsclothing.com"},
    {"name": "Turbo Brands",      "base": "https://turbobrandsfactory.com"},
    {"name": "Salt by Gul Ahmed", "base": "https://www.gulahmedshop.com"},
    {"name": "Diners",            "base": "https://diners.com.pk"},
    {"name": "Cougar Clothing",   "base": "https://cougar.com.pk"},
    {"name": "FUROR Jeans",       "base": "https://furorjeans.com"},
]

# ── STRICT KEYWORD LISTS ──────────────────────

# Product must contain AT LEAST ONE of these to be a trouser
TROUSER_MUST_HAVE = [
    "trouser", "trousers", "chino", "chinos",
    "cargo pant", "cargo trouser", "jogger trouser",
    "cotton pant", "slim trouser", "straight trouser",
    "tapered trouser", "khaki trouser", "loose trouser",
    "wide leg trouser", "men pant", "men trouser",
]

# Product must contain AT LEAST ONE of these to be a t-shirt
SHIRT_MUST_HAVE = [
    "t-shirt", "tshirt", "t shirt",
    "graphic tee", "basic tee", "printed tee",
    "crew neck tee", "round neck tee",
    "half sleeve tee", "dry fit tee", "dri-fit tee",
    "men tee", "men t-shirt", "polo tee",
]

# If product name contains ANY of these → immediately reject, no matter what
HARD_REJECT = [
    # Female
    "women", "woman", "ladies", "lady", "girls", "girl",
    "female", "womens", "her ", " her ", "she ", "kurta",
    "dupatta", "lawn suit", "unstitched", "2-piece", "3-piece",
    "frock", "maxi", "blouse", "top and", "and top",
    "kameez", "shalwar",
    # Kids / teens
    "kids", "kid", "boys", "boy ", " boy", "children",
    "child", "baby", "infant", "junior", "juniors",
    "toddler", "youth", "teen", "teenage",
    # Non-clothing items
    "shoe", "shoes", "sneaker", "sneakers", "slides",
    "socks", "cap", "caps", "hat", "hats", "belt", "belts",
    "bag", "bags", "backpack", "wallet", "perfume", "fragrance",
    "deodorant", "watch", "glasses", "sunglasses",
    "jacket", "coat", "blazer", "sweater", "hoodie",
    "sweatshirt", "tracksuit", "shacket", "waistcoat",
    "scarf", "muffler", "beanie", "gloves",
    # Other bottoms that are NOT trousers
    "shorts", "short ", " short", "skirt", "legging",
    "tights", "underwear", "boxer", "brief",
    # Shirts that are NOT t-shirts
    "formal shirt", "casual shirt", "dress shirt",
    "oxford shirt", "linen shirt", "check shirt",
    "printed shirt", "flannel shirt", "denim shirt",
    "half sleeve shirt", "full sleeve shirt",
    "button down", "button-down",
]

REQUIRED_SIZES = {"L", "XL", "LARGE", "EXTRA LARGE", "EXTRA-LARGE", "EXTRA_LARGE"}

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
            with open(CACHE_FILE, "r") as f:
                return json.load(f)
        except Exception:
            pass
    return {}

def save_cache(cache):
    with open(CACHE_FILE, "w") as f:
        json.dump(cache, f, indent=2)

# ── FILTERS ───────────────────────────────────
def hard_reject(name):
    """Returns True if product should be REJECTED immediately."""
    n = name.lower()
    return any(kw in n for kw in HARD_REJECT)

def is_men_trouser(name):
    if hard_reject(name):
        return False
    n = name.lower()
    return any(kw in n for kw in TROUSER_MUST_HAVE)

def is_men_tshirt(name):
    if hard_reject(name):
        return False
    n = name.lower()
    return any(kw in n for kw in SHIRT_MUST_HAVE)

def has_size_l_or_xl(values):
    for v in values:
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

# ── SHOPIFY SCRAPER ───────────────────────────
def scrape_shopify(base_url):
    url = base_url.rstrip('/') + "/products.json?limit=250"
    try:
        r = requests.get(url, headers=HEADERS, timeout=15)
        if r.status_code != 200:
            return None
        products = []
        for item in r.json().get("products", []):
            title  = item.get("title", "")
            handle = item.get("handle", "")

            # Collect size values from options
            size_vals = []
            for opt in item.get("options", []):
                if "size" in opt.get("name", "").lower():
                    size_vals.extend(opt.get("values", []))
            for v in item.get("variants", []):
                for key in ["title", "option1", "option2", "option3"]:
                    val = v.get(key, "")
                    if val:
                        size_vals.append(val)

            size_ok = has_size_l_or_xl(size_vals)

            # Only keep cheapest variant per product
            prices = [float(v.get("price", 0) or 0) for v in item.get("variants", []) if float(v.get("price", 0) or 0) > 0]
            if not prices:
                continue
            min_price = min(prices)

            # compare_at_price from first variant that has it
            compare = 0.0
            for v in item.get("variants", []):
                cp = float(v.get("compare_at_price") or 0)
                if cp > 0:
                    compare = cp
                    break

            products.append({
                "name": title,
                "price": min_price,
                "original_price": compare if compare > min_price else None,
                "url": base_url.rstrip('/') + "/products/" + handle,
                "size_available": size_ok,
            })
        return products
    except Exception as e:
        print(f"    [Shopify error] {e}")
        return None

def scrape_html(url):
    products = []
    try:
        r = requests.get(url, headers=HEADERS, timeout=15)
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
                            "name": name,
                            "price": price,
                            "original_price": None,
                            "url": url,
                            "size_available": True,
                        })
            if products:
                break
    except Exception as e:
        print(f"    [HTML error] {e}")
    return products

# ── CHECK ONE SITE ────────────────────────────
def check_site(site):
    deals = []
    print(f"\nChecking: {site['name']}")

    products = scrape_shopify(site["base"])
    if products is None:
        print("  Not Shopify, trying HTML...")
        products = scrape_html(site["base"] + "/collections/men")

    # Deduplicate by name
    seen, unique = set(), []
    for p in products:
        if p["name"] not in seen:
            seen.add(p["name"])
            unique.append(p)

    print(f"  Total products: {len(unique)}")

    for p in unique:
        name  = p["name"]
        price = p["price"]

        # Step 1 — hard reject anything not men's trouser or t-shirt
        if not is_men_trouser(name) and not is_men_tshirt(name):
            continue

        # Step 2 — L or XL must be available
        if not p.get("size_available", False):
            print(f"  SKIP (no L/XL): {name}")
            continue

        # Step 3 — price must be under limit
        if is_men_trouser(name) and price < TROUSER_LIMIT:
            deals.append({**p, "category": "Trouser", "emoji": "👖",
                          "limit": TROUSER_LIMIT, "site": site["name"]})
            print(f"  TROUSER: {name} — Rs {price:.0f}")

        elif is_men_tshirt(name) and price < SHIRT_LIMIT:
            deals.append({**p, "category": "T-Shirt", "emoji": "👕",
                          "limit": SHIRT_LIMIT, "site": site["name"]})
            print(f"  T-SHIRT: {name} — Rs {price:.0f}")

    print(f"  Qualifying deals: {len(deals)}")
    return deals

# ── FRESH DEALS ONLY ──────────────────────────
def filter_fresh(all_deals, cache):
    fresh = []
    for d in all_deals:
        key        = f"{d['site']}::{d['name']}"
        prev_price = cache.get(key)

        # Alert only if price dropped (or never seen before)
        if prev_price is None or d["price"] < float(prev_price):
            fresh.append(d)
            status = f"first time seen" if prev_price is None else f"dropped from Rs {prev_price:.0f}"
            print(f"  FRESH: {d['name']} @ Rs {d['price']:.0f} ({status})")

        # Always update cache to latest price
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

        # Header
        "<tr><td style='background:#fff;border-radius:18px 18px 0 0;padding:36px 36px 24px;'>"
        "<div style='font-size:11px;font-weight:600;color:#86868b;letter-spacing:0.08em;"
        "text-transform:uppercase;margin-bottom:6px;'>Fresh Discount Alert</div>"
        f"<div style='font-size:28px;font-weight:700;color:#1d1d1f;line-height:1.2;margin-bottom:6px;'>"
        f"{n} new deal{'s' if n > 1 else ''} just dropped</div>"
        f"<div style='font-size:14px;color:#86868b;'>{now} &nbsp;&middot;&nbsp; "
        f"Lowest: <strong style='color:#1d1d1f;'>Rs {lowest:,.0f}</strong></div>"
        "<div style='margin-top:18px;'>"
        f"<span style='background:#f5f5f7;border-radius:980px;font-size:11px;"
        f"color:#515154;padding:5px 12px;margin-right:6px;'>Men only</span>"
        f"<span style='background:#f5f5f7;border-radius:980px;font-size:11px;"
        f"color:#515154;padding:5px 12px;margin-right:6px;'>Trouser &lt; Rs {TROUSER_LIMIT:,}</span>"
        f"<span style='background:#f5f5f7;border-radius:980px;font-size:11px;"
        f"color:#515154;padding:5px 12px;margin-right:6px;'>T-Shirt &lt; Rs {SHIRT_LIMIT:,}</span>"
        f"<span style='background:#f5f5f7;border-radius:980px;font-size:11px;"
        f"color:#515154;padding:5px 12px;'>L &amp; XL only</span>"
        "</div></td></tr>"

        # Divider
        "<tr><td style='background:#fff;padding:0 36px;'>"
        "<div style='height:1px;background:#f0f0f0;'></div></td></tr>"

        # Deals
        "<tr><td style='background:#fff;border-radius:0 0 18px 18px;padding:28px 36px 36px;'>"
        + section_block("Trousers", trousers)
        + section_block("T-Shirts", shirts)
        + "</td></tr>"

        # Footer
        "<tr><td style='padding:20px 0 0;text-align:center;'>"
        "<div style='font-size:11px;color:#adadb0;line-height:1.8;'>"
        "Only fresh price drops &mdash; no repeat alerts<br>"
        "Monitoring 11 stores every 6 hours &bull; GitHub Actions"
        "</div></td></tr>"

        "</table></td></tr></table></body></html>"
    )

    msg = MIMEMultipart("alternative")
    msg["Subject"] = (
        f"{'1 new deal' if n == 1 else f'{n} new deals'} — "
        f"from Rs {lowest:,.0f} | Discount Bot"
    )
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
print(f"Men's Trousers < Rs {TROUSER_LIMIT:,} | T-Shirts < Rs {SHIRT_LIMIT:,} | L/XL | Fresh only")
print(f"Stores: {len(SITES)}")
print("=" * 60)

cache     = load_cache()
all_deals = []

for site in SITES:
    all_deals.extend(check_site(site))

print(f"\nTotal qualifying deals: {len(all_deals)}")
fresh = filter_fresh(all_deals, cache)
save_cache(cache)
print(f"Fresh deals (new drops): {len(fresh)}")
print("-" * 60)

if fresh:
    send_email(fresh)
else:
    print("No new discounts since last check. No email sent.")
print("-" * 60)
