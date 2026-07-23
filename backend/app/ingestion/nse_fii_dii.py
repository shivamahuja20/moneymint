"""
Attempts to pull today's FII/DII net flow from NSE's official CSV report.

Source: https://www.nseindia.com/reports/fii-dii (their own "Download (.csv)" link)
Note: NSE's site aggressively blocks non-browser requests, even with correct headers.
This script may simply fail with a 403 — that's NSE's bot protection, not a bug here.
If it fails consistently, use add_flow_manual.py instead (takes 10 seconds/day, always works).

Run:
    ./venv/bin/python -m app.ingestion.nse_fii_dii
"""
import sys, os, io, csv, datetime
import httpx

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from app.db import SessionLocal
from app import models

HOME_URL = "https://www.nseindia.com"
CSV_URL = "https://www.nseindia.com/api/reports?archives=%5B%7B%22name%22%3A%22CM%20-%20FII%20and%20DII%20Trading%20Activity%22%2C%22type%22%3A%22daily-reports%22%2C%22category%22%3A%22capital-market%22%2C%22section%22%3A%22equities%22%7D%5D&date=&type=equities&mode=single"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    "Accept": "text/csv,application/json,*/*",
    "Referer": "https://www.nseindia.com/reports/fii-dii",
}


def fetch_fii_dii():
    with httpx.Client(headers=HEADERS, timeout=20.0, follow_redirects=True) as client:
        # NSE requires an initial homepage visit to set session cookies before the API call works
        client.get(HOME_URL)
        resp = client.get(CSV_URL)
        resp.raise_for_status()
        return resp.text


def run():
    print("Attempting to fetch NSE FII/DII data...")
    try:
        text = fetch_fii_dii()
    except Exception as e:
        print(f"Failed to fetch from NSE: {e}")
        print("This usually means NSE's bot protection blocked the request.")
        print("Use add_flow_manual.py to enter today's figure by hand instead — takes 10 seconds.")
        return

    # NSE's CSV typically has columns like: Date, FII/FPI Gross Purchase, Gross Sales, Net,
    # DII Gross Purchase, Gross Sales, Net — parse defensively since the exact layout can shift.
    reader = csv.reader(io.StringIO(text))
    rows = list(reader)
    print("Raw response (first 5 rows) for inspection:")
    for r in rows[:5]:
        print(r)
    print("\nIf this doesn't look like a clean CSV table, NSE likely returned an error page —")
    print("use add_flow_manual.py instead.")


if __name__ == "__main__":
    run()
