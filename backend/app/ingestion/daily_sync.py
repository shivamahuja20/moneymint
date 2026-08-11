"""
Daily sync for the all-schemes world. Replaces amfi_nav.py + compute_returns.py.

One download of AMFI's NAVAll.txt, then:
1. scheme_master upsert (registers new schemes, refreshes names/last_seen)
2. nav_history upsert for ALL ~14k schemes for the file's NAV date (idempotent)
3. Legacy `funds` table: refresh nav for the 10 frontend funds
4. compute_metrics: rebuild returns/risk/category for all schemes and rewire the
   legacy fund_returns table with real fund/benchmark/category numbers

Run: ./venv/bin/python -m app.ingestion.daily_sync
"""
import sys
import os
import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from psycopg2.extras import execute_values

from app.db import engine, SessionLocal
from app import models
from app.ingestion.amfi_parse import fetch_navall_text, parse_navall
from app.ingestion import sync_scheme_master, compute_metrics


def upsert_navs(schemes) -> int:
    rows = [(s["scheme_code"], s["nav_date"], s["nav"])
            for s in schemes if s["nav"] is not None and s["nav_date"] is not None]
    raw = engine.raw_connection()
    try:
        with raw.cursor() as cur:
            execute_values(
                cur,
                "INSERT INTO nav_history (scheme_code, date, nav) VALUES %s "
                "ON CONFLICT (scheme_code, date) DO UPDATE SET nav = EXCLUDED.nav",
                rows, page_size=2000,
            )
        raw.commit()
    finally:
        raw.close()
    return len(rows)


def run():
    print(f"[{datetime.datetime.now():%Y-%m-%d %H:%M:%S}] Daily sync starting.")
    navall = fetch_navall_text()

    n_master = sync_scheme_master.sync(navall)
    print(f"scheme_master: upserted {n_master} schemes.")

    schemes = list(parse_navall(navall))
    n_nav = upsert_navs(schemes)
    print(f"nav_history: upserted {n_nav} NAV rows.")

    # Phase 4 analytics: rebuild scheme_returns / scheme_risk / category_stats /
    # rankings for every scheme, and flag data-quality outliers.
    compute_metrics.run()
    print("Daily sync done.")


if __name__ == "__main__":
    run()
