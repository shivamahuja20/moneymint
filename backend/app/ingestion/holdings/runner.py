"""
Holdings ETL orchestrator.

Runs each registered per-AMC parser inside its own try/except so one AMC's broken
file (a layout change, a 404, a corrupt workbook) is logged and skipped — it can
never sink the other AMCs. Discovery + row parsing are generic (base.py); a per-AMC
module only supplies AMC_NAME / AMC_SLUG / discover().

Run:  ./venv/bin/python -m app.ingestion.holdings.runner
"""
import sys
import os
import datetime
import traceback

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

import openpyxl

from app.db import engine, SessionLocal
from app.ingestion.holdings import base
from app.ingestion.holdings.parsers import ppfas

# registry — add a module here as each AMC parser is written
PARSERS = [ppfas]


def process_amc(mod) -> dict:
    """Download + parse every file the AMC exposes, write matched schemes' holdings."""
    db = SessionLocal()
    stats = {"amc": mod.AMC_NAME, "files": 0, "schemes": 0, "rows": 0, "unmatched": []}
    try:
        files = mod.discover()
        for f in files:
            stats["files"] += 1
            path = base.cache_workbook(mod.AMC_SLUG, f["filename"], f["url"])
            wb = openpyxl.load_workbook(path, data_only=True, read_only=True)
            for ws in wb.worksheets:
                scheme_name, as_of, rows = base.parse_standard_sheet(ws)
                if not rows or not scheme_name:
                    continue
                as_of = as_of or datetime.date.today()
                codes = base.match_scheme_codes(db, mod.AMC_NAME, scheme_name)
                if not codes:
                    stats["unmatched"].append(scheme_name[:50])
                    continue
                with engine.begin() as conn:
                    for code in codes:
                        base.write_holdings(conn, code, as_of, rows)
                stats["schemes"] += 1
                stats["rows"] += len(rows) * len(codes)
            wb.close()
    finally:
        db.close()
    return stats


def run():
    print(f"[{datetime.datetime.now():%Y-%m-%d %H:%M:%S}] Holdings ETL starting "
          f"({len(PARSERS)} AMC parser(s)).", flush=True)
    ok = failed = 0
    for mod in PARSERS:
        try:
            s = process_amc(mod)
            ok += 1
            print(f"  ✓ {s['amc']}: {s['files']} file(s), {s['schemes']} scheme(s) matched, "
                  f"{s['rows']} holding rows"
                  + (f", {len(s['unmatched'])} unmatched sheets" if s["unmatched"] else ""),
                  flush=True)
        except Exception as e:  # isolation: one AMC failing must not stop the rest
            failed += 1
            name = getattr(mod, "AMC_NAME", None) or getattr(mod, "__name__", str(mod))
            print(f"  ✗ {name}: {type(e).__name__}: {e}", flush=True)
            traceback.print_exc()
    print(f"Holdings ETL done: {ok} AMC(s) ok, {failed} failed.", flush=True)


if __name__ == "__main__":
    run()
