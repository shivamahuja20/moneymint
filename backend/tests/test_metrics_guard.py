"""Unit tests for the discontinuity guard in app/ingestion/compute_metrics.py.

The SQL passes need a database, but the risk-window guard lives in the pure
numpy helper `window_metrics`: a NAV discontinuity inside the window must make it
return None (an honest "no metric") rather than a garbage stdev/sharpe. These
tests pin that behaviour without a DB.

Run: ./venv/bin/python -m pytest tests/test_metrics_guard.py -v
"""
import datetime as dt

import numpy as np

from app.ingestion import compute_metrics as cm


def _series(n=201, daily=0.001, jump_at=None, jump=0.5, start=dt.date(2020, 1, 1)):
    """n NAV points growing `daily` per day, optionally with one `jump` (fractional
    single-day change) injected at index `jump_at`. Returns (dates, rets, navs)
    already sliced the way compute_scheme_risk feeds window_metrics."""
    rows, nav = [], 100.0
    for i in range(n):
        rows.append((start + dt.timedelta(days=i), nav))
        nav = nav * (1 + jump) if i == jump_at else nav * (1 + daily)
    dates, rets = cm.daily_returns_series(rows)
    navs = np.array([r[1] for r in rows], dtype=float)[1:]
    return dates, rets, navs


def test_clean_window_yields_metrics():
    dates, rets, navs = _series()
    m = cm.window_metrics(dates, rets, navs, dates[0])
    assert m is not None
    assert m["stdev"] >= 0
    assert set(m) >= {"stdev", "sharpe", "max_drawdown", "ann_ret"}


def test_discontinuity_inside_window_is_skipped():
    # a +50% single-day jump (> DISCONTINUITY_PCT) anywhere in the window -> None
    dates, rets, navs = _series(jump_at=100, jump=0.5)
    assert cm.window_metrics(dates, rets, navs, dates[0]) is None


def test_jump_below_threshold_is_kept():
    # a 30% move is under the 40% threshold -> still a real, computable window
    dates, rets, navs = _series(jump_at=100, jump=0.30)
    assert cm.window_metrics(dates, rets, navs, dates[0]) is not None


def test_threshold_boundary_uses_configured_pct():
    # sanity: the guard reads the module constant, not a hardcoded number
    assert 0 < cm.DISCONTINUITY_PCT < 1
    over = cm.DISCONTINUITY_PCT + 0.05
    dates, rets, navs = _series(jump_at=100, jump=over)
    assert cm.window_metrics(dates, rets, navs, dates[0]) is None


def test_too_few_points_yields_none():
    # below MIN_RISK_POINTS the window is statistically meaningless -> None
    dates, rets, navs = _series(n=cm.MIN_RISK_POINTS - 5)
    assert cm.window_metrics(dates, rets, navs, dates[0]) is None
