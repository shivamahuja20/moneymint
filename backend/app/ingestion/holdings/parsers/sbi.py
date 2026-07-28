"""
SBI Mutual Fund holdings parser.

SBI publishes one consolidated workbook/month ("all-schemes-monthly-portfolio")
with an Index sheet + one sheet per scheme. Its host (www.sbimf.com) is reachable,
but its download page is a JS app, so we resolve the latest file's direct URL via
advisorkhoj's index. Layout is the SEBI template with two SBI quirks handled
generically in base.py now: the weight column is "% to AUM" and the statement date
is a date cell beside a "PORTFOLIO STATEMENT AS ON" label (not inline text).
"""
from . import _advisorkhoj

AMC_NAME = "SBI Mutual Fund"        # must equal scheme_master.amc
AMC_SLUG = "sbi"
ADVISORKHOJ_SLUG = "SBI-Mutual-Fund"


def discover():
    files = _advisorkhoj.latest_files(ADVISORKHOJ_SLUG)
    if not files:
        return []
    d, url = files[0]
    return [{"filename": f"SBI_{d.year}_{d.month:02d}.xlsx", "url": url}]
