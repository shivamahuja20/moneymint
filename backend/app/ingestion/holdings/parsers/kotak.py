"""
Kotak Mahindra Mutual Fund holdings parser.

Kotak publishes one consolidated workbook/month (one sheet per scheme). Two Kotak
quirks are handled generically in base.py: the header reads "Name of Instrument"
(no "the") and its Name column is merged/shifted from the data column (names sit
beside the ISIN), and sheet titles read "Portfolio of <fund> as on <date>". We
resolve the latest file's direct URL via advisorkhoj's index.
"""
from . import _advisorkhoj

AMC_NAME = "Kotak Mahindra Mutual Fund"     # must equal scheme_master.amc
AMC_SLUG = "kotak"
ADVISORKHOJ_SLUG = "Kotak-Mahindra-Mutual-Fund"


def discover():
    files = _advisorkhoj.latest_files(ADVISORKHOJ_SLUG)
    if not files:
        return []
    d, url = files[0]
    return [{"filename": f"Kotak_{d.year}_{d.month:02d}.xlsx", "url": url}]
