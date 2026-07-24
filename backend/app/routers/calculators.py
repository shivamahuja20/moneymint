"""
Phase 7 calculator endpoints.

Two surfaces:
- /api/schemes/{code}/backtest — historical simulation over the scheme's real NAVs,
  with a taxation estimate on the gain.
- /api/calc/project — forward projections (pure math, assumption-based).

Endpoints return plain dicts (shapes are mode-dependent and self-describing); the
money math lives in app/calc.py and is unit-tested separately.
"""
import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import text

from ..db import get_db
from .. import calc

router = APIRouter(tags=["calculators"])


def _load_nav_rows(db: Session, code: str):
    rows = db.execute(text(
        "SELECT date, nav FROM nav_history WHERE scheme_code=:c ORDER BY date"
    ), {"c": code}).all()
    return [(d, float(n)) for d, n in rows]


@router.get("/api/schemes/{code}/backtest")
def backtest(
    code: str,
    mode: str = Query("sip", description="sip | lumpsum"),
    amount: float = Query(..., gt=0, description="SIP installment or lumpsum amount (INR)"),
    start: datetime.date = Query(..., description="Investment start date (YYYY-MM-DD)"),
    end: Optional[datetime.date] = Query(None, description="Defaults to latest NAV"),
    freq: str = Query("monthly", description="monthly | quarterly (SIP only)"),
    marginal_rate: float = Query(30.0, ge=0, le=50,
                                 description="Slab rate % for non-equity tax"),
    tax_class: Optional[str] = Query(None, description="Override: equity | non_equity"),
    db: Session = Depends(get_db),
):
    m = db.execute(text(
        "SELECT name, category FROM scheme_master WHERE scheme_code=:c"), {"c": code}
    ).mappings().first()
    if not m:
        raise HTTPException(404, f"Unknown scheme code '{code}'.")

    nav_rows = _load_nav_rows(db, code)
    if not nav_rows:
        raise HTTPException(400, "No NAV history for this scheme.")
    first_date = nav_rows[0][0]
    if start < first_date:
        raise HTTPException(400, f"Fund's history starts {first_date.isoformat()}; "
                                 "can't back-test before that.")
    if start >= nav_rows[-1][0]:
        raise HTTPException(400, "Start date is at/after the latest NAV — nothing to simulate.")

    if mode == "sip":
        result = calc.backtest_sip(nav_rows, amount, start, end, freq)
    elif mode == "lumpsum":
        result = calc.backtest_lumpsum(nav_rows, amount, start, end)
    else:
        raise HTTPException(400, f"Invalid mode '{mode}'.")
    if result is None:
        raise HTTPException(400, "Not enough NAV history to run this back-test.")

    # taxation on the gain if redeemed at the end NAV
    cls = tax_class if tax_class in ("equity", "non_equity") else calc.classify_tax(m["category"], m["name"])
    holding_days = (datetime.date.fromisoformat(result["end"])
                    - datetime.date.fromisoformat(result["start"])).days
    result["tax"] = calc.estimate_tax(result["gain"], holding_days, cls, marginal_rate / 100)

    # default forward-projection rate = the fund's own long-run CAGR
    full = calc.backtest_lumpsum(nav_rows, 100000, first_date)
    result["fund_cagr_pct"] = full["cagr_pct"] if full else None
    return result


@router.get("/api/calc/project")
def project(
    mode: str = Query(..., description="sip | lumpsum | swp | goal"),
    annual_rate: float = Query(..., description="Assumed annual return %"),
    amount: Optional[float] = Query(None, gt=0, description="SIP/lumpsum amount"),
    years: Optional[float] = Query(None, gt=0, le=100),
    target: Optional[float] = Query(None, gt=0, description="Goal corpus (goal mode)"),
    corpus: Optional[float] = Query(None, gt=0, description="Starting corpus (swp mode)"),
    monthly_withdrawal: Optional[float] = Query(None, gt=0, description="swp mode"),
):
    if mode == "sip":
        if amount is None or years is None:
            raise HTTPException(400, "sip needs amount and years.")
        return calc.project_sip(amount, years, annual_rate)
    if mode == "lumpsum":
        if amount is None or years is None:
            raise HTTPException(400, "lumpsum needs amount and years.")
        return calc.project_lumpsum(amount, years, annual_rate)
    if mode == "goal":
        if target is None or years is None:
            raise HTTPException(400, "goal needs target and years.")
        return calc.project_goal(target, years, annual_rate)
    if mode == "swp":
        if corpus is None or monthly_withdrawal is None:
            raise HTTPException(400, "swp needs corpus and monthly_withdrawal.")
        return calc.project_swp(corpus, monthly_withdrawal, annual_rate)
    raise HTTPException(400, f"Invalid mode '{mode}'.")
