from __future__ import annotations

import logging

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from bot.models import CubeSeasonWindow
from bot.services.refresh import refresh_public_matviews
from bot.sets import CUBE_SEASONS

log = logging.getLogger(__name__)


def sync_cube_seasons(session: Session) -> int:
    """Make ``cube_seasons`` match the registry and return the declared count"""
    declared = {
        (variant.slug, season.code): season
        for variant, season in CUBE_SEASONS
    }
    existing = {
        (row.variant, row.set_code): row
        for row in session.execute(select(CubeSeasonWindow)).scalars().all()
    }
    changed = False

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
            changed = True
        elif row.start_date != season.start_date or row.end_date != season.end_date:
            row.start_date = season.start_date
            row.end_date = season.end_date
            log.info(f"updating cube season CUBE-{season.code} ({key[0]})")
            changed = True

    for key, row in existing.items():
        if key not in declared:
            session.execute(delete(CubeSeasonWindow).where(CubeSeasonWindow.id == row.id))
            log.info(f"removing undeclared cube season CUBE-{row.set_code} ({row.variant})")
            changed = True

    session.commit()
    refresh_public_matviews(session, ingested_rows=changed)
    return len(declared)
