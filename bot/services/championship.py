"""Set Championship scheduling and frozen-standings logic — the season-closing 8-player invitational.

Date/plan derivation over `bot.sets` (no Discord), plus the seed snapshot the event freezes at
creation so seeds lock in. The championship for the active set is held the second Saturday before its
successor's Arena release (the Saturday before the successor's prerelease weekend) at 2 PM ET, and is
created `CREATION_LEAD_DAYS` ahead so the standings freeze and the invite waves have runway.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from bot.database import SessionLocal
from bot.models import MagicSet, PodChampionshipSeed, PodDraftEvent
from bot.services.player_stats import SeededAttendee, rank_players_for_set
from bot.services.pod_drafts import is_championship
from bot.sets import ALL_SETS, RELEASE_TZ, active_set_code, release_instant

SATURDAY = 5
CHAMPIONSHIP_TIME = time(14, 0)
CREATION_LEAD_DAYS = 5
CREATION_HOUR_ET = 12
SEAT_COUNT = 8
INVITE_DEPTH = 32
INVITE_WAVE_TIERS: tuple[tuple[int, int], ...] = ((0, 10), (10, 20), (20, 32))


@dataclass(frozen=True)
class ChampionshipPlan:
    set_code: str
    set_name: str
    event_at: datetime
    create_on: date
    next_set_code: str
    next_set_name: str
    next_release_at: datetime


def _last_saturday_before(day: date) -> date:
    back = (day.weekday() - SATURDAY) % 7 or 7
    return day - timedelta(days=back)


def championship_date_before(release: date) -> date:
    """The championship Saturday for a successor releasing on `release`: the Saturday before its
    prerelease weekend, i.e. the second Saturday before the release."""
    return _last_saturday_before(release) - timedelta(days=7)


def plan_for(when: datetime | None = None) -> ChampionshipPlan | None:
    """The championship plan for the set active at `when`, or None when the active set is the newest
    registered entry and has no successor to anchor the date to."""
    active = active_set_code(when)
    codes = [seed.code for seed in ALL_SETS]
    index = codes.index(active)
    if index + 1 >= len(ALL_SETS):
        return None
    current = ALL_SETS[index]
    successor = ALL_SETS[index + 1]
    event_date = championship_date_before(successor.start_date)
    event_at = datetime.combine(event_date, CHAMPIONSHIP_TIME, tzinfo=RELEASE_TZ)
    return ChampionshipPlan(
        set_code=current.code,
        set_name=current.name,
        event_at=event_at,
        create_on=event_date - timedelta(days=CREATION_LEAD_DAYS),
        next_set_code=successor.code,
        next_set_name=successor.name,
        next_release_at=release_instant(successor.start_date),
    )


def signup_post_at(plan: ChampionshipPlan) -> datetime:
    """When the tick posts the signup card."""
    return datetime.combine(plan.create_on, time(CREATION_HOUR_ET), tzinfo=RELEASE_TZ)


def plan_due_for_creation(when: datetime) -> ChampionshipPlan | None:
    """The plan whose creation day is the ET date of `when`, else None. The caller still guards
    against double-creation; this only answers 'is today the day to post it'."""
    plan = plan_for(when)
    if plan is None:
        return None
    return plan if when.astimezone(RELEASE_TZ).date() == plan.create_on else None


@dataclass(frozen=True)
class SeedRow:
    rank: int
    player_id: str | None
    discord_id: str | None
    display_name: str
    score: float


def freeze_seeds_sync(event_id: str, set_code: str, depth: int = INVITE_DEPTH) -> int:
    """Snapshot the current leaderboard standings for `set_code` onto the event, top `depth` players,
    so seeds lock in at creation. Idempotent: replaces any existing snapshot for the event."""
    with SessionLocal() as session:
        set_id = session.execute(
            select(MagicSet.id).where(func.upper(MagicSet.code) == set_code.upper())
        ).scalar_one_or_none()
        if set_id is None:
            return 0
        ranked = rank_players_for_set(session, set_id)[:depth]
        session.execute(delete(PodChampionshipSeed).where(PodChampionshipSeed.event_id == event_id))
        for player in ranked:
            session.add(PodChampionshipSeed(
                event_id=event_id, player_id=player.player_id, discord_id=player.discord_id,
                display_name=player.display_name, rank=player.rank, score=player.score,
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


def frozen_rank_by_player(session: Session, event_id: str) -> dict[str, int]:
    """The frozen seed rank keyed by player_id, so the seeding table seeds off the snapshot taken at
    creation instead of live standings. Players outside the snapshot are absent and fall back to their
    live rank in the seeding path: a player who joined the board after the freeze is placed where they
    stand now, which keeps them from passing anyone who was already ranked on the freeze day."""
    rows = session.execute(
        select(PodChampionshipSeed.player_id, PodChampionshipSeed.rank)
        .where(PodChampionshipSeed.event_id == event_id)
    ).all()
    return {row.player_id: row.rank for row in rows if row.player_id is not None}


def rank_override(session: Session, event_id: str) -> dict[str, int] | None:
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
    return frozen_rank_by_player(session, event_id)


def rank_override_sync(event_id: str) -> dict[str, int] | None:
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
