from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .db import Base, engine
from .routers import funds, sectors, flows

Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="Mutual Fund Analyser API",
    description="Fund performance, costs, sector rotation and FII/DII flow data.",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # tighten to your frontend's origin before production
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(funds.router)
app.include_router(sectors.router)
app.include_router(flows.router)


@app.get("/api/health")
def health():
    return {"status": "ok"}
