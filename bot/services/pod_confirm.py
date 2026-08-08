"""The confirmation window for a busy pod: who has answered in the hour before the draft, how many
players the room should plan around, and the table shape that seats them.

Read by the T-60 roster reminder, which asks for the answers, and by the lobby, which uses them to decide
whether starting with eight leaves people out.
"""
from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import select

from bot.commands.messages import (
    MSG_SHAPE_JOIN,
    MSG_SHAPE_TABLE_MANY,
    MSG_SHAPE_TABLE_ONE,
    MSG_SHAPE_TEAM_DRAFT,
)
from bot.database import SessionLocal
from bot.models import PodSignal, PodSignalMember
from bot.services.pod_signals import RSVP_MAYBE, RSVP_YES


CONFIRM_TRIGGER_YES = 8
CONFIRM_WINDOW_MINUTES = 60
POD_SIZES = (8, 6, 10)
RECRUITABLE_REMAINDER = 5
CONFIRMED = "confirmed"


@dataclass(frozen=True)
class Attendance:
    """The three answers a signup can be holding an hour out. Saying they cannot make it deletes the
    signup, so anyone who dropped is absent from all three."""

    confirmed: tuple[str, ...] = ()
    yes: tuple[str, ...] = ()
    maybe: tuple[str, ...] = ()

    @property
    def expected(self) -> int:
        """Players to plan around. An unanswered Yes still counts, because not answering is not a
        withdrawal and most people never answer. An unanswered Maybe holds nothing up."""
        return len(self.confirmed) + len(self.yes)

    @property
    def signed_up(self) -> int:
        return len(self.confirmed) + len(self.yes) + len(self.maybe)

    @property
    def answered(self) -> bool:
        return bool(self.confirmed)


def opens_confirmation(attendance: Attendance) -> bool:
    """A full table of committed players is where both failure modes go live: one more player of any kind
    and somebody gets left out, one fewer than expected and the table cannot fire at all."""
    return attendance.expected >= CONFIRM_TRIGGER_YES


@dataclass(frozen=True)
class Table:
    """One table: who is on it, and how many seats it is holding open."""

    seated: int
    capacity: int

    @property
    def full(self) -> bool:
        return self.seated >= self.capacity

    @property
    def empty_seats(self) -> int:
        return max(0, self.capacity - self.seated)


@dataclass(frozen=True)
class TablePlan:
    tables: tuple[Table, ...]

    @property
    def splits(self) -> bool:
        return len(self.tables) > 1

    @property
    def seated(self) -> int:
        return sum(table.seated for table in self.tables)


def plan_tables(n: int) -> TablePlan:
    """Seat n players in pods of 8, 6, or 10.

    Each table takes the largest size it can while leaving behind either nobody or a group close enough to
    a pod to recruit into one. That one rule produces every shape the room wants: twelve splits 6 and 6
    because a table of 8 would strand four with nowhere to go, thirteen runs 8 and leaves five who need a
    single player, and thirty becomes 8 + 8 + 8 + 6 rather than three tens.

    A remainder of five is one player short of a draft, which this server can usually find. Four or fewer
    is not close enough to justify shrinking the table that could be playing now.
    """
    sizes: list[int] = []
    remaining = n
    while remaining >= min(POD_SIZES):
        size = _clean_table(remaining)
        if size is None:
            size = _largest_pod_within(remaining)
            sizes.append(size)
            remaining -= size
            break
        sizes.append(size)
        remaining -= size
    tables = [Table(seated=size, capacity=size) for size in sizes]
    return TablePlan(tuple(_absorb(tables, remaining)))


POD_AIM = 8


def card_plan(attendance: Attendance) -> TablePlan:
    """The plan as the roster card draws it, which aims at a table of eight until the room says otherwise.

    Eight is what the first Draftmancer table is opened for, so a quiet pod shows eight seats with the
    empty ones visible rather than shrinking to a table of six nobody has decided on. Once the room is big
    enough to split, the real plan takes over and the sizes are the ones it will actually run."""
    plan = plan_tables(attendance.expected)
    if len(plan.tables) == 1 and plan.tables[0].capacity < POD_AIM:
        return TablePlan((Table(seated=plan.tables[0].seated, capacity=POD_AIM),))
    return plan


