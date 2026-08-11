"""
Portfolio overlap — how much of two funds is actually the same stocks.

Holding three "different" equity funds often means holding one portfolio three
times: the same index heavyweights, at three expense ratios. The standard measure
is the sum over commonly-held instruments of the SMALLER of the two weights —
i.e. the share of your money that is genuinely duplicated.

We match on ISIN, never on name: "HDFC Bank Ltd", "HDFC Bank Limited" and
"HDFC Bank Ltd." are one company but three strings, and name-matching would
silently understate overlap.

Pure functions over {isin: weight} dicts — no DB, no I/O — so this is fast and
directly unit-testable. The router loads holdings.

Honesty rules:
  * a fund with no disclosed holdings yields None, never 0% (0% would read as
    "no overlap" when the truth is "we don't know");
  * portfolios are disclosed monthly, so two funds can sit on different as-of
    dates — we return each fund's date and let the caller flag the mismatch
    rather than silently comparing across months;
  * disclosed weights don't total 100 (cash, derivatives and unrated items carry
    no ISIN and are excluded by the ETL), so we report the covered weight and
    never rescale it to make the number look tidier.
"""
from collections import defaultdict


def to_weights(rows):
    """rows: [(isin, pct_of_aum, instrument_name)] -> ({isin: pct}, {isin: name}).

    A fund occasionally lists one ISIN on several lines (different series of the
    same bond, or a split disclosure); those are summed, not overwritten."""
    weights = defaultdict(float)
    names = {}
    for isin, pct, name in rows:
        if not isin or pct is None:
            continue
        weights[isin] += float(pct)
        names.setdefault(isin, name)
    return dict(weights), names


def covered_weight(weights):
    """Total disclosed weight we can actually compare (ISIN-bearing holdings)."""
    return round(sum(weights.values()), 2)


def pairwise_overlap(a, b, names=None, top=10):
    """Overlap between two {isin: weight} portfolios.

    overlap_pct = sum of min(weight_a, weight_b) over commonly-held ISINs — the
    proportion of a rupee that is duplicated across the two funds.
    Returns None if either side has nothing disclosed."""
    if not a or not b:
        return None
    common = set(a) & set(b)
    shared = [(i, min(a[i], b[i]), a[i], b[i]) for i in common]
    shared.sort(key=lambda x: -x[1])
    names = names or {}
    return {
        "overlap_pct": round(sum(s[1] for s in shared), 2),
        "common_count": len(common),
        "top_common": [
            {"isin": i, "name": names.get(i, i),
             "min_pct": round(m, 2), "a_pct": round(wa, 2), "b_pct": round(wb, 2)}
            for i, m, wa, wb in shared[:top]
        ],
    }


def combined_exposure(funds, top=10):
    """What you actually own if you split money equally across `funds`.

    funds: [(weights, names)]. Equal allocation is the honest default — it is the
    assumption the user can reason about, and it makes concentration visible:
    three funds sharing the same top holdings still leave you concentrated.
    Returns [{isin, name, pct, held_by}] sorted by combined weight."""
    live = [(w, n) for w, n in funds if w]
    if not live:
        return []
    share = 1.0 / len(live)
    agg = defaultdict(float)
    held_by = defaultdict(int)
    names = {}
    for weights, nmap in live:
        for isin, pct in weights.items():
            agg[isin] += pct * share
            held_by[isin] += 1
            names.setdefault(isin, nmap.get(isin, isin))
    rows = sorted(agg.items(), key=lambda kv: -kv[1])
    return [{"isin": i, "name": names.get(i, i), "pct": round(p, 2),
             "held_by": held_by[i]} for i, p in rows[:top]]


def concentration(funds, n=5):
    """Combined weight sitting in the top `n` instruments across the equal-split
    portfolio — the 'you thought you were diversified' number. None if no data."""
    rows = combined_exposure(funds, top=n)
    if not rows:
        return None
    return round(sum(r["pct"] for r in rows), 2)
