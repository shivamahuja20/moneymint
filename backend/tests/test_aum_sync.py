"""Unit tests for the pure helpers in app/ingestion/aum_sync.py (no network/DB)."""
import datetime as dt

from app.ingestion import aum_sync as a


def test_period_end_date_quarter():
    assert a.period_end_date("April - June 2026") == dt.date(2026, 6, 30)
    assert a.period_end_date("July - September 2026") == dt.date(2026, 9, 30)
    assert a.period_end_date("January - March 2025") == dt.date(2025, 3, 31)


def test_period_end_date_single_month():
    assert a.period_end_date("June 2026") == dt.date(2026, 6, 30)


def test_period_end_date_unparseable():
    assert a.period_end_date("") is None
    assert a.period_end_date("no date here") is None


def test_lakh_to_cr():
    assert a.lakh_to_cr(9377503.7) == 93775.04     # PPFAS Flexi Direct-Growth ~₹93.7k cr
    assert a.lakh_to_cr("4784.48") == 47.84
    assert a.lakh_to_cr(0) is None
    assert a.lakh_to_cr(None) is None
    assert a.lakh_to_cr("junk") is None


def test_flatten_extracts_code_and_cr():
    groups = [{
        "Mfname": "X Mutual Fund", "SchemeCat_Desc": "Equity",
        "schemes": [
            {"SchemeNAVName": "X Fund Direct", "AMFI_Code": 122639,
             "AverageAumForTheMonth": {a.AAUM_FIELD: 9377503.7, "FundOfFundsDomestic": 0}},
            {"SchemeNAVName": "X Fund zero", "AMFI_Code": 999,
             "AverageAumForTheMonth": {a.AAUM_FIELD: 0}},   # zero -> dropped
        ],
    }]
    out = a.flatten(groups)
    assert out == [("122639", 93775.04)]


def test_flatten_uses_fof_field_for_domestic_fund_of_funds():
    # domestic FoFs report 0 in the headline field, real AUM in FundOfFundsDomestic
    groups = [{"schemes": [
        {"SchemeNAVName": "X FoF", "AMFI_Code": 148928,
         "AverageAumForTheMonth": {a.AAUM_FIELD: 0, a.FOF_FIELD: 115899.97}},
    ]}]
    assert a.flatten(groups) == [("148928", 1159.0)]
