"""
Seeds the database with realistic sample data so every endpoint is testable
before the real AMFI/NSDL ingestion is wired up.

Run: ./venv/bin/python seed.py
"""
import datetime
from app.db import Base, engine, SessionLocal
from app import models

Base.metadata.drop_all(bind=engine)
Base.metadata.create_all(bind=engine)

db = SessionLocal()
today = datetime.date.today()

FUNDS = [
    dict(id="hdfc-flexi-cap", amfi_code="118955", name="HDFC Flexi Cap Fund", amc="HDFC Mutual Fund",
         category="Equity - Flexi Cap", sector_focus="Diversified", nav=1842.30, expense_ratio=0.68,
         exit_load="1% if redeemed < 365 days", aum_cr=68450.0, returns_1y=(28.6, 21.0, 23.5)),
    dict(id="parag-parikh-flexi", amfi_code="122639", name="Parag Parikh Flexi Cap Fund", amc="PPFAS Mutual Fund",
         category="Equity - Flexi Cap", sector_focus="Diversified", nav=95.14, expense_ratio=0.62,
         exit_load="2% if redeemed < 365 days", aum_cr=89210.0, returns_1y=(24.1, 21.0, 23.5)),
    dict(id="icici-tech", amfi_code="120594", name="ICICI Prudential Technology Fund", amc="ICICI Prudential",
         category="Equity - Sectoral (Technology)", sector_focus="IT Services", nav=214.87, expense_ratio=1.05,
         exit_load="1% if redeemed < 15 days", aum_cr=13540.0, returns_1y=(31.8, 24.2, 26.0)),
    dict(id="sbi-banking-fin", amfi_code="133859", name="SBI Banking & Financial Services Fund", amc="SBI Mutual Fund",
         category="Equity - Sectoral (Banking)", sector_focus="Banking & Fin.", nav=38.62, expense_ratio=0.95,
         exit_load="1% if redeemed < 12 months", aum_cr=7620.0, returns_1y=(19.4, 18.0, 17.2)),
    dict(id="nippon-pharma", amfi_code="118759", name="Nippon India Pharma Fund", amc="Nippon India MF",
         category="Equity - Sectoral (Pharma)", sector_focus="Pharma", nav=412.55, expense_ratio=1.12,
         exit_load="1% if redeemed < 30 days", aum_cr=8930.0, returns_1y=(22.7, 17.5, 18.1)),
    dict(id="quant-infra", amfi_code="120833", name="Quant Infrastructure Fund", amc="Quant Mutual Fund",
         category="Equity - Sectoral (Infra)", sector_focus="Capital Goods", nav=48.90, expense_ratio=1.28,
         exit_load="1% if redeemed < 90 days", aum_cr=4120.0, returns_1y=(35.2, 26.4, 27.9)),
    dict(id="hdfc-defence", amfi_code="151750", name="HDFC Defence Fund", amc="HDFC Mutual Fund",
         category="Equity - Sectoral (Defence)", sector_focus="Capital Goods", nav=27.44, expense_ratio=1.35,
         exit_load="1% if redeemed < 6 months", aum_cr=6890.0, returns_1y=(38.9, 26.4, 27.9)),
    dict(id="axis-realty", amfi_code="150532", name="Tata Housing Opportunities Fund", amc="Tata Mutual Fund",
         category="Equity - Thematic (Housing)", sector_focus="Realty", nav=16.11, expense_ratio=2.44,
         exit_load="1% if redeemed < 365 days", aum_cr=472.9, returns_1y=(33.5, 28.1, 27.0)),
    dict(id="tata-fmcg", amfi_code="135805", name="Tata India Consumer Fund", amc="Tata Mutual Fund",
         category="Equity - Thematic (Consumption)", sector_focus="FMCG", nav=46.44, expense_ratio=1.08,
         exit_load="0.25% if redeemed < 30 days", aum_cr=2590.6, returns_1y=(9.8, 12.4, 11.6)),
    dict(id="dsp-energy", amfi_code="119028", name="DSP Natural Resources & Energy Fund", amc="DSP Mutual Fund",
         category="Equity - Sectoral (Energy)", sector_focus="Energy", nav=88.30, expense_ratio=1.22,
         exit_load="1% if redeemed < 365 days", aum_cr=2980.0, returns_1y=(6.4, 12.0, 10.9)),
]

for f in FUNDS:
    fund = models.Fund(
        id=f["id"], amfi_code=f["amfi_code"], name=f["name"], amc=f["amc"],
        category=f["category"], sector_focus=f["sector_focus"], nav=f["nav"],
        expense_ratio=f["expense_ratio"], exit_load=f["exit_load"], aum_cr=f["aum_cr"],
        inception_date=today - datetime.timedelta(days=365 * 6),
    )
    db.add(fund)

    fund_ret, bench_ret, cat_ret = f["returns_1y"]
    db.add(models.FundReturn(fund_id=f["id"], period="1Y", fund_return=fund_ret,
                              benchmark_return=bench_ret, category_avg_return=cat_ret, as_of_date=today))
    # rough shorter-period figures derived from the 1Y number, just for demo completeness
    db.add(models.FundReturn(fund_id=f["id"], period="1M", fund_return=round(fund_ret / 11, 2),
                              benchmark_return=round(bench_ret / 11, 2), category_avg_return=round(cat_ret / 11, 2),
                              as_of_date=today))
    db.add(models.FundReturn(fund_id=f["id"], period="3Y", fund_return=round(fund_ret * 0.78, 2),
                              benchmark_return=round(bench_ret * 0.75, 2), category_avg_return=round(cat_ret * 0.76, 2),
                              as_of_date=today))

SECTORS = [
    ("IT Services", 78, 6.4), ("Banking & Fin.", 65, 3.1), ("Capital Goods", 82, 8.9),
    ("FMCG", 34, -1.2), ("Auto", 58, 2.4), ("Pharma", 71, 5.0),
    ("Metals & Mining", 45, -0.6), ("Realty", 88, 11.2), ("Energy", 29, -3.4), ("Telecom", 52, 1.1),
]
for name, momentum, ret1m in SECTORS:
    db.add(models.SectorDaily(sector=name, date=today, momentum_score=momentum, return_1m=ret1m))

FLOWS = [
    (-1240, 2100), (-880, 1650), (1560, 980), (2340, 1120),
    (-560, 1980), (1890, 1340), (2410, 890),
]
for i, (fii, dii) in enumerate(FLOWS):
    db.add(models.FlowDaily(date=today - datetime.timedelta(days=(len(FLOWS) - i) * 30), fii_cr=fii, dii_cr=dii))

db.commit()
db.close()
print("Seeded: 10 funds, 10 sectors, 7 months of flow data.")
