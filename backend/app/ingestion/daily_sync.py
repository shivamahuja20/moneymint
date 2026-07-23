"""
Daily sync for the all-schemes world. Replaces amfi_nav.py + compute_returns.py.

One download of AMFI's NAVAll.txt, then:
1. scheme_master upsert (registers new schemes, refreshes names/last_seen)
2. nav_history upsert for ALL ~14k schemes for the file's NAV date (idempotent)
3. Legacy `funds` table: refresh nav for the 10 frontend funds
4. Legacy `fund_returns`: recompute each fund's own 1M/6M/1Y/3Y/5Y from the full
   nav_history (real numbers — benchmark/category columns stay untouched until
   Phase 4's proxy engine)

Run: ./venv/bin/python -m app.ingestion.daily_sync
"""
import sys
import os
import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from psycopg2.extras import execute_values
from sqlalchemy import text

from app.db import engine, SessionLocal
from app import models
from app.ingestion.amfi_parse import fetch_navall_text, parse_navall
from app.ingestion import sync_scheme_master

PERIODS_DAYS = {"1M": 30, "6M": 182, "1Y": 365, "3Y": 365 * 3, "5Y": 365 * 5}


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


def refresh_legacy_funds(db, schemes_by_code) -> int:
    updated = 0
    for fund in db.query(models.Fund).filter(models.Fund.amfi_code.isnot(None)).all():
        row = schemes_by_code.get(fund.amfi_code)
        if row and row["nav"] is not None:
            fund.nav = row["nav"]
            updated += 1
    db.commit()
    return updated


def nav_on_or_before(db, scheme_code: str, target: datetime.date):
    return db.execute(
        text("SELECT date, nav FROM nav_history WHERE scheme_code = :c AND date <= :d "
             "ORDER BY date DESC LIMIT 1"),
        {"c": scheme_code, "d": target},
    ).first()


def recompute_legacy_returns(db) -> int:
    today = datetime.date.today()
    updated = 0
    for fund in db.query(models.Fund).filter(models.Fund.amfi_code.isnot(None)).all():
        latest = nav_on_or_before(db, fund.amfi_code, today)
        if not latest:
            continue
        for period, days in PERIODS_DAYS.items():
            past = nav_on_or_before(db, fund.amfi_code, today - datetime.timedelta(days=days))
            if not past or past.nav <= 0:
                continue
            # skip if we don't actually have history reaching that far back
            if (today - past.date).days < days - 15:
                continue
            if days >= 365 * 3:
                years = days / 365
                ret = round(((latest.nav / past.nav) ** (1 / years) - 1) * 100, 2)
            else:
                ret = round((latest.nav - past.nav) / past.nav * 100, 2)
            existing = (db.query(models.FundReturn)
                        .filter_by(fund_id=fund.id, period=period).first())
            if existing:
                existing.fund_return = ret
                existing.as_of_date = today
            else:
                db.add(models.FundReturn(
                    fund_id=fund.id, period=period, fund_return=ret,
                    benchmark_return=0.0, category_avg_return=0.0, as_of_date=today))
            updated += 1
    db.commit()
    return updated


def run():
    print(f"[{datetime.datetime.now():%Y-%m-%d %H:%M:%S}] Daily sync starting.")
    navall = fetch_navall_text()

    n_master = sync_scheme_master.sync(navall)
    print(f"scheme_master: upserted {n_master} schemes.")

    schemes = list(parse_navall(navall))
    n_nav = upsert_navs(schemes)
    print(f"nav_history: upserted {n_nav} NAV rows.")

    db = SessionLocal()
    try:
        n_funds = refresh_legacy_funds(db, {s["scheme_code"]: s for s in schemes})
        n_rets = recompute_legacy_returns(db)
    finally:
        db.close()
    print(f"legacy funds: {n_funds} NAVs refreshed, {n_rets} return rows recomputed.")
    print("Daily sync done.")


if __name__ == "__main__":
    run()
