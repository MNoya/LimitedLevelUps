"""Pod-draft slot table, role names, and the underfill-nudge copy.

Pure date/selection logic — no Discord, no DB. The APScheduler wiring lives in bot/tasks/pod_underfill.py.
"""
from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from bot import emojis
from bot.services.pod_reminder_copy import (
    DRAFT_STARTED,
    RECRUITING_BELOW_FLOOR,
    RECRUITING_MAYBE,
    RECRUITING_READY,
    RECRUITING_SECOND_TABLE,
    RECRUITING_SHORT,
)


NUM_RE = re.compile(r"#(\d+)")

SCHEDULE_TZ = ZoneInfo("America/New_York")

WEDNESDAY = 2
THURSDAY = 3
SATURDAY = 5

SLOT_EMOJI_AMERICAS = "🌎"
SLOT_EMOJI_EU = "🇪🇺"
SLOT_EMOJI_SATURDAY = "🪐"

POD_DRAFTERS_ROLE_NAME = "Pod Drafters"
EARLY_POD_ROLE_NAME = "Early Pod"
LATE_POD_ROLE_NAME = "Late Pod"
WEEKEND_EARLY_POD_ROLE_NAME = "Weekend Early Pod"
WEEKEND_LATE_POD_ROLE_NAME = "Weekend Late Pod"
POD_QUEUE_ROLE_NAME = "Pod Draft Queue"
MOCK_DRAFT_ROLE_NAME = "Mock Draft"

CREATE_MENTIONS_EARLY = f"@{EARLY_POD_ROLE_NAME}"
CREATE_MENTIONS_LATE = f"@{LATE_POD_ROLE_NAME}"
CREATE_MENTIONS_WEEKEND = f"@{WEEKEND_EARLY_POD_ROLE_NAME}"
CREATE_DESCRIPTION = f"{SLOT_EMOJI_AMERICAS} Please RSVP"
CREATE_DESCRIPTION_EARLY = f"{SLOT_EMOJI_EU} Early Draft! Please RSVP"
CREATE_DESCRIPTION_SAT = f"{SLOT_EMOJI_SATURDAY} Weekend Draft! Please RSVP"


@dataclass(frozen=True)
class WeeklySlot:
    weekday: int
    start: time
    description: str
    emoji: str
    mentions: str
    send_monday_noon: bool = False


WEEKLY_SLOTS: tuple[WeeklySlot, ...] = (
    WeeklySlot(
        WEDNESDAY, time(20, 0), CREATE_DESCRIPTION, SLOT_EMOJI_AMERICAS, CREATE_MENTIONS_LATE, send_monday_noon=True
    ),
    WeeklySlot(THURSDAY, time(14, 0), CREATE_DESCRIPTION_EARLY, SLOT_EMOJI_EU, CREATE_MENTIONS_EARLY),
    WeeklySlot(SATURDAY, time(15, 0), CREATE_DESCRIPTION_SAT, SLOT_EMOJI_SATURDAY, CREATE_MENTIONS_WEEKEND),
)


def slots_for_week(monday: date) -> list[datetime]:
    return [
        datetime.combine(monday + timedelta(days=slot.weekday), slot.start, tzinfo=SCHEDULE_TZ)
        for slot in WEEKLY_SLOTS
    ]


def slot_by_weekday(weekday: int) -> WeeklySlot | None:
    for slot in WEEKLY_SLOTS:
        if slot.weekday == weekday:
            return slot
    return None


def next_slot_datetime(slot: WeeklySlot, *, now: datetime | None = None) -> datetime:
    """The next future occurrence of a slot in ET, for rendering a localized Discord timestamp."""
    now = now or datetime.now(SCHEDULE_TZ)
    candidate = datetime.combine(
        now.date() + timedelta(days=(slot.weekday - now.weekday()) % 7), slot.start, tzinfo=SCHEDULE_TZ
    )
    if candidate <= now:
        candidate += timedelta(days=7)
    return candidate


def highest_event_number(event_names: Iterable[str]) -> int:
    """Largest '#N' across recorded pod names, so a new pod's number continues upward."""
    highest = 0
    for name in event_names:
        match = NUM_RE.search(name or "")
        if match is not None:
            highest = max(highest, int(match.group(1)))
    return highest


_DATE_SUFFIX_RE = re.compile(r"\s+-\s+[A-Z][a-z]+\s+\d{1,2}$")


def short_event_name(name: str) -> str:
    """Pod name without the trailing ' - Month Day' suffix the scheduler appends, for tight inline copy."""
    return _DATE_SUFFIX_RE.sub("", name)


def build_recruiting_message(
    thread_name: str,
    count: int,
    floor: int,
    aim: int,
    event_time: datetime,
    jump_url: str,
    maybe_count: int = 0,
) -> str:
    """The pod's public status in one message: how many are in, what the next number gets them, and where
    to sign up. One shape carries a pod from its first signup to its lobby, so the surface a player learns
    to read never disappears and never reads as closed.

    One number is asked for at a time. Under the floor the only thing a reader decides is whether to make
    the draft happen, so the aim would compete with the ask; past the floor the aim is the ask. A full pod
    has nothing left to ask for and switches to its Yes and Maybe counts, keeping the link, because a player
    who drops at game time is the common way an eight-player pod plays with seven. Once Yes and Maybe
    together reach two tables, the same line says so.

    Never adds a role mention — pinging is the caller's call; edits keep a mention already in the message so
    a pinged player still sees why."""
    name = short_event_name(thread_name)
    unix = int(event_time.timestamp())
    shared = {
        "hello": emojis.prefix("chordoHello"), "name": name, "count": count, "unix": unix,
        "jump_url": jump_url, "manat": emojis.get("manat"),
    }
    if count < floor:
        needed = floor - count
        return RECRUITING_BELOW_FLOOR.format(to_floor=needed, plural=_plural(needed), **shared).rstrip()
    if count < aim:
        needed = aim - count
        return RECRUITING_SHORT.format(to_aim=needed, plural=_plural(needed), **shared).rstrip()
    maybe = RECRUITING_MAYBE.format(maybe=maybe_count) if maybe_count else ""
    tail = RECRUITING_SECOND_TABLE if count + maybe_count >= 2 * aim else ""
    return RECRUITING_READY.format(yes=count, maybe=maybe, tail=tail, **shared).rstrip()


def _plural(count: int) -> str:
    return "" if count == 1 else "s"


def build_underfill_fired_message(name: str, player_count: int, thread_url: str) -> str:
    """The terminal form of the recruiting nudge once the draft starts: a fired record linking the pod
    thread. Carries no signup link, so `clear_underfill_nudge` cannot match it and a later cancel leaves
    the record standing. A Team Draft shows through the linked thread, which the bot renames on lock, so
    the copy stays one line for every pod."""
    players = "players" if player_count != 1 else "player"
    return DRAFT_STARTED.format(
        hello=emojis.prefix("chordoHello"), name=short_event_name(name), count=player_count,
        players=players, thread_url=thread_url, manat=emojis.get("manat"),
    )


