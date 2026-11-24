from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import date, datetime, time
from functools import cache
from pathlib import Path
from zoneinfo import ZoneInfo

from bot.sets import active_set_code

PRO_EVENTS_PATH = Path(__file__).resolve().parents[2] / "pro_events.json"
EDITION_NUMBER = re.compile(r"(\d+)$")


@dataclass(frozen=True)
class CoverageKind:
    key: str
    name: str
    headline: bool


WORLDS = CoverageKind("worlds", "World Championship", headline=True)
PRO_TOUR = CoverageKind("pt", "Pro Tour", headline=True)
ARENA_CHAMPIONSHIP = CoverageKind("ac", "Arena Championship", headline=True)
SPOTLIGHT = CoverageKind("spotlight", "Spotlight Series", headline=False)
HEADLINER_ORDER = (WORLDS, PRO_TOUR, ARENA_CHAMPIONSHIP, SPOTLIGHT)


@dataclass(frozen=True)
class EventDay:
    day: date
    start: time
    end: time
    subject: str


@dataclass(frozen=True)
class EventSchedule:
    tz: ZoneInfo
    days: tuple[EventDay, ...]


@dataclass(frozen=True)
class CoveredEvent:
    name: str
    kind: CoverageKind
    details: str
    is_draft: bool
    schedule: EventSchedule
    stream_url: str | None
    estimated: bool

    @property
    def first_day(self) -> date:
        return self.schedule.days[0].day

    @property
    def last_day(self) -> date:
        return self.schedule.days[-1].day

    @property
    def short_name(self) -> str:
        if self.kind is WORLDS:
            return _numbered("Worlds", self.edition_number)
        if self.kind is ARENA_CHAMPIONSHIP:
            return _numbered("AC", self.edition_number)
        if self.kind is PRO_TOUR:
            return f"PT {active_set_code(self.starts_at())}"
        return self.name

    @property
    def edition_number(self) -> str | None:
        match = EDITION_NUMBER.search(self.name)
        return match.group(1) if match else None

    def starts_at(self) -> datetime:
        first = self.schedule.days[0]
        return datetime.combine(first.day, first.start, self.schedule.tz)

    def ends_at(self) -> datetime:
        last = self.schedule.days[-1]
        return datetime.combine(last.day, last.end, self.schedule.tz)

    def first_subject(self) -> str:
        return self.schedule.days[0].subject


@cache
def load_pro_events() -> tuple[CoveredEvent, ...]:
    with PRO_EVENTS_PATH.open(encoding="utf-8") as source:
        return tuple(parse_pro_events(json.load(source)))


def parse_pro_events(raw_events: list[dict]) -> list[CoveredEvent]:
    kinds = {kind.key: kind for kind in HEADLINER_ORDER}
    return [_parse_event(raw, kinds) for raw in raw_events]


def event_schedule(name: str | None) -> EventSchedule | None:
    for covered in load_pro_events():
        if covered.name == name:
            return covered.schedule
    return None


def _parse_event(raw: dict, kinds: dict[str, CoverageKind]) -> CoveredEvent:
    days = tuple(
        EventDay(date.fromisoformat(day["date"]), time.fromisoformat(day["start"]), time.fromisoformat(day["end"]),
                 day["subject"])
        for day in raw["days"]
    )
    return CoveredEvent(
        name=raw["name"],
        kind=kinds[raw["kind"]],
        details=raw["details"],
        is_draft=raw["draft"],
        schedule=EventSchedule(ZoneInfo(raw["timezone"]), days),
        stream_url=raw.get("stream"),
        estimated=raw["estimated"],
    )


def _numbered(prefix: str, number: str | None) -> str:
    return f"{prefix} {number}" if number else prefix
