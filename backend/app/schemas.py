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


# ---------- Phase 5: all-schemes explorer ----------

class SchemeListItem(BaseModel):
    scheme_code: str
    name: str
    amc: Optional[str] = None
    category: Optional[str] = None
    plan_type: Optional[str] = None
    option_type: Optional[str] = None
    nav: Optional[float] = None
    nav_date: Optional[date] = None
    ret_1y: Optional[float] = None
    ret_3y: Optional[float] = None
    ret_5y: Optional[float] = None
    sharpe_3y: Optional[float] = None
    percentile_3y: Optional[float] = None   # category standing on 3Y return, 100 = best
    aaum_cr: Optional[float] = None          # latest quarterly average AUM, INR crore


class SchemeListResponse(BaseModel):
    total: int
    page: int
    page_size: int
    schemes: list[SchemeListItem]


class FacetValue(BaseModel):
    value: str
    count: int


class FacetsResponse(BaseModel):
    categories: list[FacetValue]
    amcs: list[FacetValue]


class SchemeReturnRow(BaseModel):
    period: str
    fund_return: Optional[float] = None
    benchmark_return: Optional[float] = None
    category_avg_return: Optional[float] = None


class SchemeRiskRow(BaseModel):
    period: str
    stdev: Optional[float] = None
    sharpe: Optional[float] = None
    beta: Optional[float] = None
    alpha: Optional[float] = None
    max_drawdown: Optional[float] = None


class BenchmarkInfo(BaseModel):
    proxy_scheme_code: str
    proxy_name: Optional[str] = None
    note: Optional[str] = None


class RankingRow(BaseModel):
    period: str
    rank_in_category: Optional[int] = None
    category_size: Optional[int] = None
    percentile: Optional[float] = None   # 0-100, 100 = best in category


class SchemeDetail(BaseModel):
    scheme_code: str
    name: str
    amc: Optional[str] = None
    category: Optional[str] = None
    plan_type: Optional[str] = None
    option_type: Optional[str] = None
    isin: Optional[str] = None
    launch_date: Optional[date] = None
    nav: Optional[float] = None
    nav_date: Optional[date] = None
    data_quality: Optional[str] = None   # None=ok | 'stale' | 'discontinuity'
    ter: Optional[float] = None           # latest real TER % from AMFI (null if unknown)
    ter_as_of: Optional[date] = None
    aaum_cr: Optional[float] = None        # latest quarterly average AUM, INR crore
    aaum_as_of: Optional[date] = None
    benchmark: Optional[BenchmarkInfo] = None
    returns: list[SchemeReturnRow]
    risk: list[SchemeRiskRow]
    rankings: list[RankingRow]


class NavPoint(BaseModel):
    date: date
    nav: float


class NavSeriesResponse(BaseModel):
    scheme_code: str
    range: str
    points: list[NavPoint]


class CompareScheme(BaseModel):
    scheme_code: str
    name: str
    category: Optional[str] = None
    data_quality: Optional[str] = None   # None=ok | 'stale' | 'discontinuity'
    returns: list[SchemeReturnRow]
    risk: list[SchemeRiskRow]


class CompareResponse(BaseModel):
    schemes: list[CompareScheme]


class HoldingRow(BaseModel):
    instrument_name: str
    isin: Optional[str] = None
    sector: Optional[str] = None
    pct_of_aum: Optional[float] = None
    market_value_cr: Optional[float] = None


class SectorRow(BaseModel):
    sector: str
    pct_of_aum: float


class HoldingsResponse(BaseModel):
    scheme_code: str
    as_of_date: Optional[date] = None
    holdings: list[HoldingRow]
    sector_allocation: list[SectorRow]
