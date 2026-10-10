"""Seed the declared cube runs into ``cube_seasons``, which the cube views join.

Idempotent: re-running updates dates that moved and removes rows no longer declared, so the table
always mirrors the registry.

    DATABASE_URL=postgresql://... python -m bot.scripts.seed_cube_seasons

Season metadata lives in ``cube_variants.json`` — edit there, not here.
"""
from __future__ import annotations

import logging

from bot.database import SessionLocal
from bot.services.cube_seasons import sync_cube_seasons


logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger("seed_cube_seasons")


def main() -> None:
    with SessionLocal() as session:
        count = sync_cube_seasons(session)
    log.info(f"done. {count} declared season(s)")


if __name__ == "__main__":
    main()
