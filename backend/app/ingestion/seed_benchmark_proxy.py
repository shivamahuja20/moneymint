"""
Seeds benchmark_proxy: maps each equity category to a real index fund whose NAV
(already in nav_history) serves as the benchmark TRI proxy — decision #4 in the
project brief: no licensed index data.

Proxy funds (verified in scheme_master, longest available history):
    120716  UTI Nifty 50 Index Fund - Direct              (history since 2013)
    147625  Motilal Oswal Nifty 500 Index Fund - Direct   (since 2019)
    147622  Motilal Oswal Nifty Midcap 150 Index - Direct (since 2019)
    147623  Motilal Oswal Nifty Smallcap 250 - Direct     (since 2019)

Debt, hybrid, index, FoF and "Other" categories get NO proxy: there is no honest
free proxy for them, so their benchmark stays NULL and the UI shows a gap.

Rerunnable (upsert). Run: ./venv/bin/python -m app.ingestion.seed_benchmark_proxy
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from sqlalchemy.dialects.postgresql import insert

from app.db import engine
from app.models import BenchmarkProxy

NIFTY50 = ("120716", "UTI Nifty 50 Index Fund - Direct")
NIFTY500 = ("147625", "Motilal Oswal Nifty 500 Index Fund - Direct")
MIDCAP150 = ("147622", "Motilal Oswal Nifty Midcap 150 Index Fund - Direct")
SMALLCAP250 = ("147623", "Motilal Oswal Nifty Smallcap 250 Index Fund - Direct")

BROAD_NOTE = "Broad-market reference; free sector/style indices are not available"

# category string in scheme_master -> (proxy, note). AMFI uses both "Scheme" and
# "Schemes" spellings across open/closed-end sections; both are mapped.
MAPPING = {
    "Equity Scheme - Large Cap Fund": (NIFTY50, None),
    "Equity Schemes - Large Cap Fund": (NIFTY50, None),
    "Equity Scheme - Mid Cap Fund": (MIDCAP150, None),
    "Equity Scheme - Small Cap Fund": (SMALLCAP250, None),
    "Equity Schemes - Small Cap Fund": (SMALLCAP250, None),
    "Equity Scheme - Large & Mid Cap Fund": (NIFTY500, BROAD_NOTE),
    "Equity Scheme - Flexi Cap Fund": (NIFTY500, None),
    "Equity Schemes - Flexi Cap Fund": (NIFTY500, None),
    "Equity Scheme - Multi Cap Fund": (NIFTY500, None),
    "Equity Schemes - Multi Cap Fund": (NIFTY500, None),
    "Equity Scheme - ELSS": (NIFTY500, None),
    "Equity Schemes - ELSS- Tax Saver Fund": (NIFTY500, None),
    "Equity Scheme - Focused Fund": (NIFTY500, None),
    "Equity Schemes - Focused Fund": (NIFTY500, None),
    "Equity Scheme - Value Fund": (NIFTY500, None),
    "Equity Schemes - Value Fund": (NIFTY500, None),
    "Equity Scheme - Contra Fund": (NIFTY500, None),
    "Equity Scheme - Dividend Yield Fund": (NIFTY500, None),
    "Equity Scheme - Sectoral/ Thematic": (NIFTY500, BROAD_NOTE),
    "Equity Schemes - Sectoral Fund": (NIFTY500, BROAD_NOTE),
    "Equity Schemes - Thematic Fund": (NIFTY500, BROAD_NOTE),
}


def run():
    rows = [
        {"category": cat, "proxy_scheme_code": proxy[0], "proxy_name": proxy[1], "note": note}
        for cat, (proxy, note) in MAPPING.items()
    ]
    with engine.begin() as conn:
        stmt = insert(BenchmarkProxy).values(rows)
        stmt = stmt.on_conflict_do_update(
            index_elements=["category"],
            set_={
                "proxy_scheme_code": stmt.excluded.proxy_scheme_code,
                "proxy_name": stmt.excluded.proxy_name,
                "note": stmt.excluded.note,
            },
        )
        conn.execute(stmt)
    print(f"benchmark_proxy: {len(rows)} category mappings seeded.")


if __name__ == "__main__":
    run()
