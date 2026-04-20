"""
PAKISTAN CLOTHING DISCOUNT BOT — GitHub Actions Version
Runs once per execution (no schedule loop needed — GitHub Actions handles timing)
"""

import requests
from bs4 import BeautifulSoup
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import re
import os
from datetime import datetime

# ─────────────────────────────────────────────
#  CONFIG — reads from GitHub Secrets (env vars)
#  or you can hardcode here for local testing
# ─────────────────────────────────────────────

ALERT_EMAIL        = os.environ.get("ALERT_EMAIL",        "your@email.com")
GMAIL_SENDER       = os.environ.get("GMAIL_SENDER",       "your.gmail@gmail.com")
GMAIL_APP_PASSWORD = os.environ.get("GMAIL_APP_PASSWORD", "xxxx xxxx xxxx xxxx")

TROUSER_LIMIT = 2000   # PKR
SHIRT_LIMIT   = 1500   # PKR

SITES = [
    {"name": "Outfitters Trousers", "url": "https://outfitters.com.pk/collections/men-trousers"},
    {"name": "Outfitters T-Shirts", "url": "https://outfitters.com.pk/collections/men-t-shirts"},
    {"name": "Bonanza Satrangi",    "url": "https://bonanzasatrangi.com/collections/men-trousers"},
    {"name": "Breakout",            "url": "https://breakout.com.pk/collections/men"},
    {"name": "Sapphire Men",        "url": "https://pk.sapphireonline.pk/collections/men"},
    # Add more:
    # {"name": "SITE NAME", "url": "https://yoursite.com/men"},
]

# ─────────────────────────────────────────────
#  KEYWORD FILTERS
# ─────────────────────────────────────────────

TROUSER_KEYWORDS = [
    "trouser", "trousers", "chino", "chinos", "pants", "pant",
    "jeans", "denim", "cargo", "slim fit", "straight fit",
    "tapered", "khaki", "slacks"
]

SHIRT_KEYWORDS = [
    "t-shirt", "tshirt", "t shirt", "tee", "crew neck",
    "crewneck", "round neck", "polo", "graphic tee",
    "half sleeve", "half-sleeve"
]

EXCLUDE_KEYWORDS = [
    "women", "woman", "ladies", "lady", "girl", "female",
    "kid", "kids", "child", "children", "baby",
    "bag", "shoe", "shoes", "socks", "cap", "hat",
    "jacket", "coat", "sweater", "hoodie", "perfume",
    "accessory", "accessories"
]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}

# ─────────────────────────────────────────────
#  HELPERS
# ─────────────────────────────────────────────

def extract_price(price_str):
    if not price_str:
        return None
    cleaned = re.sub(r'[^\d.]', '', price_str.replace(',', ''))
    try:
        return float(cleaned)
    except ValueError:
        return None

def is_trouser(name):
    n = name.lower()
    if any(kw in n for kw in EXCLUDE_KEYWORDS):
        return False
    return any(kw in n for kw in TROUSER_KEYWORDS)

def is_shirt(name):
    n = name.lower()
    if any(kw in n for kw in EXCLUDE_KEYWORDS):
        return False
    return any(kw in n for kw in SHIRT_KEYWORDS)

# ─────────────────────────────────────────────
#  SCRAPERS
# ─────────────────────────────────────────────

def scrape_shopify_json(url):
    base_url = url.split('/collections')[0] if '/collections' in url else url.rstrip('/')
    json_url = base_url + "/products.json?limit=250"
    try:
        resp = requests.get(json_url, headers=HEADERS, timeout=15)
        if resp.status_code != 200:
            return None
        products = []
        for item in resp.json().get("products", []):
            title = item.get("title", "")
            for variant in item.get("variants", []):
                price = float(variant.get("price", 0))
                compare = float(variant.get("compare_at_price") or 0)
                products.append({
                    "name": title,
                    "price": price,
                    "original_price": compare if compare > price else None,
                    "url": base_url + "/products/" + item.get("handle", ""),
                })
        return products
    except Exception as e:
        print(f"  [Shopify JSON error] {e}")
        return None

def scrape_html(site_url):
    products = []
    try:
        resp = requests.get(site_url, headers=HEADERS, timeout=15)
        soup = BeautifulSoup(resp.text, 'html.parser')
        selectors = [
            ("h3.product-title", ".price"),
            (".product-item__title", ".price"),
            (".product__title", ".product__price"),
            (".woocommerce-loop-product__title", ".price"),
            (".grid-item__title", ".grid-item__price"),
        ]
        for name_sel, _ in selectors:
            name_tags = soup.select(name_sel)
            if not name_tags:
                continue
            for tag in name_tags:
                name = tag.get_text(strip=True)
                price_tag = tag.find_next(class_=re.compile(r'price', re.I))
                if price_tag:
                    price = extract_price(price_tag.get_text(strip=True))
                    if price and price > 0:
                        products.append({
                            "name": name,
                            "price": price,
                            "original_price": None,
                            "url": site_url,
                        })
            if products:
                break
    except Exception as e:
        print(f"  [HTML scrape error] {e}")
    return products

