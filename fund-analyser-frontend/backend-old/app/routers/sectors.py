from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func

from ..db import get_db
from .. import models, schemas

router = APIRouter(prefix="/api/sectors", tags=["sectors"])


@router.get("", response_model=list[schemas.SectorSummary])
def list_sectors(db: Session = Depends(get_db)):
    """Latest momentum score + 1M return per sector, for the rotation grid."""
    latest_date = db.query(func.max(models.SectorDaily.date)).scalar()
    if not latest_date:
        return []
    rows = db.query(models.SectorDaily).filter(models.SectorDaily.date == latest_date).all()
    return [schemas.SectorSummary.model_validate(r) for r in rows]
