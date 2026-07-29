"""
Shared helpers for the holdings ETL.

Most AMCs publish monthly portfolios on the same SEBI template — a sheet with a
header row containing "Name of the Instrument", "ISIN", "Industry / Rating",
"Quantity", "Market/Fair Value (Rs. in Lakhs)" and "% to Net Assets". So the row
parsing is generic (parse_standard_sheet); a per-AMC module only has to say where
its files come from and how sheets map to schemes.

Honest by construction: a row is a real holding only if it carries a valid ISIN and
a numeric weight. Section headers, sub-totals, grand totals, derivatives and the
notes blocks all lack an ISIN in the ISIN column and are skipped — never summed.
"""
import os
import io
import re
import datetime

import openpyxl
import httpx

DATA_ROOT = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))),
    "data", "holdings_raw",
)
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 " \
     "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"

ISIN_RE = re.compile(r"^[A-Z]{2}[A-Z0-9]{9}[0-9]$")
# credit-rating strings that appear in the Industry column for debt/MMI holdings
RATING_RE = re.compile(r"CRISIL|ICRA|CARE|FITCH|IND\b|A1\+|AAA|AA\+|SOV|UNRATED", re.I)
# "as on/at" followed by a date in any common wording
# (June 30, 2026 | June 30,2026 | 30-Jun-2026 | 30 June 2026)
DATE_RE = re.compile(
    r"as\s+(?:on|at)\s+([A-Za-z]+\s+\d{1,2},?\s*\d{4}|\d{1,2}[-\s][A-Za-z]+[-\s]\d{4})", re.I)

HEADER_FIELDS = {
    "name": ("name of the instrument", "name of instrument"),
    "isin": ("isin",),
    "industry": ("industry", "rating"),
    "market_value": ("market", "fair value"),
    "pct": ("% to net", "% of net", "% to nav", "% to aum", "% of aum", "% to total"),
}


def is_isin(v) -> bool:
    return bool(v) and bool(ISIN_RE.match(str(v).strip()))


def open_workbook(path):
    """Load a workbook by CONTENT, not extension. Some AMCs (e.g. Nippon) serve a
    modern .xlsx under a .xls filename; openpyxl rejects the .xls path outright, so
    we hand it the bytes via BytesIO. Genuinely old OLE .xls would still raise, and
    the runner's per-file guard skips it."""
    with open(path, "rb") as f:
        return openpyxl.load_workbook(io.BytesIO(f.read()), data_only=True, read_only=True)


def cache_workbook(amc_slug: str, filename: str, url: str) -> str:
    """Download url once into data/holdings_raw/<amc>/<filename>; skip if present."""
    folder = os.path.join(DATA_ROOT, amc_slug)
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, filename)
    if os.path.exists(path) and os.path.getsize(path) > 0:
        return path
    resp = httpx.get(url, headers={"User-Agent": UA}, timeout=60.0, follow_redirects=True)
    resp.raise_for_status()
    with open(path, "wb") as f:
        f.write(resp.content)
    return path


def find_header_row(ws, scan=25):
    """Row index (1-based) whose cells contain 'Name of the Instrument' + 'ISIN'."""
    for i, row in enumerate(ws.iter_rows(min_row=1, max_row=scan, values_only=True), 1):
        vals = [str(c).lower() for c in row if c]
        joined = " ".join(vals)
        has_name = "name of the instrument" in joined or "name of instrument" in joined
        if has_name and "isin" in joined:
            return i
    return None


def _column_map(header_row):
    """Map logical field -> 0-based column index from the header cells."""
    cols = {}
    for idx, cell in enumerate(header_row):
        if cell is None:
            continue
        text = str(cell).lower().replace("\n", " ")
        for field, keys in HEADER_FIELDS.items():
            if field in cols:
                continue
            if any(k in text for k in keys):
                cols[field] = idx
    return cols


def extract_as_of_date(ws, scan=8):
    from dateutil import parser as dateparser
    rows = list(ws.iter_rows(min_row=1, max_row=scan, values_only=True))
    # (a) a real date/datetime cell in the header region — SBI puts the statement
    #     date as a date value beside a "PORTFOLIO STATEMENT AS ON" label.
    for row in rows:
        for c in row:
            if isinstance(c, datetime.datetime):
                return c.date()
            if isinstance(c, datetime.date):
                return c
    # (b) "as on <date>" written inside a text cell (PPFAS/HDFC/Nippon)
    for row in rows:
        for c in row:
            if not c:
                continue
            m = DATE_RE.search(str(c))
            if m:
                try:
                    return dateparser.parse(m.group(1), dayfirst=True).date()
                except (ValueError, OverflowError):
                    pass
    return None


