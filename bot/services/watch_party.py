from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime, time
from zoneinfo import ZoneInfo

from bot.services.mtgscribe import ScribeEvent
from bot.sets import active_set_code

CHANNEL_PREFIX = "📺🎉-"
CHANNEL_SUFFIX = "watch-party"
COVERAGE_TAG = "coverage"
QUALIFIER_TAG = "qualifier"
SCG_TAG = "star-city-games"
MAGIC_TWITCH_URL = "https://twitch.tv/magic"
SCG_TWITCH_URL = "https://twitch.tv/starcitygames"
CHANNEL_TZ = ZoneInfo("America/New_York")
FALLBACK_START = time(9, 0)
FALLBACK_END = time(18, 0)
ARENA_CHAMPIONSHIP_NUMBER = re.compile(r"Arena Championship (\d+)")
QUALIFIER_TITLE_WORDS = ("Qualifier", "ACQ")


@dataclass(frozen=True)
class CoverageKind:
    key: str
    name: str
    tag: str | None
    title_phrase: str
    always_covered: bool
    scheduled_event: bool
    announced: bool


WORLDS = CoverageKind("worlds", "World Championship", "magic-world-championship", "World Championship",
                      always_covered=True, scheduled_event=True, announced=True)
PRO_TOUR = CoverageKind("pt", "Pro Tour", None, "Pro Tour",
                        always_covered=True, scheduled_event=True, announced=True)
ARENA_CHAMPIONSHIP = CoverageKind("ac", "Arena Championship", "arena-championship", "Arena Championship",
                                  always_covered=True, scheduled_event=True, announced=False)
SPOTLIGHT = CoverageKind("spotlight", "Spotlight Series", "magic-spotlight-series", "Spotlight Series",
                         always_covered=False, scheduled_event=False, announced=False)
REGIONAL = CoverageKind("rc", "Regional Championship", "regional-championship", "Regional Championship",
                        always_covered=False, scheduled_event=False, announced=False)
HEADLINER_ORDER = (WORLDS, PRO_TOUR, ARENA_CHAMPIONSHIP, SPOTLIGHT, REGIONAL)


@dataclass(frozen=True)
class EventDay:
    day: date
    start: time
    end: time
    subject: str


@dataclass(frozen=True)
class PremierSchedule:
    tz: ZoneInfo
    days: tuple[EventDay, ...]
    ordinal: str | None = None


PREMIER_SCHEDULES: dict[str, PremierSchedule] = {
    "Arena Championship 13": PremierSchedule(ZoneInfo("America/Los_Angeles"), (
        EventDay(date(2026, 10, 24), time(9, 0), time(18, 0), "Day 1"),
        EventDay(date(2026, 10, 25), time(9, 0), time(18, 0), "Day 2"),
    )),
    "World Championship 32": PremierSchedule(ZoneInfo("America/New_York"), (
        EventDay(date(2026, 11, 13), time(9, 0), time(20, 0), "Draft Day 1"),
        EventDay(date(2026, 11, 14), time(9, 0), time(20, 0), "Draft Day 2"),
        EventDay(date(2026, 11, 15), time(9, 0), time(17, 0), "Top 8"),
    )),
}


