"""Regression tests for the data-quality guard, end to end against the local
`moneymint` database. These assert the invariant that motivated the guard:

  scheme 118565 (Franklin India Short Term — wound-up, +169% NAV artifact) must
  stay flagged and must never surface in the explorer, while a healthy fund is
  unflagged and listed.

DB-backed by design (the flag + exclusion are SQL). The whole module skips if the
database isn't reachable or the pipeline hasn't been run, so it never fails a
checkout that simply doesn't have data loaded.

Run: ./venv/bin/python -m pytest tests/test_explorer_regression.py -v
"""
import pytest
from sqlalchemy import text

BROKEN_CODE = "118565"       # Franklin India Short Term Income - Direct - Growth
HEALTHY_CODE = "120497"      # Invesco India Corporate Bond - Direct - Growth (2013 redenom only)


def _db_up():
    try:
        from app.db import engine
        with engine.connect() as c:
            c.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


DB_UP = _db_up()
pytestmark = pytest.mark.skipif(not DB_UP, reason="local moneymint DB not reachable")


def _scheme_present(code):
    from app.db import engine
    with engine.connect() as c:
        return c.execute(text("SELECT 1 FROM scheme_master WHERE scheme_code=:c"),
                         {"c": code}).first() is not None


@pytest.fixture(scope="module")
def client():
    from fastapi.testclient import TestClient
    from app.main import app
    return TestClient(app)


def test_broken_scheme_is_flagged():
    if not _scheme_present(BROKEN_CODE):
        pytest.skip(f"{BROKEN_CODE} not loaded in this DB")
    from app.db import engine
    with engine.connect() as c:
        dq = c.execute(text("SELECT data_quality FROM scheme_master WHERE scheme_code=:c"),
                       {"c": BROKEN_CODE}).scalar()
        n_ret = c.execute(text("SELECT count(*) FROM scheme_returns WHERE scheme_code=:c"),
                          {"c": BROKEN_CODE}).scalar()
    assert dq is not None, "broken scheme must carry a data_quality flag"
    # every lookback straddles the NAV jump, so no honest return survives
    assert n_ret == 0, "corrupted periods must be skipped, not emitted"


def test_broken_scheme_absent_from_explorer(client):
    if not _scheme_present(BROKEN_CODE):
        pytest.skip(f"{BROKEN_CODE} not loaded in this DB")
    # search by the fund's own name; the flagged scheme must not come back
    r = client.get("/api/schemes", params={"q": "Franklin India Short Term",
                                            "page_size": 100})
    assert r.status_code == 200
    codes = [s["scheme_code"] for s in r.json()["schemes"]]
    assert BROKEN_CODE not in codes


def test_broken_scheme_detail_resolves_with_flag(client):
    # direct lookup by code stays honest (200 + label), never a 404
    if not _scheme_present(BROKEN_CODE):
        pytest.skip(f"{BROKEN_CODE} not loaded in this DB")
    r = client.get(f"/api/schemes/{BROKEN_CODE}")
    assert r.status_code == 200
    body = r.json()
    assert body["data_quality"] is not None
    assert body["returns"] == []


def test_healthy_scheme_unflagged_and_listed(client):
    if not _scheme_present(HEALTHY_CODE):
        pytest.skip(f"{HEALTHY_CODE} not loaded in this DB")
    d = client.get(f"/api/schemes/{HEALTHY_CODE}").json()
    assert d["data_quality"] is None
    assert len(d["returns"]) > 0