def check_site(site):
    print(f"Checking: {site['name']}")
    products = scrape_shopify_json(site["url"])
    if products is None:
        products = scrape_html(site["url"])
    print(f"  Scanned {len(products)} products")

    deals = []
    for p in products:
        name, price = p["name"], p["price"]
        if price <= 0:
            continue
        if is_trouser(name) and price < TROUSER_LIMIT:
            deals.append({**p, "category": "Trouser", "emoji": "👖", "limit": TROUSER_LIMIT})
            print(f"  ✅ TROUSER: {name} → Rs {price:.0f}")
        elif is_shirt(name) and price < SHIRT_LIMIT:
            deals.append({**p, "category": "T-Shirt", "emoji": "👕", "limit": SHIRT_LIMIT})
            print(f"  ✅ T-SHIRT: {name} → Rs {price:.0f}")
    return deals

# ─────────────────────────────────────────────
#  EMAIL
# ─────────────────────────────────────────────

def send_email(deals):
    rows = ""
    for d in deals:
        orig = f"<s style='color:#999;'>Rs {d['original_price']:.0f}</s> → " if d.get("original_price") else ""
        rows += f"""
        <tr style='border-bottom:1px solid #f0f0f0;'>
          <td style='padding:10px 8px;font-size:20px;'>{d['emoji']}</td>
          <td style='padding:10px 8px;'>
            <strong style='color:#1a1a1a;font-size:14px;'>{d['name']}</strong><br>
            <span style='color:#888;font-size:12px;'>{d['site']} · Men\'s {d['category']}</span>
          </td>
          <td style='padding:10px 8px;text-align:right;white-space:nowrap;'>
            {orig}<strong style='color:#1a7a3a;font-size:16px;'>Rs {d['price']:.0f}</strong><br>
            <span style='color:#bbb;font-size:11px;'>limit Rs {d['limit']:,}</span>
          </td>
          <td style='padding:10px 8px;'>
            <a href='{d['url']}' style='background:#1a1a1a;color:#fff;padding:6px 14px;
            border-radius:6px;text-decoration:none;font-size:12px;'>View →</a>
          </td>
        </tr>"""

    html = f"""
    <html><body style='font-family:Arial,sans-serif;max-width:620px;margin:0 auto;background:#f9f9f9;padding:20px;'>
      <div style='background:#111;padding:20px 24px;border-radius:10px 10px 0 0;'>
        <h2 style='color:#fff;margin:0;font-size:18px;'>🛍️ Clothing Deal Alert</h2>
        <p style='color:#888;margin:4px 0 0;font-size:12px;'>
          {datetime.now().strftime('%B %d, %Y · %I:%M %p')} PKT
        </p>
      </div>
      <div style='background:#fff;border:1px solid #eee;border-top:none;border-radius:0 0 10px 10px;padding:20px;'>
        <p style='color:#555;font-size:13px;margin:0 0 16px;'>
          {len(deals)} deal(s) found below your limits —
          Trousers &lt; Rs {TROUSER_LIMIT:,} · T-Shirts &lt; Rs {SHIRT_LIMIT:,}
        </p>
        <table style='width:100%;border-collapse:collapse;'>
          <thead>
            <tr style='border-bottom:2px solid #eee;'>
              <th style='padding:8px;text-align:left;font-size:11px;color:#bbb;'></th>
              <th style='padding:8px;text-align:left;font-size:11px;color:#bbb;'>PRODUCT</th>
              <th style='padding:8px;text-align:right;font-size:11px;color:#bbb;'>PRICE</th>
              <th style='padding:8px;font-size:11px;color:#bbb;'></th>
            </tr>
          </thead>
          <tbody>{rows}</tbody>
        </table>
        <p style='color:#ccc;font-size:11px;margin-top:24px;border-top:1px solid #f0f0f0;padding-top:12px;'>
          Sent by your Discount Bot · Running on GitHub Actions every 6 hours
        </p>
      </div>
    </body></html>"""

    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"🛍️ {len(deals)} clothing deal(s) found!"
    msg["From"]    = GMAIL_SENDER
    msg["To"]      = ALERT_EMAIL
    msg.attach(MIMEText(html, "html"))

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(GMAIL_SENDER, GMAIL_APP_PASSWORD)
            server.sendmail(GMAIL_SENDER, ALERT_EMAIL, msg.as_string())
        print(f"\n📧 Email sent to {ALERT_EMAIL}")
    except Exception as e:
        print(f"\n❌ Email failed: {e}")

# ─────────────────────────────────────────────
#  MAIN — runs once, GitHub Actions handles schedule
# ─────────────────────────────────────────────

print(f"{'='*50}")
print(f"Discount Bot — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
print(f"Trouser limit: Rs {TROUSER_LIMIT:,}  |  T-shirt limit: Rs {SHIRT_LIMIT:,}")
print(f"{'='*50}\n")

all_deals = []
for site in SITES:
    found = check_site(site)
    for d in found:
        d["site"] = site["name"]
    all_deals.extend(found)

print(f"\n{'─'*50}")
if all_deals:
    print(f"Total deals: {len(all_deals)} — sending email...")
    send_email(all_deals)
else:
    print("No deals found this run. No email sent.")
print(f"{'─'*50}")
