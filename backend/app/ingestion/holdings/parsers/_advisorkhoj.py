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
_MONTH = (r"jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|"
          r"aug(?:ust)?|sep(?:tember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?")
# AMCs date their filenames every which way; try the common shapes in order:
_DATE_PATTERNS = [
    # 30th-September-2025 | 30 June 2026 | 31-May-26
    re.compile(rf"(\d{{1,2}})(?:st|nd|rd|th)?[-_ ]({_MONTH})[-_ ](\d{{2,4}})", re.I),
    # December-31,-2025 | June 30 2026
    re.compile(rf"({_MONTH})[-_ ](\d{{1,2}})(?:st|nd|rd|th)?,?[-_ ](\d{{2,4}})", re.I),
]


def _url_date(u):
    for i, pat in enumerate(_DATE_PATTERNS):
        m = pat.search(u)
        if not m:
            continue
        day, month, year = (m.group(2), m.group(1), m.group(3)) if i == 1 \
            else (m.group(1), m.group(2), m.group(3))
        try:
            return dateparser.parse(f"{day} {month} {year}").date()
        except (ValueError, OverflowError):
            return None
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
