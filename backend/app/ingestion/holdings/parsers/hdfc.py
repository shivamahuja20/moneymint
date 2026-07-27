"""
HDFC Mutual Fund holdings parser.

HDFC publishes one .xlsx per scheme on an open S3 bucket
(files.hdfcfund.com/s3fs-public/<YYYY-MM>/Monthly <Scheme> - <DD Month YYYY>.xlsx).
The listing page blocks non-browser clients, but the S3 files download fine with a
browser UA — so we reconstruct the latest month's URLs from the known scheme list
(captured once from the listing) rather than scraping the page each run. The runner
skips any file that 404s, so the list can drift without breaking the AMC.

Layout is the standard SEBI template (base.parse_standard_sheet handles it): here
"% to NAV" is a percent (not a fraction) and the date reads "Portfolio as on 30-Jun-2026"
— both handled generically in base.py.
"""
import calendar
import datetime

import httpx

from .. import base

AMC_NAME = "HDFC Mutual Fund"       # must equal scheme_master.amc
AMC_SLUG = "hdfc"
S3 = "https://files.hdfcfund.com/s3fs-public/{folder}/Monthly {name} - {d} {month} {year}.xlsx"

# Scheme names as they appear in HDFC's filenames (captured from the disclosure page).
SCHEMES = [
    "HDFC Arbitrage Fund", "HDFC Balanced Advantage Fund", "HDFC Banking  Financial Services Fund",
    "HDFC Banking and PSU Debt Fund", "HDFC Business Cycle Fund", "HDFC Childrens Fund",
    "HDFC Consumption Fund", "HDFC Corporate Bond Fund", "HDFC Credit Risk Debt Fund",
    "HDFC Defence Fund", "HDFC Dividend Yield Fund", "HDFC Dynamic Debt Fund",
    "HDFC ELSS Tax saver", "HDFC Equity Savings Fund", "HDFC Flexi Cap Fund",
    "HDFC Floating Rate Debt Fund", "HDFC Focused Fund", "HDFC Gilt Fund",
    "HDFC Housing Opportunities Fund", "HDFC Hybrid Debt Fund", "HDFC Hybrid Equity Fund",
    "HDFC Income Fund", "HDFC Infrastructure Fund", "HDFC Innovation Fund",
    "HDFC Large Cap Fund", "HDFC Large and Mid Cap Fund", "HDFC Liquid Fund",
    "HDFC Long Duration Debt Fund", "HDFC Low Duration Fund", "HDFC MNC Fund",
    "HDFC Manufacturing Fund", "HDFC Medium Term Debt Fund", "HDFC Mid Cap Fund",
    "HDFC Money Market Fund", "HDFC Multi Cap Fund", "HDFC Multi-Asset Allocation Fund",
    "HDFC Overnight Fund", "HDFC Pharma and Healthcare Fund",
    "HDFC Retirement Savings Fund - Equity Plan", "HDFC Retirement Savings Fund - Hybrid-Debt Plan",
    "HDFC Retirement Savings Fund - Hybrid-Equity Plan", "HDFC Short Term Debt Fund",
    "HDFC Small Cap Fund", "HDFC Technology Fund", "HDFC Transportation and Logistics Fund",
    "HDFC Ultra Short Term Fund", "HDFC Value Fund",
]


def _candidates():
    """(folder, data_date) for the last two disclosure months. HDFC files a month's
    data in the *next* month's folder (June data -> 2026-07 folder, '30 June 2026')."""
    today = datetime.date.today()
    for back in (0, 1):
        disclosure = (today.replace(day=1) - datetime.timedelta(days=back * 28)).replace(day=1)
        data_month = (disclosure - datetime.timedelta(days=1))  # last day of prior month
        yield disclosure.strftime("%Y-%m"), data_month


def _url(folder, data_date, name):
    return S3.format(folder=folder, name=name, d=data_date.day,
                     month=data_date.strftime("%B"), year=data_date.year)


def discover():
    # pick the most recent month whose files exist (probe one bellwether fund)
    for folder, data_date in _candidates():
        probe = _url(folder, data_date, "HDFC Flexi Cap Fund")
        try:  # S3 rejects HEAD here, so probe with a normal GET
            r = httpx.get(probe, headers={"User-Agent": base.UA}, timeout=30.0,
                          follow_redirects=True)
        except httpx.HTTPError:
            continue
        if r.status_code == 200:
            tag = f"{data_date.year}_{data_date.month:02d}"
            return [{"filename": f"{name}_{tag}.xlsx".replace("/", "-"),
                     "url": _url(folder, data_date, name)} for name in SCHEMES]
    return []
