"""The formats the launcher offers each day, resolved against a DB overlay.

A slot is one of the two daily draft positions (Early or Late) on one day. `pod_schedule_slots` holds the
overlay: a row per (day, slot) whose `formats` list names the codes that slot opens, in launcher order.
`LATEST` stands for whichever set is current, so a
row written months ahead survives a rotation; an empty list closes the slot. A slot with no overlay row falls
back to `default_formats`.

`load_overlay` reads one window in a single query and `schedule_overlay` parks it in a ContextVar for the
render's duration, so every per-cell resolution reads memory. A render that opens no overlay resolves through
`default_formats` alone, which is the schedule with nothing overridden.

Codes are set codes or registered cube codes; `FLASHBACK` is the one that is neither: it marks a day planned
as flashback with no set chosen yet, so it draws on the calendar and never reaches the launcher.
"""
from __future__ import annotations

from collections.abc import Sequence
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from bot.models import PodDraftEvent, PodScheduleSlot
from bot.services.championship_dates import PARALLEL_LEAD_DAYS, championship_date_for, plan_for
from bot.services.pod_format import PEASANT_CODE, resolve_format_code
from bot.services.pod_signals import SLOT_EARLY, SLOT_LATE, is_weekend
from bot.sets import active_set_code, release_instant


LATEST = "LATEST"
FLASHBACK = "FLASHBACK"
CLOSED: tuple[str, ...] = ()

_DAY_SLOTS = (SLOT_EARLY, SLOT_LATE)


@dataclass(frozen=True)
class SlotOverlay:
    rows: dict[tuple[date, str], tuple[str, ...]]
    real_formats: dict[date, tuple[str, ...]]


_overlay: ContextVar[SlotOverlay | None] = ContextVar("pod_schedule_overlay", default=None)


def load_overlay(session: Session, start: date, end: date) -> SlotOverlay:
    result = session.execute(
        select(PodScheduleSlot.day, PodScheduleSlot.slot, PodScheduleSlot.formats)
        .where(PodScheduleSlot.day >= start, PodScheduleSlot.day <= end)
    )
    rows = {(day, slot_key): tuple(formats) for day, slot_key, formats in result}
    return SlotOverlay(rows=rows, real_formats=_load_real_formats(session, start, end))


@contextmanager
def schedule_overlay(session: Session, start: date, end: date):
    token = _overlay.set(load_overlay(session, start, end))
    try:
        yield
    finally:
        _overlay.reset(token)


def set_slot(
    session: Session, day: date, slot_key: str, formats: Sequence[str], *, source: str = "manual",
    decided_by: str | None = None,
) -> None:
    """Write one slot's overlay row, replacing any row already on that (day, slot_key). An empty `formats`
    closes the slot. `source='manual'` marks an owner override the weekly allocator never overwrites."""
    session.execute(delete(PodScheduleSlot).where(PodScheduleSlot.day == day, PodScheduleSlot.slot == slot_key))
    session.add(PodScheduleSlot(
        day=day, slot=slot_key, formats=list(formats), source=source,
        decided_by=decided_by, decided_at=datetime.now(timezone.utc),
    ))
    session.flush()


def manual_slots(session: Session, start: date, end: date) -> set[tuple[date, str]]:
    """The (day, slot) pairs an organizer has overridden in the window, which the allocator leaves alone."""
    rows = session.execute(
        select(PodScheduleSlot.day, PodScheduleSlot.slot)
        .where(PodScheduleSlot.day >= start, PodScheduleSlot.day <= end, PodScheduleSlot.source == "manual")
    )
    return {(day, slot) for day, slot in rows}


def auto_slots(session: Session, start: date, end: date) -> set[tuple[date, str]]:
    """The (day, slot) pairs the allocator already filled in the window, so a top-up sweep leaves them in place"""
    rows = session.execute(
        select(PodScheduleSlot.day, PodScheduleSlot.slot)
        .where(PodScheduleSlot.day >= start, PodScheduleSlot.day <= end, PodScheduleSlot.source == "auto")
    )
    return {(day, slot) for day, slot in rows}


def clear_auto_slots(session: Session, start: date, end: date, *, except_days: frozenset[date] = frozenset()) -> None:
    """Drop the allocator's own rows in the window before it writes fresh ones, so a slot it no longer fills
    falls back to the default rather than keeping a stale format. `except_days` are left untouched, which is how
    a re-sweep keeps the days already on the launcher."""
    query = (
        delete(PodScheduleSlot)
        .where(PodScheduleSlot.day >= start, PodScheduleSlot.day <= end, PodScheduleSlot.source == "auto")
    )
    if except_days:
        query = query.where(PodScheduleSlot.day.notin_(except_days))
    session.execute(query)
    session.flush()


def formats_for(day: date, slot_key: str | None = None, when: datetime | None = None) -> tuple[str, ...]:
    """The pods a slot opens. The slot's overlay row first, then the derived default, so a day with no row
    stays on the set. `LATEST` resolves to the active set and repeats collapse, so a row can never open two
    pods on one format. A day planned as flashback with no set chosen opens nothing.

    `when` is the instant `LATEST` reads the active set at, defaulting to now. A surface rendering days ahead
    passes the day itself through `formats_on`, so a day past a rotation names its own set."""
    return tuple(code for code in _resolved(day, slot_key, active_set_code(when)) if code != FLASHBACK)


