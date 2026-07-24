"""
Phase 7 calculators: historical backtests (over real nav_history) and forward
projections, plus an Indian mutual-fund taxation estimate.

This is an illustrative calculator, NOT financial advice. Tax rules are encoded
with dated constants (current regime as of FY2025-26) and every result carries
the assumptions it applied so the UI can show and let the user override them.

All functions are pure (no DB access) so they are trivially testable; the router
loads NAV rows and passes them in.
"""
import datetime
from bisect import bisect_left

# --- taxation constants (India, FY2025-26; update if the law changes) ---------
EQUITY_STCG_RATE = 0.20          # <12m holding, Sec 111A (rate eff. 23-Jul-2024)
EQUITY_LTCG_RATE = 0.125         # >=12m holding, Sec 112A
EQUITY_LTCG_EXEMPTION = 125000.0  # per financial year, Sec 112A
EQUITY_LTCG_MIN_DAYS = 365
DEFAULT_MARGINAL_RATE = 0.30     # slab rate assumed for non-equity gains
TAX_REGIME_NOTE = "India FY2025-26 rules; illustrative estimate, not tax advice."

MONTHS_PER_YEAR = 12


# ---------------------------------------------------------------------------
# XIRR (annualised money-weighted return for dated cashflows)
# ---------------------------------------------------------------------------
def xirr(cashflows, guess=0.1):
    """cashflows: list of (date, amount); investments negative, redemption positive.
    Returns annualised rate as a decimal, or None if it doesn't converge."""
    if len(cashflows) < 2:
        return None
    t0 = cashflows[0][0]
    years = [(d - t0).days / 365.0 for d, _ in cashflows]
    amts = [a for _, a in cashflows]
    if not (any(a < 0 for a in amts) and any(a > 0 for a in amts)):
        return None

    rate = guess
    for _ in range(100):
        f = fp = 0.0
        for a, t in zip(amts, years):
            base = 1.0 + rate
            if base <= 0:
                return None
            f += a / base ** t
            fp += -t * a / base ** (t + 1)
        if abs(fp) < 1e-12:
            break
        new = rate - f / fp
        if abs(new - rate) < 1e-8:
            return round(new, 6)
        rate = new
    return None


# ---------------------------------------------------------------------------
# NAV helpers — nav_rows is a list of (date, nav) ascending by date
# ---------------------------------------------------------------------------
def _nav_on_or_after(nav_rows, dates, target):
    i = bisect_left(dates, target)
    return nav_rows[i] if i < len(nav_rows) else None


def _installment_dates(start, end, freq):
    step = {"monthly": 1, "quarterly": 3}.get(freq, 1)
    out, d = [], start
    while d <= end:
        out.append(d)
        # advance by `step` months, clamping day to 28 to stay valid
        m = d.month - 1 + step
        y = d.year + m // 12
        d = datetime.date(y, m % 12 + 1, min(d.day, 28))
    return out


# ---------------------------------------------------------------------------
# Backtests (real NAVs)
# ---------------------------------------------------------------------------
def backtest_sip(nav_rows, amount, start, end=None, freq="monthly"):
    """Simulate a SIP of `amount` each period from start..end using actual NAVs."""
    dates = [d for d, _ in nav_rows]
    latest_date, latest_nav = nav_rows[-1]
    if end is None or end > latest_date:
        end = latest_date

    units = invested = 0.0
    cashflows = []
    series = []
    for dt in _installment_dates(start, end, freq):
        row = _nav_on_or_after(nav_rows, dates, dt)
        if not row:
            break
        buy_date, nav = row
        bought = amount / nav
        units += bought
        invested += amount
        cashflows.append((buy_date, -amount))
        series.append({"date": buy_date.isoformat(), "invested": round(invested, 2),
                       "value": round(units * nav, 2)})

    if invested == 0:
        return None
    current_value = units * latest_nav
    cashflows.append((latest_date, current_value))
    gain = current_value - invested
    return {
        "mode": "sip", "invested": round(invested, 2), "units": round(units, 4),
        "current_value": round(current_value, 2), "gain": round(gain, 2),
        "absolute_return_pct": round(gain / invested * 100, 2),
        "xirr_pct": (lambda r: round(r * 100, 2) if r is not None else None)(xirr(cashflows)),
        "start": start.isoformat(), "end": latest_date.isoformat(),
        "series": series,
    }


def backtest_lumpsum(nav_rows, amount, start, end=None):
    dates = [d for d, _ in nav_rows]
    latest_date, latest_nav = nav_rows[-1]
    if end is None or end > latest_date:
        end = latest_date
    start_row = _nav_on_or_after(nav_rows, dates, start)
    if not start_row:
        return None
    buy_date, buy_nav = start_row
    units = amount / buy_nav
    current_value = units * latest_nav
    gain = current_value - amount
    years = max((latest_date - buy_date).days / 365.0, 1e-9)
    cagr = ((current_value / amount) ** (1 / years) - 1) * 100
    # sparse value series (month-stride) for the chart
    series, seen = [], set()
    for d, nav in nav_rows:
        if d < buy_date:
            continue
        key = (d.year, d.month)
        if key in seen:
            continue
        seen.add(key)
        series.append({"date": d.isoformat(), "invested": round(amount, 2),
                       "value": round(units * nav, 2)})
    return {
        "mode": "lumpsum", "invested": round(amount, 2), "units": round(units, 4),
        "current_value": round(current_value, 2), "gain": round(gain, 2),
        "absolute_return_pct": round(gain / amount * 100, 2),
        "cagr_pct": round(cagr, 2),
        "start": buy_date.isoformat(), "end": latest_date.isoformat(),
        "series": series,
    }


