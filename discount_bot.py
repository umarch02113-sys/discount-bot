"""
PAKISTAN CLOTHING DISCOUNT BOT — GitHub Actions Version
- Monitors 11 Pakistani stores
- Men's Trousers & T-Shirts only
- L / XL size must be available
- Only alerts on FRESH discounts (not previously seen)
- Price memory stored in price_cache.json (committed to repo)
- Clean Apple-style white email
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

TROUSER_LIMIT = 2000   # PKR
SHIRT_LIMIT   = 1500   # PKR

CACHE_FILE = "price_cache.json"   # saved in repo root by GitHub Actions

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

# ── KEYWORDS ──────────────────────────────────
TROUSER_KEYWORDS = [
    "trouser","trousers","chino","chinos","pant","pants",
    "cargo","slim fit","straight fit","tapered","khaki",
    "jogger","joggers","denim","jeans"
]
SHIRT_KEYWORDS = [
    "t-shirt","tshirt","t shirt","tee","crew neck","crewneck",
    "round neck","polo","graphic tee","half sleeve","basic tee",
    "dry fit","dri-fit","jersey","knitted tee"
]
EXCLUDE_KEYWORDS = [
    "women","woman","ladies","lady","girl","female",
    "kid","kids","child","children","baby","boys",
    "bag","shoe","shoes","socks","cap","hat","belt",
    "jacket","coat","sweater","hoodie","perfume",
    "accessory","accessories","scarf","muffler"
]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
}

# ── PRICE CACHE ───────────────────────────────
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

# ── HELPERS ───────────────────────────────────
def extract_price(text):
    if not text: return None
    cleaned = re.sub(r'[^\d.]', '', text.replace(',', ''))
    try:
        val = float(cleaned)
        return val if val > 100 else None
    except ValueError:
        return None

def is_trouser(name):
    n = name.lower()
    if any(kw in n for kw in EXCLUDE_KEYWORDS): return False
    return any(kw in n for kw in TROUSER_KEYWORDS)

def is_shirt(name):
    n = name.lower()
    if any(kw in n for kw in EXCLUDE_KEYWORDS): return False
    return any(kw in n for kw in SHIRT_KEYWORDS)

def has_required_size(values):
    for v in values:
        v_up = str(v).strip().upper()
        if v_up in ["L", "XL", "LARGE", "EXTRA LARGE", "EXTRA-LARGE"]:
            return True
    return False

# ── SCRAPER ───────────────────────────────────
def scrape_shopify(base_url):
    url = base_url.rstrip('/') + "/products.json?limit=250"
    try:
        r = requests.get(url, headers=HEADERS, timeout=15)
        if r.status_code != 200: return None
        products = []
        for item in r.json().get("products", []):
            title  = item.get("title", "")
            handle = item.get("handle", "")
            size_vals = []
            for opt in item.get("options", []):
                if "size" in opt.get("name", "").lower():
                    size_vals.extend(opt.get("values", []))
            for v in item.get("variants", []):
                size_vals += [v.get("title",""), v.get("option1",""), v.get("option2","")]
            size_ok = has_required_size(size_vals)
            for v in item.get("variants", []):
                price   = float(v.get("price", 0) or 0)
                compare = float(v.get("compare_at_price") or 0)
                if price <= 0: continue
                products.append({
                    "name": title,
                    "price": price,
                    "original_price": compare if compare > price else None,
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
        for name_sel in [".product-item__title", ".grid-item__title",
                         ".product__title", ".woocommerce-loop-product__title"]:
            tags = soup.select(name_sel)
            if not tags: continue
            for tag in tags:
                name = tag.get_text(strip=True)
                pt   = tag.find_next(class_=re.compile(r'price', re.I))
                if pt:
                    price = extract_price(pt.get_text(strip=True))
                    if price:
                        products.append({"name": name, "price": price,
                            "original_price": None, "url": url, "size_available": True})
            if products: break
    except Exception as e:
        print(f"    [HTML error] {e}")
    return products

def check_site(site):
    deals = []
    print(f"\nChecking: {site['name']}")
    products = scrape_shopify(site["base"])
    if products is None:
        print("  Trying HTML fallback...")
        products = scrape_html(site["base"] + "/collections/men")
    seen, unique = set(), []
    for p in products:
        if p["name"] not in seen:
            seen.add(p["name"]); unique.append(p)
    print(f"  Scanned {len(unique)} unique products")
    for p in unique:
        name, price = p["name"], p["price"]
        if not p.get("size_available", True): continue
        if is_trouser(name) and price < TROUSER_LIMIT:
            deals.append({**p, "category": "Trouser", "emoji": "👖",
                          "limit": TROUSER_LIMIT, "site": site["name"]})
        elif is_shirt(name) and price < SHIRT_LIMIT:
            deals.append({**p, "category": "T-Shirt", "emoji": "👕",
                          "limit": SHIRT_LIMIT, "site": site["name"]})
    return deals

# ── FRESH DEALS FILTER ────────────────────────
def filter_fresh_deals(all_deals, cache):
    """
    Only return deals where the price is LOWER than what we last saw.
    If product never seen before and already under limit — it's fresh.
    Updates cache with current prices.
    """
    fresh = []
    for d in all_deals:
        key = f"{d['site']}::{d['name']}"
        prev_price = cache.get(key)

        # Fresh if: never seen before, OR price dropped since last check
        if prev_price is None or d["price"] < prev_price:
            fresh.append(d)
            print(f"  NEW DEAL: {d['name']} @ Rs {d['price']:.0f}"
                  + (f" (was Rs {prev_price:.0f})" if prev_price else " (first time)"))

        # Always update cache with latest price
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
            f"<div style='font-size:15px;font-weight:600;color:#1d1d1f;'>"
            f"{d['emoji']} {d['name']}{badge}</div>"
            f"<div style='font-size:12px;color:#86868b;margin-top:3px;'>"
            f"{d['site']} &nbsp;&middot;&nbsp; Men&#39;s {d['category']}"
            f" &nbsp;&middot;&nbsp; L / XL available</div>"
            f"</td>"
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
        "<table width='100%' cellpadding='0' cellspacing='0' style='background:#f5f5f7;'>"
        "<tr><td align='center' style='padding:40px 16px;'>"
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
        f"<span style='background:#f5f5f7;border-radius:980px;font-size:11px;color:#515154;"
        f"padding:5px 12px;margin-right:6px;'>Trouser &lt; Rs {TROUSER_LIMIT:,}</span>"
        f"<span style='background:#f5f5f7;border-radius:980px;font-size:11px;color:#515154;"
        f"padding:5px 12px;margin-right:6px;'>T-Shirt &lt; Rs {SHIRT_LIMIT:,}</span>"
        f"<span style='background:#f5f5f7;border-radius:980px;font-size:11px;color:#515154;"
        f"padding:5px 12px;'>L &amp; XL only</span>"
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
        "Only fresh discounts &mdash; repeat deals are skipped<br>"
        "Monitoring 11 stores every 6 hours &bull; GitHub Actions"
        "</div></td></tr>"

        "</table></td></tr></table></body></html>"
    )

    msg = MIMEMultipart("alternative")
    msg["Subject"] = (f"{'1 new deal' if n == 1 else f'{n} new deals'} — "
                      f"from Rs {lowest:,.0f} | Discount Bot")
    msg["From"]    = GMAIL_SENDER
    msg["To"]      = ALERT_EMAIL
    msg.attach(MIMEText(html, "html"))
    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(GMAIL_SENDER, GMAIL_APP_PASSWORD)
            server.sendmail(GMAIL_SENDER, ALERT_EMAIL, msg.as_string())
        print(f"\n  Email sent to {ALERT_EMAIL}")
    except Exception as e:
        print(f"\n  Email failed: {e}")

# ── MAIN ──────────────────────────────────────
print("=" * 55)
print(f"Discount Bot  {datetime.now().strftime('%Y-%m-%d %H:%M')}")
print(f"Trouser < Rs {TROUSER_LIMIT:,} | T-Shirt < Rs {SHIRT_LIMIT:,} | L/XL | Fresh only")
print(f"Stores: {len(SITES)}")
print("=" * 55)

cache     = load_cache()
all_deals = []

for site in SITES:
    all_deals.extend(check_site(site))

print(f"\n  Total qualifying deals found: {len(all_deals)}")

fresh_deals = filter_fresh_deals(all_deals, cache)
save_cache(cache)

print(f"  Fresh deals (new price drops): {len(fresh_deals)}")
print("-" * 55)

if fresh_deals:
    send_email(fresh_deals)
else:
    print("No new discounts since last check. No email sent.")
print("-" * 55)
