"""The second format the launcher offers each day beside the latest set.

Hardcoded on purpose. The format has to be known before signups open, so a table someone edits ahead of
time is the whole mechanism: no poll, no derivation, nothing to be decided while players are already
signing up. A day with no entry offers only the latest set, which is also what a fresh set cycle starts
as — flashback comes back when dates get added here, not automatically.

A plain date sets both of that day's slots. A `(date, lane)` key overrides one slot, for a day that wants
a format at one time and nothing, or something else, at the other. Entries are set codes or registered
cube codes; `test_pod_format_schedule` fails on one that resolves to neither, so a typo here cannot reach
a launcher post.
"""
from __future__ import annotations

from datetime import date


OTHER_FORMAT_BY_DAY: dict[date | tuple[date, str], str] = {
    date(2026, 7, 25): "PEASANT",
    date(2026, 7, 26): "SAMP",
    date(2026, 7, 27): "DMU",
    date(2026, 7, 28): "MOM",
    date(2026, 7, 29): "EOE",
    date(2026, 7, 30): "BRO",
    date(2026, 7, 31): "LTR",
}


def other_format_for(day: date, lane: str | None = None) -> str | None:
    """The slot's own override first, then the whole-day entry, so one line covers the common case."""
    if lane is not None and (day, lane) in OTHER_FORMAT_BY_DAY:
        return OTHER_FORMAT_BY_DAY[(day, lane)]
    return OTHER_FORMAT_BY_DAY.get(day)
