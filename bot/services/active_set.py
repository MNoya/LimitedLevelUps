"""Resolve the date-derived active set to a seeded DB row, and the board set players see.

``active_set_code`` is pure date math against ``ALL_SETS``; the row it names only exists once
``seed_sets`` has run against the database. Seeding stays manual, so when a freshly rotated set
hasn't been seeded yet this falls back to the latest prior set that does have a row — the board
holds on the previous set instead of going blank — and warns so the owner knows to seed.

The board runs ahead of the Arena set. Players hold cards before the Arena drop, through Early
Access or the paper prerelease, and log those results, so the set claiming the board is the one
results exist for, not the one the calendar says. ``public_sets.is_active`` computes the same
answer in SQL for the site — keep them in lockstep.
"""
from __future__ import annotations

import logging

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from bot.models import MagicSet, PlayerStats, SelfReportedEvent
from bot.sets import ALL_SETS, active_set_code, upcoming_sets

log = logging.getLogger(__name__)


def resolve_active_set(session: Session) -> MagicSet | None:
    code = active_set_code()
    magic_set = session.execute(
        select(MagicSet).where(MagicSet.code == code)
    ).scalar_one_or_none()
    if magic_set is not None:
        return magic_set

    fallback = _latest_seeded_prior_set(session, code)
    if fallback is not None:
        log.warning(f"active set {code} not seeded; holding leaderboard on {fallback.code} — run seed_sets")
    else:
        log.warning(f"active set {code} not seeded and no prior set seeded; leaderboard has no set")
    return fallback


def resolve_board_set(session: Session) -> MagicSet | None:
    """The set the leaderboard and player profiles default to.

    The next set takes the board as soon as its first result lands, whether that came from Early
    Access on 17lands or from a paper prerelease trophy logged with ``/trophy``. Only the set
    immediately after the active one can claim it, so a result filed against a set further out
    leaves the board where it is.
    """
    upcoming = upcoming_sets()
    if upcoming:
        next_up = session.execute(
            select(MagicSet).where(MagicSet.code == upcoming[0].code)
        ).scalar_one_or_none()
        if next_up is not None and set_has_results(session, next_up.code):
            return next_up
    return resolve_active_set(session)


def set_has_results(session: Session, code: str) -> bool:
    """Whether anyone has played a set yet: 17lands aggregates, or any result logged with
    ``/trophy``. Matches on the set code so a result logged before the set was seeded still
    counts."""
    return session.execute(
        select(
            or_(
                select(PlayerStats.id)
                .join(MagicSet, MagicSet.id == PlayerStats.set_id)
                .where(MagicSet.code == code)
                .exists(),
                select(SelfReportedEvent.id)
                .where(func.upper(SelfReportedEvent.set_code) == code.upper())
                .exists(),
            )
        )
    ).scalar()


def _latest_seeded_prior_set(session: Session, code: str) -> MagicSet | None:
    active_seed: object | None = None
    for seed in ALL_SETS:
        if seed.code == code:
            active_seed = seed
            break
    if active_seed is None:
        return None

    prior_codes = [s.code for s in ALL_SETS if s.start_date < active_seed.start_date]
    if not prior_codes:
        return None
    return session.execute(
        select(MagicSet)
        .where(MagicSet.code.in_(prior_codes))
        .order_by(MagicSet.start_date.desc())
    ).scalars().first()
