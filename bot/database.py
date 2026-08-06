import logging
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from bot.config import settings

engine = create_engine(settings.database_url, pool_pre_ping=True, pool_recycle=1800)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def run_migrations() -> None:
    """Run Alembic migrations on bot startup. Crashes loudly on failure."""
    try:
        ini_path = Path(__file__).resolve().parent.parent / "alembic.ini"
        alembic_cfg = Config(str(ini_path))
        command.upgrade(alembic_cfg, "head")
        logging.info("Migrations applied successfully.")
    except Exception as e:
        logging.critical(f"Migration failed: {e}")
        raise SystemExit(1)
