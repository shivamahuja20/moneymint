"""
One-time migration: copies the legacy tables from the old SQLite file into
PostgreSQL, correcting the AMFI scheme codes that were wrong in the seed data
(verified 2026-07-23 against AMFI's official NAVAll.txt by name lookup).

The old nav_history (9 rows, partly recorded under wrong codes) is deliberately
NOT migrated — the MFAPI backfill rebuilds complete, correct history.

Run: ./venv/bin/python migrate_from_sqlite.py
"""
import sqlite3

from app.db import SessionLocal
from app import models

SQLITE_PATH = "fund_analyser.db"

# slug -> verified AMFI code (Direct Plan - Growth for every fund)
CORRECTED_CODES = {
    "hdfc-flexi-cap": "118955",    # was 118825 = Mirae Asset Large Cap (wrong)
    "parag-parikh-flexi": "122639",
    "icici-tech": "120594",        # was 120638 = ICICI Interval Fund (wrong)
    "sbi-banking-fin": "133859",   # was 119598 = SBI Large Cap (wrong)
    "nippon-pharma": "118759",     # was 118778 = Nippon Small Cap (wrong)
    "quant-infra": "120833",
    "hdfc-defence": "151750",
    "axis-realty": "150532",
    "tata-fmcg": "135805",         # was missing
    "dsp-energy": "119028",
}


def main():
    src = sqlite3.connect(SQLITE_PATH)
    src.row_factory = sqlite3.Row
    db = SessionLocal()
    try:
        if db.query(models.Fund).count() > 0:
            print("funds table already populated in Postgres — nothing to do.")
            return

        for r in src.execute("SELECT * FROM funds"):
            row = dict(r)
            row["amfi_code"] = CORRECTED_CODES[row["id"]]
            db.add(models.Fund(**row))

        for r in src.execute("SELECT * FROM fund_returns"):
            row = dict(r)
            row.pop("id", None)
            db.add(models.FundReturn(**row))

        for r in src.execute("SELECT * FROM sector_daily"):
            row = dict(r)
            row.pop("id", None)
            db.add(models.SectorDaily(**row))

        for r in src.execute("SELECT * FROM flow_daily"):
            row = dict(r)
            row.pop("id", None)
            db.add(models.FlowDaily(**row))

        db.commit()
        print(f"Migrated: {db.query(models.Fund).count()} funds, "
              f"{db.query(models.FundReturn).count()} return rows, "
              f"{db.query(models.SectorDaily).count()} sector rows, "
              f"{db.query(models.FlowDaily).count()} flow rows. "
              "AMFI codes corrected for 4 funds, added for 1.")
    finally:
        db.close()
        src.close()


if __name__ == "__main__":
    main()
