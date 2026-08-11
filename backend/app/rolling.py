"""
Rolling returns — the honest way to read past performance.

A point-to-point return ("5Y = 18%") is one accident of two dates: it tells you
nothing about the ride in between, and it flatters or damns a fund purely on where
the window happens to start. A rolling return instead computes the return for EVERY
possible start date in the history and looks at the whole distribution: the worst
window, the median, how often the fund lost money, how often it beat its benchmark.

Free tools that offer this ration it hard (typically 3-5 funds at a time). We hold
the full daily NAV history for every scheme, so there is no reason to cap it.

Everything here is pure numpy over (dates, navs) — no DB, no I/O — so it is fast
(~5k windows per scheme) and directly unit-testable. The router loads NAV rows.

Honesty rules kept consistent with the rest of the codebase:
  * a window only counts if a real NAV exists at BOTH ends (within a small tolerance
    for weekends/holidays) — we never interpolate a NAV that didn't happen;
  * windows spanning a NAV discontinuity (side-pocket / restatement) are dropped,
    the same >40% single-day guard compute_metrics uses;
  * too few windows -> None rather than a number that looks authoritative.
"""
import datetime
import math

import numpy as np

# windows offered by the API. Sub-year windows report absolute return; >= 1Y annualise.
WINDOW_DAYS = {
    "1M": 30, "3M": 91, "6M": 182,
    "1Y": 365, "2Y": 365 * 2, "3Y": 365 * 3, "5Y": 365 * 5, "7Y": 365 * 7, "10Y": 365 * 10,
}
END_TOLERANCE_DAYS = 7      # the window's far end may land on a weekend/holiday
MIN_WINDOWS = 30            # below this the distribution isn't worth reporting
DISCONTINUITY_PCT = 0.40    # same non-economic NAV jump threshold as compute_metrics


def _as_arrays(rows):
    """rows: [(date, nav)] ascending -> (dates[datetime64[D]], navs[float])."""
    dates = np.array([r[0] for r in rows], dtype="datetime64[D]")
    navs = np.array([float(r[1]) for r in rows], dtype=float)
    return dates, navs


def _discontinuity_mask(navs):
    """True where the NAV step INTO this point is non-economic (side-pocket etc.).
    Index i refers to the move from i-1 to i; index 0 is always False."""
    step = np.empty(len(navs), dtype=bool)
    step[0] = False
    with np.errstate(divide="ignore", invalid="ignore"):
        chg = np.abs(navs[1:] / np.where(navs[:-1] == 0, np.nan, navs[:-1]) - 1.0)
    step[1:] = np.nan_to_num(chg, nan=0.0) > DISCONTINUITY_PCT
    return step


def rolling_series(rows, window_days, tolerance_days=END_TOLERANCE_DAYS):
    """Return (start_dates, returns_pct) for every start date whose window closes.

    Returns are annualised (CAGR) when the window is >= 1 year, else absolute.
    Windows whose span contains a NAV discontinuity are excluded."""
    if not rows or len(rows) < 2:
        return np.array([], dtype="datetime64[D]"), np.array([])
    dates, navs = _as_arrays(rows)

    target = dates + np.timedelta64(int(window_days), "D")
    end_idx = np.searchsorted(dates, target, side="left")

    n = len(dates)
    ok = end_idx < n
    # clamp so the fancy-indexing below is safe; ok[] masks the junk out after
    safe_end = np.where(ok, end_idx, n - 1)

    # the located NAV must be within tolerance of the intended end date
    drift = (dates[safe_end] - target).astype("timedelta64[D]").astype(int)
    ok &= drift <= tolerance_days
    # and both ends must be real, positive NAVs
    ok &= (navs > 0) & (navs[safe_end] > 0)

    # drop any window containing a non-economic jump: cumulative count of bad steps
    # must be identical at both ends of the window
    bad_cum = np.cumsum(_discontinuity_mask(navs))
    ok &= bad_cum[safe_end] == bad_cum

    if not ok.any():
        return np.array([], dtype="datetime64[D]"), np.array([])

    start_d = dates[ok]
    growth = navs[safe_end][ok] / navs[ok]
    span_days = (dates[safe_end][ok] - start_d).astype("timedelta64[D]").astype(float)
    span_days[span_days <= 0] = np.nan

    if window_days >= 365:
        years = span_days / 365.0
        rets = (np.power(growth, 1.0 / years) - 1.0) * 100.0
    else:
        rets = (growth - 1.0) * 100.0

    good = np.isfinite(rets)
    return start_d[good], rets[good]


def distribution(rets, min_windows=MIN_WINDOWS):
    """Summary stats for a rolling-return series. None if too few windows."""
    if rets is None or len(rets) < min_windows:
        return None
    return {
        "windows": int(len(rets)),
        "min": round(float(np.min(rets)), 2),
        "p25": round(float(np.percentile(rets, 25)), 2),
        "median": round(float(np.median(rets)), 2),
        "avg": round(float(np.mean(rets)), 2),
        "p75": round(float(np.percentile(rets, 75)), 2),
        "max": round(float(np.max(rets)), 2),
        # the questions people actually have:
        "pct_negative": round(float((rets < 0).mean() * 100), 1),
        "pct_above_8": round(float((rets >= 8).mean() * 100), 1),
        "pct_above_12": round(float((rets >= 12).mean() * 100), 1),
    }


def beat_rate(fund_dates, fund_rets, bench_dates, bench_rets):
    """% of common start dates where the fund's rolling return beat the benchmark's.
    None if the overlap is too thin to mean anything."""
    if len(fund_dates) == 0 or len(bench_dates) == 0:
        return None
    idx = np.searchsorted(bench_dates, fund_dates)
    idx = np.clip(idx, 0, len(bench_dates) - 1)
    same = bench_dates[idx] == fund_dates
    if same.sum() < MIN_WINDOWS:
        return None
    return round(float((fund_rets[same] > bench_rets[idx][same]).mean() * 100), 1)


def downsample(dates, rets, max_points=400):
    """Evenly thin the series for charting, always keeping the last point."""
    n = len(dates)
    if n == 0:
        return []
    stride = max(1, math.ceil(n / max_points))
    keep = list(range(0, n, stride))
    if keep[-1] != n - 1:
        keep.append(n - 1)
    return [{"date": str(dates[i]), "ret": round(float(rets[i]), 2)} for i in keep]