def attendance_for_event_sync(event_id: str) -> Attendance:
    """The answers currently held by the pod behind this event.

    Empty for a pod with no signup roster, which is what a queue or poll pod is, and is why those never
    hold a lobby up: there is nobody the bot could say it is waiting for."""
    with SessionLocal() as session:
        signal = session.execute(
            select(PodSignal).where(PodSignal.event_id == event_id)
        ).scalar_one_or_none()
        if signal is None:
            return Attendance()
        rows = session.execute(
            select(PodSignalMember.rsvp, PodSignalMember.display_name, PodSignalMember.confirmed_at)
            .where(PodSignalMember.signal_id == signal.id)
            .order_by(PodSignalMember.created_at)
        ).all()
    buckets: dict[str, list[str]] = {CONFIRMED: [], RSVP_YES: [], RSVP_MAYBE: []}
    for state, name, confirmed_at in rows:
        bucket = CONFIRMED if confirmed_at is not None else state
        if bucket in buckets:
            buckets[bucket].append(name)
    return Attendance(
        confirmed=tuple(buckets[CONFIRMED]), yes=tuple(buckets[RSVP_YES]), maybe=tuple(buckets[RSVP_MAYBE]),
    )


def confirm_present_players_sync(event_id: str, discord_ids: Iterable[str]) -> int:
    """Stamp a confirmation for signups who turned up in the Draftmancer lobby, and say how many were
    stamped.

    Being in the room is the answer the confirmation asks for, and a stronger one than any button: the
    seat is not saved, it is taken. Only a signup still holding no confirmation is touched, so a lobby
    broadcasting through a whole draft writes nothing after the first pass."""
    ids = list(discord_ids)
    if not ids:
        return 0
    with SessionLocal() as session:
        signal = session.execute(
            select(PodSignal).where(PodSignal.event_id == event_id)
        ).scalar_one_or_none()
        if signal is None:
            return 0
        members = session.execute(
            select(PodSignalMember).where(
                PodSignalMember.signal_id == signal.id,
                PodSignalMember.discord_user_id.in_(ids),
                PodSignalMember.confirmed_at.is_(None),
            )
        ).scalars().all()
        now = datetime.now(timezone.utc)
        for member in members:
            member.confirmed_at = now
            member.rsvp = RSVP_YES
        session.commit()
        return len(members)


def _absorb(tables: list[Table], remaining: int) -> list[Table]:
    """Seat the players the sizes above could not place, so nobody is ever left outside a table.

    A group large enough to be one player short of a draft opens its own table and shows what it needs. A
    single player instead widens the last table to the next size up, because one person waiting on five
    more is not a table, it is somebody going home."""
    if remaining <= 0:
        return tables
    if remaining >= RECRUITABLE_REMAINDER:
        return tables + [Table(seated=remaining, capacity=min(POD_SIZES))]
    if tables:
        last = tables[-1]
        wider = _next_capacity(last.capacity)
        if wider is not None:
            return tables[:-1] + [Table(seated=last.seated + remaining, capacity=wider)]
    return tables + [Table(seated=remaining, capacity=min(POD_SIZES))]


def _next_capacity(capacity: int) -> int | None:
    for size in sorted(POD_SIZES):
        if size > capacity:
            return size
    return None


def shape_phrase(plan: TablePlan) -> str:
    """The plan as the room would say it out loud: how many tables, of what size, and who is left over.

    A table of six is a 3v3 team draft, which is a different night to a table of eight, so it is named as
    one when it sits beside a bigger table. Two sixes are just two tables of six, since nothing there
    needs distinguishing."""
    groups: list[tuple[int, int]] = []
    for table in plan.tables:
        if groups and groups[-1][0] == table.capacity:
            groups[-1] = (table.capacity, groups[-1][1] + 1)
        else:
            groups.append((table.capacity, 1))
    parts = [_group_phrase(size, count, mixed=len(groups) > 1) for size, count in groups]
    return MSG_SHAPE_JOIN.join(parts)


def _group_phrase(size: int, count: int, *, mixed: bool) -> str:
    if size == min(POD_SIZES) and count == 1 and mixed:
        return MSG_SHAPE_TEAM_DRAFT
    if count == 1:
        return MSG_SHAPE_TABLE_ONE.format(size=size)
    return MSG_SHAPE_TABLE_MANY.format(count=count, size=size)


def _clean_table(remaining: int) -> int | None:
    """The size this table should take, or None when every size strands an awkward remainder. Tries 8
    first, then 6, and only reaches for 10 when it absorbs everyone left."""
    for size in POD_SIZES:
        if size > remaining:
            continue
        rest = remaining - size
        if rest == 0 or rest >= RECRUITABLE_REMAINDER:
            return size
    return None


def _largest_pod_within(remaining: int) -> int:
    """The biggest real pod these players can form when no size leaves a tidy remainder. Whoever is over
    waits for one more player rather than shrinking the table that can start now."""
    for size in (10, 8, 6):
        if size <= remaining:
            return size
    return min(POD_SIZES)
