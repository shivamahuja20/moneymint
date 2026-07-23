"""
Syncs scheme_master with AMFI's daily NAVAll.txt — ALL schemes, ~14k rows.

Upserts every scheme found in the file (name/amc/category can change over time),
stamps last_seen, and marks schemes absent from the file for 30+ days inactive.

Run: ./venv/bin/python -m app.ingestion.sync_scheme_master
"""
import sys
import os
import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from sqlalchemy import text
from sqlalchemy.dialects.postgresql import insert

from app.db import SessionLocal, engine
from app.models import SchemeMaster
from app.ingestion.amfi_parse import fetch_navall_text, parse_navall

INACTIVE_AFTER_DAYS = 30


def sync(navall_text: str | None = None) -> int:
    if navall_text is None:
        navall_text = fetch_navall_text()
    today = datetime.date.today()

    rows = []
    for s in parse_navall(navall_text):
        rows.append({
            "scheme_code": s["scheme_code"],
            "name": s["name"],
            "amc": s["amc"],
            "scheme_type": s["scheme_type"],
            "category": s["category"],
            "sub_category": s["sub_category"],
            "plan_type": s["plan_type"],
            "option_type": s["option_type"],
            "isin": s["isin"],
            "is_active": True,
            "fund_group_id": s["fund_group_id"],
            "first_seen": today,
            "last_seen": today,
        })

    with engine.begin() as conn:
        for i in range(0, len(rows), 1000):
            batch = rows[i:i + 1000]
            stmt = insert(SchemeMaster).values(batch)
            stmt = stmt.on_conflict_do_update(
                index_elements=["scheme_code"],
                set_={
                    "name": stmt.excluded.name,
                    "amc": stmt.excluded.amc,
                    "scheme_type": stmt.excluded.scheme_type,
                    "category": stmt.excluded.category,
                    "sub_category": stmt.excluded.sub_category,
                    "plan_type": stmt.excluded.plan_type,
                    "option_type": stmt.excluded.option_type,
                    "isin": stmt.excluded.isin,
                    "is_active": True,
                    "fund_group_id": stmt.excluded.fund_group_id,
                    "last_seen": stmt.excluded.last_seen,
                },
            )
            conn.execute(stmt)
        conn.execute(
            text("UPDATE scheme_master SET is_active = false "
                 "WHERE last_seen < :cutoff AND is_active"),
            {"cutoff": today - datetime.timedelta(days=INACTIVE_AFTER_DAYS)},
        )
    return len(rows)


def run():
    n = sync()
    db = SessionLocal()
    try:
        total = db.query(SchemeMaster).count()
    finally:
        db.close()
    print(f"Upserted {n} schemes from AMFI. scheme_master now has {total} rows.")


if __name__ == "__main__":
    run()
