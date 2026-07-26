"""The formats the launcher offers each day.

Hardcoded on purpose. A format has to be known before signups open, so a table someone edits ahead of time
is the whole mechanism: no poll, no derivation, nothing to be decided while players are already signing up.

An entry is the full list of formats a day offers, in the order the launcher shows them. `LATEST` stands for
whichever set is current, so a table written months ahead survives a rotation; a day that drops it entirely
lists only the codes it wants. A plain date sets both of that day's slots, a `(date, lane)` key overrides one
slot, and a day off the table offers `(LATEST,)` — which is also what a fresh set cycle starts as, so
flashback comes back when dates get added here, not automatically.

Entries are set codes or registered cube codes; `test_pod_format_schedule` fails on one that resolves to
neither, so a typo here cannot reach a launcher post.
"""
from __future__ import annotations

from datetime import date

from bot.sets import active_set_code


LATEST = "LATEST"

FORMATS_BY_DAY: dict[date | tuple[date, str], tuple[str, ...]] = {
    date(2026, 7, 25): (LATEST, "PEASANT"),
    date(2026, 7, 26): (LATEST, "SAMP"),
    date(2026, 7, 27): (LATEST, "SOS"),
    date(2026, 7, 28): (LATEST, "MH3"),
    date(2026, 7, 29): (LATEST, "MID"),
    date(2026, 7, 30): (LATEST, "LTR"),
    date(2026, 7, 31): (LATEST, "EOE"),
    date(2026, 8, 3): (LATEST, "STX"),
    date(2026, 8, 4): (LATEST, "DMU"),
    date(2026, 8, 5): (LATEST, "MOM"),
    date(2026, 8, 6): (LATEST, "DOM"),
    date(2026, 8, 7): (LATEST, "ELD"),
    date(2026, 8, 10): (LATEST, "BRO"),
}


def formats_for(day: date, lane: str | None = None) -> tuple[str, ...]:
    """The slot's own override first, then the whole-day entry, so one line covers the common case. `LATEST`
    resolves to the active set and repeats collapse, so a table entry can never open two pods on one format."""
    entry = FORMATS_BY_DAY.get((day, lane)) if lane is not None else None
    if entry is None:
        entry = FORMATS_BY_DAY.get(day, (LATEST,))
    resolved: list[str] = []
    for code in entry:
        format_code = active_set_code() if code == LATEST else code
        if format_code not in resolved:
            resolved.append(format_code)
    return tuple(resolved)
