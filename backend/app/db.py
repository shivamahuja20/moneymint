"""
Database connection.

Defaults to the local PostgreSQL `moneymint` database (Homebrew postgresql@17).
Override with the DATABASE_URL env var if needed, e.g. to point at the old
SQLite file: DATABASE_URL=sqlite:///./fund_analyser.db
"""
import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+psycopg2://localhost:5432/moneymint")

connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, connect_args=connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
