"""
Shared parser for AMFI's daily NAVAll.txt.

File layout (semicolon-separated), repeated in sections:
    Open Ended Schemes(Equity Scheme - Flexi Cap Fund)     <- scheme_type(category)
    <blank>
    Aditya Birla Sun Life Mutual Fund                       <- AMC name
    Scheme Code;ISIN...;Scheme Name;Net Asset Value;Date    <- column header
    119551;INF209KA12Z1;INF209KA13Z9;Name;106.6107;22-Jul-2026

parse_navall() yields one dict per scheme row, carrying the section context.
"""
import hashlib
import re
import time

import httpx
from dateutil import parser as dateparser

AMFI_URL = "https://www.amfiindia.com/spages/NAVAll.txt"

_SECTION_RE = re.compile(r"^(.*?Schemes?)\s*\(\s*(.*?)\s*\)\s*$", re.I)

_PLAN_OPTION_TOKENS = re.compile(
    r"\b(direct|regular|growth|idcw|dividend|div|bonus|payout|reinvestment|"
    r"re-?investment|income distribution cum capital withdrawal|"
    r"daily|weekly|fortnightly|monthly|quarterly|half yearly|halfyearly|annual|"
    r"periodic|option|plan|of|cum|capital|withdrawal|income|distribution)\b",
    re.I,
)


def fetch_navall_text(attempts: int = 5) -> str:
    """Download AMFI's daily NAV file, retrying transient network failures.

    The nightly job runs at 23:30, when the Mac may still be waking or the
    network not yet up: a single DNS blip ("nodename nor servname provided")
    used to abort the whole sync and cost that day's data — 3 of 14 runs died
    that way, leaving NAV 8 days stale. Retrying with backoff turns a blip into
    a delay instead of a missed day.
    """
    delay = 20.0
    last = None
    for attempt in range(1, attempts + 1):
        try:
            resp = httpx.get(AMFI_URL, timeout=60.0, follow_redirects=True)
            resp.raise_for_status()
            return resp.text
        except (httpx.HTTPError, OSError) as e:
            last = e
            if attempt == attempts:
                break
            print(f"  AMFI fetch failed ({type(e).__name__}), retry "
                  f"{attempt}/{attempts - 1} in {delay:.0f}s", flush=True)
            time.sleep(delay)
            delay = min(delay * 2, 300)
    raise RuntimeError(
        f"AMFI fetch failed after {attempts} attempts: {type(last).__name__}: {last}")


def derive_plan_type(name: str):
    if re.search(r"\bdirect\b", name, re.I):
        return "Direct"
    if re.search(r"\bregular\b", name, re.I):
        return "Regular"
    return None


def derive_option_type(name: str):
    has_idcw = re.search(r"\bidcw\b|\bdcw\b|\bdividend\b|income distribution", name, re.I)
    has_growth = re.search(r"\bgrowth\b", name, re.I)
    if has_idcw:
        return "IDCW"
    if has_growth:
        return "Growth"
    return None


def fund_group_id(amc: str, scheme_name: str) -> str:
    """Same id for Direct/Regular x Growth/IDCW variants of one underlying fund."""
    base = _PLAN_OPTION_TOKENS.sub(" ", scheme_name.lower())
    base = re.sub(r"[^a-z0-9]+", "", base)
    key = f"{(amc or '').lower().strip()}|{base}"
    return hashlib.md5(key.encode()).hexdigest()[:16]


def parse_navall(text: str):
    """Yields dicts: scheme_code, isin, name, nav (float|None), nav_date (date|None),
    scheme_type, category, sub_category, amc, plan_type, option_type, fund_group_id."""
    scheme_type = category = sub_category = amc = None
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        parts = line.split(";")
        if len(parts) < 6:
            m = _SECTION_RE.match(line)
            if m:
                scheme_type = m.group(1).strip()
                category = m.group(2).strip()
                sub_category = category.split(" - ", 1)[1].strip() if " - " in category else None
            else:
                amc = line
            continue
        code = parts[0].strip()
        if not code.isdigit():
            continue  # column header row
        name = parts[3].strip()
        # AMFI changed NAVAll.txt's layout in Aug 2026: it grew from 6 columns to 8,
        # adding explicit "Plan" and "Option" columns and dropping the plan/option
        # suffix from the Scheme Name. Reading NAV from a fixed index silently
        # produced zero usable rows (NAV column became the literal "Direct Plan"),
        # so the layout is detected per row and both are supported.
        if len(parts) >= 8:
            plan_src, option_src = parts[4].strip(), parts[5].strip()
            nav_raw, date_raw = parts[6], parts[7]
        else:
            plan_src = option_src = name        # legacy: it was all in the name
            nav_raw, date_raw = parts[4], parts[5]
        try:
            nav = float(nav_raw)
        except ValueError:
            nav = None  # "N.A."
        try:
            nav_date = dateparser.parse(date_raw.strip(), dayfirst=True).date()
        except (ValueError, OverflowError):
            nav_date = None
        isin = parts[1].strip()
        if isin in ("", "-"):
            isin = parts[2].strip()
        if isin in ("", "-"):
            isin = None
        yield {
            "scheme_code": code,
            "isin": isin,
            "name": name,
            "nav": nav,
            "nav_date": nav_date,
            "scheme_type": scheme_type,
            "category": category,
            "sub_category": sub_category,
            "amc": amc,
            "plan_type": derive_plan_type(plan_src),
            "option_type": derive_option_type(option_src),
            "fund_group_id": fund_group_id(amc, name),
        }
