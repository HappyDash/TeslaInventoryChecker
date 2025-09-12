"""
check_tesla_inventory.py

- Checks Tesla inventory for Model Y around ZIP 95054.
- Uses API first; falls back to Playwright scraping if API fails.
- Sends email alert when a new Model Y is found.
- Keeps last seen listings in last_seen.json to avoid duplicate emails.
"""

import os
import json
from pathlib import Path
import requests
import smtplib
from email.mime.text import MIMEText

# Playwright import
from playwright.sync_api import sync_playwright

# ------------------------
# Config
# ------------------------
ZIP = os.getenv("TARGET_ZIP", "95054")
SEARCH_DISTANCE = int(os.getenv("SEARCH_DISTANCE", "50"))
LAST_SEEN_FILE = Path("last_seen.json")

EMAIL_ADDRESS = os.getenv("EMAIL_ADDRESS")
EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD")
TO_EMAIL = os.getenv("TO_EMAIL")
EMAIL_FROM = os.getenv("EMAIL_FROM", EMAIL_ADDRESS)


# ------------------------
# Helpers
# ------------------------
def load_last_seen():
    if LAST_SEEN_FILE.exists():
        return set(json.load(LAST_SEEN_FILE))
    return set()


def save_last_seen(ids):
    with open(LAST_SEEN_FILE, "w") as f:
        json.dump(list(ids), f)


def send_email(subject, body):
    if not (EMAIL_ADDRESS and EMAIL_PASSWORD and TO_EMAIL):
        print("[WARN] Email credentials missing. Would send:\n", body)
        return
    msg = MIMEText(body)
    msg["Subject"] = subject
    msg["From"] = EMAIL_FROM
    msg["To"] = TO_EMAIL
    try:
        with smtplib.SMTP("smtp.gmail.com", 587) as server:
            server.starttls()
            server.login(EMAIL_ADDRESS, EMAIL_PASSWORD)
            server.send_message(msg)
        print("Email sent to", TO_EMAIL)
    except Exception as e:
        print("Failed to send email:", e)


# ------------------------
# Tesla inventory API
# ------------------------
def query_tesla_inventory_api(zip_code, distance):
    try:
        payload = {
            "query": {
                "model": "MY",
                "condition": "new",
                "zip": zip_code,
                "range": distance
            }
        }
        url = "https://www.tesla.com/inventory/api/v1/inventory-results"
        r = requests.post(url, json=payload, timeout=15)
        r.raise_for_status()
        data = r.json()
        vehicles = data.get("results", [])
        parsed = []
        for v in vehicles:
            vid = v.get("id") or v.get("vin")
            parsed.append({
                "id": vid,
                "vin": v.get("vin"),
                "trim": v.get("trim"),
                "price": v.get("price"),
                "city": v.get("city"),
                "state": v.get("state")
            })
        print(f"[API] Found {len(parsed)} vehicles via API.")
        return parsed
    except Exception as e:
        print("[API] Failed:", e)
        return None  # None signals fallback to Playwright


# ------------------------
# Playwright fallback
# ------------------------
def query_tesla_inventory_playwright(zip_code, distance):
    print("[Playwright] Scraping inventory page...")
    results = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        url = f"https://www.tesla.com/inventory/new/m?zip={zip_code}&distance={distance}&model=MY"
        page.goto(url)
        # Wait for listings to load
        page.wait_for_selector("div.result-item, .inventory-listing", timeout=30000)
        items = page.query_selector_all("div.result-item, .inventory-listing")
        for item in items:
            text = item.inner_text()
            if "Model Y" in text:
                results.append({
                    "id": hash(text),  # fallback unique ID
                    "text": text[:300]
                })
        browser.close()
    print(f"[Playwright] Found {len(results)} vehicles via scraping.")
    return results


# ------------------------
# Main
# ------------------------
def main():
    last_seen = load_last_seen()
    listings = query_tesla_inventory_api(ZIP, SEARCH_DISTANCE)
    if listings is None or len(listings) == 0:
        listings = query_tesla_inventory_playwright(ZIP, SEARCH_DISTANCE)
    if not listings:
        print("No listings found.")
        return

    new_listings = []
    for l in listings:
        lid = str(l.get("id"))
        if lid not in last_seen:
            new_listings.append(lid)
            last_seen.add(lid)

    if new_listings:
        first = listings[0]
        body = "\n".join([
            f"🚗 Tesla Model Y available near {ZIP}!",
            f"Trim: {first.get('trim') or first.get('text','N/A')}",
            f"Price: {first.get('price') or 'N/A'}",
            f"VIN/ID: {first.get('vin') or first.get('id')}",
            f"Location: {first.get('city','N/A')}, {first.get('state','N/A')}",
            f"Link: https://www.tesla.com/inventory/new/m?zip={ZIP}&model=MY"
        ])
        send_email("Tesla Model Y Available", body)
        print(f"New listings detected: {new_listings}")
    else:
        print("No new listings since last check.")

    save_last_seen(last_seen)


if __name__ == "__main__":
    main()
