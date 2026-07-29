"""
Franklin Templeton Mutual Fund holdings parser.

Franklin publishes one consolidated workbook/month (one sheet per scheme, SEBI
template with ISIN before Name — handled by the label-based column map). Its own
site is a JS app, so we resolve the latest file's direct URL via advisorkhoj's
index (which currently carries Franklin's June-2026 file).
"""
from . import _advisorkhoj

AMC_NAME = "Franklin Templeton Mutual Fund"   # must equal scheme_master.amc
AMC_SLUG = "franklin"
ADVISORKHOJ_SLUG = "Franklin-Templeton-Mutual-Fund"


def discover():
    files = _advisorkhoj.latest_files(ADVISORKHOJ_SLUG)
    if not files:
        return []
    d, url = files[0]
    return [{"filename": f"Franklin_{d.year}_{d.month:02d}.xlsx", "url": url}]
