"""The P0P1 podium at a contest's scoring date: top three ballots by summed GIH win rate from the final snapshot"""
from __future__ import annotations

import logging
from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.exc import ProgrammingError

from bot.database import SessionLocal
from bot.services.p0p1_ratings import load_final_ratings

log = logging.getLogger(__name__)

GIH_SAMPLE_FLOOR = 500
PODIUM_SIZE = 3

PODIUM_SQL = text("""
    select
      e.user_id                              as user_id,
      i.provider_id                          as discord_id,
      coalesce(v.name,
               p.display_name,
               u.raw_user_meta_data->>'full_name',
               u.raw_user_meta_data->>'user_name')  as name,
      e.slot                                 as slot,
      e.card_name                            as card_name
    from p0p1_entries e
    join auth.users u on u.id = e.user_id
    left join auth.identities i on i.user_id = u.id and i.provider = 'discord'
    left join p0p1_voters v on v.user_id = e.user_id
    left join players p on p.discord_id = i.provider_id
    where e.set_code = :set_code
""")


@dataclass(frozen=True)
class Winner:
    rank: int
    name: str
    discord_id: str | None
    score: float


def normalize_card_name(name: str) -> str:
    return name.split(" // ")[0].strip()


def score_picks(picks: dict[str, str], ratings: dict[str, tuple[float | None, int]]) -> float:
    total = 0.0
    for card_name in picks.values():
        rating = ratings.get(normalize_card_name(card_name))
        if rating is None:
            continue
        gihwr, gih = rating
        if gihwr is None or gih < GIH_SAMPLE_FLOOR:
            continue
        total += gihwr * 100
    return total


def podium_sync(set_code: str, limit: int = PODIUM_SIZE) -> list[Winner] | None:
    """The top ballots by summed GIHWR, mirroring the site's rankBallots. None when the auth schema is
    absent, so a caller on a developer database knows the real podium cannot be read there."""
    with SessionLocal() as session:
        ratings = _ratings_by_name(load_final_ratings(session, set_code))
        if not ratings:
            log.warning(f"p0p1-ceremony: no final ratings for {set_code} yet")
            return []
        try:
            rows = session.execute(PODIUM_SQL, {"set_code": set_code.upper()}).all()
        except ProgrammingError:
            session.rollback()
            log.warning("p0p1-ceremony: no auth schema, podium unavailable off production")
            return None

    ballots: dict[str, dict] = {}
    for user_id, discord_id, name, slot, card_name in rows:
        ballot = ballots.setdefault(str(user_id), {"name": name, "discord_id": discord_id, "picks": {}})
        ballot["picks"][slot] = card_name

    scored = []
    for ballot in ballots.values():
        scored.append((score_picks(ballot["picks"], ratings), ballot))
    scored.sort(key=lambda entry: -entry[0])

    winners = []
    for index, (score, ballot) in enumerate(scored[:limit], start=1):
        discord_id = str(ballot["discord_id"]) if ballot["discord_id"] is not None else None
        winners.append(Winner(rank=index, name=ballot["name"] or "Unknown", discord_id=discord_id, score=score))
    return winners


def _ratings_by_name(cards: list[dict]) -> dict[str, tuple[float | None, int]]:
    ratings: dict[str, tuple[float | None, int]] = {}
    for card in cards:
        ratings[normalize_card_name(card["card_name"])] = (card.get("gihwr"), card.get("gih") or 0)
    return ratings
