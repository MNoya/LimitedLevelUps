"""When each Set Championship is held, derived from `bot.sets` alone.

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

from bot.sets import ALL_SETS, RELEASE_TZ, active_set_code, prerelease_date_for, previous_weekday, release_instant

SATURDAY = 5
CHAMPIONSHIP_TIME = time(14, 0)
CREATION_LEAD_DAYS = 5
CREATION_HOUR_ET = 12
BALLOT_LEAD_DAYS = 21
PARALLEL_LEAD_DAYS = 14
VOTE_REMINDER_LAG_DAYS = 2


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


def vote_opens_at(plan: ChampionshipPlan) -> datetime:
    """When the community format vote opens: `BALLOT_LEAD_DAYS` before the championship."""
    return plan.event_at - timedelta(days=BALLOT_LEAD_DAYS)


def voting_open(when: datetime | None = None) -> bool:
    """Whether the format vote is live now: from the ballot open through the rotation that ends the season."""
    plan = plan_for(when)
    if plan is None:
        return False
    now = when if when is not None else datetime.now(RELEASE_TZ)
    return vote_opens_at(plan) <= now < plan.next_release_at


def vote_ping_due(when: datetime) -> ChampionshipPlan | None:
    """The plan whose ballot opens on the ET date of `when`, for the one opening ping, else None."""
    plan = plan_for(when)
    if plan is None:
        return None
    return plan if when.astimezone(RELEASE_TZ).date() == vote_opens_at(plan).date() else None


def vote_reminder_due(when: datetime) -> ChampionshipPlan | None:
    """The plan whose ballot opened `VOTE_REMINDER_LAG_DAYS` before the ET date of `when`, for the single
    reminder ping, else None."""
    plan = plan_for(when)
    if plan is None:
        return None
    reminder_date = vote_opens_at(plan).date() + timedelta(days=VOTE_REMINDER_LAG_DAYS)
    return plan if when.astimezone(RELEASE_TZ).date() == reminder_date else None
