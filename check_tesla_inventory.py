"""
check_tesla_inventory.py

- Checks Tesla inventory for Model Y around ZIP 95054.
- Sends an email notification when a new Model Y listing appears.
- Keeps a small file `seen_ids.txt` to avoid duplicate notifications.
"""

import os
import json
from pathlib import Path
from typing import List, Dict

import requests
import smtplib
from email.mime.text import MIMEText

# CONFIG
ZIP = os.getenv("TARGET_ZIP", "95054")
SEARCH_DISTANCE = int(os.getenv("SEARCH_DISTANCE", "50"))  # miles
SEEN_FILE = Path("seen_ids.txt")

# Email config from GitHub Secrets / environment variables
SMTP_SERVER = os.getenv("SMTP_SERVER", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER")
SMTP_PASS = os.getenv("SMTP_PASS")
EMAIL_TO = os.getenv("EMAIL_TO")
EMAIL_FROM = os.getenv("EMAIL_FROM", SMTP_USER)


# ------------------------
# Helpers
# ------------------------
def load_seen_ids() -> set:
    if SEEN_FILE.exists():
        return set(l.strip() for l in SEEN_FILE.read_text().splitlines() if l.strip())
    return set()


def save_seen_ids(ids: set):
    SEEN_FILE.write_text("\n".join(sorted(ids)))


def send_email(subject: str, body: str):
    if not (SMTP_USER and SMTP_PASS and EMAIL_TO):
        print("[WARN] Email credentials not set; skipping email. Message would be:\n", body)
        return

    msg = MIMEText(body)
    msg["Subject"] = subject
    msg["From"] = EMAIL_FROM
    msg["To"] = EMAIL_TO

    try:
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASS)
            server.send_message(msg)
        print("Email sent to", EMAIL_TO)
    except Exception as e:
        print("Failed to send email:", e)


# ------------------------
# Tesla inventory check
# ------------------------
def query_tesla_inventory_api(zip_code: str, distance: int) -> List[Dict]:
    """
    Try to hit Tesla's public inventory endpoint.
    """
    try:
        payload = {
            "query": {
                "model": "MY",       # Model Y
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
            vid = v.get("id") or v.get("vin") or json.dumps(v)[:50]
            parsed.append({
                "id": vid,
                "vin": v.get("vin"),
                "model": v.get("model"),
                "trim": v.get("trim"),
                "price": v.get("price"),
                "miles": v.get("miles"),
                "city": v.get("city"),
                "state": v.get("state"),
                "stock": v.get("inventory_id") or v.get("id")
            })
        print(f"[api] Found {len(parsed)} vehicles via API.")
        return parsed
    except Exception as e:
        print("[api] Inventory API failed:", e)
        return []


def find_new_listings():
    return query_tesla_inventory_api(ZIP, SEARCH_DISTANCE)


# ------------------------
# Main flow
# ------------------------
def main():
    seen = load_seen_ids()
    listings = find_new_listings()
    if not listings:
        print("No listings found.")
        return

    new_items = []
    for l in listings:
        lid = str(l.get("id") or l.get("vin") or l.get("stock"))
        if lid not in seen:
            new_items.append(lid)
            seen.add(lid)

    if new_items:
        first = listings[0]
        msg_lines = [
            f"🚗 Tesla Model Y available near {ZIP}!",
            f"Trim: {first.get('trim') or 'N/A'}",
            f"Price: {first.get('price') or 'N/A'}",
            f"VIN/ID: {first.get('vin') or first.get('id')}",
            f"Location: {first.get('city')}, {first.get('state')}",
            f"Link: https://www.tesla.com/inventory/new/m?zip={ZIP}&model=MY"
        ]
        body = "\n".join(msg_lines)
        print("New listings detected:", new_items)
        send_email("Tesla Model Y Available", body)
        save_seen_ids(seen)
    else:
        print("No new listings since last check.")


if __name__ == "__main__":
    main()
