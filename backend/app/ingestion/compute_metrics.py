"""
Nightly analytics engine: computes scheme_returns, scheme_risk and category_stats
for ALL schemes from nav_history, then wires real benchmark / category numbers
into the legacy fund_returns table the 10-fund frontend reads.

All outputs are rebuild-safe (delete + rewrite inside one transaction per pass);
nothing here is ever hand-edited.

Run: ./venv/bin/python -m app.ingestion.compute_metrics
"""
import sys
import os
import time
import datetime
import math

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import numpy as np
from sqlalchemy import text

from app.db import engine, SessionLocal

PERIODS_DAYS = {
    "1M": 30, "3M": 91, "6M": 182,
    "1Y": 365, "3Y": 365 * 3, "5Y": 365 * 5, "10Y": 365 * 10,
}
PAST_NAV_TOLERANCE_DAYS = 14   # past NAV must exist within this window before cutoff
RISK_FREE_RATE = 6.5           # % p.a.; approximates recent RBI 91-day T-bill yields
RISK_WINDOWS = {"1Y": 365, "3Y": 365 * 3}
TRADING_DAYS = 252
MIN_RISK_POINTS = 150          # need at least ~7 months of daily NAVs for 1Y risk
BETA_MIN_OVERLAP = 0.9         # fund/proxy return series must overlap >= 90% of window


# ---------------------------------------------------------------------------
# Pass a: point-to-point returns for every scheme, set-based SQL
# ---------------------------------------------------------------------------

RETURNS_SQL = """
WITH latest AS (
    SELECT DISTINCT ON (scheme_code) scheme_code, date, nav
    FROM nav_history
    ORDER BY scheme_code, date DESC
)
INSERT INTO scheme_returns (scheme_code, period, ret, as_of_date)
SELECT l.scheme_code, :period,
       CASE WHEN :years >= 3
            THEN round((power((l.nav / p.nav)::numeric, 1.0 / :years) - 1) * 100, 2)
            ELSE round(((l.nav - p.nav) / p.nav * 100)::numeric, 2)
       END,
       l.date
FROM latest l
CROSS JOIN LATERAL (
    SELECT nav, date FROM nav_history h
    WHERE h.scheme_code = l.scheme_code
      AND h.date <= l.date - make_interval(days => :days)
      AND h.date >  l.date - make_interval(days => :days + :tolerance)
    ORDER BY h.date DESC LIMIT 1
) p
WHERE p.nav > 0
"""


def compute_scheme_returns(conn) -> int:
    conn.execute(text("DELETE FROM scheme_returns"))
    total = 0
    for period, days in PERIODS_DAYS.items():
        res = conn.execute(text(RETURNS_SQL), {
            "period": period, "days": days, "years": days // 365,
            "tolerance": PAST_NAV_TOLERANCE_DAYS,
        })
        total += res.rowcount
    return total


# ---------------------------------------------------------------------------
# Pass b: risk metrics per scheme (numpy on daily NAV series)
# ---------------------------------------------------------------------------

def daily_returns_series(rows):
    """rows: [(date, nav)] ascending -> (dates[1:], simple daily returns)."""
    navs = np.array([r[1] for r in rows], dtype=float)
    rets = navs[1:] / navs[:-1] - 1.0
    return [r[0] for r in rows[1:]], rets


def window_metrics(dates, rets, navs, start_date):
    """stdev (ann. %), sharpe, max_drawdown (%) for the slice from start_date on.
    Returns None if too few points."""
    idx = np.searchsorted(np.array(dates, dtype="datetime64[D]"),
                          np.datetime64(start_date))
    r = rets[idx:]
    n = navs[idx:]
    if len(r) < MIN_RISK_POINTS:
        return None
    stdev = float(np.std(r, ddof=1) * math.sqrt(TRADING_DAYS) * 100)
    years = len(r) / TRADING_DAYS
    total_growth = n[-1] / n[0]
    ann_ret = (total_growth ** (1 / years) - 1) * 100
    sharpe = (ann_ret - RISK_FREE_RATE) / stdev if stdev > 0 else None
    peak = np.maximum.accumulate(n)
    max_dd = float(((n / peak) - 1.0).min() * 100)
    return {"stdev": round(stdev, 2),
            "sharpe": round(float(sharpe), 2) if sharpe is not None else None,
            "max_drawdown": round(max_dd, 2),
            "ann_ret": ann_ret,
            "idx": idx}


def beta_alpha(f_dates, f_rets, p_map, start_date, f_ann_ret, p_series_metrics):
    """Beta/alpha of fund vs proxy over the window; None if overlap too thin."""
    pairs = [(fr, p_map[d]) for d, fr in zip(f_dates, f_rets)
             if d >= start_date and d in p_map]
    if not pairs:
        return None, None
    window_len = sum(1 for d in f_dates if d >= start_date)
    if window_len == 0 or len(pairs) / window_len < BETA_MIN_OVERLAP or len(pairs) < MIN_RISK_POINTS:
        return None, None
    f = np.array([p[0] for p in pairs])
    b = np.array([p[1] for p in pairs])
    var_b = np.var(b, ddof=1)
    if var_b <= 0:
        return None, None
    beta = float(np.cov(f, b, ddof=1)[0, 1] / var_b)
    p_ann_ret = p_series_metrics["ann_ret"]
    alpha = float(f_ann_ret - (RISK_FREE_RATE + beta * (p_ann_ret - RISK_FREE_RATE)))
    return round(beta, 2), round(alpha, 2)


