"""Set Championship seeds and roster — the season-closing 8-player invitational.

The snapshot the event freezes at creation so seeds lock in, over the models and a session. When each
championship is held lives in `championship_dates`, which stays free of the ORM for the schedule and its
calendar image; it is re-exported here so callers reach the whole subsystem through one module.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from bot.database import SessionLocal
from bot.models import MagicSet, PodChampionshipSeed, PodDraftEvent
from bot.services.championship_dates import (
    CHAMPIONSHIP_TIME,
    CREATION_HOUR_ET,
    CREATION_LEAD_DAYS,
    SATURDAY,
    ChampionshipPlan,
    championship_date_before,
    championship_date_for,
    championship_on,
    plan_due_for_creation,
    plan_for,
    signup_post_at,
)
from bot.services.player_stats import FrozenSeed, SeededAttendee, rank_players_for_set
from bot.services.pod_drafts import is_championship

__all__ = [
    "CHAMPIONSHIP_TIME",
    "CREATION_HOUR_ET",
    "CREATION_LEAD_DAYS",
    "INVITE_DEPTH",
    "INVITE_WAVE_TIERS",
    "SATURDAY",
    "SEAT_COUNT",
    "ChampionshipPlan",
    "SeedRow",
    "championship_date_before",
    "championship_date_for",
    "championship_on",
    "plan_due_for_creation",
    "plan_for",
    "signup_post_at",
]

SEAT_COUNT = 8
INVITE_DEPTH = 32
INVITE_WAVE_TIERS: tuple[tuple[int, int], ...] = ((0, 10), (10, 20), (20, 32))


@dataclass(frozen=True)
class SeedRow:
    rank: int
    player_id: str | None
    discord_id: str | None
    display_name: str
    score: float


def freeze_seeds_sync(
    event_id: str, set_code: str, cutoff: datetime | None = None, depth: int | None = None,
) -> int:
    """Snapshot the leaderboard standings for `set_code` onto the event, so seeds lock in at the deadline.
    Idempotent: replaces any existing snapshot for the event.

    `cutoff` is the deadline the board is rebuilt as of, which makes the snapshot reproducible: re-running it
    any time returns the same standings, and a player whose 17lands profile is linked after the deadline is
    still counted on the drafts they had finished before it. Without one it snapshots today's board.

    The whole board is stored, not the invite depth. A snapshot that stopped at 32 left everyone below it
    with no frozen rank, and the seeding path then fell back to their live rank, which put two different
    scales in one table and let a player ranked after the deadline pass one ranked before it. `depth` still
    trims it for a caller that wants a slice."""
    with SessionLocal() as session:
        set_id = session.execute(
            select(MagicSet.id).where(func.upper(MagicSet.code) == set_code.upper())
        ).scalar_one_or_none()
        if set_id is None:
            return 0
        ranked = rank_players_for_set(session, set_id, cutoff)
        ranked = ranked[:depth] if depth is not None else ranked
        session.execute(delete(PodChampionshipSeed).where(PodChampionshipSeed.event_id == event_id))
        for player in ranked:
            session.add(PodChampionshipSeed(
                event_id=event_id, player_id=player.player_id, discord_id=player.discord_id,
                display_name=player.display_name, rank=player.rank, score=player.score,
                trophies=player.trophies,
            ))
        session.commit()
        return len(ranked)


def frozen_seeds_sync(event_id: str) -> list[SeedRow]:
    """The event's frozen standings, best rank first."""
    with SessionLocal() as session:
        rows = session.execute(
            select(
                PodChampionshipSeed.rank, PodChampionshipSeed.player_id, PodChampionshipSeed.discord_id,
                PodChampionshipSeed.display_name, PodChampionshipSeed.score,
            )
            .where(PodChampionshipSeed.event_id == event_id)
            .order_by(PodChampionshipSeed.rank)
        ).all()
    return [
        SeedRow(rank=row.rank, player_id=row.player_id, discord_id=row.discord_id,
                display_name=row.display_name, score=row.score)
        for row in rows
    ]


def frozen_seeds_by_player(session: Session, event_id: str) -> dict[str, FrozenSeed]:
    """The frozen standings keyed by player_id, rank and score together, so every surface seeds and prints
    off the board as it stood at the deadline rather than mixing that rank with today's points."""
    rows = session.execute(
        select(
            PodChampionshipSeed.player_id, PodChampionshipSeed.rank,
            PodChampionshipSeed.score, PodChampionshipSeed.trophies,
        )
        .where(PodChampionshipSeed.event_id == event_id)
    ).all()
    return {
        row.player_id: FrozenSeed(rank=row.rank, score=row.score, trophies=row.trophies)
        for row in rows if row.player_id is not None
    }


