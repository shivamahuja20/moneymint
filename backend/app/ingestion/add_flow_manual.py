"""
Manually record today's FII/DII net flow — takes 10 seconds, always works.

Where to get today's numbers (pick any, they're the same official figures):
  - https://www.nseindia.com/reports/fii-dii  (official NSE page, view in browser)
  - https://groww.in/fii-dii-data  (same numbers, easier to read)

Run:
    ./venv/bin/python app/ingestion/add_flow_manual.py
It will ask you to type in FII net (crore) and DII net (crore), then save it.
"""
import sys, os, datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from app.db import SessionLocal
from app import models


def run():
    print("Enter today's FII/DII net flow (in INR crore).")
    print("Use a negative number for net selling, e.g. -1240")
    print("Check https://www.nseindia.com/reports/fii-dii or https://groww.in/fii-dii-data for today's figures.\n")

    fii_input = input("FII net (crore): ").strip()
    dii_input = input("DII net (crore): ").strip()

    try:
        fii_val = float(fii_input)
        dii_val = float(dii_input)
    except ValueError:
        print("That didn't look like a number — please run again and enter digits only (e.g. -1240 or 890.5).")
        return

    today = datetime.date.today()
    db = SessionLocal()
    existing = db.query(models.FlowDaily).filter(models.FlowDaily.date == today).first()
    if existing:
        existing.fii_cr = fii_val
        existing.dii_cr = dii_val
        print(f"Updated existing entry for {today}.")
    else:
        db.add(models.FlowDaily(date=today, fii_cr=fii_val, dii_cr=dii_val))
        print(f"Added new entry for {today}.")
    db.commit()
    db.close()
    print("Saved.")


if __name__ == "__main__":
    run()