def compute_scheme_risk(conn) -> int:
    today = datetime.date.today()
    fetch_from = today - datetime.timedelta(days=RISK_WINDOWS["3Y"] + 60)

    proxies = {r.category: r.proxy_scheme_code for r in
               conn.execute(text("SELECT category, proxy_scheme_code FROM benchmark_proxy"))}

    # preload each distinct proxy's return series and per-window metrics
    proxy_data = {}
    for code in set(proxies.values()):
        rows = conn.execute(text(
            "SELECT date, nav FROM nav_history WHERE scheme_code=:c AND date>=:d ORDER BY date"
        ), {"c": code, "d": fetch_from}).all()
        if len(rows) < MIN_RISK_POINTS:
            continue
        dates, rets = daily_returns_series(rows)
        navs = np.array([r[1] for r in rows], dtype=float)[1:]
        per_window = {}
        for w, wdays in RISK_WINDOWS.items():
            m = window_metrics(dates, rets, navs, today - datetime.timedelta(days=wdays))
            if m:
                per_window[w] = m
        proxy_data[code] = {"map": dict(zip(dates, rets)), "windows": per_window}

    schemes = conn.execute(text(
        "SELECT scheme_code, category FROM scheme_master WHERE backfill_status='done'"
    )).all()

    conn.execute(text("DELETE FROM scheme_risk"))
    inserted = 0
    batch = []
    for scheme_code, category in schemes:
        rows = conn.execute(text(
            "SELECT date, nav FROM nav_history WHERE scheme_code=:c AND date>=:d ORDER BY date"
        ), {"c": scheme_code, "d": fetch_from}).all()
        if len(rows) <= MIN_RISK_POINTS:
            continue
        dates, rets = daily_returns_series(rows)
        navs = np.array([r[1] for r in rows], dtype=float)[1:]

        pcode = proxies.get(category)
        pdata = proxy_data.get(pcode) if pcode else None

        for w, wdays in RISK_WINDOWS.items():
            start = datetime.date.today() - datetime.timedelta(days=wdays)
            m = window_metrics(dates, rets, navs, start)
            if not m:
                continue
            beta = alpha = None
            if pdata and w in pdata["windows"] and scheme_code != pcode:
                beta, alpha = beta_alpha(dates, rets, pdata["map"], start,
                                         m["ann_ret"], pdata["windows"][w])
            batch.append({
                "scheme_code": scheme_code, "period": w, "stdev": m["stdev"],
                "sharpe": m["sharpe"], "beta": beta, "alpha": alpha,
                "max_drawdown": m["max_drawdown"], "as_of_date": datetime.date.today(),
            })
            inserted += 1
        if len(batch) >= 2000:
            conn.execute(text(
                "INSERT INTO scheme_risk (scheme_code, period, stdev, sharpe, beta, alpha, max_drawdown, as_of_date) "
                "VALUES (:scheme_code, :period, :stdev, :sharpe, :beta, :alpha, :max_drawdown, :as_of_date)"
            ), batch)
            batch = []
    if batch:
        conn.execute(text(
            "INSERT INTO scheme_risk (scheme_code, period, stdev, sharpe, beta, alpha, max_drawdown, as_of_date) "
            "VALUES (:scheme_code, :period, :stdev, :sharpe, :beta, :alpha, :max_drawdown, :as_of_date)"
        ), batch)
    return inserted


# ---------------------------------------------------------------------------
# Pass c: category averages + legacy fund_returns wiring
# ---------------------------------------------------------------------------

def compute_category_stats(conn) -> int:
    conn.execute(text("DELETE FROM category_stats"))
    res = conn.execute(text("""
        INSERT INTO category_stats (category, period, avg_return, median_return, scheme_count, as_of_date)
        SELECT m.category, r.period,
               round(avg(r.ret)::numeric, 2),
               round((percentile_cont(0.5) WITHIN GROUP (ORDER BY r.ret))::numeric, 2),
               count(*), max(r.as_of_date)
        FROM scheme_returns r
        JOIN scheme_master m ON m.scheme_code = r.scheme_code
        WHERE m.category IS NOT NULL
        GROUP BY m.category, r.period
    """))
    return res.rowcount


def wire_legacy_fund_returns(conn) -> int:
    """Rebuild fund_returns for the 10 frontend funds entirely from real data:
    fund_return from scheme_returns, benchmark from the category proxy's
    scheme_returns, category average from category_stats."""
    conn.execute(text("DELETE FROM fund_returns"))
    res = conn.execute(text("""
        INSERT INTO fund_returns (fund_id, period, fund_return, benchmark_return, category_avg_return, as_of_date)
        SELECT f.id, r.period, r.ret,
               coalesce(pr.ret, 0.0),
               coalesce(cs.avg_return, 0.0),
               r.as_of_date
        FROM funds f
        JOIN scheme_master m  ON m.scheme_code = f.amfi_code
        JOIN scheme_returns r ON r.scheme_code = f.amfi_code
        LEFT JOIN benchmark_proxy bp ON bp.category = m.category
        LEFT JOIN scheme_returns pr  ON pr.scheme_code = bp.proxy_scheme_code AND pr.period = r.period
        LEFT JOIN category_stats cs  ON cs.category = m.category AND cs.period = r.period
        WHERE r.period IN ('1M', '6M', '1Y', '3Y', '5Y')
    """))
    return res.rowcount


def run():
    started = time.time()
    with engine.begin() as conn:
        n_ret = compute_scheme_returns(conn)
        print(f"scheme_returns: {n_ret:,} rows.")
    with engine.begin() as conn:
        n_risk = compute_scheme_risk(conn)
        print(f"scheme_risk: {n_risk:,} rows.")
    with engine.begin() as conn:
        n_cat = compute_category_stats(conn)
        n_legacy = wire_legacy_fund_returns(conn)
        print(f"category_stats: {n_cat:,} rows. fund_returns rebuilt: {n_legacy} rows.")
    print(f"Metrics engine done in {time.time() - started:.0f}s.")


if __name__ == "__main__":
    run()
