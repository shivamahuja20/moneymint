"""Unit tests for app/calc.py — the money math (XIRR, backtests, projections,
taxation). All pure functions, no DB. These are the numbers a user acts on, so
they get the tightest coverage in the project.

Run: ./venv/bin/python -m pytest tests/test_calc.py -v
"""
import datetime as dt

import pytest

from app import calc


# ---------------------------------------------------------------------------
# XIRR
# ---------------------------------------------------------------------------
def test_xirr_simple_ten_percent():
    # -1000 today, +1100 exactly one (non-leap) year later -> 10% annualised
    r = calc.xirr([(dt.date(2021, 1, 1), -1000), (dt.date(2022, 1, 1), 1100)])
    assert r == pytest.approx(0.10, abs=1e-4)


def test_xirr_loss():
    r = calc.xirr([(dt.date(2021, 1, 1), -1000), (dt.date(2022, 1, 1), 900)])
    assert r == pytest.approx(-0.10, abs=1e-4)


def test_xirr_needs_two_flows():
    assert calc.xirr([(dt.date(2021, 1, 1), -1000)]) is None


def test_xirr_needs_a_sign_change():
    # all outflows -> no rate can make NPV zero
    assert calc.xirr([(dt.date(2021, 1, 1), -1000),
                      (dt.date(2022, 1, 1), -500)]) is None


# ---------------------------------------------------------------------------
# Forward projections
# ---------------------------------------------------------------------------
def test_project_lumpsum_compounding():
    out = calc.project_lumpsum(100000, 10, 12)
    assert out["future_value"] == pytest.approx(310584.82, abs=0.01)
    assert out["gain"] == pytest.approx(210584.82, abs=0.01)


def test_project_sip_annuity_due():
    out = calc.project_sip(10000, 1, 12)
    assert out["months"] == 12
    assert out["invested"] == 120000
    assert out["future_value"] == pytest.approx(128093.28, abs=0.5)


def test_project_sip_zero_rate():
    out = calc.project_sip(1000, 1, 0)
    assert out["future_value"] == 12000
    assert out["gain"] == 0


def test_project_goal_roundtrips_through_sip():
    # the monthly SIP goal returns should, fed back into project_sip, reach target
    target, years, rate = 1_200_000, 10, 12
    monthly = calc.project_goal(target, years, rate)["monthly_sip"]
    fv = calc.project_sip(monthly, years, rate)["future_value"]
    assert fv == pytest.approx(target, rel=1e-3)


def test_project_swp_sustained_when_growth_exceeds_withdrawal():
    # 12% p.a. on 12L = ~12k/mo interest > 10k withdrawal -> never depletes
    out = calc.project_swp(1_200_000, 10000, 12)
    assert out["sustained"] is True
    assert out["lasts_months"] is None


def test_project_swp_depletes_with_zero_growth():
    out = calc.project_swp(100000, 10000, 0)
    assert out["sustained"] is False
    assert out["lasts_months"] == 10


# ---------------------------------------------------------------------------
# Installment date generation (SIP schedule, day clamped to 28)
# ---------------------------------------------------------------------------
def test_installment_dates_clamp_to_28():
    out = calc._installment_dates(dt.date(2020, 1, 31), dt.date(2020, 4, 30), "monthly")
    assert out == [dt.date(2020, 1, 31), dt.date(2020, 2, 28),
                   dt.date(2020, 3, 28), dt.date(2020, 4, 28)]


def test_installment_dates_quarterly_step():
    out = calc._installment_dates(dt.date(2020, 1, 15), dt.date(2020, 12, 31), "quarterly")
    assert out == [dt.date(2020, 1, 15), dt.date(2020, 4, 15),
                   dt.date(2020, 7, 15), dt.date(2020, 10, 15)]


