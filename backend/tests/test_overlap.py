"""Unit tests for app/overlap.py — portfolio overlap maths (pure, no DB).

Run: ./venv/bin/python -m pytest tests/test_overlap.py -v
"""
from app import overlap


A = ("INE001A01001", "INE002A01002", "INE003A01003")


def test_to_weights_sums_duplicate_isin_lines():
    rows = [(A[0], 5.0, "Alpha Ltd"), (A[0], 3.0, "Alpha Ltd"), (A[1], 2.0, "Beta Ltd")]
    w, names = overlap.to_weights(rows)
    assert w == {A[0]: 8.0, A[1]: 2.0}
    assert names[A[0]] == "Alpha Ltd"


def test_to_weights_skips_missing_isin_or_pct():
    rows = [(None, 5.0, "x"), ("", 1.0, "y"), (A[0], None, "z"), (A[1], 4.0, "Beta")]
    w, _ = overlap.to_weights(rows)
    assert w == {A[1]: 4.0}


def test_covered_weight_is_not_rescaled():
    # cash/derivatives carry no ISIN, so a real fund totals ~95, not 100
    w, _ = overlap.to_weights([(A[0], 60.0, "a"), (A[1], 35.4, "b")])
    assert overlap.covered_weight(w) == 95.4


# ---------------------------------------------------------------------------
# pairwise overlap
# ---------------------------------------------------------------------------
def test_identical_portfolios_overlap_fully():
    w = {A[0]: 50.0, A[1]: 45.0}
    r = overlap.pairwise_overlap(w, dict(w))
    assert r["overlap_pct"] == 95.0
    assert r["common_count"] == 2


def test_disjoint_portfolios_have_zero_overlap():
    r = overlap.pairwise_overlap({A[0]: 50.0}, {A[1]: 50.0})
    assert r["overlap_pct"] == 0.0
    assert r["common_count"] == 0
    assert r["top_common"] == []


def test_overlap_uses_the_smaller_weight():
    # 10 vs 4 on the shared name contributes 4, not 10 or 14
    a = {A[0]: 10.0, A[1]: 5.0}
    b = {A[0]: 4.0, A[2]: 20.0}
    r = overlap.pairwise_overlap(a, b)
    assert r["overlap_pct"] == 4.0
    assert r["common_count"] == 1


def test_top_common_is_ranked_and_reports_both_sides():
    a = {A[0]: 8.0, A[1]: 3.0}
    b = {A[0]: 6.0, A[1]: 9.0}
    names = {A[0]: "Alpha Ltd", A[1]: "Beta Ltd"}
    r = overlap.pairwise_overlap(a, b, names)
    assert r["overlap_pct"] == 9.0          # min(8,6)=6 + min(3,9)=3
    top = r["top_common"]
    assert top[0]["name"] == "Alpha Ltd" and top[0]["min_pct"] == 6.0
    assert top[0]["a_pct"] == 8.0 and top[0]["b_pct"] == 6.0
    assert top[1]["name"] == "Beta Ltd"


def test_missing_holdings_give_none_not_zero():
    # "we don't know" must never render as "no overlap"
    assert overlap.pairwise_overlap({}, {A[0]: 5.0}) is None
    assert overlap.pairwise_overlap({A[0]: 5.0}, {}) is None
    assert overlap.pairwise_overlap(None, None) is None


# ---------------------------------------------------------------------------
# combined exposure / concentration
# ---------------------------------------------------------------------------
def test_combined_exposure_equal_split():
    f1 = ({A[0]: 10.0, A[1]: 6.0}, {A[0]: "Alpha", A[1]: "Beta"})
    f2 = ({A[0]: 8.0, A[2]: 4.0}, {A[0]: "Alpha", A[2]: "Gamma"})
    rows = overlap.combined_exposure([f1, f2])
    top = {r["name"]: r for r in rows}
    assert top["Alpha"]["pct"] == 9.0        # (10 + 8) / 2
    assert top["Alpha"]["held_by"] == 2
    assert top["Beta"]["pct"] == 3.0         # 6 / 2, held by one fund
    assert top["Beta"]["held_by"] == 1
    assert rows[0]["name"] == "Alpha"        # sorted by combined weight


def test_combined_exposure_reveals_hidden_concentration():
    # three "different" funds all holding the same two names heavily
    same = {A[0]: 9.0, A[1]: 8.0}
    funds = [(dict(same), {}) for _ in range(3)]
    assert overlap.concentration(funds, n=2) == 17.0


def test_combined_exposure_ignores_empty_funds():
    f1 = ({A[0]: 10.0}, {})
    rows = overlap.combined_exposure([f1, ({}, {})])
    assert rows[0]["pct"] == 10.0            # divided by 1 live fund, not 2


def test_concentration_none_without_data():
    assert overlap.concentration([({}, {})]) is None
    assert overlap.concentration([]) is None
