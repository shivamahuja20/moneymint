from pydantic import BaseModel
from datetime import date
from typing import Optional


class FundListItem(BaseModel):
    id: str
    name: str
    amc: str
    category: str
    sector_focus: str
    nav: float
    return_1y: Optional[float] = None
    benchmark_1y: Optional[float] = None
    expense_ratio: Optional[float] = None

    class Config:
        from_attributes = True


class FundListResponse(BaseModel):
    sectors: list[str]
    funds: list[FundListItem]
    nav_as_of: Optional[date] = None


class ReturnRow(BaseModel):
    period: str
    fund_return: float
    benchmark_return: float
    category_avg_return: float
    as_of_date: date

    class Config:
        from_attributes = True


class FundDetail(BaseModel):
    id: str
    name: str
    amc: str
    category: str
    sector_focus: str
    nav: float
    expense_ratio: float
    exit_load: str
    aum_cr: float
    returns: list[ReturnRow]

    class Config:
        from_attributes = True


class SectorSummary(BaseModel):
    sector: str
    momentum_score: float
    return_1m: float
    date: date

    class Config:
        from_attributes = True


class FlowPoint(BaseModel):
    date: date
    fii_cr: float
    dii_cr: float

    class Config:
        from_attributes = True
