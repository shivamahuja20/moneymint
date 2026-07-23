"""
One-time historical NAV backfill from MFAPI.in (https://api.mfapi.in/mf/{code})
for every scheme in scheme_master.

MFAPI generates each scheme's history on first request (~15-25s cold, cached
after), so a sequential crawl mostly sits waiting on the server. A small pool
of parallel fetch workers overlaps those waits; the effective request rate
stays low (~0.5/sec) and polite. Database writes happen in the main thread.

Resumable: each scheme is committed and marked (backfill_status = 'done' /
'no_data' / 'error') individually, so rerunning skips completed schemes and an
interruption never loses more than the schemes in flight.

Run (background, keeps the Mac awake):
    nohup caffeinate -is ./venv/bin/python -m app.ingestion.backfill_nav >> backfill.log 2>&1 &
"""
import sys
import os
import time
import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import httpx
from psycopg2.extras import execute_values

from app.db import engine, SessionLocal
from app.models import SchemeMaster

MFAPI_URL = "https://api.mfapi.in/mf/{code}"
WORKERS = 10
MAX_RETRIES = 5


def fetch_history(client: httpx.Client, code: str):
    """Returns (code, rows | None) where rows is a list of (date, nav).
    None means the API has no data for this scheme."""
    backoff = 2.0
    for attempt in range(MAX_RETRIES):
        try:
            resp = client.get(MFAPI_URL.format(code=code), timeout=90.0)
            if resp.status_code == 200:
                payload = resp.json()
                rows = []
                for d in payload.get("data", []):
                    try:
                        dt = datetime.datetime.strptime(d["date"], "%d-%m-%Y").date()
                        nav = float(d["nav"])
                    except (KeyError, ValueError):
                        continue
                    if nav > 0:
                        rows.append((dt, nav))
                return code, rows
            if resp.status_code == 404:
                return code, None
            # 429 / 5xx: back off and retry
        except (httpx.HTTPError, ValueError):
            pass
        time.sleep(backoff)
        backoff = min(backoff * 2, 60)
    raise RuntimeError(f"gave up on scheme {code} after {MAX_RETRIES} attempts")


def insert_navs(raw_conn, code: str, rows):
    with raw_conn.cursor() as cur:
        execute_values(
            cur,
            "INSERT INTO nav_history (scheme_code, date, nav) VALUES %s "
            "ON CONFLICT (scheme_code, date) DO NOTHING",
            [(code, d, n) for d, n in rows],
            page_size=2000,
        )
    raw_conn.commit()


def run():
    db = SessionLocal()
    pending = [
        r[0] for r in db.query(SchemeMaster.scheme_code)
        .filter(SchemeMaster.backfill_status.is_(None))
        .order_by(SchemeMaster.scheme_code)
        .all()
    ]
    total = len(pending)
    print(f"[{datetime.datetime.now():%H:%M:%S}] Backfill starting: "
          f"{total} schemes pending, {WORKERS} workers.", flush=True)

    raw_conn = engine.raw_connection()
    client = httpx.Client(headers={"User-Agent": "MoneyMint-personal/1.0"})

    def mark(code, status):
        db.query(SchemeMaster).filter_by(scheme_code=code).update(
            {"backfill_status": status, "backfill_date": datetime.date.today()})
        db.commit()

    done = errors = nav_rows = 0
    started = time.time()
    try:
        with ThreadPoolExecutor(max_workers=WORKERS) as pool:
            futures = {pool.submit(fetch_history, client, c): c for c in pending}
            for i, fut in enumerate(as_completed(futures), 1):
                code = futures[fut]
                try:
                    _, rows = fut.result()
                except RuntimeError as e:
                    print(f"  ERROR {e}", flush=True)
                    mark(code, "error")
                    errors += 1
                    continue
                if rows:
                    insert_navs(raw_conn, code, rows)
                    nav_rows += len(rows)
                    mark(code, "done")
                else:
                    mark(code, "no_data")
                done += 1
                if i % 200 == 0:
                    rate = i / (time.time() - started)
                    eta_min = (total - i) / rate / 60
                    print(f"[{datetime.datetime.now():%H:%M:%S}] {i}/{total} "
                          f"({nav_rows:,} NAV rows, {errors} errors, "
                          f"{rate:.2f}/s, ETA {eta_min:.0f} min)", flush=True)
    finally:
        client.close()
        raw_conn.close()
        db.close()

    print(f"[{datetime.datetime.now():%H:%M:%S}] Backfill finished: {done} schemes, "
          f"{nav_rows:,} NAV rows inserted, {errors} errors.", flush=True)


if __name__ == "__main__":
    run()
