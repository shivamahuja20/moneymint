from sqlalchemy import (
    Column, String, Float, Date, ForeignKey, Integer, Boolean, BigInteger,
    Numeric, UniqueConstraint, Index,
)
from sqlalchemy.orm import relationship
from .db import Base


# ---------------------------------------------------------------------------
# Legacy tables (the original 10-fund frontend is built on these; kept working
# through Phase 3, will be retired when the all-schemes UI lands in Phase 5)
# ---------------------------------------------------------------------------

class Fund(Base):
    __tablename__ = "funds"

    id = Column(String, primary_key=True)          # slug, e.g. "hdfc-flexi-cap"
    amfi_code = Column(String, index=True)          # AMFI scheme code, for NAV lookups
    name = Column(String, nullable=False)
    amc = Column(String, nullable=False)            # e.g. "HDFC Mutual Fund"
    category = Column(String, nullable=False)       # e.g. "Equity - Flexi Cap"
    sector_focus = Column(String, nullable=False)   # "Diversified" or a specific sector bet
    nav = Column(Float)
    expense_ratio = Column(Float)                   # percent, e.g. 0.62
    exit_load = Column(String)                      # free text, e.g. "1% if redeemed < 365 days"
    aum_cr = Column(Float)                           # AUM in INR crore
    inception_date = Column(Date)

    returns = relationship("FundReturn", back_populates="fund", cascade="all, delete-orphan")


class FundReturn(Base):
    __tablename__ = "fund_returns"

    id = Column(Integer, primary_key=True, autoincrement=True)
    fund_id = Column(String, ForeignKey("funds.id"), index=True, nullable=False)
    period = Column(String, nullable=False)          # '1M' | '6M' | '1Y' | '3Y' | '5Y'
    fund_return = Column(Float, nullable=False)       # percent (CAGR for 3Y/5Y)
    benchmark_return = Column(Float, nullable=False)
    category_avg_return = Column(Float, nullable=False)
    as_of_date = Column(Date, nullable=False)

    fund = relationship("Fund", back_populates="returns")


class SectorDaily(Base):
    __tablename__ = "sector_daily"

    id = Column(Integer, primary_key=True, autoincrement=True)
    sector = Column(String, index=True, nullable=False)
    date = Column(Date, nullable=False)
    momentum_score = Column(Float, nullable=False)   # 0-100 composite
    return_1m = Column(Float, nullable=False)         # percent


class FlowDaily(Base):
    __tablename__ = "flow_daily"

    id = Column(Integer, primary_key=True, autoincrement=True)
    date = Column(Date, nullable=False, unique=True)
    fii_cr = Column(Float, nullable=False)             # net FII flow, INR crore
    dii_cr = Column(Float, nullable=False)             # net DII flow, INR crore


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