def clean_sector(industry) -> str:
    if not industry:
        return "Cash & Equivalents"
    s = re.sub(r"[#*^~]+", "", str(industry)).strip()  # drop footnote markers
    if not s:
        return "Cash & Equivalents"
    if RATING_RE.search(s):
        return "Debt / Money Market"
    return s


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _clean_name(name: str) -> str:
    """Strip trailing footnote markers some AMCs append to instrument names,
    e.g. Franklin's 'HDFC Bank Ltd $$ ~~' -> 'HDFC Bank Ltd'."""
    return re.sub(r"[\s$~#*^@]+$", "", str(name).strip())


# "<AMC> Mutual Fund" on its own is the house name, not a scheme — don't take it
_AMC_LINE = re.compile(r"^[\w .&'-]{0,45}\bmutual fund$", re.I)


def _extract_scheme_name(ws, hidx):
    """The fund name from the rows above the header. Two shapes are common:
    an explicit 'Scheme Name : <fund>' label (e.g. SBI), or the fund name sitting
    as the first real cell (e.g. PPFAS/HDFC/Nippon). Skip a bare '<AMC> Mutual Fund'
    line and internal codes (single tokens)."""
    rows = [[(str(c).strip() if c is not None else "") for c in row]
            for row in ws.iter_rows(min_row=1, max_row=hidx - 1, values_only=True)]
    # 1) explicit "Scheme Name" label — value after the colon or in a later cell
    for cells in rows:
        for j, cell in enumerate(cells):
            if "scheme name" in cell.lower():
                after = cell.split(":", 1)[1].strip() if ":" in cell else ""
                if len(after) > 3:
                    return after
                for k in range(j + 1, len(cells)):
                    if len(cells[k]) > 3:
                        return cells[k]
    # 2) fallback — first multi-word alphabetic cell that isn't the AMC's own name
    for cells in rows:
        for s in cells:
            if len(s) > 5 and " " in s and re.search(r"[A-Za-z]{3}", s) \
                    and not _AMC_LINE.match(s):
                # some AMCs title the sheet "Portfolio of <fund> as on <date>" (Kotak)
                s = re.sub(r"^portfolio\s+of\s+", "", s, flags=re.I)
                s = re.sub(r"\s+as\s+(?:on|at|of)\b.*$", "", s, flags=re.I)
                return s.strip()
    return None


def _name_beside_isin(row, cols):
    """The instrument name from the cell adjacent to the ISIN (left then right),
    skipping the industry column — for sheets whose Name header is column-shifted."""
    ci = cols["isin"]
    for cand in (ci - 1, ci + 1):
        if 0 <= cand < len(row) and cand != cols.get("industry"):
            v = row[cand]
            if v and not is_isin(v) and re.search(r"[A-Za-z]{3}", str(v)):
                return str(v).strip()
    return None


def parse_standard_sheet(ws):
    """Parse one SEBI-template sheet -> (scheme_name, as_of_date, [holding dict]).

    holding dict: {instrument_name, isin, sector, pct_of_aum, market_value_cr}.
    pct is stored as a fraction in the file (0.0833 = 8.33%) -> *100.
    market value is in Rs. Lakhs -> /100 for crore. Returns (None, ...) if no header."""
    hidx = find_header_row(ws)
    if hidx is None:
        return None, None, []
    header = list(ws.iter_rows(min_row=hidx, max_row=hidx, values_only=True))[0]
    cols = _column_map(header)
    if "name" not in cols or "isin" not in cols or "pct" not in cols:
        return None, None, []

    scheme_name = _extract_scheme_name(ws, hidx)

    as_of = extract_as_of_date(ws)

    raw = []
    for row in ws.iter_rows(min_row=hidx + 1, values_only=True):
        isin = row[cols["isin"]] if cols["isin"] < len(row) else None
        if not is_isin(isin):
            continue
        name = row[cols["name"]] if cols["name"] < len(row) else None
        if not name or not str(name).strip():
            # some AMCs merge cells so the "Name" header sits in a different column
            # than the data (e.g. Kotak: header col A, names in col C). Fall back to
            # the text cell next to the ISIN.
            name = _name_beside_isin(row, cols)
        if not name:
            continue
        pct = _num(row[cols["pct"]]) if cols["pct"] < len(row) else None
        mv = _num(row[cols["market_value"]]) if cols.get("market_value", 99) < len(row) else None
        industry = row[cols["industry"]] if cols.get("industry", 99) < len(row) else None
        raw.append((str(name).strip(), str(isin).strip(), industry, pct, mv))

    # AMCs differ: some store "% to NAV" as a fraction (0.0833), some as a percent
    # (9.18). Detect from the total — a fund's weights sum to ~1 or ~100 — and scale
    # everything to true percent uniformly.
    pct_sum = sum(p for *_, p, _ in raw if p)
    scale = 100.0 if 0 < pct_sum <= 3 else 1.0

    rows = [{
        "instrument_name": _clean_name(name),
        "isin": isin,
        "sector": clean_sector(industry),
        "pct_of_aum": round(pct * scale, 4) if pct is not None else 0.0,
        "market_value_cr": round(mv / 100, 2) if mv is not None else None,
    } for name, isin, industry, pct, mv in raw]
    return scheme_name, as_of, rows