# ---------------------------------------------------------------------------
# Forward projections (pure math; assumption-based)
# ---------------------------------------------------------------------------
def project_lumpsum(amount, years, annual_rate):
    fv = amount * (1 + annual_rate / 100) ** years
    return {"mode": "lumpsum", "invested": round(amount, 2),
            "future_value": round(fv, 2), "gain": round(fv - amount, 2)}


def project_sip(amount, years, annual_rate):
    n = int(round(years * MONTHS_PER_YEAR))
    r = annual_rate / 100 / MONTHS_PER_YEAR
    # future value of an annuity-due (invest at start of each month)
    fv = amount * (((1 + r) ** n - 1) / r) * (1 + r) if r else amount * n
    invested = amount * n
    return {"mode": "sip", "months": n, "invested": round(invested, 2),
            "future_value": round(fv, 2), "gain": round(fv - invested, 2)}


def project_goal(target, years, annual_rate):
    """Monthly SIP needed to reach `target` in `years` at `annual_rate`."""
    n = int(round(years * MONTHS_PER_YEAR))
    r = annual_rate / 100 / MONTHS_PER_YEAR
    monthly = target / n if not r else target / ((((1 + r) ** n - 1) / r) * (1 + r))
    return {"mode": "goal", "target": round(target, 2), "months": n,
            "monthly_sip": round(monthly, 2), "total_invested": round(monthly * n, 2)}


def project_swp(corpus, monthly_withdrawal, annual_rate, max_years=60):
    """How long `corpus` lasts under a fixed monthly withdrawal; schedule of yearly balances."""
    r = annual_rate / 100 / MONTHS_PER_YEAR
    bal = corpus
    months = 0
    schedule = []
    limit = max_years * MONTHS_PER_YEAR
    while bal > 0 and months < limit:
        bal = bal * (1 + r) - monthly_withdrawal
        months += 1
        if months % 12 == 0:
            schedule.append({"year": months // 12, "balance": round(max(bal, 0), 2)})
    depleted = bal <= 0 and months < limit
    return {"mode": "swp", "corpus": round(corpus, 2),
            "monthly_withdrawal": round(monthly_withdrawal, 2),
            "lasts_months": months if depleted else None,
            "sustained": not depleted,   # withdrawal <= growth, corpus never runs out
            "schedule": schedule}


# ---------------------------------------------------------------------------
# Taxation
# ---------------------------------------------------------------------------
_EQUITY_KEYS = ("equity", "elss", "tax saver", "aggressive hybrid", "arbitrage",
                "balanced advantage", "dynamic asset", "multi asset", "equity savings")
_NONEQUITY_KEYS = ("debt", "gilt", "liquid", "overnight", "money market", "income",
                   "conservative hybrid", "gold", "silver", "fof overseas",
                   "overseas", "banking and psu", "corporate bond", "credit risk",
                   "floater", "duration")


def classify_tax(category, name=""):
    """'equity' (equity-oriented, >=65% equity) or 'non_equity' (debt/gold/intl).
    Best-effort from category + name; the UI shows and can override this."""
    text = f"{category or ''} {name or ''}".lower()
    # explicit debt/gold/intl signals win over a generic 'index/etf' label
    if any(k in text for k in _NONEQUITY_KEYS):
        # ...unless it's clearly an equity index/ETF (e.g. "Nifty 50 Index")
        if ("index" in text or "etf" in text) and any(
                k in text for k in ("nifty", "sensex", "bse", "midcap", "smallcap", "next 50")):
            return "equity"
        return "non_equity"
    if any(k in text for k in _EQUITY_KEYS):
        return "equity"
    if "index" in text or "etf" in text:  # equity index/ETF by default
        return "equity"
    return "equity"  # safest default for unlabeled equity-scheme families


def estimate_tax(gain, holding_days, tax_class, marginal_rate=DEFAULT_MARGINAL_RATE):
    """Tax on `gain` (INR) given holding period and class. Returns tax + assumptions."""
    assumptions = [TAX_REGIME_NOTE]
    if gain <= 0:
        return {"tax": 0.0, "effective_rate_pct": 0.0, "tax_class": tax_class,
                "gain_type": "none", "assumptions": assumptions + ["No gain, no tax."]}

    if tax_class == "equity":
        if holding_days is not None and holding_days < EQUITY_LTCG_MIN_DAYS:
            tax = gain * EQUITY_STCG_RATE
            gain_type = "STCG"
            assumptions.append(f"Equity STCG at {EQUITY_STCG_RATE*100:.0f}% (held < 12 months).")
        else:
            taxable = max(0.0, gain - EQUITY_LTCG_EXEMPTION)
            tax = taxable * EQUITY_LTCG_RATE
            gain_type = "LTCG"
            assumptions.append(
                f"Equity LTCG at {EQUITY_LTCG_RATE*100:.1f}% above "
                f"₹{EQUITY_LTCG_EXEMPTION:,.0f}/yr exemption.")
    else:
        tax = gain * marginal_rate
        gain_type = "slab"
        assumptions.append(
            f"Non-equity gain taxed at your slab rate ({marginal_rate*100:.0f}% assumed); "
            "post-Apr-2023 units, no indexation/LTCG benefit.")

    return {"tax": round(tax, 2), "effective_rate_pct": round(tax / gain * 100, 2),
            "tax_class": tax_class, "gain_type": gain_type, "assumptions": assumptions}