# ---------------------------------------------------------------------------
# Backtests over real NAV series (synthetic deterministic NAVs here)
# ---------------------------------------------------------------------------
def _flat_navs(days, value=100.0, start=dt.date(2020, 1, 1)):
    return [(start + dt.timedelta(days=i), value) for i in range(days)]


def test_backtest_lumpsum_flat_nav_zero_gain():
    out = calc.backtest_lumpsum(_flat_navs(400), 100000, dt.date(2020, 1, 1))
    assert out["gain"] == 0.0
    assert out["absolute_return_pct"] == 0.0
    assert out["units"] == pytest.approx(1000.0)


def test_backtest_lumpsum_doubling():
    navs = [(dt.date(2019, 1, 1), 100.0), (dt.date(2020, 1, 1), 150.0),
            (dt.date(2021, 1, 1), 200.0)]
    out = calc.backtest_lumpsum(navs, 100000, dt.date(2019, 1, 1))
    assert out["absolute_return_pct"] == 100.0
    assert out["current_value"] == pytest.approx(200000.0)
    assert out["cagr_pct"] == pytest.approx(41.35, abs=0.1)


def test_backtest_sip_flat_nav_zero_gain():
    out = calc.backtest_sip(_flat_navs(400), 10000, dt.date(2020, 1, 1))
    assert out["absolute_return_pct"] == 0.0
    assert out["xirr_pct"] is not None and abs(out["xirr_pct"]) < 1.0


def test_backtest_lumpsum_before_history_returns_none():
    # start after the last NAV -> nothing to simulate
    navs = _flat_navs(10)
    assert calc.backtest_lumpsum(navs, 1000, dt.date(2025, 1, 1)) is None


# ---------------------------------------------------------------------------
# Tax classification
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("category,name,expected", [
    ("Equity Scheme - Flexi Cap Fund", "", "equity"),
    ("Equity Scheme - ELSS", "Axis Long Term Equity", "equity"),
    ("Debt Scheme - Liquid Fund", "", "non_equity"),
    ("Debt Scheme - Gilt Fund", "", "non_equity"),
    ("Other Scheme - Gold ETF", "Nippon Gold ETF", "non_equity"),
    ("Index Fund", "SBI Nifty 50 Index Fund", "equity"),   # equity index beats 'index'
    ("Other Scheme - FoF Overseas", "Motilal Nasdaq 100 FoF", "non_equity"),
])
def test_classify_tax(category, name, expected):
    assert calc.classify_tax(category, name) == expected


# ---------------------------------------------------------------------------
# Taxation estimate
# ---------------------------------------------------------------------------
def test_tax_no_gain_no_tax():
    out = calc.estimate_tax(-5000, 400, "equity")
    assert out["tax"] == 0.0
    assert out["gain_type"] == "none"


def test_tax_equity_stcg():
    # held < 12 months -> 20% flat, no exemption
    out = calc.estimate_tax(200000, 100, "equity")
    assert out["gain_type"] == "STCG"
    assert out["tax"] == pytest.approx(40000.0)


def test_tax_equity_ltcg_above_exemption():
    # held >= 12 months -> 12.5% on gain above 1.25L exemption
    out = calc.estimate_tax(200000, 400, "equity")
    assert out["gain_type"] == "LTCG"
    assert out["tax"] == pytest.approx((200000 - 125000) * 0.125)  # 9375


def test_tax_equity_ltcg_within_exemption_is_zero():
    out = calc.estimate_tax(100000, 400, "equity")
    assert out["gain_type"] == "LTCG"
    assert out["tax"] == 0.0


def test_tax_equity_unknown_holding_defaults_to_ltcg():
    out = calc.estimate_tax(200000, None, "equity")
    assert out["gain_type"] == "LTCG"


def test_tax_non_equity_uses_slab_rate():
    out = calc.estimate_tax(100000, 400, "non_equity", marginal_rate=0.30)
    assert out["gain_type"] == "slab"
    assert out["tax"] == pytest.approx(30000.0)
