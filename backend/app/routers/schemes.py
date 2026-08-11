"""
Phase 5: all-schemes explorer API.

Read-only surface over the Phase 3/4 tables (scheme_master, nav_history,
scheme_returns, scheme_risk, category_stats, benchmark_proxy). Honesty rule:
metrics that don't exist (no benchmark proxy for a category, history too short
for a period) come back as null — never faked.
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import text
from typing import Optional

from ..db import get_db
from .. import schemas, rolling

router = APIRouter(prefix="/api/schemes", tags=["schemes"])

SORT_COLUMNS = {
    "name": "m.name",
    "nav": "nav.nav",
    "1Y": "r1.ret",
    "3Y": "r3.ret",
    "5Y": "r5.ret",
    "sharpe": "rk.sharpe",
    "aum": "aum.aaum_cr",
}


# ---------------------------------------------------------------------------
# /facets — filter dropdown values (declared before /{code} so it isn't
# captured by the path-parameter route)
# ---------------------------------------------------------------------------
@router.get("/facets", response_model=schemas.FacetsResponse)
def facets(db: Session = Depends(get_db)):
    cats = db.execute(text(
        "SELECT category AS value, count(*) AS count FROM scheme_master "
        "WHERE is_active AND data_quality IS NULL AND category IS NOT NULL "
        "GROUP BY category ORDER BY category"
    )).mappings().all()
    amcs = db.execute(text(
        "SELECT amc AS value, count(*) AS count FROM scheme_master "
        "WHERE is_active AND data_quality IS NULL AND amc IS NOT NULL "
        "GROUP BY amc ORDER BY amc"
    )).mappings().all()
    return schemas.FacetsResponse(
        categories=[schemas.FacetValue(**c) for c in cats],
        amcs=[schemas.FacetValue(**a) for a in amcs],
    )


# ---------------------------------------------------------------------------
# /compare — up to 4 schemes side by side
# ---------------------------------------------------------------------------
@router.get("/compare", response_model=schemas.CompareResponse)
def compare(codes: str = Query(..., description="Comma-separated scheme codes, max 4"),
            db: Session = Depends(get_db)):
    code_list = [c.strip() for c in codes.split(",") if c.strip()]
    if not code_list:
        raise HTTPException(400, "No scheme codes provided.")
    if len(code_list) > 4:
        raise HTTPException(400, "Compare supports at most 4 schemes.")

    out = []
    for code in code_list:
        m = db.execute(text(
            "SELECT scheme_code, name, category, data_quality "
            "FROM scheme_master WHERE scheme_code=:c"
        ), {"c": code}).mappings().first()
        if not m:
            raise HTTPException(404, f"Unknown scheme code '{code}'.")
        out.append(schemas.CompareScheme(
            scheme_code=m["scheme_code"], name=m["name"], category=m["category"],
            data_quality=m["data_quality"],
            returns=_returns_for(db, code, m["category"]),
            risk=_risk_for(db, code),
        ))
    return schemas.CompareResponse(schemes=out)


# ---------------------------------------------------------------------------
# /rolling — rolling returns for one or many schemes
#
# Point-to-point returns depend entirely on their two end dates. Rolling returns
# compute the return from EVERY start date and show the distribution, which is the
# honest read of past performance. Free tools that offer this cap it at 3-5 funds;
# we hold every scheme's full daily history, so the cap here is only about latency.
# Declared before /{code} so the path isn't swallowed by the detail route.
# ---------------------------------------------------------------------------
MAX_ROLLING_FUNDS = 12


def _nav_rows(db, code):
    return db.execute(text(
        "SELECT date, nav FROM nav_history WHERE scheme_code=:c ORDER BY date"
    ), {"c": code}).all()


@router.get("/rolling", response_model=schemas.RollingResponse)
def rolling_returns(
    codes: str = Query(..., description=f"Comma-separated scheme codes, max {MAX_ROLLING_FUNDS}"),
    window: str = Query("3Y", description="1M|3M|6M|1Y|2Y|3Y|5Y|7Y|10Y"),
    points: bool = Query(True, description="Include the downsampled series for charting"),
    db: Session = Depends(get_db),
):
    if window not in rolling.WINDOW_DAYS:
        raise HTTPException(400, f"Invalid window '{window}'.")
    code_list = [c.strip() for c in codes.split(",") if c.strip()]
    if not code_list:
        raise HTTPException(400, "No scheme codes provided.")
    if len(code_list) > MAX_ROLLING_FUNDS:
        raise HTTPException(400, f"At most {MAX_ROLLING_FUNDS} schemes at a time.")
    window_days = rolling.WINDOW_DAYS[window]

    # benchmark proxy of the FIRST scheme's category, used as the comparison line
    first = db.execute(text(
        "SELECT category FROM scheme_master WHERE scheme_code=:c"), {"c": code_list[0]}
    ).mappings().first()
    if not first:
        raise HTTPException(404, f"Unknown scheme code '{code_list[0]}'.")
    bench = db.execute(text(
        "SELECT proxy_scheme_code, proxy_name, note FROM benchmark_proxy WHERE category=:cat"
    ), {"cat": first["category"]}).mappings().first()

    b_dates = b_rets = None
    if bench:
        b_dates, b_rets = rolling.rolling_series(
            _nav_rows(db, bench["proxy_scheme_code"]), window_days)

    out = []
    for code in code_list:
        m = db.execute(text(
            "SELECT scheme_code, name FROM scheme_master WHERE scheme_code=:c"), {"c": code}
        ).mappings().first()
        if not m:
            raise HTTPException(404, f"Unknown scheme code '{code}'.")
        d, r = rolling.rolling_series(_nav_rows(db, code), window_days)
        stats = rolling.distribution(r)
        beat = None
        if stats and b_dates is not None and code != (bench or {}).get("proxy_scheme_code"):
            beat = rolling.beat_rate(d, r, b_dates, b_rets)
        out.append(schemas.RollingFund(
            scheme_code=m["scheme_code"], name=m["name"],
            stats=schemas.RollingStats(**stats) if stats else None,
            beat_benchmark_pct=beat,
            points=[schemas.RollingPoint(**p) for p in rolling.downsample(d, r)] if points else [],
        ))

    return schemas.RollingResponse(
        window=window, annualised=window_days >= 365,
        benchmark=schemas.BenchmarkInfo(**bench) if bench else None,
        funds=out,
    )


# ---------------------------------------------------------------------------
# / — search / filter / sort / paginate
# ---------------------------------------------------------------------------
@router.get("", response_model=schemas.SchemeListResponse)
def list_schemes(
    q: Optional[str] = Query(None, description="Search name or AMC"),
    category: Optional[str] = None,
    amc: Optional[str] = None,
    plan_type: Optional[str] = None,
    option_type: Optional[str] = None,
    sort: str = Query("3Y", description="1Y|3Y|5Y|sharpe|nav|name"),
    order: str = Query("desc", description="asc|desc"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    db: Session = Depends(get_db),
):
    if sort not in SORT_COLUMNS:
        raise HTTPException(400, f"Invalid sort '{sort}'.")
    order_sql = "ASC" if order.lower() == "asc" else "DESC"

    # data_quality IS NULL hard-excludes stale / discontinuity-corrupted schemes
    # from the explorer so garbage metrics never surface or rank (see compute_metrics).
    where = ["m.is_active", "m.data_quality IS NULL"]
    params: dict = {}
    if q:
        where.append("(m.name ILIKE :q OR m.amc ILIKE :q)")
        params["q"] = f"%{q}%"
    if category:
        where.append("m.category = :category"); params["category"] = category
    if amc:
        where.append("m.amc = :amc"); params["amc"] = amc
    if plan_type:
        where.append("m.plan_type = :plan_type"); params["plan_type"] = plan_type
    if option_type:
        where.append("m.option_type = :option_type"); params["option_type"] = option_type
    where_sql = " AND ".join(where)

    total = db.execute(text(
        f"SELECT count(*) FROM scheme_master m WHERE {where_sql}"), params).scalar()

    sort_col = SORT_COLUMNS[sort]
    params["limit"] = page_size
    params["offset"] = (page - 1) * page_size
    rows = db.execute(text(f"""
        SELECT m.scheme_code, m.name, m.amc, m.category, m.plan_type, m.option_type,
               nav.nav, nav.date AS nav_date,
               r1.ret AS ret_1y, r3.ret AS ret_3y, r5.ret AS ret_5y,
               rk.sharpe AS sharpe_3y, rnk.percentile AS percentile_3y,
               aum.aaum_cr
        FROM scheme_master m
        LEFT JOIN LATERAL (
            SELECT nav, date FROM nav_history h
            WHERE h.scheme_code = m.scheme_code ORDER BY date DESC LIMIT 1
        ) nav ON true
        LEFT JOIN LATERAL (
            SELECT aaum_cr FROM scheme_aum a
            WHERE a.scheme_code = m.scheme_code ORDER BY as_of_date DESC LIMIT 1
        ) aum ON true
        LEFT JOIN scheme_returns r1 ON r1.scheme_code = m.scheme_code AND r1.period = '1Y'
        LEFT JOIN scheme_returns r3 ON r3.scheme_code = m.scheme_code AND r3.period = '3Y'
        LEFT JOIN scheme_returns r5 ON r5.scheme_code = m.scheme_code AND r5.period = '5Y'
        LEFT JOIN scheme_risk    rk ON rk.scheme_code = m.scheme_code AND rk.period = '3Y'
        LEFT JOIN rankings      rnk ON rnk.scheme_code = m.scheme_code AND rnk.period = '3Y'
        WHERE {where_sql}
        ORDER BY {sort_col} {order_sql} NULLS LAST, m.name ASC
        LIMIT :limit OFFSET :offset
    """), params).mappings().all()

    return schemas.SchemeListResponse(
        total=total, page=page, page_size=page_size,
        schemes=[schemas.SchemeListItem(**r) for r in rows],
    )


# ---------------------------------------------------------------------------
# /{code} — full detail
# ---------------------------------------------------------------------------
@router.get("/{code}", response_model=schemas.SchemeDetail)
def scheme_detail(code: str, db: Session = Depends(get_db)):
    m = db.execute(text("""
        SELECT scheme_code, name, amc, category, plan_type, option_type, isin,
               launch_date, data_quality
        FROM scheme_master WHERE scheme_code = :c
    """), {"c": code}).mappings().first()
    if not m:
        raise HTTPException(404, f"Unknown scheme code '{code}'.")

    nav = db.execute(text(
        "SELECT nav, date FROM nav_history WHERE scheme_code=:c ORDER BY date DESC LIMIT 1"
    ), {"c": code}).mappings().first()

    bench = db.execute(text(
        "SELECT proxy_scheme_code, proxy_name, note FROM benchmark_proxy WHERE category=:cat"
    ), {"cat": m["category"]}).mappings().first()

    cost = db.execute(text(
        "SELECT ter, as_of_date FROM scheme_costs WHERE scheme_code=:c "
        "ORDER BY as_of_date DESC LIMIT 1"
    ), {"c": code}).mappings().first()

    aum = db.execute(text(
        "SELECT aaum_cr, as_of_date FROM scheme_aum WHERE scheme_code=:c "
        "ORDER BY as_of_date DESC LIMIT 1"
    ), {"c": code}).mappings().first()

    return schemas.SchemeDetail(
        scheme_code=m["scheme_code"], name=m["name"], amc=m["amc"], category=m["category"],
        plan_type=m["plan_type"], option_type=m["option_type"], isin=m["isin"],
        launch_date=m["launch_date"],
        nav=nav["nav"] if nav else None,
        nav_date=nav["date"] if nav else None,
        data_quality=m["data_quality"],
        ter=cost["ter"] if cost else None,
        ter_as_of=cost["as_of_date"] if cost else None,
        aaum_cr=aum["aaum_cr"] if aum else None,
        aaum_as_of=aum["as_of_date"] if aum else None,
        benchmark=schemas.BenchmarkInfo(**bench) if bench else None,
        returns=_returns_for(db, code, m["category"]),
        risk=_risk_for(db, code),
        rankings=_rankings_for(db, code),
    )


# ---------------------------------------------------------------------------
# /{code}/nav — downsampled NAV series for the chart
# ---------------------------------------------------------------------------
RANGE_DAYS = {"1Y": 365, "3Y": 365 * 3, "5Y": 365 * 5, "max": None}
MAX_POINTS = 400


@router.get("/{code}/nav", response_model=schemas.NavSeriesResponse)
def scheme_nav(code: str, range: str = Query("3Y"), db: Session = Depends(get_db)):
    if range not in RANGE_DAYS:
        raise HTTPException(400, f"Invalid range '{range}'.")
    exists = db.execute(text(
        "SELECT 1 FROM scheme_master WHERE scheme_code=:c"), {"c": code}).first()
    if not exists:
        raise HTTPException(404, f"Unknown scheme code '{code}'.")

    params: dict = {"c": code}
    date_filter = ""
    days = RANGE_DAYS[range]
    if days is not None:
        date_filter = ("AND date >= (SELECT max(date) FROM nav_history WHERE scheme_code=:c) "
                       "- make_interval(days => :days)")
        params["days"] = days

    n = db.execute(text(
        f"SELECT count(*) FROM nav_history WHERE scheme_code=:c {date_filter}"), params).scalar()
    stride = max(1, (n // MAX_POINTS) + (1 if n % MAX_POINTS else 0))

    # stride-sample by row number, always keeping the most recent point
    rows = db.execute(text(f"""
        SELECT date, nav FROM (
            SELECT date, nav, row_number() OVER (ORDER BY date DESC) - 1 AS rn
            FROM nav_history WHERE scheme_code=:c {date_filter}
        ) s WHERE rn % :stride = 0 ORDER BY date ASC
    """), {**params, "stride": stride}).mappings().all()

    return schemas.NavSeriesResponse(
        scheme_code=code, range=range,
        points=[schemas.NavPoint(date=r["date"], nav=r["nav"]) for r in rows],
    )


# ---------------------------------------------------------------------------
# /{code}/holdings — latest monthly portfolio (Phase 8)
# ---------------------------------------------------------------------------
@router.get("/{code}/holdings", response_model=schemas.HoldingsResponse)
def scheme_holdings(code: str, limit: int = Query(25, ge=1, le=200),
                    db: Session = Depends(get_db)):
    exists = db.execute(text("SELECT 1 FROM scheme_master WHERE scheme_code=:c"),
                        {"c": code}).first()
    if not exists:
        raise HTTPException(404, f"Unknown scheme code '{code}'.")

    as_of = db.execute(text(
        "SELECT max(as_of_date) FROM holdings WHERE scheme_code=:c"), {"c": code}).scalar()
    if as_of is None:
        # honest empty shape — holdings not available for this scheme yet
        return schemas.HoldingsResponse(scheme_code=code, as_of_date=None,
                                        holdings=[], sector_allocation=[])

    holdings = db.execute(text(
        "SELECT instrument_name, isin, sector, pct_of_aum, market_value_cr FROM holdings "
        "WHERE scheme_code=:c AND as_of_date=:d ORDER BY pct_of_aum DESC LIMIT :lim"),
        {"c": code, "d": as_of, "lim": limit}).mappings().all()
    sectors = db.execute(text(
        "SELECT sector, pct_of_aum FROM sector_allocation WHERE scheme_code=:c AND as_of_date=:d "
        "ORDER BY pct_of_aum DESC"), {"c": code, "d": as_of}).mappings().all()

    return schemas.HoldingsResponse(
        scheme_code=code, as_of_date=as_of,
        holdings=[schemas.HoldingRow(**h) for h in holdings],
        sector_allocation=[schemas.SectorRow(**s) for s in sectors],
    )


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def _returns_for(db, code, category):
    """All-period returns joined to the category proxy's returns and category avg."""
    rows = db.execute(text("""
        SELECT r.period, r.ret AS fund_return, pr.ret AS benchmark_return,
               cs.avg_return AS category_avg_return
        FROM scheme_returns r
        LEFT JOIN benchmark_proxy bp ON bp.category = :cat
        LEFT JOIN scheme_returns pr ON pr.scheme_code = bp.proxy_scheme_code AND pr.period = r.period
        LEFT JOIN category_stats cs ON cs.category = :cat AND cs.period = r.period
        WHERE r.scheme_code = :c
        ORDER BY array_position(ARRAY['1M','3M','6M','1Y','3Y','5Y','10Y'], r.period)
    """), {"c": code, "cat": category}).mappings().all()
    return [schemas.SchemeReturnRow(**r) for r in rows]


def _risk_for(db, code):
    rows = db.execute(text("""
        SELECT period, stdev, sharpe, beta, alpha, max_drawdown
        FROM scheme_risk WHERE scheme_code = :c
        ORDER BY array_position(ARRAY['1Y','3Y','5Y'], period)
    """), {"c": code}).mappings().all()
    return [schemas.SchemeRiskRow(**r) for r in rows]


def _rankings_for(db, code):
    rows = db.execute(text("""
        SELECT period, rank_in_category, category_size, percentile
        FROM rankings WHERE scheme_code = :c
        ORDER BY array_position(ARRAY['1M','3M','6M','1Y','3Y','5Y','10Y'], period)
    """), {"c": code}).mappings().all()
    return [schemas.RankingRow(**r) for r in rows]
