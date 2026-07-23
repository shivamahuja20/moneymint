from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import distinct
from typing import Optional

from ..db import get_db
from .. import models, schemas

router = APIRouter(prefix="/api/funds", tags=["funds"])


@router.get("", response_model=schemas.FundListResponse)
def list_funds(
    sector: Optional[str] = Query(None, description="Filter by sector_focus, e.g. 'IT Services'"),
    sort: str = Query("return_1y", description="'return_1y' | 'nav' | 'expense_ratio'"),
    limit: int = Query(50, le=200),
    db: Session = Depends(get_db),
):
    """
    Landing page endpoint: every fund with its 1Y return, grouped/filterable by sector.
    """
    q = db.query(models.Fund)
    if sector:
        q = q.filter(models.Fund.sector_focus == sector)
    funds = q.all()

    sectors = [r[0] for r in db.query(distinct(models.Fund.sector_focus)).all()]

    items = []
    for f in funds:
        one_yr = (
            db.query(models.FundReturn)
            .filter(models.FundReturn.fund_id == f.id, models.FundReturn.period == "1Y")
            .order_by(models.FundReturn.as_of_date.desc())
            .first()
        )
        items.append(
            schemas.FundListItem(
                id=f.id,
                name=f.name,
                amc=f.amc,
                category=f.category,
                sector_focus=f.sector_focus,
                nav=f.nav,
                return_1y=one_yr.fund_return if one_yr else None,
                benchmark_1y=one_yr.benchmark_return if one_yr else None,
                expense_ratio=f.expense_ratio,
            )
        )

    reverse = sort in ("return_1y",)
    items.sort(key=lambda x: (getattr(x, sort) if getattr(x, sort) is not None else -999), reverse=reverse)
    items = items[:limit]

    return schemas.FundListResponse(sectors=sorted(sectors), funds=items)


@router.get("/{fund_id}", response_model=schemas.FundDetail)
def get_fund(fund_id: str, db: Session = Depends(get_db)):
    f = db.query(models.Fund).filter(models.Fund.id == fund_id).first()
    if not f:
        raise HTTPException(status_code=404, detail=f"No fund with id '{fund_id}'")

    returns = (
        db.query(models.FundReturn)
        .filter(models.FundReturn.fund_id == fund_id)
        .order_by(models.FundReturn.as_of_date.desc())
        .all()
    )

    return schemas.FundDetail(
        id=f.id, name=f.name, amc=f.amc, category=f.category,
        sector_focus=f.sector_focus, nav=f.nav, expense_ratio=f.expense_ratio,
        exit_load=f.exit_load, aum_cr=f.aum_cr,
        returns=[schemas.ReturnRow.model_validate(r) for r in returns],
    )
