"""The confirmation window for a busy pod: who has answered in the hour before the draft, how many
players the room should plan around, and the table shape that seats them.

Read by the T-60 roster reminder, which asks for the answers, and by the lobby, which uses them to decide
whether starting with eight leaves people out.
"""
from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from bot.commands.messages import (
    MSG_SHAPE_JOIN,
    MSG_SHAPE_TABLE_MANY,
    MSG_SHAPE_TABLE_ONE,
    MSG_SHAPE_TEAM_DRAFT,
)
from bot.database import SessionLocal
from bot.models import Player, PodDraftEvent, PodSignal, PodSignalMember
from bot.services.pod_drafts import new_drafter_column
from bot.services.pod_signals import KIND_SCHEDULED, RSVP_MAYBE, RSVP_NO, RSVP_YES


CONFIRM_TRIGGER_YES = 8
CONFIRM_WINDOW_MINUTES = 60
POD_SIZES = (8, 6, 10)
SESSION_SEATS = max(POD_SIZES)
MIN_TABLE = min(POD_SIZES)
CONFIRMED = "confirmed"


@dataclass(frozen=True)
class Attendance:
    """The answers a signup can be holding an hour out.

    A decline is kept rather than deleted, so someone who pressed Leave by mistake keeps the signup time
    that orders them into a seat when they press Sign Up again."""

    confirmed: tuple[str, ...] = ()
    yes: tuple[str, ...] = ()
    maybe: tuple[str, ...] = ()
    declined: tuple[str, ...] = ()
    new_drafters: frozenset[str] = frozenset()

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

    def as_if_all_confirmed(self) -> "Attendance":
        """The same pod with every outstanding Yes answered, which is the shape the card promises the room
        it could still have."""
        return Attendance(
            confirmed=self.confirmed + self.yes, maybe=self.maybe, declined=self.declined,
            new_drafters=self.new_drafters,
        )


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


def seating_plan(attendance: Attendance) -> TablePlan:
    """The tables this pod will open and who lands on each. The one answer to that question.

    Drawn by the card and built by the release; planned separately they disagreed silently, and a player
    read one plan while a different one opened.

    Only confirmed players count. Not being planned for is not being turned away — seat routing still
    finds a walk-in a table with room. Planning around them put thirteen people in a room that holds
    eight."""
    shape = plan_tables(len(attendance.confirmed))
    if not shape.tables:
        return TablePlan((Table(seated=0, capacity=POD_AIM),)) if attendance.expected else shape
    if len(shape.tables) == 1 and shape.tables[0].capacity < POD_AIM:
        return TablePlan((Table(seated=shape.tables[0].seated, capacity=POD_AIM),))
    return shape


def table_capacity_for(seatable: int) -> int:
    """The seat cap one table opens at to hold this many players, never under the eight the room aims for.

    The single answer to how wide a table is, read by the board that draws it, the seat routing that fills
    it and the Draftmancer room it opens. Computed three separate ways it disagreed with itself: a table of
    eight confirmed carrying three unconfirmed drew as a table of ten and opened a room for eight, so the
    riders raced the roster for the same eight seats."""
    plan = plan_tables(seatable)
    return max(plan.tables[0].capacity if plan.tables else MIN_TABLE, POD_AIM)


def attendance_of(
    rosters: dict[str, list[str]], new_drafters: frozenset[str] = frozenset(),
) -> Attendance:
    """A rendered roster read as the four answers the confirmation window cares about."""
    return Attendance(
        confirmed=tuple(rosters.get(CONFIRMED) or ()),
        yes=tuple(rosters.get(RSVP_YES) or ()),
        maybe=tuple(rosters.get(RSVP_MAYBE) or ()),
        declined=tuple(rosters.get(RSVP_NO) or ()),
        new_drafters=new_drafters,
    )


def attendance_for_event_sync(event_id: str) -> Attendance:
    """The answers currently held by the pod behind this event.

    A decline outranks any confirmation the row still carries, since it is the later statement and the
    only one that says the player is not coming.

    Empty for a pod with no signup roster, which is what a queue or poll pod is, and is why those never
    hold a lobby up: there is nobody the bot could say it is waiting for."""
    return roster_attendance_for_event_sync(event_id) or Attendance()


