from sqlalchemy import Column, String, Float, Date, ForeignKey, Integer
from sqlalchemy.orm import relationship
from .db import Base


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
