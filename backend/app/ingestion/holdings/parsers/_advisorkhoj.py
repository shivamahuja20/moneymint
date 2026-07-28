"""
Helper: discover an AMC's latest monthly-portfolio file via advisorkhoj's
download centre.

advisorkhoj (a third-party MF site) lists each AMC's monthly portfolio files as
direct links to the AMC's OWN file host — so it gives us a stable, scrapable index
without reverse-engineering each AMC's JavaScript site. We only read the links and
download the official file; nothing is redistributed (personal use).
"""
import re

import httpx
from dateutil import parser as dateparser

from .. import base

INDEX = ("https://www.advisorkhoj.com/form-download-centre/Mutual/"
         "{slug}/Monthly-Portfolio-Disclosures")
_DATE_IN_URL = re.compile(
    r"(\d{1,2})(?:st|nd|rd|th)?[-_ ]([A-Za-z]+)[-_ ](\d{4})", re.I)


def _url_date(u):
    m = _DATE_IN_URL.search(u)
    if not m:
        return None
    try:
        return dateparser.parse(f"{m.group(1)} {m.group(2)} {m.group(3)}").date()
    except (ValueError, OverflowError):
        return None


def latest_files(slug, exts=("xlsx", "xls")):
    """[(date, url)] of the AMC's portfolio files, newest first."""
    r = httpx.get(INDEX.format(slug=slug), headers={"User-Agent": base.UA},
                  timeout=60.0, follow_redirects=True)
    r.raise_for_status()
    pat = r"https?://[^\"'>\s]+\.(?:" + "|".join(exts) + r")"
    dated = []
    for u in set(re.findall(pat, r.text, re.I)):
        d = _url_date(u)
        if d:
            dated.append((d, u))
    dated.sort(reverse=True)
    return dated


def latest_url(slug, exts=("xlsx", "xls")):
    files = latest_files(slug, exts)
    return files[0][1] if files else None
