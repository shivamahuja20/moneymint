"""
PPFAS Mutual Fund holdings parser.

PPFAS publishes one .xlsx per scheme per month on a server-rendered listing page,
so we auto-discover the latest month's per-fund files (no hardcoded URLs) and let
the generic SEBI-template parser in base.py read each. Layout confirmed against the
June 2026 PPFCF file: standard Name/ISIN/Industry/Qty/Market Value/% to NAV columns.
"""
import re

import httpx

from .. import base

AMC_NAME = "PPFAS Mutual Fund"       # must equal scheme_master.amc
AMC_SLUG = "ppfas"
LISTING_URL = "https://amc.ppfas.com/downloads/portfolio-disclosure/"

_LINK_RE = re.compile(
    r'href="(/downloads/portfolio-disclosure/(\d{4})/([A-Z]+)_PPFAS_Monthly_Portfolio_Report'
    r'_([A-Za-z]+)_(\d{1,2})_(\d{4})\.xlsx[^"]*)"', re.I)
_MONTHS = {m: i for i, m in enumerate(
    ["January", "February", "March", "April", "May", "June", "July",
     "August", "September", "October", "November", "December"], 1)}


def discover():
    """Return [{filename, url}] for every per-fund .xlsx of the most recent month."""
    resp = httpx.get(LISTING_URL, headers={"User-Agent": base.UA}, timeout=60.0,
                     follow_redirects=True)
    resp.raise_for_status()
    found = []
    for href, _yr, code, mon, day, year in _LINK_RE.findall(resp.text):
        mnum = _MONTHS.get(mon.capitalize())
        if not mnum:
            continue
        found.append(((int(year), mnum), code, "https://amc.ppfas.com" + href))
    if not found:
        return []
    latest = max(k for k, _, _ in found)
    out, seen = [], set()
    for key, code, url in found:
        if key == latest and code not in seen:
            seen.add(code)
            out.append({"filename": f"{code}_{latest[0]}_{latest[1]:02d}.xlsx", "url": url})
    return out
