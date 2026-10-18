"""P0P1 results snapshots, captured once at the midway point and once at the scoring date, never rewritten"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from bot.models import P0P1Ratings
from bot.services import p0p1_contest
from bot.services.seventeenlands import SeventeenLandsClient

log = logging.getLogger(__name__)

FIXTURES_DIR = Path(__file__).resolve().parents[2] / "frontend/src/data/fixtures"
PHASE_MIDWAY = "midway"
PHASE_FINAL = "final"


@dataclass(frozen=True)
class Snapshot:
    date_start: date
    date_end: date
    cards: list[dict]


def capture_due_snapshots(session: Session, client: SeventeenLandsClient, now: datetime) -> list[tuple[str, str]]:
    captured = []
    for contest in p0p1_contest.all_contests():
        phase = due_phase(contest, now)
        if phase is None or _snapshot_exists(session, contest.code, phase):
            continue
        snapshot = _committed_snapshot(contest.code, phase) or _fetch_snapshot(client, contest, now)
        enough_rated = len(snapshot.cards) >= 0.9 * len(_pool_names(contest.code))
        if not enough_rated:
            log.warning(f"p0p1-ratings: {contest.code} has {len(snapshot.cards)} rated cards, retrying next tick")
            continue
        _store(session, contest.code, phase, snapshot)
        captured.append((contest.code, phase))
        log.info(f"p0p1-ratings: captured {contest.code} {phase} with {len(snapshot.cards)} cards")
    return captured


def due_phase(contest: p0p1_contest.Contest, now: datetime) -> str | None:
    if now >= contest.scoring_date:
        return PHASE_FINAL
    if now >= midway_date(contest):
        return PHASE_MIDWAY
    return None


def midway_date(contest: p0p1_contest.Contest) -> datetime:
    return contest.release + (contest.scoring_date - contest.release) / 2


def load_final_ratings(session: Session, set_code: str) -> list[dict]:
    query = select(P0P1Ratings.cards).where(P0P1Ratings.set_code == set_code.upper(), P0P1Ratings.phase == PHASE_FINAL)
    return session.execute(query).scalar_one_or_none() or []


def _fetch_snapshot(client: SeventeenLandsClient, contest: p0p1_contest.Contest, now: datetime) -> Snapshot:
    pool = _pool_names(contest.code)
    cards = []
    for row in client.fetch_card_ratings(contest.code):
        name = row.get("name")
        if name not in pool:
            continue
        gihwr = row.get("ever_drawn_win_rate")
        cards.append({
            "card_name": name,
            "gihwr": round(float(gihwr), 5) if gihwr is not None else None,
            "gih": int(row.get("drawn_game_count") or 0),
        })
    end = min(now, contest.scoring_date).date()
    return Snapshot(date_start=contest.release.date(), date_end=end, cards=cards)


def _snapshot_exists(session: Session, set_code: str, phase: str) -> bool:
    query = select(P0P1Ratings.set_code).where(P0P1Ratings.set_code == set_code, P0P1Ratings.phase == phase)
    return session.execute(query).first() is not None


def _store(session: Session, set_code: str, phase: str, snapshot: Snapshot) -> None:
    row = {
        "set_code": set_code, "phase": phase,
        "date_start": snapshot.date_start, "date_end": snapshot.date_end, "cards": snapshot.cards,
    }
    session.execute(insert(P0P1Ratings).values(**row).on_conflict_do_nothing())
    session.commit()


def _committed_snapshot(set_code: str, phase: str) -> Snapshot | None:
    path = FIXTURES_DIR / f"p0p1-ratings-{set_code.lower()}.ts"
    if not path.exists():
        return None
    fixture = _fixture_object(path)
    if fixture.get("phase") != phase:
        return None
    start = date.fromisoformat(fixture["dateRange"]["start"])
    end = date.fromisoformat(fixture["dateRange"]["end"])
    return Snapshot(date_start=start, date_end=end, cards=fixture["cards"])


def _pool_names(set_code: str) -> set[str]:
    body = (FIXTURES_DIR / f"cards-{set_code.lower()}.ts").read_text()
    cards = json.loads(body[body.index("["):body.index("] satisfies") + 1])
    return {card["name"] for card in cards}


def _fixture_object(path: Path) -> dict:
    body = path.read_text()
    start = body.index("{", body.index("export default"))
    return json.loads(body[start:body.rindex("}") + 1])
