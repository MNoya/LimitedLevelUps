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
    """The tables n players make, in the order they can start. `waiting` is the player no table can hold,
    which happens only at eleven, where a Draftmancer session's ten seats are the whole ceiling."""

    tables: tuple[Table, ...]
    waiting: int = 0

    @property
    def splits(self) -> bool:
        return len(self.tables) > 1

    @property
    def seated(self) -> int:
        return sum(table.seated for table in self.tables)


def plan_tables(n: int) -> TablePlan:
    """Seat n players in tables of 8, 6, or 10.

    Set the odd player aside, then take the combination of sizes holding the rest that has the **most
    tables of eight**, breaking ties on the **fewest tables**. Eight is the seat the room wants, so one
    eight beside a ten beats three sixes at eighteen, and thirty is 8 + 8 + 8 + 6 rather than three tens.

    The odd player joins the last table that is not already a ten, which shows on the card as a table of
    seven or nine with one seat still open: that table either finds one more or drops one. At eleven every
    table is a ten and there is nobody to join, so the eleventh waits.

    Tables come back in the order they can start, so the players dealt in first land on a table that is
    already whole and the odd table falls to whoever answered last.
    """
    if n < min(POD_SIZES):
        return TablePlan((Table(seated=n, capacity=min(POD_SIZES)),) if n else ())
    sizes = _even_sizes(n - n % 2)
    if n % 2 == 0:
        return TablePlan(tuple(Table(seated=size, capacity=size) for size in sizes))
    return _seat_odd_player(sizes)


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


def _even_sizes(total: int) -> list[int]:
    """Table sizes holding an even `total`, eights first, then sixes, then tens.

    Eights are taken as far as they go before anything else is tried, so the answer is the one with the
    most of them. What is left over is closed with the fewest tables it can be closed with, which is why
    sixteen is 8 + 8 and not 10 + 6."""
    for eights in range(total // 8, -1, -1):
        rest = _sixes_and_tens(total - 8 * eights)
        if rest is not None:
            return [8] * eights + rest
    return [min(POD_SIZES)]


def _sixes_and_tens(total: int) -> list[int] | None:
    """Sixes and tens summing to `total` in as few tables as possible, or None when no combination does.

    Tens are tried first because a ten is one table where the same players are two sixes, and this only
    ever runs on what the eights left behind."""
    for tens in range(total // 10, -1, -1):
        rest = total - 10 * tens
        if rest % 6 == 0:
            return [6] * (rest // 6) + [10] * tens
    return None


def _seat_odd_player(sizes: list[int]) -> TablePlan:
    """Add the odd player to the last table that can hold one more, and move that table to the end.

    The table gaining them is a seat short of a draft, so it carries an open seat and goes last: it is the
    one that has to find somebody or drop somebody, and the players dealt in first should not be on it."""
    for index in range(len(sizes) - 1, -1, -1):
        if sizes[index] < max(POD_SIZES):
            odd = sizes.pop(index)
            whole = [Table(seated=size, capacity=size) for size in sizes]
            return TablePlan(tuple(whole + [Table(seated=odd + 1, capacity=odd + 2)]))
    return TablePlan(tuple(Table(seated=size, capacity=size) for size in sizes), waiting=1)


def shape_phrase(plan: TablePlan) -> str:
    """The plan as the room would say it out loud: how many tables, of what size, and who is left over.

    A table of six is a 3v3 team draft, which plays differently to a table of eight, so it is named as
    one when it sits beside a bigger table. Two sixes are just two tables of six, since nothing there
    needs distinguishing."""
    groups: list[tuple[int, int]] = []
    for table in plan.tables:
        if groups and groups[-1][0] == table.seated:
            groups[-1] = (table.seated, groups[-1][1] + 1)
        else:
            groups.append((table.seated, 1))
    parts = [_group_phrase(size, count, mixed=len(groups) > 1) for size, count in groups]
    return MSG_SHAPE_JOIN.join(parts)


def _group_phrase(size: int, count: int, *, mixed: bool) -> str:
    if size == min(POD_SIZES) and count == 1 and mixed:
        return MSG_SHAPE_TEAM_DRAFT
    if count == 1:
        return MSG_SHAPE_TABLE_ONE.format(size=size)
    return MSG_SHAPE_TABLE_MANY.format(count=count, size=size)


