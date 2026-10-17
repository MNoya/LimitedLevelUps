"""When each Set Championship and flashback season vote happens, derived from `bot.sets` and the Scribe calendar.

Split out of `championship` so the surfaces that only need the date stay clear of the ORM: that module
carries the frozen-seed half, which imports the models and a session, and the pod format schedule and its
calendar image would drag all of it into a render otherwise. `championship` re-exports everything here, so
callers that want the whole subsystem keep one import.

The championship for a set is held the Saturday before its successor's prerelease weekend at 2 PM ET, and
is created `CREATION_LEAD_DAYS` ahead so the standings freeze and the invite waves have runway.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from functools import cache

from bot.services import mtgscribe
from bot.sets import (
    ALL_SETS,
    RELEASE_TZ,
    SetSeed,
    active_set_code,
    prerelease_date_for,
    previous_weekday,
    release_instant,
    seed_for_code,
)

SATURDAY = 5
CHAMPIONSHIP_TIME = time(14, 0)
CREATION_LEAD_DAYS = 5
CREATION_HOUR_ET = 12
BALLOT_LEAD_DAYS = 3
BALLOT_OPENS_AT = time(13, 0)
PARALLEL_LEAD_DAYS = 14
VOTE_REMINDER_LAG_DAYS = 2
SEASON_START_OVERRIDES: dict[str, date] = {"HOB": date(2026, 8, 30)}
CHAMPIONSHIP_DATE_OVERRIDES: dict[str, date] = {"FRA": date(2026, 11, 7)}
BALLOT_DATE_OVERRIDES: dict[str, date] = {"FRA": date(2026, 10, 17)}
VOTE_REMINDER_DATE_OVERRIDES: dict[str, date] = {"FRA": date(2026, 10, 18)}


@dataclass(frozen=True)
class ChampionshipPlan:
    set_code: str
    set_name: str
    event_at: datetime
    create_on: date
    next_set_code: str
    next_set_name: str
    next_release_at: datetime


def championship_date_before(prerelease: date) -> date:
    """The championship Saturday for a successor whose prerelease weekend opens on `prerelease`: the
    Saturday before it, whether that weekend starts on the Thursday or the Friday."""
    return previous_weekday(prerelease, SATURDAY)


def plan_for(when: datetime | None = None) -> ChampionshipPlan | None:
    """The championship plan for the set active at `when`, or None when the active set is the newest
    registered entry and has no successor to anchor the date to."""
    active = active_set_code(when)
    codes = [seed.code for seed in ALL_SETS]
    index = codes.index(active)
    if index + 1 >= len(ALL_SETS):
        return None
    current = ALL_SETS[index]
    successor = ALL_SETS[index + 1]
    event_date = CHAMPIONSHIP_DATE_OVERRIDES.get(current.code)
    if event_date is None:
        event_date = championship_date_before(prerelease_date_for(successor))
    event_at = datetime.combine(event_date, CHAMPIONSHIP_TIME, tzinfo=RELEASE_TZ)
    return ChampionshipPlan(
        set_code=current.code,
        set_name=current.name,
        event_at=event_at,
        create_on=event_date - timedelta(days=CREATION_LEAD_DAYS),
        next_set_code=successor.code,
        next_set_name=successor.name,
        next_release_at=release_instant(successor.start_date),
    )


def championship_date_for(day: date) -> date | None:
    """The championship day of the set live on `day`, or None when that set has no successor to anchor one.
    Read per day rather than from the plan live as a surface renders, so a span crossing a rotation finds
    each set's own championship."""
    plan = plan_for(release_instant(day))
    return plan.event_at.date() if plan is not None else None


def championship_on(day: date) -> datetime | None:
    """When the championship `day` itself holds starts, or None on every other day."""
    plan = plan_for(release_instant(day))
    return plan.event_at if plan is not None and plan.event_at.date() == day else None


def signup_post_at(plan: ChampionshipPlan) -> datetime:
    """When the tick posts the signup card."""
    return datetime.combine(plan.create_on, time(CREATION_HOUR_ET), tzinfo=RELEASE_TZ)


def plan_due_for_creation(when: datetime) -> ChampionshipPlan | None:
    """The plan whose creation day is the ET date of `when`, else None. The caller still guards
    against double-creation; this only answers 'is today the day to post it'."""
    plan = plan_for(when)
    if plan is None:
        return None
    return plan if when.astimezone(RELEASE_TZ).date() == plan.create_on else None


@cache
def season_start(set_code: str) -> date | None:
    """The first day of a set's flashback season: the day before Arena's first flashback queue inside the set's
    window, three weeks after release when Scribe lists none yet. None for an unregistered set."""
    override = SEASON_START_OVERRIDES.get(set_code)
    if override is not None:
        return override
    seed = seed_for_code(set_code)
    if seed is None:
        return None
    first_flashback = _first_arena_flashback(seed)
    if first_flashback is None:
        return seed.start_date + timedelta(weeks=3)
    return first_flashback - timedelta(days=1)


def vote_opens_at(plan: ChampionshipPlan) -> datetime | None:
    """An hour before the Early Pod `BALLOT_LEAD_DAYS` ahead of the season start"""
    ballot_date = BALLOT_DATE_OVERRIDES.get(plan.set_code)
    if ballot_date is None:
        start = season_start(plan.set_code)
        if start is None:
            return None
        ballot_date = start - timedelta(days=BALLOT_LEAD_DAYS)
    return datetime.combine(ballot_date, BALLOT_OPENS_AT, tzinfo=RELEASE_TZ)


def vote_reminder_at(plan: ChampionshipPlan) -> datetime | None:
    reminder_date = VOTE_REMINDER_DATE_OVERRIDES.get(plan.set_code)
    if reminder_date is not None:
        return datetime.combine(reminder_date, BALLOT_OPENS_AT, tzinfo=RELEASE_TZ)
    opens_at = vote_opens_at(plan)
    if opens_at is None:
        return None
    return opens_at + timedelta(days=VOTE_REMINDER_LAG_DAYS)


def voting_open(when: datetime | None = None) -> bool:
    """Whether the format vote is live now: from the ballot open through the rotation that ends the season."""
    plan = plan_for(when)
    if plan is None:
        return False
    opens_at = vote_opens_at(plan)
    if opens_at is None:
        return False
    now = when if when is not None else datetime.now(RELEASE_TZ)
    return opens_at <= now < plan.next_release_at


def vote_ping_due(when: datetime) -> ChampionshipPlan | None:
    """The plan whose ballot opened within the day before `when`, for the one opening ping, else None"""
    plan = plan_for(when)
    if plan is None:
        return None
    return plan if _within_a_day_after(vote_opens_at(plan), when) else None


def vote_reminder_due(when: datetime) -> ChampionshipPlan | None:
    """The plan whose reminder fell due within the day before `when`, for the single reminder ping, else None"""
    plan = plan_for(when)
    if plan is None:
        return None
    return plan if _within_a_day_after(vote_reminder_at(plan), when) else None


def _within_a_day_after(instant: datetime | None, when: datetime) -> bool:
    return instant is not None and instant <= when < instant + timedelta(days=1)


def _first_arena_flashback(seed: SetSeed) -> date | None:
    first = None
    for event in mtgscribe.load_events():
        if not mtgscribe.is_set_flashback(event):
            continue
        day = event.start.astimezone(RELEASE_TZ).date()
        if not seed.start_date <= day <= seed.end_date:
            continue
        if first is None or day < first:
            first = day
    return first
