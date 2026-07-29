"""Unit tests for the pure helpers in app/ingestion/ter_sync.py (no network/DB).

The network + DB paths are integration-tested by running the module; these pin the
parsing/dedup logic that decides which TER value survives.

Run: ./venv/bin/python -m pytest tests/test_ter_sync.py -v
"""
import datetime as dt

from app.ingestion import ter_sync as t


def test_norm_amc_strips_suffix_and_punctuation():
    assert t.norm_amc("HDFC Mutual Fund") == "hdfc"
    assert t.norm_amc("Aditya Birla Sun Life Mutual Fund") == "aditya birla sun life"
    assert t.norm_amc("SBI Mutual Fund") == "sbi"


def test_ter_float_parses_and_guards():
    assert t._ter_float("2.0300") == 2.03
    assert t._ter_float("0.6300") == 0.63
    assert t._ter_float("0") is None      # zero isn't a real TER
    assert t._ter_float(None) is None
    assert t._ter_float("junk") is None


def test_ter_float_rejects_implausible_values():
    # new-fund transaction-cost spikes / data errors above the SEBI-plus-GST ceiling
    assert t._ter_float("29.6100") is None
    assert t._ter_float("4.6200") is None
    assert t._ter_float(str(t.PLAUSIBLE_TER_MAX + 0.01)) is None
    assert t._ter_float("2.7500") == 2.75   # a high-but-plausible small-fund TER survives


def test_dedupe_collapses_duplicates_same_ter():
    recs = [{"Scheme_Name": "HDFC Flexi Cap Fund", "R_TER": "1.4500",
             "D_TER": "0.7700", "TER_Date": "2026-06-01T00:00:00Z"}] * 30
    out = t.dedupe_latest(recs)
    assert set(out) == {"HDFC Flexi Cap Fund"}
    assert out["HDFC Flexi Cap Fund"]["r_ter"] == 1.45
    assert out["HDFC Flexi Cap Fund"]["d_ter"] == 0.77


def test_dedupe_keeps_latest_ter_date_when_revised_midmonth():
    recs = [
        {"Scheme_Name": "X Fund", "R_TER": "1.9600", "D_TER": "0.9600",
         "TER_Date": "2026-06-01T00:00:00Z"},
        {"Scheme_Name": "X Fund", "R_TER": "1.9500", "D_TER": "0.9500",
         "TER_Date": "2026-06-20T00:00:00Z"},   # newer -> should win
    ]
    out = t.dedupe_latest(recs)
    assert out["X Fund"]["r_ter"] == 1.95
    assert out["X Fund"]["d_ter"] == 0.95
    assert out["X Fund"]["ter_date"] == dt.date(2026, 6, 20)


def test_dedupe_skips_blank_names():
    recs = [{"Scheme_Name": "", "R_TER": "1.0", "D_TER": "0.5", "TER_Date": "2026-06-01"}]
    assert t.dedupe_latest(recs) == {}
