"""
Real expense ratios (TER) for all schemes, from AMFI's official TER data.

AMFI's TER page (amfiindia.com/ter-of-mf-schemes) is a JavaScript SPA, but it is
backed by a clean public JSON API (discovered by watching the page's network):

  GET /api/populate-mf
      -> [{mfId, mfName}, ...]  every AMC and its numeric id
  GET /api/populate-te-rdata-revised?MF_ID=<id>&Month=MM-YYYY&strCat=-1&strType=1&page=&pageSize=
      -> {data:[{Scheme_Name, R_TER, D_TER, TER_Date, ...}], meta:{pageCount,...}}

So NO browser is needed at run time (Playwright was only used once, to find the
API). Each scheme comes back with BOTH the Regular-plan all-in TER (R_TER) and the
Direct-plan TER (D_TER); we attach the right one to each plan variant by name.

Honesty: only real API values are written. Schemes we can't confidently map to a
scheme_code are skipped and counted, never guessed. TER can be revised mid-month,
so per scheme we keep the row with the latest TER_Date.

Run: ./venv/bin/python -m app.ingestion.ter_sync
"""
import sys
import os
import re
import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import httpx
from sqlalchemy import text

from app.db import engine, SessionLocal
from app.ingestion.holdings.base import match_scheme_codes

API = "https://www.amfiindia.com/api"
HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"),
    "Referer": "https://www.amfiindia.com/ter-of-mf-schemes",
    "Accept": "application/json",
}
PAGE_SIZE = 500
OPEN_ENDED = 1        # strType; open-ended covers virtually every listed retail scheme
# SEBI caps the ongoing TER at ~2.25% + 0.30% (B30) + brokerage/GST, so a real all-in
# TER tops out near ~3%. AMFI still reports much higher figures for brand-new/tiny funds
# whose one-off transaction costs dominate a month's TER (e.g. 29% on a fresh index NFO).
# Those aren't a meaningful ongoing expense ratio, so we skip them (honest null > fake 29%).
PLAUSIBLE_TER_MAX = 3.0


# ---------------------------------------------------------------------------
# pure helpers (unit-tested)
# ---------------------------------------------------------------------------
def norm_amc(name: str) -> str:
    """Normalise an AMC name for matching AMFI's mfName to scheme_master.amc."""
    return re.sub(r"[^a-z0-9]+", " ", (name or "").lower()).replace(" mutual fund", "").strip()


def _ter_float(v):
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    if f <= 0 or f > PLAUSIBLE_TER_MAX:   # 0 = not reported; > cap = transient/erroneous
        return None
    return round(f, 4)


def dedupe_latest(records):
    """AMFI returns a scheme once per plan/option (same TER), and again when TER was
    revised in-month. Collapse to one row per Scheme_Name, keeping the latest TER_Date.
    Returns {scheme_name: {"r_ter", "d_ter", "ter_date"}}."""
    best = {}
    for r in records:
        name = (r.get("Scheme_Name") or "").strip()
        if not name:
            continue
        raw = (r.get("TER_Date") or "")[:10]
        try:
            d = datetime.date.fromisoformat(raw)
        except ValueError:
            d = datetime.date.min
        cur = best.get(name)
        if cur is None or d > cur["ter_date"]:
            best[name] = {"r_ter": _ter_float(r.get("R_TER")),
                          "d_ter": _ter_float(r.get("D_TER")),
                          "ter_date": d}
    return best


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------
def fetch_amcs(client):
    return [(int(m["mfId"]), m["mfName"]) for m in
            client.get(f"{API}/populate-mf", timeout=30).json()]


def fetch_ter(client, mf_id, month, str_type=OPEN_ENDED):
    """All TER records for one AMC+month, following pagination."""
    out, page = [], 1
    while True:
        r = client.get(f"{API}/populate-te-rdata-revised", timeout=60, params={
            "MF_ID": mf_id, "Month": month, "strCat": -1, "strType": str_type,
            "page": page, "pageSize": PAGE_SIZE,
        })
        rows = r.json().get("data") or []
        out.extend(rows)
        if len(rows) < PAGE_SIZE:
            break
        page += 1
    return out


def latest_month(client):
    """Newest MM-YYYY that actually has data (AMFI publishes the prior month)."""
    today = datetime.date.today()
    for back in range(0, 4):
        m = today.replace(day=1) - datetime.timedelta(days=back * 28)
        month = f"{m.month:02d}-{m.year}"
        # probe a large AMC (HDFC = 9) for this month
        if fetch_ter(client, 9, month):
            return month
    return None


# ---------------------------------------------------------------------------
# write
# ---------------------------------------------------------------------------
UPSERT = text("""
    INSERT INTO scheme_costs (scheme_code, as_of_date, ter)
    VALUES (:c, :d, :ter)
    ON CONFLICT (scheme_code, as_of_date)
    DO UPDATE SET ter = EXCLUDED.ter
""")


def sync():
    started = datetime.datetime.now()
    with httpx.Client(headers=HEADERS, follow_redirects=True) as client:
        month = latest_month(client)
        if not month:
            print("No TER month with data found; aborting.")
            return
        as_of = datetime.date(int(month[3:]), int(month[:2]), 1)
        amcs = fetch_amcs(client)
        print(f"[{started:%H:%M:%S}] TER sync for {month}: {len(amcs)} AMCs.")

        db = SessionLocal()
        master_amcs = {norm_amc(r[0]): r[0] for r in
                       db.execute(text("SELECT DISTINCT amc FROM scheme_master WHERE amc IS NOT NULL"))}

        n_written = n_schemes = n_skipped = 0
        unmapped_amcs = []
        try:
            for mf_id, mf_name in amcs:
                amc = master_amcs.get(norm_amc(mf_name))
                if not amc:
                    unmapped_amcs.append(mf_name)
                    continue
                schemes = dedupe_latest(fetch_ter(client, mf_id, month))
                batch = []
                for sname, ter in schemes.items():
                    codes = match_scheme_codes(db, amc, sname)
                    if not codes:
                        n_skipped += 1
                        continue
                    n_schemes += 1
                    rows = db.execute(text("SELECT scheme_code, name FROM scheme_master "
                                           "WHERE scheme_code = ANY(:c)"), {"c": codes}).all()
                    for code, cname in rows:
                        val = ter["d_ter"] if "direct" in (cname or "").lower() else ter["r_ter"]
                        if val is not None:
                            batch.append({"c": code, "d": as_of, "ter": val})
                if batch:
                    with engine.begin() as conn:
                        conn.execute(UPSERT, batch)
                    n_written += len(batch)
        finally:
            db.close()

    print(f"TER sync done: {n_written:,} scheme_costs rows across {n_schemes:,} funds "
          f"({n_skipped:,} unmatched schemes, {len(unmapped_amcs)} unmapped AMCs).")
    if unmapped_amcs:
        print("  Unmapped AMCs (no scheme_master match):", ", ".join(unmapped_amcs))


if __name__ == "__main__":
    sync()