def formats_on(day: date, slot_key: str | None = None) -> tuple[str, ...]:
    """`formats_for` with `LATEST` read from `day` rather than from today — what a calendar of the weeks
    ahead needs, since a row past a rotation drafts the incoming set, not the one live while it renders."""
    return formats_for(day, slot_key, when=release_instant(day))


def planned_on(day: date, slot_key: str | None = None) -> tuple[str, ...]:
    """`formats_on` plus the formats a day is planned to run that open no pod on their own, plus the pods that
    actually exist that day, which is what the calendar draws: a tail day reads as flashback there while the
    launcher leaves it for a moderator, and an off-grid draft shows instead of hiding. A real pod supersedes
    the flashback placeholder, since it names the set the placeholder was still missing."""
    planned = _resolved(day, slot_key, latest_on(day))
    real = _real_formats(day)
    if not real:
        return planned
    merged = [code for code in planned if code != FLASHBACK]
    for code in real:
        if code not in merged:
            merged.append(code)
    return tuple(merged)


def scheduled_formats(day: date) -> tuple[str, ...]:
    """The formats a day is scheduled to run, the `FLASHBACK` placeholder kept, without the real-pod merge
    `planned_on` adds. A day still on the latest set alone returns one code; a community day returns two."""
    return _resolved(day, None, latest_on(day))


def default_formats(day: date) -> tuple[str, ...]:
    """A day no overlay row names. Inside a set's run every pod drafts that set. From the day after its
    championship the latest-set pods stop, so the days left before the rotation run cube on the weekend and
    flashback in the week, where no set is chosen yet."""
    championship = championship_date_for(day)
    if championship is None or day <= championship:
        return (LATEST,)
    return (PEASANT_CODE,) if is_weekend(day) else (FLASHBACK,)


def extras_on(day: date) -> tuple[str, ...]:
    """What a day adds on top of the set every pod already drafts. Empty on a day that offers the set alone,
    which is what a calendar can leave blank instead of repeating the same code in every cell."""
    latest = latest_on(day)
    return tuple(code for code in planned_on(day) if code != latest)


def community_slots_on(day: date) -> tuple[str, ...]:
    """The slots the weekly allocator may fill with a voted community format on `day`. None before the
    parallel phase, the late slot through the championship, both slots in the tail after it. Derived from the
    championship plan alone, so a day past a rotation belongs to the next set and reads as latest-only again."""
    plan = plan_for(release_instant(day))
    if plan is None:
        return ()
    championship = plan.event_at.date()
    if day < championship - timedelta(days=PARALLEL_LEAD_DAYS):
        return ()
    if day <= championship:
        return (SLOT_LATE,)
    return (SLOT_EARLY, SLOT_LATE)


def latest_on(day: date) -> str:
    """The leaderboard set a pod on `day` opens on. Pods start in the afternoon and the board flips at noon
    ET, so the day's own release instant is the boundary that decides it."""
    return active_set_code(release_instant(day))


def calendar_days(around: date, weeks: int) -> list[date]:
    """`weeks` Monday-start weeks, beginning with the week holding `around`."""
    start = around - timedelta(days=around.weekday())
    return [start + timedelta(days=offset) for offset in range(weeks * 7)]


def is_rotation_day(day: date) -> bool:
    """Whether `day` opens on a different set than the day before it."""
    return latest_on(day) != latest_on(day - timedelta(days=1))


def rotation_in(days: Sequence[date], after: datetime | None = None) -> date | None:
    """The first rotation in `days`, or None when the span holds none. `after` drops the rotations already
    made, so a span long enough to carry two still names the one a reader is waiting for."""
    for day in days:
        if is_rotation_day(day) and (after is None or release_instant(day) > after):
            return day
    return None


def weeks_until_next_rotation(around: date, cap: int) -> int:
    for weeks in range(1, cap + 1):
        if rotation_in(calendar_days(around, weeks), release_instant(around)) is not None:
            return weeks
    return cap


def _resolved(day: date, slot_key: str | None, latest: str) -> tuple[str, ...]:
    if slot_key is None:
        codes: list[str] = []
        for day_slot in _DAY_SLOTS:
            for code in _resolved(day, day_slot, latest):
                if code not in codes:
                    codes.append(code)
        return tuple(codes)
    entry = _slot_entry(day, slot_key)
    if entry is None and slot_key == SLOT_EARLY and championship_date_for(day) == day:
        entry = CLOSED
    if entry is None:
        entry = default_formats(day)
    resolved: list[str] = []
    for code in entry:
        format_code = latest if code == LATEST else code
        if format_code not in resolved:
            resolved.append(format_code)
    return tuple(resolved)


def _slot_entry(day: date, slot_key: str) -> tuple[str, ...] | None:
    overlay = _overlay.get()
    if overlay is None:
        return None
    return overlay.rows.get((day, slot_key))


def _real_formats(day: date) -> tuple[str, ...]:
    overlay = _overlay.get()
    if overlay is None:
        return ()
    return overlay.real_formats.get(day, ())


def _load_real_formats(session: Session, start: date, end: date) -> dict[date, tuple[str, ...]]:
    result = session.execute(
        select(PodDraftEvent.event_date, PodDraftEvent.set_code)
        .where(PodDraftEvent.event_date >= start, PodDraftEvent.event_date <= end, PodDraftEvent.kind != "mock")
        .distinct()
    )
    formats: dict[date, list[str]] = {}
    for event_date, set_code in result:
        code = resolve_format_code(set_code)
        if code is None:
            continue
        codes = formats.setdefault(event_date, [])
        if code not in codes:
            codes.append(code)
    return {day: tuple(codes) for day, codes in formats.items()}
