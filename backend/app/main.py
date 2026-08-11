import datetime

from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.orm import Session

from .db import Base, engine, get_db
from .routers import schemes, calculators

Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="MoneyMint API",
    description="Indian mutual fund analytics: all-schemes NAV, returns, risk, "
                "rankings, costs, holdings and calculators.",
    version="0.4.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # tighten to your frontend's origin before production
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(schemes.router)
app.include_router(calculators.router)


@app.get("/api/health")
def health():
    return {"status": "ok"}


# Freshness thresholds (days). NAV publishes every business day, so >4 days old
# means the nightly job stopped. Holdings are monthly (SEBI deadline the 10th),
# costs quarterly-ish — allow a generous margin before crying wolf.
STALE_AFTER = {"nav": 4, "holdings": 45, "costs": 100}


@app.get("/api/health/data")
def data_health(db: Session = Depends(get_db)):
    """Freshness of each ingested dataset.

    This exists because the scheduled jobs fail SILENTLY: cron's own errors go to
    a system mail file nobody reads, and a job that never starts writes nothing to
    its log. A stale-data check that lives in the app is the one place a failure
    can't hide — the UI shows a banner off the back of this.
    """
    today = datetime.date.today()
    sources = {
        "nav": "SELECT max(date) FROM nav_history",
        "holdings": "SELECT max(as_of_date) FROM holdings",
        "costs": "SELECT max(as_of_date) FROM scheme_costs",
    }
    out, any_stale = {}, False
    for name, sql in sources.items():
        latest = db.execute(text(sql)).scalar()
        age = (today - latest).days if latest else None
        stale = age is None or age > STALE_AFTER[name]
        any_stale = any_stale or stale
        out[name] = {"latest": latest.isoformat() if latest else None,
                     "age_days": age, "stale": stale,
                     "stale_after_days": STALE_AFTER[name]}
    return {"stale": any_stale, "checked_on": today.isoformat(), "sources": out}
