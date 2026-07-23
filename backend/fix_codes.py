import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.db import SessionLocal
from app import models

CORRECTIONS = {
    "hdfc-defence": "151750",
    "quant-infra": "120833",
    "axis-realty": "REPLACE_ME",
    "dsp-energy": "REPLACE_ME",
}

db = SessionLocal()
for fund_id, code in CORRECTIONS.items():
    if code == "REPLACE_ME":
        print(f"Skipping {fund_id} - fill in the real code first.")
        continue
    fund = db.query(models.Fund).filter(models.Fund.id == fund_id).first()
    if fund:
        fund.amfi_code = code
        print(f"Updated {fund_id} -> {code}")
    else:
        print(f"No fund found with id {fund_id}")
db.commit()
db.close()
