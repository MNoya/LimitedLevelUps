"""Seed Magic sets into the leaderboard DB.

Idempotent: re-running leaves existing rows untouched. Safe to run against
any environment (local Postgres or Supabase) — pick the target via DATABASE_URL.

    DATABASE_URL=postgresql://... python -m bot.scripts.seed_sets

Set metadata lives in ``bot/sets.py`` — edit there, not here.
"""
from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from bot.database import SessionLocal
from bot.models import MagicSet
from bot.scripts.seed_cube_seasons import sync_cube_seasons
from bot.services.refresh import claim_orphan_drafts, rebuild_player_stats
from bot.sets import ALL_SETS, SetSeed


logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger("seed_sets")


def upsert_set(session: Session, seed: SetSeed) -> MagicSet:
    existing = session.execute(
        select(MagicSet).where(MagicSet.code == seed.code)
    ).scalar_one_or_none()
    if existing is not None:
        if (
            existing.end_date != seed.end_date
            or existing.start_date != seed.start_date
            or existing.name != seed.name
        ):
            existing.end_date = seed.end_date
            existing.start_date = seed.start_date
            existing.name = seed.name
            log.info(f"updating set {seed.code} (metadata refreshed)")
        else:
            log.info(f"set {seed.code} exists, leaving as-is")
        return existing
    new_set = MagicSet(
        code=seed.code,
        name=seed.name,
        start_date=seed.start_date,
        end_date=seed.end_date,
    )
    session.add(new_set)
    log.info(f"seeding set {seed.code} ({seed.name})")
    session.flush()
    return new_set


def main() -> None:
    with SessionLocal() as session:
        seeded_sets = [(seed, upsert_set(session, seed)) for seed in ALL_SETS]
        session.commit()
        sync_cube_seasons(session)

        for seed, magic_set in seeded_sets:
            affected_players = claim_orphan_drafts(
                session, magic_set, seed.expansion_alias, seed.expansion_matches,
            )
            if not affected_players:
                continue
            log.info(f"claiming orphan drafts for {magic_set.code}: {len(affected_players)} player(s)")
            for player_id in affected_players:
                rebuild_player_stats(session, player_id, magic_set.id)
            session.commit()
    log.info("done.")


if __name__ == "__main__":
    main()
