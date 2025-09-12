"""
check_tesla_inventory.py

- Scrapes Tesla Model Y inventory near ZIP 95054.
- Sends email listing all new cars found.
- Uses Playwright to scrape the page directly.
"""

import os
import json
from pathlib import Path
from playwright.sync_api import sync_playwright
import smtplib
from email.mime.text import MIMEText

# ------------------------
# Config
# ------------------------
ZIP = "95054"
TESLA_URL = f"https://www.tesla.com/inventory/new/my?arrangeby=savings&zip={ZIP}&range=0"
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
# Scrape Tesla Inventory
# ------------------------
def scrape_inventory():
    listings = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(TESLA_URL)

        # wait for inventory to load
        page.wait_for_selector("article.result.card", timeout=30000)

        items = page.query_selector_all("article.result.card")
        for item in items:
            try:
                trim = item.query_selector(".trim-name").inner_text().strip()
                price = item.query_selector(".card-info-tooltip-container span").inner_text().strip()
                vin = item.get_attribute("data-id")
                listings.append({
                    "id": vin,
                    "trim": trim,
                    "price": price
                })
            except Exception:
                continue

        browser.close()
    return listings


# ------------------------
# Main
# ------------------------
def main():
    last_seen = load_last_seen()
    listings = scrape_inventory()

    if not listings:
        print("No listings found.")
        return

    new_listings = []
    for l in listings:
        lid = l["id"]
        if lid not in last_seen:
            new_listings.append(l)
            last_seen.add(lid)

    if new_listings:
        body_lines = [f"🚗 Tesla Model Y Available near {ZIP}!\n"]
        for idx, car in enumerate(new_listings, 1):
            body_lines.append(f"Car {idx}:")
            body_lines.append(f"Trim: {car['trim']}")
            body_lines.append(f"Price: {car['price']}")
            body_lines.append(f"ID: {car['id']}")
            body_lines.append(f"Link: {TESLA_URL}")
            body_lines.append("-" * 40)
        body = "\n".join(body_lines)
        send_email("Tesla Model Y Available", body)
        print(f"New listings detected: {[l['id'] for l in new_listings]}")
    else:
        print("No new listings since last check.")

    save_last_seen(last_seen)


if __name__ == "__main__":
    main()
