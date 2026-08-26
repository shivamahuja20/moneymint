"""
Bajaj Finserv Mutual Fund holdings parser.

One consolidated workbook per month (one sheet per scheme, SEBI template). Served
as .xls but is a modern xlsx — base.open_workbook reads by content. File URL
resolved via advisorkhoj.
"""
from . import _advisorkhoj

AMC_NAME = "Bajaj Finserv Mutual Fund"     # must equal scheme_master.amc
AMC_SLUG = "bajaj"
ADVISORKHOJ_SLUG = "Bajaj-Finserv-Mutual-Fund"


def discover():
    files = _advisorkhoj.latest_files(ADVISORKHOJ_SLUG, exts=("xlsx", "xls"))
    if not files:
        return []
    d, url = files[0]
    return [{"filename": f"bajaj_{d.year}_{d.month:02d}.xlsx", "url": url}]
