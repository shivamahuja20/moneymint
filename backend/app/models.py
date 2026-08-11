from sqlalchemy import (
    Column, String, Float, Date, ForeignKey, Integer, Boolean, BigInteger,
    Numeric, UniqueConstraint, Index,
)
from sqlalchemy.orm import relationship
from .db import Base


# The original 10-fund tables (funds / fund_returns / sector_daily / flow_daily)
# were removed once the all-schemes UI replaced them. They carried seeded
# placeholder values — fabricated expense ratios, exit loads, AUM, sector
# "momentum" scores and FII/DII flows — that the app must never present as real.
# Real TER and AAUM now live in scheme_costs (AMFI), returns/risk in
# scheme_returns / scheme_risk.


# ---------------------------------------------------------------------------
# Phase 2 schema: the all-schemes world
# ---------------------------------------------------------------------------

class SchemeMaster(Base):
    __tablename__ = "scheme_master"

    scheme_code = Column(String, primary_key=True)     # AMFI scheme code
    name = Column(String, nullable=False)
    amc = Column(String, index=True)
    scheme_type = Column(String)                        # "Open Ended Schemes" etc.
    category = Column(String, index=True)               # "Equity Scheme - Flexi Cap Fund"
    sub_category = Column(String)
    plan_type = Column(String)                          # 'Direct' | 'Regular' | None
    option_type = Column(String)                        # 'Growth' | 'IDCW' | None
    isin = Column(String)
    launch_date = Column(Date)
    benchmark_name = Column(String)
    risk_level = Column(String)
    is_active = Column(Boolean, nullable=False, default=True, index=True)
    # data honesty: NULL = usable; set nightly by compute_metrics.flag_data_quality.
    #   'stale'         -> latest NAV is too old to present as current (dead/wound-up)
    #   'discontinuity' -> a recent non-economic NAV jump (side-pocket) corrupts metrics
    # Non-NULL schemes are hard-excluded from the explorer list/facets/rankings.
    data_quality = Column(String, index=True)
    fund_group_id = Column(String, index=True)          # links Direct/Regular x Growth/IDCW variants
    # backfill bookkeeping — makes the MFAPI historical backfill resumable
    backfill_status = Column(String, index=True)        # None | 'done' | 'no_data' | 'error'
    backfill_date = Column(Date)
    first_seen = Column(Date)
    last_seen = Column(Date, index=True)


# NOTE: nav_history is a *partitioned* table (PARTITION BY RANGE (date), one
# partition per year). SQLAlchemy's create_all cannot express that, so the table
# is created by raw DDL in setup_db.py and deliberately has no ORM model.
# Ingestion writes to it with SQLAlchemy Core / text() statements.


class SchemeReturn(Base):
    __tablename__ = "scheme_returns"      # computed nightly (Phase 4), rebuild-safe

    scheme_code = Column(String, primary_key=True)
    period = Column(String, primary_key=True)           # '1M' | '6M' | '1Y' | '3Y' | '5Y' | '10Y'
    ret = Column(Float, nullable=False)                  # percent (CAGR for >=3Y)
    as_of_date = Column(Date, nullable=False)


class SchemeRisk(Base):
    __tablename__ = "scheme_risk"          # computed nightly (Phase 4)

    scheme_code = Column(String, primary_key=True)
    period = Column(String, primary_key=True)           # '1Y' | '3Y' | '5Y'
    stdev = Column(Float)
    sharpe = Column(Float)
    beta = Column(Float)
    alpha = Column(Float)
    max_drawdown = Column(Float)
    as_of_date = Column(Date)


class CategoryStats(Base):
    __tablename__ = "category_stats"       # computed nightly (Phase 6)

    category = Column(String, primary_key=True)
    period = Column(String, primary_key=True)
    avg_return = Column(Float)
    median_return = Column(Float)
    scheme_count = Column(Integer)
    as_of_date = Column(Date)


class Ranking(Base):
    __tablename__ = "rankings"             # computed nightly (Phase 6)

    scheme_code = Column(String, primary_key=True)
    period = Column(String, primary_key=True)
    category = Column(String)
    rank_in_category = Column(Integer)
    category_size = Column(Integer)
    percentile = Column(Float)
    as_of_date = Column(Date)


class BenchmarkProxy(Base):
    __tablename__ = "benchmark_proxy"      # category -> index-fund NAV used as TRI proxy

    category = Column(String, primary_key=True)
    proxy_scheme_code = Column(String, nullable=False)
    proxy_name = Column(String)
    note = Column(String)


class SchemeCost(Base):
    __tablename__ = "scheme_costs"         # TER history date-stamped (Phase 8 fills)

    id = Column(Integer, primary_key=True, autoincrement=True)
    scheme_code = Column(String, index=True, nullable=False)
    as_of_date = Column(Date, nullable=False)
    ter = Column(Float)                     # percent
    exit_load = Column(String)
    min_investment = Column(Float)

    __table_args__ = (UniqueConstraint("scheme_code", "as_of_date", name="uq_scheme_costs_code_date"),)


class SchemeAUM(Base):
    __tablename__ = "scheme_aum"           # quarterly average AUM from AMFI (Phase 8)

    id = Column(Integer, primary_key=True, autoincrement=True)
    scheme_code = Column(String, index=True, nullable=False)
    as_of_date = Column(Date, nullable=False)     # quarter-end the AAUM is for
    aaum_cr = Column(Float)                        # average AUM for the period, INR crore

    __table_args__ = (UniqueConstraint("scheme_code", "as_of_date", name="uq_scheme_aum"),)


class Holding(Base):
    __tablename__ = "holdings"             # Phase 8 fills

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    scheme_code = Column(String, index=True, nullable=False)
    as_of_date = Column(Date, nullable=False)
    instrument_name = Column(String, nullable=False)
    isin = Column(String)
    sector = Column(String)
    pct_of_aum = Column(Float)
    market_value_cr = Column(Float)

    __table_args__ = (Index("ix_holdings_code_date", "scheme_code", "as_of_date"),)


class SectorAllocation(Base):
    __tablename__ = "sector_allocation"    # Phase 8 fills

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    scheme_code = Column(String, index=True, nullable=False)
    as_of_date = Column(Date, nullable=False)
    sector = Column(String, nullable=False)
    pct_of_aum = Column(Float)

    __table_args__ = (UniqueConstraint("scheme_code", "as_of_date", "sector", name="uq_sector_alloc"),)
