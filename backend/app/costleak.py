"""
Direct vs Regular: what the commission actually costs, in rupees.

A Regular plan is the same portfolio, same manager, same everything — it just
carries the distributor's commission inside its expense ratio. The gap looks
trivial as a percentage (often ~1%/yr) and enormous as a rupee figure once it
compounds, which is exactly why it is worth showing as money rather than a rate.

We do NOT model the gap from the TER difference. Both plans have their own real
NAV history, so we measure what actually happened: invest the same amount on the
same day in each plan and compare the two ending values. That captures the true
realised drag, not an assumption about it.

Honesty rules:
  * both plans are valued over an IDENTICAL window — the overlap of the two NAV
    series (Direct plans only exist from 2013, so a naive comparison would give
    the Regular plan a longer, different run and produce a meaningless number);
  * a fund with only one plan, or with too little shared history, returns None;
  * the window actually used is reported back, so the number can be checked.

Pure functions over [(date, nav)] rows — no DB, no I/O.
"""
import datetime
from bisect import bisect_left

MIN_DAYS = 365          # below a year the compounding story isn't meaningful


def _nav_on_or_after(rows, dates, target):
    i = bisect_left(dates, target)
    return rows[i] if i < len(rows) else None


def common_window(direct_rows, regular_rows, years=None):
    """The date range over which BOTH plans have real NAVs.
    Optionally trimmed to the most recent `years`. None if too short."""
    if not direct_rows or not regular_rows:
        return None
    start = max(direct_rows[0][0], regular_rows[0][0])
    end = min(direct_rows[-1][0], regular_rows[-1][0])
    if years:
        trimmed = end - datetime.timedelta(days=int(round(years * 365)))
        start = max(start, trimmed)
    if (end - start).days < MIN_DAYS:
        return None
    return start, end


def _grow(rows, amount, start, end):
    """Value of `amount` invested at the first NAV on/after `start`, valued at `end`.
    Returns (value, buy_date, buy_nav, end_nav) or None."""
    dates = [d for d, _ in rows]
    a = _nav_on_or_after(rows, dates, start)
    b = _nav_on_or_after(rows, dates, end)
    if b is None:                      # end may fall past the last row
        b = rows[-1]
    if a is None or a[1] <= 0:
        return None
    units = amount / a[1]
    return units * b[1], a[0], a[1], b[1]


def cost_leak(direct_rows, regular_rows, amount=500000.0, years=None):
    """Compare the same investment in a fund's Direct and Regular plans over the
    same window, using each plan's real NAVs. Returns None if not comparable."""
    win = common_window(direct_rows, regular_rows, years)
    if not win:
        return None
    start, end = win
    d = _grow(direct_rows, amount, start, end)
    r = _grow(regular_rows, amount, start, end)
    if not d or not r:
        return None
    d_val, buy_date, _, _ = d
    r_val = r[0]
    span_years = max((end - buy_date).days / 365.0, 1e-9)

    def cagr(v):
        return (pow(v / amount, 1 / span_years) - 1) * 100

    leak = d_val - r_val
    return {
        "amount": round(amount, 2),
        "start": buy_date.isoformat(),
        "end": end.isoformat(),
        "years": round(span_years, 2),
        "direct_value": round(d_val, 2),
        "regular_value": round(r_val, 2),
        "direct_cagr": round(cagr(d_val), 2),
        "regular_cagr": round(cagr(r_val), 2),
        # what the commission cost, in money and as a share of what you put in
        "leak_rupees": round(leak, 2),
        "leak_pct_of_investment": round(leak / amount * 100, 2),
        # the same drag expressed as an annual rate, derived from the two CAGRs
        "drag_pct_per_year": round(cagr(d_val) - cagr(r_val), 2),
    }
