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
DATE_RE = re.compile(r"as on\s+([A-Za-z]+\s+\d{1,2},?\s+\d{4})", re.I)

HEADER_FIELDS = {
    "name": ("name of the instrument", "name of instrument"),
    "isin": ("isin",),
    "industry": ("industry", "rating"),
    "market_value": ("market", "fair value"),
    "pct": ("% to net", "% of net", "% to nav"),
}


def is_isin(v) -> bool:
    return bool(v) and bool(ISIN_RE.match(str(v).strip()))


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
        if "name of the instrument" in joined and "isin" in joined:
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
    for row in ws.iter_rows(min_row=1, max_row=scan, values_only=True):
        for c in row:
            if not c:
                continue
            m = DATE_RE.search(str(c))
            if m:
                try:
                    return datetime.datetime.strptime(
                        m.group(1).replace(",", ""), "%B %d %Y").date()
                except ValueError:
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

    # scheme name = first non-empty cell above the header row
    scheme_name = None
    for row in ws.iter_rows(min_row=1, max_row=hidx - 1, values_only=True):
        for c in row:
            if c and len(str(c).strip()) > 5:
                scheme_name = str(c).strip()
                break
        if scheme_name:
            break

    as_of = extract_as_of_date(ws)

    rows = []
    for row in ws.iter_rows(min_row=hidx + 1, values_only=True):
        isin = row[cols["isin"]] if cols["isin"] < len(row) else None
        if not is_isin(isin):
            continue
        name = row[cols["name"]] if cols["name"] < len(row) else None
        if not name:
            continue
        pct = _num(row[cols["pct"]]) if cols["pct"] < len(row) else None
        mv = _num(row[cols["market_value"]]) if cols.get("market_value", 99) < len(row) else None
        industry = row[cols["industry"]] if cols.get("industry", 99) < len(row) else None
        rows.append({
            "instrument_name": str(name).strip(),
            "isin": str(isin).strip(),
            "sector": clean_sector(industry),
            "pct_of_aum": round(pct * 100, 4) if pct is not None else 0.0,
            "market_value_cr": round(mv / 100, 2) if mv is not None else None,
        })
    return scheme_name, as_of, rows


# ---------------------------------------------------------------------------
# scheme matching + DB writes
# ---------------------------------------------------------------------------
_STRIP = re.compile(
    r"\(.*?\)|-\s*(direct|regular)\s*plan|direct|regular|growth|idcw|dividend|"
    r"payout|reinvestment|option|plan|fund", re.I)


def _norm(name: str) -> str:
    name = _STRIP.sub(" ", name or "")
    return re.sub(r"[^a-z0-9]+", " ", name.lower()).strip()


def match_scheme_codes(db, amc: str, sheet_scheme_name: str):
    """All scheme_codes (Direct/Regular x Growth/IDCW) of the fund whose portfolio
    this sheet is — matched by normalised-name prefix within the AMC. Holdings are
    shared across a fund's plan/option variants, so we attach to all of them."""
    from sqlalchemy import text
    target = _norm(sheet_scheme_name)
    if not target:
        return []
    rows = db.execute(text(
        "SELECT scheme_code, name FROM scheme_master WHERE amc = :amc"), {"amc": amc}
    ).all()
    out = []
    for code, name in rows:
        n = _norm(name)
        if n == target or n.startswith(target + " ") or n.startswith(target):
            out.append(code)
    return out


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
