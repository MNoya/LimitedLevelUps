from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from bot.services.pro_events import ARENA_CHAMPIONSHIP, HEADLINER_ORDER, WORLDS, CoveredEvent
from bot.sets import active_set_code

CHANNEL_PREFIX = "📺🎉-"
CHANNEL_SUFFIX = "watch-party"
CHANNEL_TZ = ZoneInfo("America/New_York")
UPCOMING_LEAD = timedelta(days=7)
NAME_HOLD = timedelta(days=7)


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


def coverage_windows(events: Sequence[CoveredEvent]) -> list[CoverageWindow]:
    windows: list[list[CoveredEvent]] = []
    window_end: date | None = None
    for covered in sorted(events, key=lambda item: (item.first_day, item.last_day)):
        if window_end is not None and covered.first_day <= window_end:
            windows[-1].append(covered)
            window_end = max(window_end, covered.last_day)
            continue
        windows.append([covered])
        window_end = covered.last_day
    return [CoverageWindow(tuple(window)) for window in windows]


def upcoming_windows(events: Sequence[CoveredEvent], today: date) -> list[CoverageWindow]:
    return [window for window in coverage_windows(events) if window.last_day >= today]


def named_window(windows: list[CoverageWindow], today: date) -> CoverageWindow | None:
    latest = None
    following = None
    for window in windows:
        if window.last_day < today:
            latest = window
        elif following is None:
            following = window
    if following is None:
        return latest
    if latest is None or following.first_day <= today:
        return following
    held = latest.headliner.kind.headline and today <= latest.last_day + NAME_HOLD
    if not held and today >= following.first_day - UPCOMING_LEAD:
        return following
    return latest


def channel_slug(covered: CoveredEvent) -> str:
    if covered.kind is WORLDS:
        return "worlds"
    if covered.kind is ARENA_CHAMPIONSHIP:
        return f"ac{covered.edition_number or ''}"
    set_code = active_set_code(covered.starts_at()).lower()
    return f"{covered.kind.key}-{set_code}"


def channel_name(window: CoverageWindow | None) -> str:
    if window is None:
        return f"{CHANNEL_PREFIX}{CHANNEL_SUFFIX}"
    return f"{CHANNEL_PREFIX}{channel_slug(window.headliner)}-{CHANNEL_SUFFIX}"
