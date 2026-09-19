"""Resolve the pod format calendar into rows the site renders, rebuilt by the schedule tick.

Mirrors the cell logic in pod_schedule_image._rows_for so the website calendar matches the Discord card:
a championship day shows CHAMPS, a rotation day leads with the arriving set, and every other day lists the
formats the schedule planned for it. Colours are named as roles here and mapped to the palette on the client.
"""
from __future__ import annotations

from datetime import date

from sqlalchemy import delete
from sqlalchemy.orm import Session

from bot.models import PodCalendarDay
from bot.services.championship_dates import championship_on
from bot.services.pod_format import is_custom
from bot.services.pod_format_schedule import (
    FLASHBACK,
    calendar_days,
    extras_on,
    is_rotation_day,
    latest_on,
    scheduled_formats,
    schedule_overlay,
    weeks_until_next_rotation,
)

# The site shows this many weeks collapsed, then expands to the week of the next set, capped at MAX_WEEKS
COLLAPSED_WEEKS = 2
MAX_WEEKS = 8
MAX_CELL_FORMATS = 2
PLACEHOLDER_LABEL = "TBD"


def _entry(code: str, latest: str) -> dict:
    if code == FLASHBACK:
        return {"label": PLACEHOLDER_LABEL, "glyph": FLASHBACK, "role": "flashback"}
    if is_custom(code):
        role = "cube"
    elif code == latest:
        role = "latest"
    else:
        role = "flashback"
    return {"label": code, "glyph": code, "role": role}


def _entries_for(day: date) -> list[dict]:
    if championship_on(day) is not None:
        return [{"label": "CHAMPS", "glyph": latest_on(day), "role": "championship"}]
    latest = latest_on(day)
    if is_rotation_day(day):
        rows = [{"label": latest, "glyph": latest, "role": "arrival"}]
        rows.extend(_entry(code, latest) for code in extras_on(day))
        return rows[:MAX_CELL_FORMATS]
    return [_entry(code, latest) for code in scheduled_formats(day)][:MAX_CELL_FORMATS]


def _band_for(day: date) -> str | None:
    if is_rotation_day(day):
        return "arrival"
    if championship_on(day) is not None:
        return "championship"
    return None


def resolve_calendar(session: Session, today: date) -> list[PodCalendarDay]:
    weeks = max(COLLAPSED_WEEKS, weeks_until_next_rotation(today, MAX_WEEKS))
    days = calendar_days(today, weeks)
    with schedule_overlay(session, days[0], days[-1]):
        return [PodCalendarDay(day=day, entries=_entries_for(day), band=_band_for(day)) for day in days]


def persist_calendar(session: Session, today: date) -> int:
    """Rewrite the whole calendar window in one pass, so a day that drops out of range leaves no stale row."""
    rows = resolve_calendar(session, today)
    session.execute(delete(PodCalendarDay))
    session.add_all(rows)
    session.flush()
    return len(rows)
