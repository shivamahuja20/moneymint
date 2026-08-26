"""
Aditya Birla Sun Life Mutual Fund holdings parser.

ABSL publishes a monthly .zip containing one consolidated workbook (one sheet per
scheme, SEBI template — the generic parser reads it unchanged; base.iter_workbooks
unpacks the archive). Their own download page is a JS app, and an older CDN host
(abcscprod.azureedge.net) is unreachable from here, so we resolve the current file
URL via advisorkhoj's index, which points at ABSL's live host.
"""
from . import _advisorkhoj

AMC_NAME = "Aditya Birla Sun Life Mutual Fund"   # must equal scheme_master.amc
AMC_SLUG = "absl"
ADVISORKHOJ_SLUG = "Aditya-Birla-Sun-Life-Mutual-Fund"


def discover():
    files = _advisorkhoj.latest_files(ADVISORKHOJ_SLUG, exts=("zip", "xlsx", "xls"))
    if not files:
        return []
    d, url = files[0]
    ext = "zip" if url.lower().split("?")[0].endswith(".zip") else "xlsx"
    return [{"filename": f"ABSL_{d.year}_{d.month:02d}.{ext}", "url": url}]
