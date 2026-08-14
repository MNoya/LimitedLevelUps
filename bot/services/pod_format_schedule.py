"""The formats the launcher offers each day.

Hardcoded on purpose. A format has to be known before signups open, so a table someone edits ahead of time
is the whole mechanism: no poll, no derivation, nothing to be decided while players are already signing up.

An entry is the full list of formats a day offers, in the order the launcher shows them. `LATEST` stands for
whichever set is current, so a table written months ahead survives a rotation; a day that drops it entirely
lists only the codes it wants. A plain date sets both of that day's slots, a `(date, lane)` key overrides one
slot, and a day off the table falls back to `default_formats`.

An empty entry closes that slot: the launcher opens no pod there and nothing rolls into it. The Set
Championship closes its own Early Pod without one, since its Saturday is derived, and a slot entry still
overrides that for a championship day meant to carry a second pod anyway.

Entries are set codes or registered cube codes; `test_pod_format_schedule` fails on one that resolves to
neither, so a typo here cannot reach a launcher post. `FLASHBACK` is the one code that is neither: it says a
day is planned as flashback with no set chosen yet, so it renders on the calendar and never reaches the
launcher.
"""
from __future__ import annotations

from collections.abc import Sequence
from datetime import date, datetime, timedelta

from bot.services.championship_dates import championship_date_for
from bot.services.pod_format import PEASANT_CODE
from bot.services.pod_signals import LANE_EARLY, is_weekend
from bot.sets import active_set_code, release_instant


LATEST = "LATEST"
FLASHBACK = "FLASHBACK"
CLOSED: tuple[str, ...] = ()

FORMATS_BY_DAY: dict[date | tuple[date, str], tuple[str, ...]] = {
    date(2026, 7, 20): (LATEST, "FIN"),
    date(2026, 7, 21): (LATEST, "DSK"),
    date(2026, 7, 22): (LATEST, "FIN"),
    date(2026, 7, 23): (LATEST, "FIN"),
    date(2026, 7, 24): (LATEST, "NEO"),
    date(2026, 7, 25): (LATEST, "PEASANT"),
    date(2026, 7, 27): (LATEST, "SOS"),
    date(2026, 7, 28): (LATEST, "MH3"),
    date(2026, 7, 29): (LATEST, "MID"),
    date(2026, 7, 30): (LATEST, "LTR"),
    date(2026, 7, 31): (LATEST, "EOE"),
    date(2026, 8, 1): (LATEST, "PEASANT"),
    date(2026, 8, 2): (LATEST, "PEASANT"),
    date(2026, 8, 3): (LATEST, "STX"),
    date(2026, 8, 4): (LATEST, "DMU"),
    date(2026, 8, 5): (LATEST, "MOM"),
    date(2026, 8, 6): (LATEST, "DOM"),
    date(2026, 8, 7): (LATEST, "ELD"),
    date(2026, 8, 8): (LATEST, "PEASANT"),
    date(2026, 8, 9): (LATEST, "PEASANT"),
    date(2026, 8, 10): (LATEST, "BRO"),
}


def formats_for(day: date, lane: str | None = None, when: datetime | None = None) -> tuple[str, ...]:
    """The pods a slot opens. The slot's own override first, then the whole-day entry, so one line covers the
    common case. `LATEST` resolves to the active set and repeats collapse, so a table entry can never open
    two pods on one format. A day planned as flashback with no set chosen opens nothing.

    `when` is the instant `LATEST` reads the active set at, defaulting to now. A surface rendering days
    ahead passes the day itself through `formats_on`, so a day past a rotation names its own set."""
    return tuple(code for code in _resolved(day, lane, active_set_code(when)) if code != FLASHBACK)


def formats_on(day: date, lane: str | None = None) -> tuple[str, ...]:
    """`formats_for` with `LATEST` read from `day` rather than from today — what a calendar of the weeks
    ahead needs, since a row past a rotation drafts the incoming set, not the one live while it renders."""
    return formats_for(day, lane, when=release_instant(day))


def planned_on(day: date, lane: str | None = None) -> tuple[str, ...]:
    """`formats_on` plus the formats a day is planned to run that open no pod on their own, which is what
    the calendar draws: a tail day reads as flashback there while the launcher leaves it for a moderator."""
    return _resolved(day, lane, latest_on(day))


def default_formats(day: date) -> tuple[str, ...]:
    """A day the table does not name. Inside a set's run every pod drafts that set. From the day after its
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


def _resolved(day: date, lane: str | None, latest: str) -> tuple[str, ...]:
    entry = FORMATS_BY_DAY.get((day, lane)) if lane is not None else None
    if entry is None and lane == LANE_EARLY and championship_date_for(day) == day:
        entry = CLOSED
    if entry is None:
        entry = FORMATS_BY_DAY.get(day, default_formats(day))
    resolved: list[str] = []
    for code in entry:
        format_code = latest if code == LATEST else code
        if format_code not in resolved:
            resolved.append(format_code)
    return tuple(resolved)
