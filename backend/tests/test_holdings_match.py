"""Unit tests for holdings scheme-name matching (app/ingestion/holdings/base.py).

The matcher decides which scheme_code(s) a monthly-portfolio sheet belongs to.
Getting it wrong silently pins a fund's portfolio to the wrong scheme — a data-
honesty failure — so these tests pin the "refuse to guess" behaviour.

Run: ./venv/bin/python -m pytest tests/test_holdings_match.py -v
"""
from app.ingestion.holdings.base import _resolve_codes, _norm


# a realistic AMC scheme list: one fund fans out into plan/option variants
ROWS = [
    ("A", "HDFC Flexi Cap Fund - Direct Plan - Growth"),
    ("B", "HDFC Flexi Cap Fund - Regular Plan - Growth"),
    ("C", "HDFC Flexi Cap Fund - Direct Plan - IDCW"),
    ("D", "HDFC Top 100 Fund - Direct Plan - Growth"),
    ("E", "HDFC Mid-Cap Opportunities Fund - Direct Plan - Growth"),
]


def _match(name, rows=ROWS):
    return set(_resolve_codes(_norm(name), rows))


def test_exact_name_fans_out_to_all_variants():
    # every Direct/Regular x Growth/IDCW variant of the fund, and nothing else
    assert _match("HDFC Flexi Cap Fund") == {"A", "B", "C"}


def test_trailing_descriptor_still_matches():
    # sheet titles often carry extra words; token-boundary prefix tolerates them
    assert _match("HDFC Flexi Cap Fund - Monthly Portfolio (Unaudited)") == {"A", "B", "C"}


def test_distinct_fund_matches_only_itself():
    assert _match("HDFC Top 100 Fund") == {"D"}
    assert _match("HDFC Mid Cap Opportunities Fund") == {"E"}


def test_generic_name_matches_nothing():
    # the key regression: a bad/short header must NOT mass-attach to every HDFC fund
    assert _match("HDFC") == set()
    assert _match("HDFC Fund") == set()   # normalises to just "hdfc"


def test_ambiguous_prefix_is_refused():
    rows = ROWS + [("F", "HDFC Flexi Cap Fund II - Direct Plan - Growth")]
    # exact normalised match on a fund still wins cleanly, ignoring the "II" sibling
    assert set(_resolve_codes(_norm("HDFC Flexi Cap Fund"), rows)) == {"A", "B", "C"}
    # but a prefix that could be either "Flexi Cap" or "Flexi Cap II" resolves to neither
    assert _resolve_codes(_norm("HDFC Flexi"), rows) == []


def test_unknown_fund_matches_nothing():
    assert _match("HDFC Balanced Advantage Fund") == set()
