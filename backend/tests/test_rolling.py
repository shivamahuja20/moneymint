"""Unit tests for app/rolling.py — the rolling-returns engine (pure numpy, no DB).

These pin the maths (annualisation, window location) and the honesty guards
(discontinuity exclusion, minimum-window floor).

Run: ./venv/bin/python -m pytest tests/test_rolling.py -v
"""
import datetime as dt

import numpy as np
import pytest

from app import rolling


def series(days, daily_rate=0.0, start=dt.date(2015, 1, 1), start_nav=100.0,
           jump_at=None, jump=0.5):
    """Daily NAV rows compounding at `daily_rate`, optional one-day `jump`."""
    rows, nav = [], start_nav
    for i in range(days):
        rows.append((start + dt.timedelta(days=i), nav))
        nav = nav * (1 + jump) if i == jump_at else nav * (1 + daily_rate)
    return rows


def const_growth(days, annual_pct, **kw):
    """Series growing at a steady `annual_pct` per year (compounded daily)."""
    return series(days, daily_rate=(1 + annual_pct / 100) ** (1 / 365.0) - 1, **kw)


# ---------------------------------------------------------------------------
# core maths
# ---------------------------------------------------------------------------
def test_steady_12pct_gives_12pct_rolling_1y():
    rows = const_growth(365 * 3, 12.0)
    dates, rets = rolling.rolling_series(rows, rolling.WINDOW_DAYS["1Y"])
    assert len(rets) > 500
    assert np.allclose(rets, 12.0, atol=0.05)


def test_three_year_window_is_annualised_not_cumulative():
    # 10%/yr for 6 years: a 3Y window must report ~10 (CAGR), not ~33 (cumulative)
    rows = const_growth(365 * 6, 10.0)
    _, rets = rolling.rolling_series(rows, rolling.WINDOW_DAYS["3Y"])
    assert len(rets) > 300
    assert np.allclose(rets, 10.0, atol=0.05)


def test_sub_year_window_is_absolute_not_annualised():
    # 6M of a 12%/yr fund is ~5.8% absolute, NOT 12%
    rows = const_growth(365 * 2, 12.0)
    _, rets = rolling.rolling_series(rows, rolling.WINDOW_DAYS["6M"])
    assert len(rets) > 100
    assert 5.0 < float(np.median(rets)) < 6.5


def test_flat_nav_gives_zero():
    rows = series(365 * 2, daily_rate=0.0)
    _, rets = rolling.rolling_series(rows, rolling.WINDOW_DAYS["1Y"])
    assert np.allclose(rets, 0.0, atol=1e-6)


def test_start_dates_are_returned_and_ordered():
    rows = const_growth(365 * 2, 10.0)
    dates, rets = rolling.rolling_series(rows, rolling.WINDOW_DAYS["1Y"])
    assert len(dates) == len(rets)
    assert list(dates) == sorted(dates)


def test_history_shorter_than_window_yields_nothing():
    rows = const_growth(200, 10.0)
    dates, rets = rolling.rolling_series(rows, rolling.WINDOW_DAYS["1Y"])
    assert len(dates) == 0 and len(rets) == 0


def test_empty_input_is_safe():
    d, r = rolling.rolling_series([], rolling.WINDOW_DAYS["1Y"])
    assert len(d) == 0 and len(r) == 0


# ---------------------------------------------------------------------------
# honesty guards
# ---------------------------------------------------------------------------
def test_windows_spanning_a_discontinuity_are_excluded():
    # a +50% one-day jump at day 400 must not appear in any 1Y window
    rows = const_growth(365 * 3, 10.0, jump_at=400, jump=0.5)
    _, rets = rolling.rolling_series(rows, rolling.WINDOW_DAYS["1Y"])
    # every surviving window is clean, so all sit at the underlying 10%
    assert len(rets) > 100
    assert rets.max() < 20.0, "a side-pocket jump leaked into a rolling window"
    assert np.allclose(rets, 10.0, atol=0.1)


def test_distribution_needs_enough_windows():
    assert rolling.distribution(np.array([1.0, 2.0, 3.0])) is None
    assert rolling.distribution(np.arange(100.0)) is not None


def test_distribution_stats_are_sane():
    rets = np.array([-5.0] * 25 + [10.0] * 50 + [20.0] * 25)
    d = rolling.distribution(rets)
    assert d["windows"] == 100
    assert d["min"] == -5.0 and d["max"] == 20.0
    assert d["median"] == 10.0
    assert d["pct_negative"] == 25.0
    assert d["pct_above_8"] == 75.0      # the 10s and 20s
    assert d["pct_above_12"] == 25.0     # only the 20s


# ---------------------------------------------------------------------------
# fund vs benchmark
# ---------------------------------------------------------------------------
def test_beat_rate_all_and_none():
    rows_f = const_growth(365 * 3, 15.0)
    rows_b = const_growth(365 * 3, 8.0)
    fd, fr = rolling.rolling_series(rows_f, rolling.WINDOW_DAYS["1Y"])
    bd, br = rolling.rolling_series(rows_b, rolling.WINDOW_DAYS["1Y"])
    assert rolling.beat_rate(fd, fr, bd, br) == 100.0    # fund always ahead
    assert rolling.beat_rate(bd, br, fd, fr) == 0.0      # and never, reversed


def test_beat_rate_none_when_no_overlap():
    rows_f = const_growth(365 * 2, 12.0, start=dt.date(2010, 1, 1))
    rows_b = const_growth(365 * 2, 12.0, start=dt.date(2020, 1, 1))
    fd, fr = rolling.rolling_series(rows_f, rolling.WINDOW_DAYS["1Y"])
    bd, br = rolling.rolling_series(rows_b, rolling.WINDOW_DAYS["1Y"])
    assert rolling.beat_rate(fd, fr, bd, br) is None


# ---------------------------------------------------------------------------
# charting helper
# ---------------------------------------------------------------------------
def test_downsample_caps_points_and_keeps_last():
    rows = const_growth(365 * 5, 10.0)
    dates, rets = rolling.rolling_series(rows, rolling.WINDOW_DAYS["1Y"])
    pts = rolling.downsample(dates, rets, max_points=50)
    assert len(pts) <= 51
    assert pts[-1]["date"] == str(dates[-1])
    assert set(pts[0]) == {"date", "ret"}


def test_downsample_empty():
    assert rolling.downsample(np.array([], dtype="datetime64[D]"), np.array([])) == []
