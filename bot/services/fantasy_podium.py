"""The fantasy Podium: the top three of the final standings with their Discord ids from auth.identities"""
from __future__ import annotations

import logging
from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.exc import ProgrammingError

from bot.database import SessionLocal

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class FantasyWinner:
    rank: int
    name: str
    discord_id: str | None
    points: int
    bracket_points: int


def podium_sync(event_code: str, size: int = 3) -> list[FantasyWinner] | None:
    """None off production, where the auth schema that maps members to Discord ids is absent"""
    with SessionLocal() as session:
        try:
            rows = session.execute(text("""
                SELECT s.rank, s.name, i.provider_id AS discord_id, s.points, s.bracket_points
                FROM fantasy_member_scores m
                JOIN public_fantasy_standings s
                  ON s.event_code = m.event_code
                 AND s.member_key = left(encode(sha256(m.user_id::text::bytea), 'hex'), 16)
                LEFT JOIN auth.identities i ON i.user_id = m.user_id AND i.provider = 'discord'
                WHERE m.event_code = :event_code AND s.rank <= :size
                ORDER BY s.rank, s.name
            """), {"event_code": event_code.upper(), "size": size}).all()
        except ProgrammingError:
            session.rollback()
            log.warning("fantasy-podium: no auth schema, podium unavailable off production")
            return None
    winners = []
    for rank, name, discord_id, points, bracket_points in rows:
        winners.append(FantasyWinner(
            rank=rank, name=name, discord_id=str(discord_id) if discord_id is not None else None,
            points=points, bracket_points=bracket_points,
        ))
    return winners
