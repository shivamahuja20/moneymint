"""
Real average AUM (AAUM) per scheme, from AMFI's official quarterly disclosure.

Like the TER data, AMFI's AAUM page is a JavaScript SPA backed by a clean JSON API
(discovered from the page bundle — no browser needed at run time):

  GET /api/average-aum-schemewise?strType=Categorywise&MF_ID=0
      -> {data:[{id, financial_year}]}                      # financial years
  GET /api/average-aum-schemewise?fyId=<id>&strType=Categorywise&MF_ID=0
      -> {type:"periods", data:{periods:[{id, period}]}}    # quarters in that FY
  GET /api/average-aum-schemewise?strType=Categorywise&fyId=<id>&periodId=<id>&MF_ID=0
      -> {data:[{Mfname, SchemeCat_Desc, schemes:[{SchemeNAVName, AMFI_Code,
                 AverageAumForTheMonth:{Excluding...:<lakhs>}}]}]}

Each plan/option carries its own AMFI_Code and its own AAUM, so we map DIRECTLY to
scheme_code (no name matching). Values are in ₹ lakh -> /100 for crore. We use the
"ExcludingFundOfFundsDomesticButIncludingFundOfFundsOverseas" figure (AMFI's headline
AAUM, which avoids double-counting domestic fund-of-funds).

Run: ./venv/bin/python -m app.ingestion.aum_sync
"""
import sys
import os
import re
import calendar
import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import httpx
from sqlalchemy import text

from app.db import engine, SessionLocal

API = "https://www.amfiindia.com/api/average-aum-schemewise"
HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"),
    "Referer": "https://www.amfiindia.com/aum-data/average-aum",
    "Accept": "application/json",
}
AAUM_FIELD = "ExcludingFundOfFundsDomesticButIncludingFundOfFundsOverseas"
FOF_FIELD = "FundOfFundsDomestic"   # domestic FoFs report their AUM here instead
_MONTHS = {m.lower(): i for i, m in enumerate(calendar.month_name) if m}


# ---------------------------------------------------------------------------
# pure helpers (unit-tested)
# ---------------------------------------------------------------------------
def period_end_date(period_label: str):
    """'April - June 2026' -> date(2026, 6, 30) (quarter end). Falls back to the
    last month/year found in the label; None if unparseable."""
    year_m = re.search(r"(\d{4})", period_label or "")
    months = re.findall(r"[A-Za-z]+", period_label or "")
    months = [m for m in months if m.lower() in _MONTHS]
    if not year_m or not months:
        return None
    year = int(year_m.group(1))
    month = _MONTHS[months[-1].lower()]
    return datetime.date(year, month, calendar.monthrange(year, month)[1])


def lakh_to_cr(raw):
    """AMFI reports AAUM in ₹ lakh; convert to ₹ crore (÷100). None/<=0 -> None."""
    try:
        v = float(raw)
    except (TypeError, ValueError):
        return None
    return round(v / 100.0, 2) if v > 0 else None


def flatten(groups):
    """AMFI groups schemes by AMC+category; flatten to [(scheme_code, aaum_cr)]."""
    out = []
    for gp in groups or []:
        for s in gp.get("schemes", []):
            code = s.get("AMFI_Code")
            m = s.get("AverageAumForTheMonth") or {}
            # domestic FoFs carry 0 in the headline field and their real AUM in FOF_FIELD
            aaum = lakh_to_cr(m.get(AAUM_FIELD)) or lakh_to_cr(m.get(FOF_FIELD))
            if code is not None and aaum is not None:
                out.append((str(code), aaum))
    return out


# ---------------------------------------------------------------------------
# API + write
# ---------------------------------------------------------------------------
def _get(client, **params):
    return client.get(API, params={"strType": "Categorywise", "MF_ID": 0, **params},
                      timeout=90).json()


UPSERT = text("""
    INSERT INTO scheme_aum (scheme_code, as_of_date, aaum_cr)
    VALUES (:c, :d, :a)
    ON CONFLICT (scheme_code, as_of_date) DO UPDATE SET aaum_cr = EXCLUDED.aaum_cr
""")


def sync():
    started = datetime.datetime.now()
    with httpx.Client(headers=HEADERS, follow_redirects=True) as client:
        fys = _get(client).get("data") or []
        if not fys:
            print("No financial years returned; aborting.")
            return
        fy_id = fys[0]["id"]                                   # latest FY
        periods = (_get(client, fyId=fy_id).get("data") or {}).get("periods") or []
        if not periods:
            print("No periods returned; aborting.")
            return
        period = periods[0]                                   # latest quarter
        as_of = period_end_date(period["period"])
        rows = flatten(_get(client, fyId=fy_id, periodId=period["id"]).get("data"))
        print(f"[{started:%H:%M:%S}] AAUM for '{period['period']}' (as of {as_of}): "
              f"{len(rows):,} scheme rows from AMFI.")

    db = SessionLocal()
    try:
        known = {r[0] for r in db.execute(text("SELECT scheme_code FROM scheme_master"))}
    finally:
        db.close()

    batch = [{"c": c, "d": as_of, "a": a} for c, a in rows if c in known]
    skipped = len(rows) - len(batch)
    with engine.begin() as conn:
        conn.execute(UPSERT, batch)
    print(f"AAUM sync done: {len(batch):,} scheme_aum rows written "
          f"({skipped:,} codes not in scheme_master).")


if __name__ == "__main__":
    sync()
