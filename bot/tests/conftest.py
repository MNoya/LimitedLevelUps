import os
import sys
from pathlib import Path

import pytest
from dotenv import dotenv_values
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker
from testcontainers.postgres import PostgresContainer

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from bot.models import Base  # noqa: E402


@pytest.fixture(scope="session")
def postgres_url():
    """TEST_DATABASE_URL reuses an already-running Postgres and skips the container start, which otherwise costs every
    run about 1.6s. Reading .env by value keeps the rest of it out of os.environ, so local runs match CI."""
    env_file = dotenv_values(REPO_ROOT / ".env")
    configured = os.environ.get("TEST_DATABASE_URL") or env_file.get("TEST_DATABASE_URL")
    if configured:
        os.environ["DATABASE_URL"] = verified_test_database(configured)
        yield configured
        return
    with PostgresContainer("postgres:17-alpine") as pg:
        url = pg.get_connection_url()
        os.environ["DATABASE_URL"] = url
        yield url


@pytest.fixture(scope="session")
def engine(postgres_url):
    """One engine and one schema for the whole run: per-test isolation comes from clean_db, which is far cheaper than
    rebuilding the schema for every test."""
    engine = create_engine(postgres_url)
    Base.metadata.create_all(engine)
    try:
        yield engine
    finally:
        engine.dispose()


@pytest.fixture
def clean_db(engine):
    """Empty every table, sequences included, so each test starts from nothing."""
    tables = ", ".join(f'"{name}"' for name in Base.metadata.tables)
    with engine.begin() as conn:
        conn.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))


@pytest.fixture
def session(clean_db, engine):
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    s = SessionLocal()
    try:
        yield s
    finally:
        s.close()


def verified_test_database(url):
    """clean_db truncates every table, so a TEST_DATABASE_URL aimed at the dev or prod database would erase it."""
    name = make_url(url).database or ""
    if "test" not in name:
        raise pytest.UsageError(
            f"TEST_DATABASE_URL points at database {name!r}, which is not a test database. "
            "Every table in it would be truncated. Use a database with 'test' in the name."
        )
    return url
