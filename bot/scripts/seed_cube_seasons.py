"""Seed the declared cube runs into ``cube_seasons``, which the cube views join.

Idempotent: re-running updates dates that moved and removes rows no longer declared, so the table
always mirrors the registry.

    DATABASE_URL=postgresql://... python -m bot.scripts.seed_cube_seasons

Season metadata lives in ``cube_variants.json`` — edit there, not here.
"""
from __future__ import annotations

import logging

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from bot.database import SessionLocal
from bot.models import CubeSeasonWindow
from bot.services.refresh import refresh_public_matviews
from bot.sets import CUBE_SEASONS


logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger("seed_cube_seasons")


def sync_cube_seasons(session: Session) -> int:
    """Make ``cube_seasons`` match the registry. Returns the row count written."""
    declared = {
        (variant.slug, season.code): season
        for variant, season in CUBE_SEASONS
    }
    existing = {
        (row.variant, row.set_code): row
        for row in session.execute(select(CubeSeasonWindow)).scalars().all()
    }

    for key, season in declared.items():
        row = existing.get(key)
        if row is None:
            session.add(CubeSeasonWindow(
                variant=key[0],
                set_code=season.code,
                start_date=season.start_date,
                end_date=season.end_date,
            ))
            log.info(f"seeding cube season CUBE-{season.code} ({key[0]})")
        elif row.start_date != season.start_date or row.end_date != season.end_date:
            row.start_date = season.start_date
            row.end_date = season.end_date
            log.info(f"updating cube season CUBE-{season.code} ({key[0]})")

    for key, row in existing.items():
        if key not in declared:
            session.execute(delete(CubeSeasonWindow).where(CubeSeasonWindow.id == row.id))
            log.info(f"removing undeclared cube season CUBE-{row.set_code} ({row.variant})")

    session.commit()
    # public_cube_seasons is a snapshot, so a season declared here is not a board until it rebuilds
    refresh_public_matviews(session)
    return len(declared)


def main() -> None:
    with SessionLocal() as session:
        count = sync_cube_seasons(session)
    log.info(f"done. {count} declared season(s)")


if __name__ == "__main__":
    main()
