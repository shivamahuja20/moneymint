from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from ..db import get_db
from .. import models, schemas

router = APIRouter(prefix="/api/flows", tags=["flows"])


@router.get("", response_model=list[schemas.FlowPoint])
def list_flows(days: int = Query(180, le=730), db: Session = Depends(get_db)):
    """Recent net FII/DII flow history, most recent last (chart-ready order)."""
    rows = (
        db.query(models.FlowDaily)
        .order_by(models.FlowDaily.date.desc())
        .limit(days)
        .all()
    )
    rows.reverse()
    return [schemas.FlowPoint.model_validate(r) for r in rows]