def roster_attendance_for_event_sync(event_id: str) -> Attendance | None:
    """None for a pod carrying no signup roster, not an empty Attendance"""
    with SessionLocal() as session:
        signal = session.execute(
            select(PodSignal).where(PodSignal.event_id == event_id)
        ).scalar_one_or_none()
        if signal is None:
            return Attendance()
        rows = session.execute(
            select(
                PodSignalMember.rsvp, PodSignalMember.display_name, PodSignalMember.confirmed_at,
                new_drafter_column(),
            )
            .outerjoin(Player, Player.discord_id == PodSignalMember.discord_user_id)
            .where(PodSignalMember.signal_id == signal.id)
            .order_by(PodSignalMember.created_at)
        ).all()
    buckets: dict[str, list[str]] = {CONFIRMED: [], RSVP_YES: [], RSVP_MAYBE: [], RSVP_NO: []}
    new_drafters: set[str] = set()
    for state, name, confirmed_at, new_drafter in rows:
        if state == RSVP_NO:
            bucket = RSVP_NO
        elif confirmed_at is not None:
            bucket = CONFIRMED
        else:
            bucket = state
        if bucket in buckets:
            buckets[bucket].append(name)
        if new_drafter:
            new_drafters.add(name)
    return Attendance(
        confirmed=tuple(buckets[CONFIRMED]), yes=tuple(buckets[RSVP_YES]),
        maybe=tuple(buckets[RSVP_MAYBE]), declined=tuple(buckets[RSVP_NO]),
        new_drafters=frozenset(new_drafters),
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


def set_confirmations_sync(
    event_id: str, confirmed_ids: Iterable[str], asked_about: Iterable[str] | None = None,
) -> tuple[int, int]:
    """Make the pod's confirmations exactly this set of players, and say how many are confirmed and how
    many are still pending afterwards.

    The organizer's answer replaces the roster's, both ways: someone they tick is confirmed even if they
    never pressed anything, and someone they untick goes back to pending even if they did. A person in
    the room knows things the buttons cannot, which is the whole reason the control exists. Unticking
    never records a No, since not being counted and saying you are not coming are different answers and
    only the player can give the second.

    `asked_about` is who the organizer was actually shown, and nobody outside it is touched. A Discord
    select holds twenty-five options, so a bigger pod is presented a slice of itself, and reading that
    slice as the whole answer would unconfirm every player past the twenty-fifth for never appearing in
    a list they were never in. The counts come back for the whole pod either way."""
    wanted = set(confirmed_ids)
    scope = set(asked_about) if asked_about is not None else None
    now = datetime.now(timezone.utc)
    with SessionLocal() as session:
        signal = session.execute(
            select(PodSignal).where(PodSignal.event_id == event_id)
        ).scalar_one_or_none()
        if signal is None:
            return 0, 0
        members = session.execute(
            select(PodSignalMember).where(
                PodSignalMember.signal_id == signal.id, PodSignalMember.rsvp == RSVP_YES,
            )
        ).scalars().all()
        for member in members:
            if scope is not None and member.discord_user_id not in scope:
                continue
            if member.discord_user_id in wanted:
                member.confirmed_at = member.confirmed_at or now
            else:
                member.confirmed_at = None
        session.commit()
        confirmed = sum(1 for member in members if member.confirmed_at is not None)
        return confirmed, len(members) - confirmed


def fits_one_table(attendance: Attendance) -> bool:
    """Whether a single table seats everybody who could still turn up, pending answers included.

    The line between a pod that only has to start and a pod that has to be split. Below it a confirmation
    changes nothing about who plays, so no surface has a reason to tell a confirmed player apart from a
    pending one."""
    whole = seating_plan(attendance.as_if_all_confirmed())
    return len(whole.tables) <= 1 and not whole.waiting


def card_tables(attendance: Attendance) -> tuple[TablePlan, bool]:
    """The tables the card draws, and whether players still pending are drawn sitting at them.

    One table seats everybody: there is nowhere else to put them, so a signup in a seat is a fact. Two
    tables seat only the confirmed, since placing somebody says which room to walk into and the pod
    cannot say that about a player it has not heard from.

    One table that cannot hold them all seats only the confirmed as well: the overflow column is a
    waitlist, and somebody who has not answered is Pending rather than waiting for a seat."""
    if fits_one_table(attendance):
        return seating_plan(attendance.as_if_all_confirmed()), True
    return seating_plan(attendance), False


def decline_players_sync(event_id: str, discord_ids: Iterable[str]) -> int:
    """Record these players as not coming, and say how many moved.

    The organizer's hand on the answer only a player can normally give. Somebody who says in chat that
    they cannot make it and never presses Leave otherwise stays on the roster holding a seat nobody can
    take, and the tables are built one player wrong. The row is kept rather than deleted, exactly as a
    Leave keeps it, so signing back up returns them to the place their original signup earned."""
    wanted = set(discord_ids)
    if not wanted:
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
                PodSignalMember.discord_user_id.in_(wanted),
            )
        ).scalars().all()
        for member in members:
            member.rsvp = RSVP_NO
            member.confirmed_at = None
        session.commit()
        return len(members)


CLASH_WINDOW_MINUTES = 120


@dataclass(frozen=True)
class ClashingSignup:
    """A pod still counting on a player who has just confirmed somewhere else at the same hour."""

    event_id: str
    name: str
    card_message_id: str


def clashing_signups_sync(event_id: str, discord_user_id: str) -> list[ClashingSignup]:
    """The other pods this player holds a Yes on close enough in time to the one they just confirmed that
    they cannot play both.

    Confirming names the pod a player is playing, and every pod it clashes with is building a table around
    a Yes that is no longer true. Two hours either side is the span of a draft, so the weekly slots sit far
    enough apart that answering Wednesday never touches Thursday, and what is left is the real clash: two
    pods at one slot time.

    Only pods with a scheduled card are found, so an extra table is never read as a rival to the pod it
    split off: a table carries no card of its own.
    """
    with SessionLocal() as session:
        confirmed_start = session.execute(
            select(PodDraftEvent.event_time).where(PodDraftEvent.id == event_id)
        ).scalar_one_or_none()
        if confirmed_start is None:
            return []
        window = timedelta(minutes=CLASH_WINDOW_MINUTES)
        rows = session.execute(
            select(PodDraftEvent.id, PodDraftEvent.name, PodSignal.message_id)
            .join(PodSignal, PodSignal.event_id == PodDraftEvent.id)
            .join(PodSignalMember, PodSignalMember.signal_id == PodSignal.id)
            .where(
                PodSignalMember.discord_user_id == discord_user_id,
                PodSignalMember.rsvp == RSVP_YES,
                PodSignal.kind == KIND_SCHEDULED,
                PodDraftEvent.id != event_id,
                PodDraftEvent.finalized_at.is_(None),
                PodDraftEvent.event_time >= confirmed_start - window,
                PodDraftEvent.event_time <= confirmed_start + window,
            )
            .order_by(PodDraftEvent.event_time)
        ).all()
    return [ClashingSignup(clashing_id, name, card_message_id) for clashing_id, name, card_message_id in rows]


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


