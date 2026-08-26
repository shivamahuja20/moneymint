"""Regression tests for AMFI NAVAll.txt column-layout handling.

In Aug 2026 AMFI changed the file from 6 columns to 8, adding explicit "Plan" and
"Option" columns and dropping the plan/option suffix from Scheme Name. Because the
parser read NAV from a fixed index, every row silently became unusable (NAV parsed
as the literal "Direct Plan") and the nightly sync inserted ZERO NAVs for days
without any error. These tests pin both layouts so that can't recur quietly.
"""
import datetime as dt

from app.ingestion.amfi_parse import parse_navall, derive_option_type, derive_plan_type

HEADER_NEW = ("Scheme Code;ISIN Div Payout/ ISIN Growth;ISIN Div Reinvestment;"
              "Scheme Name;Plan;Option;Net Asset Value;Date")
HEADER_OLD = ("Scheme Code;ISIN Div Payout/ ISIN Growth;ISIN Div Reinvestment;"
              "Scheme Name;Net Asset Value;Date")
SECTION = "Open Ended Schemes ( Equity Scheme - Flexi Cap Fund )"
AMC = "PPFAS Mutual Fund"


def _parse(header, row):
    return list(parse_navall("\n".join([SECTION, AMC, header, row])))


def test_new_eight_column_layout():
    row = "122639;INF879O01019;-;Parag Parikh Flexi Cap Fund;Direct Plan;Growth;92.05;25-Aug-2026"
    (r,) = _parse(HEADER_NEW, row)
    assert r["scheme_code"] == "122639"
    assert r["name"] == "Parag Parikh Flexi Cap Fund"
    assert r["nav"] == 92.05
    assert r["nav_date"] == dt.date(2026, 8, 25)
    assert r["plan_type"] == "Direct"
    assert r["option_type"] == "Growth"


def test_legacy_six_column_layout_still_works():
    row = ("122639;INF879O01019;-;"
           "Parag Parikh Flexi Cap Fund - Direct Plan - Growth;92.05;25-Aug-2026")
    (r,) = _parse(HEADER_OLD, row)
    assert r["nav"] == 92.05
    assert r["nav_date"] == dt.date(2026, 8, 25)
    assert r["plan_type"] == "Direct"
    assert r["option_type"] == "Growth"


def test_new_layout_regular_and_idcw_variants():
    row = "122640;INF879O01027;-;Parag Parikh Flexi Cap Fund;Regular Plan;IDCW-Re-investment;41.2;25-Aug-2026"
    (r,) = _parse(HEADER_NEW, row)
    assert r["plan_type"] == "Regular"
    assert r["option_type"] == "IDCW"


def test_blank_plan_column_is_none_not_a_guess():
    # closed-ended FMP series genuinely have no Direct/Regular split
    row = "100001;INF109K01234;-;ICICI Prudential Fixed Maturity Plan - Series 1;;;10.5;25-Aug-2026"
    (r,) = _parse(HEADER_NEW, row)
    assert r["plan_type"] is None and r["option_type"] is None


def test_na_nav_is_none():
    row = "122639;INF879O01019;-;Some Fund;Direct Plan;Growth;N.A.;25-Aug-2026"
    (r,) = _parse(HEADER_NEW, row)
    assert r["nav"] is None


def test_option_derivation_covers_amfi_dcw_spellings():
    assert derive_option_type("MONTHLY DCW Payout") == "IDCW"
    assert derive_option_type("IDCW-Re-investment") == "IDCW"
    assert derive_option_type("Growth") == "Growth"
    assert derive_plan_type("Direct Plan") == "Direct"
    assert derive_plan_type("Regular Plan") == "Regular"
