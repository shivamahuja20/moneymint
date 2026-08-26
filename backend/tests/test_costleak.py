"""Unit tests for app/costleak.py — Direct vs Regular comparison (pure, no DB)."""
import datetime as dt

from app import costleak


def series(days, annual_pct, start=dt.date(2015, 1, 1), nav0=100.0):
    r = (1 + annual_pct / 100) ** (1 / 365.0) - 1
    rows, nav = [], nav0
    for i in range(days):
        rows.append((start + dt.timedelta(days=i), nav))
        nav *= (1 + r)
    return rows


def test_identical_plans_show_no_leak():
    a = series(365 * 5, 12.0)
    out = costleak.cost_leak(a, list(a), amount=100000)
    assert abs(out["leak_rupees"]) < 1
    assert abs(out["drag_pct_per_year"]) < 0.05


def test_regular_lags_direct_by_the_expense_gap():
    d = series(365 * 5, 12.0)          # Direct
    r = series(365 * 5, 11.0)          # Regular, 1%/yr worse
    out = costleak.cost_leak(d, r, amount=100000)
    assert out["direct_cagr"] > out["regular_cagr"]
    assert out["drag_pct_per_year"] == 1.0
    assert out["leak_rupees"] > 0
    # ~1%/yr over 5 years on 1L compounds to roughly ₹8k
    assert 6000 < out["leak_rupees"] < 10000


def test_leak_scales_with_amount():
    d, r = series(365 * 5, 12.0), series(365 * 5, 11.0)
    small = costleak.cost_leak(d, r, amount=100000)["leak_rupees"]
    big = costleak.cost_leak(d, r, amount=1000000)["leak_rupees"]
    assert abs(big / small - 10) < 0.01


def test_window_is_aligned_to_the_shorter_history():
    # Regular started in 2010, Direct only in 2015 — must compare 2015 onward only
    reg = series(365 * 12, 11.0, start=dt.date(2010, 1, 1))
    dir_ = series(365 * 7, 12.0, start=dt.date(2015, 1, 1))
    out = costleak.cost_leak(dir_, reg, amount=100000)
    assert out["start"].startswith("2015")
    assert out["years"] < 7.1


def test_years_argument_trims_to_recent_window():
    d, r = series(365 * 10, 12.0), series(365 * 10, 11.0)
    out = costleak.cost_leak(d, r, amount=100000, years=3)
    assert 2.9 < out["years"] < 3.1


def test_too_little_shared_history_returns_none():
    d = series(200, 12.0, start=dt.date(2020, 1, 1))
    r = series(200, 11.0, start=dt.date(2020, 1, 1))
    assert costleak.cost_leak(d, r) is None


def test_missing_plan_returns_none():
    a = series(365 * 3, 12.0)
    assert costleak.cost_leak(a, []) is None
    assert costleak.cost_leak([], a) is None


def test_common_window_none_when_no_overlap():
    a = series(365 * 2, 12.0, start=dt.date(2010, 1, 1))
    b = series(365 * 2, 12.0, start=dt.date(2020, 1, 1))
    assert costleak.common_window(a, b) is None