# ---------------------------------------------------------------------------
# scheme matching + DB writes
# ---------------------------------------------------------------------------
_STRIP = re.compile(
    r"\(.*?\)|-\s*(direct|regular)\s*plan|direct|regular|growth|idcw|dividend|"
    r"payout|reinvestment|option|plan|fund|"
    # IDCW payout-frequency qualifiers: these distinguish *options* of one fund,
    # not different funds, so stripping them collapses e.g. "…Monthly IDCW" and
    # "…Quarterly IDCW" onto the same scheme the monthly portfolio sheet names.
    r"\b(daily|weekly|fortnightly|monthly|quarterly|half\s*yearly|yearly|annual|normal)\b",
    re.I)


# join words that AMCs write inconsistently: "&" (dropped as punctuation) vs the
# word "and"; a stray "the". Removing these makes "Banking & Financial" and
# "Banking And Financial" normalise identically.
_NOISE_WORDS = {"and", "the"}


def _norm(name: str) -> str:
    name = _STRIP.sub(" ", name or "")
    s = re.sub(r"[^a-z0-9]+", " ", name.lower())
    return " ".join(t for t in s.split() if t not in _NOISE_WORDS)


def _resolve_codes(target: str, rows):
    """Pure matcher (no DB, so it's unit-testable). `target` is the normalised sheet
    scheme name; `rows` is [(scheme_code, master_name)] for the AMC. Returns the
    scheme_codes of the SINGLE fund whose normalised name matches — all its
    Direct/Regular x Growth/IDCW variants share one normalised name, so they come
    back together and holdings attach to every variant.

    Honest by design: it refuses to guess. A name too generic to be safe (bad header
    extraction, e.g. just "hdfc") or a match ambiguous across two different funds
    returns [] — so a portfolio is never silently pinned to the wrong scheme.
    Previously a loose `startswith(target)` could mass-attach one sheet to every fund
    sharing a prefix."""
    if not target or len(target.split()) < 2:
        return []                      # too generic — don't risk a mass mis-match
    groups: dict[str, list] = {}
    for code, name in rows:
        groups.setdefault(_norm(name), []).append(code)
    # 1) exact normalised-name match wins outright (the common case)
    if target in groups:
        return groups[target]
    # 2) else a UNIQUE token-boundary prefix match — tolerates trailing descriptors
    #    ("... Monthly Portfolio") on either side, but bails if >1 fund could match
    cands = [n for n in groups
             if target.startswith(n + " ") or n.startswith(target + " ")]
    return groups[cands[0]] if len(cands) == 1 else []


def match_scheme_codes(db, amc: str, sheet_scheme_name: str):
    """scheme_codes of the fund whose portfolio this sheet is, within the AMC.
    Thin DB wrapper over _resolve_codes (which holds the matching logic)."""
    from sqlalchemy import text
    rows = db.execute(text(
        "SELECT scheme_code, name FROM scheme_master WHERE amc = :amc"), {"amc": amc}
    ).all()
    return _resolve_codes(_norm(sheet_scheme_name), [(c, n) for c, n in rows])


def write_holdings(conn, scheme_code: str, as_of_date, rows):
    """Rebuild-safe: replace this scheme+date's holdings and derive sector_allocation."""
    from sqlalchemy import text
    conn.execute(text("DELETE FROM holdings WHERE scheme_code=:c AND as_of_date=:d"),
                 {"c": scheme_code, "d": as_of_date})
    conn.execute(text("DELETE FROM sector_allocation WHERE scheme_code=:c AND as_of_date=:d"),
                 {"c": scheme_code, "d": as_of_date})
    for r in rows:
        conn.execute(text(
            "INSERT INTO holdings (scheme_code, as_of_date, instrument_name, isin, sector, "
            "pct_of_aum, market_value_cr) VALUES (:c,:d,:name,:isin,:sector,:pct,:mv)"),
            {"c": scheme_code, "d": as_of_date, "name": r["instrument_name"],
             "isin": r["isin"], "sector": r["sector"], "pct": r["pct_of_aum"],
             "mv": r["market_value_cr"]})
    # sector allocation = sum of pct by sector
    sectors = {}
    for r in rows:
        sectors[r["sector"]] = sectors.get(r["sector"], 0.0) + (r["pct_of_aum"] or 0.0)
    for sector, pct in sectors.items():
        conn.execute(text(
            "INSERT INTO sector_allocation (scheme_code, as_of_date, sector, pct_of_aum) "
            "VALUES (:c,:d,:s,:p)"),
            {"c": scheme_code, "d": as_of_date, "s": sector, "p": round(pct, 4)})
