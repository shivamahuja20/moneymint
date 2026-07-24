from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .db import Base, engine
from .routers import funds, sectors, flows, schemes

Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="MoneyMint API",
    description="Indian mutual fund analytics: all-schemes NAV data, returns, costs, sector rotation and FII/DII flows.",
    version="0.3.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # tighten to your frontend's origin before production
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(schemes.router)
app.include_router(funds.router)
app.include_router(sectors.router)
app.include_router(flows.router)


@app.get("/api/health")
def health():
    return {"status": "ok"}
