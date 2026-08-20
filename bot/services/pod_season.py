"""Pod season standings — the board `limitedlevelups.com/pods` publishes, in Python.

A season is a set's Arena window holding every pod played inside it whatever it drafted, so the latest
set, the cube and the flashbacks all count, plus any pod of that set played outside the window. Points
are the same flat pod term the leaderboard adds, so a season standing reads off `scoring_buckets.json`
like every other board.

Mirrors `frontend/src/data/podSeasons.ts`, which is what lets the Pod Champion and the championship
wildcard name the same #1 the site shows. Keep the two in lockstep.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from bot.database import SessionLocal
from bot.models import Player, PodDraftEvent, PodDraftParticipant
from bot.scoring import pod_points
from bot.services.pod_drafts import summarize_pod_records
from bot.sets import SetSeed, seed_for_code


@dataclass(frozen=True)
class PodSeasonStanding:
    rank: int
    player_id: str
    discord_id: str | None
    display_name: str
    avatar_hash: str | None
    events: int
    wins: int
    trophies: int
    points: int


def rank_pod_season(
    session: Session, seed: SetSeed, before: datetime | None = None,
) -> list[PodSeasonStanding]:
    """The season's pod standings, best first; `before` counts only the pods finished by that instant"""
    window = [PodDraftEvent.event_date >= seed.start_date]
    if seed.end_date is not None:
        window.append(PodDraftEvent.event_date <= seed.end_date)
    query = (
        select(
            PodDraftParticipant.player_id, PodDraftParticipant.record,
            Player.discord_id, Player.display_name, Player.avatar_hash,
        )
        .join(PodDraftEvent, PodDraftEvent.id == PodDraftParticipant.event_id)
        .join(Player, Player.id == PodDraftParticipant.player_id)
        .where(
            Player.active.is_(True),
            PodDraftParticipant.record.isnot(None),
            or_(and_(*window), func.upper(PodDraftEvent.set_code) == seed.code.upper()),
        )
    )
    if before is not None:
        query = query.where(PodDraftEvent.event_time < before)

    records: dict[str, list[str | None]] = {}
    identities: dict[str, tuple[str | None, str, str | None]] = {}
    for row in session.execute(query).all():
        records.setdefault(row.player_id, []).append(row.record)
        identities[row.player_id] = (row.discord_id, row.display_name, row.avatar_hash)

    standings: list[PodSeasonStanding] = []
    for player_id, player_records in records.items():
        summary = summarize_pod_records(player_records)
        discord_id, display_name, avatar_hash = identities[player_id]
        standings.append(PodSeasonStanding(
            rank=0, player_id=player_id, discord_id=discord_id, display_name=display_name,
            avatar_hash=avatar_hash, events=summary.events, wins=summary.wins,
            trophies=summary.trophies,
            points=pod_points(summary.trophies, summary.two_win_finishes, summary.one_win_finishes),
        ))

    standings.sort(key=lambda s: (-s.points, -s.trophies, -s.wins, s.display_name.lower()))
    return [replace(standing, rank=rank) for rank, standing in enumerate(standings, start=1)]


def season_leader_sync(set_code: str, before: datetime | None = None) -> PodSeasonStanding | None:
    """The season's #1, or None for a set nobody podded in or one the rotation does not carry"""
    seed = seed_for_code(set_code)
    if seed is None:
        return None
    with SessionLocal() as session:
        standings = rank_pod_season(session, seed, before)
    return standings[0] if standings else None