@dataclass(frozen=True)
class CoveredEvent:
    event: ScribeEvent
    kind: CoverageKind

    @property
    def name(self) -> str:
        return self.event.format_label or self.event.title

    @property
    def details(self) -> str:
        return self.event.group_label

    @property
    def first_day(self) -> date:
        return self.event.start_local.date()

    @property
    def last_day(self) -> date:
        return self.event.end_local.date()

    @property
    def stream_url(self) -> str | None:
        if self.kind in (WORLDS, PRO_TOUR):
            return MAGIC_TWITCH_URL
        if SCG_TAG in self.event.tag_slugs:
            return SCG_TWITCH_URL
        return None

    @property
    def ordinal(self) -> str | None:
        schedule = PREMIER_SCHEDULES.get(self.name)
        return schedule.ordinal if schedule is not None else None

    def starts_at(self) -> datetime:
        tz, days = self._timed_days()
        return datetime.combine(days[0].day, days[0].start, tz)

    def ends_at(self) -> datetime:
        tz, days = self._timed_days()
        return datetime.combine(days[-1].day, days[-1].end, tz)

    def first_day_ends_at(self) -> datetime:
        tz, days = self._timed_days()
        return datetime.combine(days[0].day, days[0].end, tz)

    def first_subject(self) -> str:
        _, days = self._timed_days()
        return days[0].subject

    def _timed_days(self) -> tuple[ZoneInfo, tuple[EventDay, ...]]:
        schedule = PREMIER_SCHEDULES.get(self.name)
        if schedule is not None:
            return schedule.tz, schedule.days
        first = EventDay(self.first_day, FALLBACK_START, FALLBACK_END, "")
        last = EventDay(self.last_day, FALLBACK_START, FALLBACK_END, "")
        return CHANNEL_TZ, (first, last)


@dataclass(frozen=True)
class CoverageWindow:
    events: tuple[CoveredEvent, ...]

    @property
    def first_day(self) -> date:
        return min(covered.first_day for covered in self.events)

    @property
    def last_day(self) -> date:
        return max(covered.last_day for covered in self.events)

    def ends_at(self) -> datetime:
        latest = self.events[0].ends_at()
        for covered in self.events[1:]:
            latest = max(latest, covered.ends_at())
        return latest

    @property
    def headliner(self) -> CoveredEvent:
        best = self.events[0]
        for covered in self.events[1:]:
            if HEADLINER_ORDER.index(covered.kind) < HEADLINER_ORDER.index(best.kind):
                best = covered
        return best


def coverage_kind(event: ScribeEvent) -> CoverageKind | None:
    for kind in HEADLINER_ORDER:
        if kind is ARENA_CHAMPIONSHIP and _is_qualifier(event):
            continue
        if (kind.tag is not None and kind.tag in event.tag_slugs) or kind.title_phrase in event.title:
            return kind
    return None


def covered_events(events: list[ScribeEvent]) -> list[CoveredEvent]:
    covered = []
    for event in events:
        kind = coverage_kind(event)
        if kind is None:
            continue
        if kind.always_covered or COVERAGE_TAG in event.tag_slugs:
            covered.append(CoveredEvent(event, kind))
    return sorted(covered, key=lambda item: (item.first_day, item.last_day))


def coverage_windows(events: list[ScribeEvent]) -> list[CoverageWindow]:
    windows: list[list[CoveredEvent]] = []
    window_end: date | None = None
    for covered in covered_events(events):
        if window_end is not None and covered.first_day <= window_end:
            windows[-1].append(covered)
            window_end = max(window_end, covered.last_day)
            continue
        windows.append([covered])
        window_end = covered.last_day
    return [CoverageWindow(tuple(window)) for window in windows]


def upcoming_windows(events: list[ScribeEvent], today: date) -> list[CoverageWindow]:
    return [window for window in coverage_windows(events) if window.last_day >= today]


def channel_slug(covered: CoveredEvent) -> str:
    if covered.kind is WORLDS:
        return "worlds"
    if covered.kind is ARENA_CHAMPIONSHIP:
        number = ARENA_CHAMPIONSHIP_NUMBER.search(covered.event.title)
        return f"ac{number.group(1)}" if number else "ac"
    set_code = active_set_code(covered.starts_at()).lower()
    return f"{covered.kind.key}-{set_code}"


def channel_name(window: CoverageWindow | None) -> str:
    if window is None:
        return f"{CHANNEL_PREFIX}{CHANNEL_SUFFIX}"
    return f"{CHANNEL_PREFIX}{channel_slug(window.headliner)}-{CHANNEL_SUFFIX}"


def _is_qualifier(event: ScribeEvent) -> bool:
    return QUALIFIER_TAG in event.tag_slugs or any(word in event.title for word in QUALIFIER_TITLE_WORDS)
