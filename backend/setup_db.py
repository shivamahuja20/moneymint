"""
One-time database setup for the PostgreSQL `moneymint` database.

Creates every table from app/models.py, plus the partitioned nav_history table
(one partition per year — SQLAlchemy can't express native partitioning, so it's
raw DDL here). Safe to rerun: everything is IF NOT EXISTS.

Run: ./venv/bin/python setup_db.py
"""
import datetime
from sqlalchemy import text

from app.db import Base, engine
from app import models  # noqa: F401  (registers all ORM tables on Base)

FIRST_YEAR = 2006   # AMFI/MFAPI history goes back to ~2006
LAST_YEAR = datetime.date.today().year + 1


def create_nav_history(conn):
    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS nav_history (
            scheme_code varchar NOT NULL,
            date        date    NOT NULL,
            nav         double precision NOT NULL,
            PRIMARY KEY (scheme_code, date)
        ) PARTITION BY RANGE (date);
    """))
    for year in range(FIRST_YEAR, LAST_YEAR + 1):
        conn.execute(text(f"""
            CREATE TABLE IF NOT EXISTS nav_history_y{year}
            PARTITION OF nav_history
            FOR VALUES FROM ('{year}-01-01') TO ('{year + 1}-01-01');
        """))
    # catch-all for any pre-2006 stragglers so inserts never fail
    conn.execute(text(f"""
        CREATE TABLE IF NOT EXISTS nav_history_early
        PARTITION OF nav_history
        FOR VALUES FROM ('1990-01-01') TO ('{FIRST_YEAR}-01-01');
    """))
    conn.execute(text(
        "CREATE INDEX IF NOT EXISTS ix_nav_history_date ON nav_history (date);"
    ))


def main():
    Base.metadata.create_all(bind=engine)
    with engine.begin() as conn:
        create_nav_history(conn)
    print("Schema created (ORM tables + partitioned nav_history "
          f"{FIRST_YEAR}-{LAST_YEAR}).")


if __name__ == "__main__":
    main()
