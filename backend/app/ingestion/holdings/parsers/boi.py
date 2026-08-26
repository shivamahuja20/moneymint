"""
Bank of India Mutual Fund holdings parser.

One consolidated workbook per month, one sheet per scheme on the SEBI template.
BOI writes the house name behind a label ("Name of Mutual Fund : ...") on the
first row with the scheme name below it — handled generically by base._AMC_LINE.
File URL resolved via advisorkhoj (BOI's own page is a JS app).
"""
from . import _advisorkhoj

AMC_NAME = "Bank of India Mutual Fund"     # must equal scheme_master.amc
AMC_SLUG = "boi"
ADVISORKHOJ_SLUG = "Bank-of-India-Mutual-Fund"


def discover():
    files = _advisorkhoj.latest_files(ADVISORKHOJ_SLUG, exts=("xlsx", "xls"))
    if not files:
        return []
    d, url = files[0]
    return [{"filename": f"boi_{d.year}_{d.month:02d}.xlsx", "url": url}]
