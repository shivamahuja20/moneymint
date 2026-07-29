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


def test_plan_word_in_fund_name_is_not_stripped():
    """Regression: "DSP Regular Savings Fund" and "DSP Savings Fund" are DIFFERENT
    funds. Stripping the plan word "Regular" from the fund's own name merged their
    portfolios onto one scheme (weights summed to 164%)."""
    from app.ingestion.holdings.base import _norm_sheet
    rows = [("A", "DSP Savings Fund - Direct Plan - Growth"),
            ("B", "DSP Savings Fund - Regular Plan - Growth"),
            ("C", "DSP Regular Savings Fund - Direct Plan - Growth")]
    assert set(_resolve_codes(_norm_sheet("DSP Savings Fund"), rows)) == {"A", "B"}
    assert set(_resolve_codes(_norm_sheet("DSP Regular Savings Fund"), rows)) == {"C"}


def test_sub_plan_funds_stay_distinct():
    """A fund whose sub-plans are separate schemes (retirement funds) must not
    collapse, and the most specific prefix wins over a shorter sibling."""
    from app.ingestion.holdings.base import _norm_sheet
    rows = [("A", "SBI Retirement Benefit Fund - Aggressive Plan - Direct Plan - Growth"),
            ("B", "SBI Retirement Benefit Fund - Aggressive Hybrid Plan - Direct Plan - Growth"),
            ("C", "SBI Retirement Benefit Fund - Conservative Plan - Direct Plan - Growth")]
    assert set(_resolve_codes(
        _norm_sheet("SBI RETIREMENT BENEFIT FUND - AGGRESSIVE HYBRID PLAN"), rows)) == {"B"}
    assert set(_resolve_codes(
        _norm_sheet("SBI RETIREMENT BENEFIT FUND - CONSERVATIVE PLAN"), rows)) == {"C"}


def test_and_ampersand_equivalence():
    # AMCs write "&" and "And" interchangeably; both must resolve to the same fund
    rows = [("X", "SBI Banking & Financial Services Fund - Direct Plan - Growth"),
            ("Y", "SBI Banking & Financial Services Fund - Regular Plan - Growth")]
    assert set(_resolve_codes(_norm("SBI Banking And Financial Services Fund"), rows)) == {"X", "Y"}