def rank_override(session: Session, event_id: str) -> dict[str, FrozenSeed] | None:
    """The frozen seed ranks a championship orders off, or None for any other pod so a regular leaderboard
    pod stays on live standings. Every surface that ranks a championship roster resolves through here, so
    the card, the launcher and the seats the draft is dealt in cannot read different scales.

    Reads the name column alone: a `PodDraftEvent` carries its whole draft log, which is a lot to pull over
    the wire to answer what the pod is called."""
    name = session.execute(
        select(PodDraftEvent.name).where(PodDraftEvent.id == event_id)
    ).scalar_one_or_none()
    if not is_championship(name):
        return None
    return frozen_seeds_by_player(session, event_id)


def playing_roster(
    session: Session, event_id: str, roster: list[tuple[str, str]],
) -> list[tuple[str, str]]:
    """The (discord id, name) pairs a pod actually seats: `roster` untouched for an ordinary pod, and for a
    championship the `SEAT_COUNT` best frozen seeds in it.

    A championship is one table of eight and nothing else. Every Yes past the cut is an alternate, so the
    lobby ping, the waiting list and the link DMs all narrow through here instead of addressing a roster of
    thirty. Ordering is the frozen seed, which is what makes a seat pass down to the next player when
    someone above them drops. A player carrying no seed sorts last, keeping a roster that lost its snapshot
    seatable rather than empty."""
    if rank_override(session, event_id) is None:
        return roster
    ranks = {
        row.discord_id: row.rank for row in session.execute(
            select(PodChampionshipSeed.discord_id, PodChampionshipSeed.rank)
            .where(PodChampionshipSeed.event_id == event_id)
        ).all()
        if row.discord_id is not None
    }
    if not ranks:
        return roster
    ordered = sorted(roster, key=lambda pair: ranks.get(pair[0], len(ranks) + 1))
    return ordered[:SEAT_COUNT]


def playing_roster_sync(event_id: str, roster: list[tuple[str, str]]) -> list[tuple[str, str]]:
    with SessionLocal() as session:
        return playing_roster(session, event_id, roster)


def rank_override_sync(event_id: str) -> dict[str, FrozenSeed] | None:
    with SessionLocal() as session:
        return rank_override(session, event_id)


def standings_seed_attendees_sync(set_code: str) -> list[SeededAttendee]:
    """The live leaderboard for `set_code` as seeded attendees, best rank first, for the locked
    standings table the championship posts in its thread."""
    with SessionLocal() as session:
        set_id = session.execute(
            select(MagicSet.id).where(func.upper(MagicSet.code) == set_code.upper())
        ).scalar_one_or_none()
        if set_id is None:
            return []
        ranked = rank_players_for_set(session, set_id)
    return [
        SeededAttendee(
            slug=player.slug, display_name=player.display_name, rank=player.rank,
            score=player.score, trophies=player.trophies,
        )
        for player in ranked
    ]


_invites_pending: set[str] = set()


def mark_invites_pending(event_id: str) -> None:
    """Hold the Yes-tally seeding table back while the invite waves go out, so it lands once after the
    last wave with a full picture instead of posting on the first RSVP. Cleared by mark_invites_complete
    when the tally is posted. In-memory, like the armed wave jobs, so a restart mid-window opens it."""
    _invites_pending.add(event_id)


def mark_invites_complete(event_id: str) -> None:
    _invites_pending.discard(event_id)


def invites_pending(event_id: str) -> bool:
    return event_id in _invites_pending


def wave_recipients(seeds: list[SeedRow], wave_index: int) -> list[SeedRow]:
    """The seeds to ping for an invite wave: the tier's ranks that carry a Discord id. Pings are
    awareness only, never a gate — every wave fires regardless of how many have already RSVP'd, and
    anyone may RSVP whether or not they were pinged."""
    low, high = INVITE_WAVE_TIERS[wave_index]
    return [seed for seed in seeds[low:high] if seed.discord_id]


def event_for_set_sync(set_code: str) -> tuple[str, datetime] | None:
    """(event_id, event_time) of a set's championship, or None while it has not been created. Matched by
    name, the same marker the creator guards double-creation with."""
    with SessionLocal() as session:
        row = session.execute(
            select(PodDraftEvent.id, PodDraftEvent.event_time).where(
                func.upper(PodDraftEvent.set_code) == set_code.upper(),
                func.lower(PodDraftEvent.name).like("%championship%"),
            )
        ).first()
    return (row.id, row.event_time) if row else None


def event_meta_sync(event_id: str) -> tuple[str, datetime] | None:
    """(set_code, event_time) for a championship event, or None when it is gone."""
    with SessionLocal() as session:
        row = session.execute(
            select(PodDraftEvent.set_code, PodDraftEvent.event_time).where(PodDraftEvent.id == event_id)
        ).first()
    return (row.set_code, row.event_time) if row else None
