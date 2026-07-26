"""The formats the launcher offers each day.

Hardcoded on purpose. A format has to be known before signups open, so a table someone edits ahead of time
is the whole mechanism: no poll, no derivation, nothing to be decided while players are already signing up.

An entry is the full list of formats a day offers, in the order the launcher shows them. `LATEST` stands for
whichever set is current, so a table written months ahead survives a rotation; a day that drops it entirely
lists only the codes it wants. A plain date sets both of that day's slots, a `(date, lane)` key overrides one
slot, and a day off the table offers `(LATEST,)` — which is also what a fresh set cycle starts as, so
flashback comes back when dates get added here, not automatically.

An empty entry closes that slot: the launcher opens no pod there and nothing rolls into it. That is how a
slot already spoken for by another event, the Set Championship holding the Early Pod on its Saturday, keeps
a second pod from opening on top of it.

Entries are set codes or registered cube codes; `test_pod_format_schedule` fails on one that resolves to
neither, so a typo here cannot reach a launcher post.
"""
from __future__ import annotations

from collections.abc import Sequence
from datetime import date, datetime, timedelta

from bot.services.pod_signals import LANE_EARLY
from bot.sets import active_set_code, release_instant


LATEST = "LATEST"
CLOSED: tuple[str, ...] = ()

FORMATS_BY_DAY: dict[date | tuple[date, str], tuple[str, ...]] = {
    date(2026, 7, 20): (LATEST, "FIN"),
    date(2026, 7, 21): (LATEST, "DSK"),
    date(2026, 7, 22): (LATEST, "FIN"),
    date(2026, 7, 23): (LATEST, "FIN"),
    date(2026, 7, 24): (LATEST, "NEO"),
    date(2026, 7, 25): (LATEST, "PEASANT"),
    date(2026, 7, 26): (LATEST, "SAMP"),
    date(2026, 7, 27): (LATEST, "SOS"),
    date(2026, 7, 28): (LATEST, "MH3"),
    date(2026, 7, 29): (LATEST, "MID"),
    date(2026, 7, 30): (LATEST, "LTR"),
    date(2026, 7, 31): (LATEST, "EOE"),
    date(2026, 8, 1): (LATEST, "PEASANT"),
    (date(2026, 8, 1), LANE_EARLY): CLOSED,
    date(2026, 8, 2): (LATEST, "SAMP"),
    date(2026, 8, 3): (LATEST, "STX"),
    date(2026, 8, 4): (LATEST, "DMU"),
    date(2026, 8, 5): (LATEST, "MOM"),
    date(2026, 8, 6): (LATEST, "DOM"),
    date(2026, 8, 7): (LATEST, "ELD"),
    date(2026, 8, 8): (LATEST, "PEASANT"),
    date(2026, 8, 9): (LATEST, "SAMP"),
    date(2026, 8, 10): (LATEST, "BRO"),
}


def formats_for(day: date, lane: str | None = None, when: datetime | None = None) -> tuple[str, ...]:
    """The slot's own override first, then the whole-day entry, so one line covers the common case. `LATEST`
    resolves to the active set and repeats collapse, so a table entry can never open two pods on one format.

    `when` is the instant `LATEST` reads the active set at, defaulting to now. A surface rendering days
    ahead passes the day itself through `formats_on`, so a day past a rotation names its own set."""
    entry = FORMATS_BY_DAY.get((day, lane)) if lane is not None else None
    if entry is None:
        entry = FORMATS_BY_DAY.get(day, (LATEST,))
    latest = active_set_code(when)
    resolved: list[str] = []
    for code in entry:
        format_code = latest if code == LATEST else code
        if format_code not in resolved:
            resolved.append(format_code)
    return tuple(resolved)


def formats_on(day: date, lane: str | None = None) -> tuple[str, ...]:
    """`formats_for` with `LATEST` read from `day` rather than from today — what a calendar of the weeks
    ahead needs, since a row past a rotation drafts the incoming set, not the one live while it renders."""
    return formats_for(day, lane, when=release_instant(day))


def extras_on(day: date) -> tuple[str, ...]:
    """What a day adds on top of the set every pod already drafts. Empty on a day that offers the set alone,
    which is what a calendar can leave blank instead of repeating the same code in every cell."""
    latest = latest_on(day)
    return tuple(code for code in formats_on(day) if code != latest)


def latest_on(day: date) -> str:
    """The leaderboard set a pod on `day` opens on. Pods start in the afternoon and the board flips at noon
    ET, so the day's own release instant is the boundary that decides it."""
    return active_set_code(release_instant(day))


def calendar_days(around: date, weeks: int) -> list[date]:
    """`weeks` Monday-start weeks, beginning with the week holding `around`."""
    start = around - timedelta(days=around.weekday())
    return [start + timedelta(days=offset) for offset in range(weeks * 7)]


def rotation_in(days: Sequence[date]) -> date | None:
    """The first day in `days` that opens on a different set than the day before it, or None when the whole
    span sits inside one set."""
    for day in days:
        if latest_on(day) != latest_on(day - timedelta(days=1)):
            return day
    return None
