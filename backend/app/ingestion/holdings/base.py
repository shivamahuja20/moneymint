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

# Where downloaded AMC workbooks are cached.
#
# NOT inside the project: on macOS the project lives under ~/Desktop, which is a
# TCC-protected folder. A *scheduled* job (launchd/cron) may read the project but
# is refused permission to WRITE there ("Operation not permitted"), so caching
# workbooks into backend/data/ made this ETL impossible to automate. Application
# Support is writable from any context. Override with MONEYMINT_HOLDINGS_DIR.
DATA_ROOT = os.environ.get(
    "MONEYMINT_HOLDINGS_DIR",
    os.path.expanduser("~/Library/Application Support/MoneyMint/holdings_raw"),
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


def iter_workbooks(path):
    """Yield (member_label, workbook) for a downloaded file.

    Most AMCs publish a workbook directly; some (DSP, UTI) publish a .zip bundling
    several workbooks. Handling both here keeps every per-AMC parser trivial.
    Individual unreadable members are skipped rather than failing the archive."""
    import zipfile
    if zipfile.is_zipfile(path) and not path.lower().endswith((".xlsx", ".xls")):
        with zipfile.ZipFile(path) as z:
            for member in z.namelist():
                if not member.lower().endswith((".xlsx", ".xls")) or "/." in member:
                    continue
                try:
                    yield member, openpyxl.load_workbook(
                        io.BytesIO(z.read(member)), data_only=True, read_only=True)
                except Exception:
                    continue
    else:
        yield os.path.basename(path), open_workbook(path)


def cache_workbook(amc_slug: str, filename: str, url: str) -> str:
    """Download url once into DATA_ROOT/<amc>/<filename>; skip if present."""
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


def extract_as_of_date(ws, scan=8, header_row=None):
    """The statement date from the sheet's title area.

    `header_row` bounds the scan to rows ABOVE the column headers. Without it the
    scan ran into the data and picked up a holding's "Maturity Date" — DSP's
    10Y G-Sec fund ended up stamped 2036, and one fund 2065.
    """
    from dateutil import parser as dateparser
    limit = min(scan, header_row - 1) if header_row and header_row > 1 else scan
    if limit < 1:
        return None
    rows = list(ws.iter_rows(min_row=1, max_row=limit, values_only=True))
    today = datetime.date.today()
    # (a) a real date/datetime cell in the header region — SBI puts the statement
    #     date as a date value beside a "PORTFOLIO STATEMENT AS ON" label.
    for row in rows:
        for c in row:
            d = c.date() if isinstance(c, datetime.datetime) else (
                c if isinstance(c, datetime.date) else None)
            # a portfolio is always as-of the past; a future date is a maturity
            # or some other column bleeding in, never the statement date
            if d and d <= today:
                return d
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


# The house name is not a scheme. It appears bare ("Bank of India Mutual Fund")
# or behind a label ("Name of Mutual Fund : Bank of India Mutual Fund" — BOI),
# so allow an optional label prefix and punctuation before it.
_AMC_LINE = re.compile(
    r"^(?:name\s+of\s+(?:the\s+)?(?:mutual\s+fund|amc)\s*[:\-]\s*)?"
    r"[\w .&',\-]{0,45}\bmutual fund\.?$", re.I)


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

    as_of = extract_as_of_date(ws, header_row=hidx)

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
    # (9.18). Decide from the total, which for a fund is ~1 (fractions) or ~100
    # (percents). Junk values in the weight column (e.g. DSP's written-off IL&FS
    # side-pocket rows carry 372 there) are dropped BEFORE totalling — a single
    # outlier must not flip the scale for the whole sheet.
    weights = [p for *_, p, _ in raw if p and p <= 100]
    scale = 100.0 if 0 < sum(weights) <= 3 else 1.0

    rows = [{
        "instrument_name": _clean_name(name),
        "isin": isin,
        "sector": clean_sector(industry),
        "pct_of_aum": round(pct * scale, 4) if pct is not None else 0.0,
        "market_value_cr": round(mv / 100, 2) if mv is not None else None,
    } for name, isin, industry, pct, mv in raw]
    # a single holding can't exceed 100% of the fund — such a row is junk in the
    # weight column (defaulted/side-pocketed instruments), not a real position
    rows = [r for r in rows if r["pct_of_aum"] <= 100.0]
    return scheme_name, as_of, rows


# ---------------------------------------------------------------------------
# scheme matching + DB writes
# ---------------------------------------------------------------------------
# Master (scheme_master) names carry plan/option suffixes that a monthly-portfolio
# sheet never has — "…Fund - Direct Plan - Growth", "…- Regular - IDCW Monthly".
# Stripping these collapses a fund's variants onto one key so holdings attach to all.
_STRIP = re.compile(
    r"\(.*?\)|"
    r"\b(direct|regular|dir|reg)\b|\bplan\b|"
    r"\bgrowth\b|\bidcw\b|\bdividend\b|\bpayout\b|\breinvestment\b|\boption\b|\bfund\b|"
    # IDCW payout-frequency qualifiers: these distinguish *options* of one fund,
    # not different funds, so stripping them collapses e.g. "…Monthly IDCW" and
    # "…Quarterly IDCW" onto the same scheme the monthly portfolio sheet names.
    r"\b(daily|weekly|fortnightly|monthly|quarterly|half\s*yearly|yearly|annual|normal)\b",
    re.I)

# A portfolio SHEET title is just the fund's name — it has no plan/option suffix.
# So it gets only light cleaning. Stripping plan words from the sheet side too was a
# real bug: "DSP Regular Savings Fund" lost its "Regular" and collided with the
# different "DSP Savings Fund", merging two funds' portfolios (sums hit 164%).
_STRIP_SHEET = re.compile(r"\(.*?\)|\bfund\b|\bscheme\b", re.I)


# join words that AMCs write inconsistently: "&" (dropped as punctuation) vs the
# word "and"; a stray "the". Removing these makes "Banking & Financial" and
# "Banking And Financial" normalise identically.
_NOISE_WORDS = {"and", "the"}


def _tokens(name: str) -> str:
    s = re.sub(r"[^a-z0-9]+", " ", (name or "").lower())
    return " ".join(t for t in s.split() if t not in _NOISE_WORDS)


# words that only ever describe a plan/option, never a fund's identity
_PLAN_NOISE = {
    "direct", "regular", "dir", "reg", "plan", "growth", "idcw", "dividend",
    "payout", "reinvestment", "option", "options", "bonus", "income",
    "distribution", "cum", "capital", "withdrawal", "of", "daily", "weekly",
    "fortnightly", "monthly", "quarterly", "half", "yearly", "annual", "normal",
}


def _norm(name: str) -> str:
    """Normalise a scheme_master name to its fund identity.

    Master names are "<fund name> Fund - <plan> - <option>". Splitting at the word
    "Fund" keeps the identity intact — including words like the "Regular" in
    "DSP Regular Savings Fund", which a blanket plan-word strip would wrongly
    remove and merge into the different "DSP Savings Fund". Anything meaningful
    after "Fund" (e.g. "- Equity Plan" of a retirement fund) is kept, since that
    genuinely distinguishes schemes; pure plan/option words are dropped.
    """
    raw = re.sub(r"\(.*?\)", " ", name or "")
    m = re.search(r"\bfunds?\b", raw, re.I)
    if not m:
        return _tokens(_STRIP.sub(" ", raw))       # no "Fund" word — fall back
    head = _tokens(raw[:m.start()])
    tail = [t for t in _tokens(raw[m.end():]).split() if t not in _PLAN_NOISE]
    return " ".join([head] + tail).strip()


def _norm_sheet(name: str) -> str:
    """Normalise a portfolio-sheet title (keeps words that are part of the fund's
    real name, e.g. the 'Regular' in 'DSP Regular Savings Fund')."""
    return _tokens(_STRIP_SHEET.sub(" ", name or ""))


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
    # 2) the sheet title carries trailing descriptors the master name lacks
    #    ("SBI Retirement Benefit Fund - Aggressive Hybrid Plan"). Several master
    #    names may prefix it ("…Aggressive", "…Aggressive Hybrid"); the LONGEST is
    #    the most specific and is the right fund. A tie is genuinely ambiguous.
    contained = [n for n in groups if target.startswith(n + " ")]
    if contained:
        longest = max(len(n) for n in contained)
        best = [n for n in contained if len(n) == longest]
        if len(best) == 1:
            return groups[best[0]]
        return []
    # 3) the reverse — the target is SHORTER than the master name, i.e. too vague
    #    ("HDFC Flexi" could be "HDFC Flexi Cap" or "HDFC Flexi Cap II"). Only a
    #    single possible fund is safe; otherwise refuse rather than guess.
    cands = [n for n in groups if n.startswith(target + " ")]
    return groups[cands[0]] if len(cands) == 1 else []


def match_scheme_codes(db, amc: str, sheet_scheme_name: str):
    """scheme_codes of the fund whose portfolio this sheet is, within the AMC.
    Thin DB wrapper over _resolve_codes (which holds the matching logic)."""
    from sqlalchemy import text
    rows = db.execute(text(
        "SELECT scheme_code, name FROM scheme_master WHERE amc = :amc"), {"amc": amc}
    ).all()
    return _resolve_codes(_norm_sheet(sheet_scheme_name), [(c, n) for c, n in rows])


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
