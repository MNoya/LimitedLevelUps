"""The spoiler-free marker: results show only through the round the coverage has shown"""
from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from bot.models import FantasyEvent as FantasyEventRow
from bot.models import FantasyRound
from bot.services.fantasy_event import FantasyEvent

TOP8_ROUND_NAMES = (
    ("quarterfinal", "quarterfinals", "quarters"),
    ("semifinal", "semifinals", "semis"),
    ("final", "finals"),
)
COVERAGE_DELAY = timedelta(minutes=90)
DAY_ONE_COMPLETE = "day_one_complete"
SWISS_COMPLETE = "swiss_complete"
EVENT_COMPLETE = "event_complete"


def reveal_through(session: Session, event_code: str, round_number: int) -> int:
    previous = revealed_round(session, event_code) or 0
    session.execute(
        FantasyEventRow.__table__.update()
        .where(FantasyEventRow.code == event_code)
        .values(revealed_through_round=round_number)
    )
    return previous


def revealed_round(session: Session, event_code: str) -> int | None:
    return session.scalar(select(FantasyEventRow.revealed_through_round).where(FantasyEventRow.code == event_code))


def revealed_milestones(event: FantasyEvent, previous: int, revealed: int) -> list[str]:
    final_round = event.swiss_rounds + len(TOP8_ROUND_NAMES)
    milestones = []
    if previous < event.cut_round <= revealed:
        milestones.append(DAY_ONE_COMPLETE)
    if previous < event.swiss_rounds <= revealed:
        milestones.append(SWISS_COMPLETE)
    if previous < final_round <= revealed:
        milestones.append(EVENT_COMPLETE)
    return milestones


def advance_auto_reveal(session: Session, event: FantasyEvent, now: datetime) -> tuple[int, int] | None:
    current = revealed_round(session, event.code)
    if current is None:
        return None
    completed = dict(session.execute(
        select(FantasyRound.round_number, FantasyRound.completed_at).where(FantasyRound.event_code == event.code)
    ).all())
    target = auto_reveal_through(current, completed, now, manual_release_rounds(event))
    if target == current:
        return None
    reveal_through(session, event.code, target)
    return current, target


def auto_reveal_through(
    current: int, completed: dict[int, datetime], now: datetime, manual_rounds: set[int]
) -> int:
    revealed = current
    while True:
        next_round = revealed + 1
        if next_round in manual_rounds or next_round not in completed:
            return revealed
        if completed[next_round] + COVERAGE_DELAY > now:
            return revealed
        revealed = next_round


def manual_release_rounds(event: FantasyEvent) -> set[int]:
    day_openers = {1, event.cut_round + 1}
    top8_rounds = set(range(event.swiss_rounds + 1, event.swiss_rounds + len(TOP8_ROUND_NAMES) + 1))
    return day_openers | top8_rounds


def round_number_for_reveal(argument: str, swiss_rounds: int) -> int | None:
    text = argument.strip().lower()
    if text.isdigit():
        number = int(text)
        return number if 0 <= number <= swiss_rounds else None
    for offset, names in enumerate(TOP8_ROUND_NAMES, start=1):
        if text in names:
            return swiss_rounds + offset
    return None
