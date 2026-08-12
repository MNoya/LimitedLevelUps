"""Turning a table plan into real pods: a sibling event sharing the start time, its own roster in
confirmation order, its own thread and its own lobby.

Nothing here decides *when* to split. The attendance hold does, at the scheduled time or when an organizer
locks the count early, because a pod opened before the room is counted locks the shape while nobody knows
it. This is the machinery it calls. Design in `spec/pod-confirm-signup.md`.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from bot.database import SessionLocal
from bot.models import PodDraftEvent, PodSignal, PodSignalMember
from bot.services.pod_confirm import (
    POD_SIZES,
    SESSION_SEATS,
    Attendance,
    TablePlan,
    attendance_for_event_sync,
    plan_tables,
)
from bot.services.pod_signals import RSVP_MAYBE, RSVP_YES


log = logging.getLogger(__name__)

MIN_POD_SIZE = min(POD_SIZES)
POD_INDEX_RE = re.compile(r"\s(\d+)$")


@dataclass(frozen=True)
class Signup:
    """One person on a pod's roster, with whether they have confirmed."""

    discord_id: str
    display_name: str
    confirmed: bool


def deal_into_plan(roster: list[Signup], plan: TablePlan) -> list[list[Signup]]:
    """Hand the roster out across the plan's tables, in the order the plan seats them.

    The plan already says how many players each table holds, and it was built from this same roster, so
    the slices land exactly. The seats the plan left waiting stay waiting: eleven players draw a table of
    ten and one player over, and seating that eleventh anyway would put them in a room that cannot hold
    them and contradict the card they just read. Anything beyond even that goes on the last table rather
    than off the end, since a player the card drew and the release dropped is the worst outcome here."""
    groups: list[list[Signup]] = []
    cursor = 0
    for table in plan.tables:
        groups.append(roster[cursor:cursor + table.seated])
        cursor += table.seated
    excess = roster[cursor + plan.waiting:]
    if excess and groups:
        groups[-1].extend(excess)
    return groups


@dataclass(frozen=True)
class FamilyState:
    """Every pod this signup split into beside every answer across them, read in one pass.

    The two are one question. Asked apart, the pods came from a read filtered on the start time and the
    count from a read that was not, so they could answer differently about the same set of pods."""

    pods: list[FamilyPod]
    attendance: Attendance

    @property
    def staged(self) -> int:
        """The highest number a pod of this family carries, which is how many tables exist. Taken off the
        numbers rather than the count, so a cancelled middle pod never hands its number out twice."""
        return max((pod.index for pod in self.pods), default=1)


def family_state_sync(event_id: str) -> FamilyState:
    """The pods this signup has split into and the room they hold between them.

    Read the source pod alone and the count goes wrong the moment a table is handed its players: the pod
    that gave six away reads as a pod of six, and the family looks smaller than it is."""
    pods = pod_family_sync(event_id)
    confirmed: list[str] = []
    yes: list[str] = []
    maybe: list[str] = []
    for pod in pods:
        attendance = attendance_for_event_sync(pod.event_id)
        confirmed += list(attendance.confirmed)
        yes += list(attendance.yes)
        maybe += list(attendance.maybe)
    return FamilyState(
        pods, Attendance(confirmed=tuple(confirmed), yes=tuple(yes), maybe=tuple(maybe)),
    )


def pod_base_name(name: str) -> str:
    """The pod's name without its number. `Early Pod 2` is `Early Pod`, and a pod that never split keeps
    the name it already has."""
    return POD_INDEX_RE.sub("", name).strip()


def numbered_pod_name(base_name: str, index: int) -> str:
    return f"{base_name} {index}"


NUMERAL_EMOJI = ("0\ufe0f\u20e3", "1\ufe0f\u20e3", "2\ufe0f\u20e3", "3\ufe0f\u20e3", "4\ufe0f\u20e3",
                 "5\ufe0f\u20e3", "6\ufe0f\u20e3", "7\ufe0f\u20e3", "8\ufe0f\u20e3", "9\ufe0f\u20e3")


def pod_numeral(index: int) -> str:
    """A pod's number as the numeral emoji cards and threads wear."""
    return "".join(NUMERAL_EMOJI[int(digit)] for digit in str(index))


def pod_index(name: str) -> int:
    """The pod's number off its name. A pod that was never numbered is the first one."""
    match = POD_INDEX_RE.search(name or "")
    return int(match.group(1)) if match else 1


def pod_is_numbered(name: str) -> bool:
    """Whether this pod belongs to a signup that split.

    A pod is born without a number and gains one the moment a second opens, which renumbers the first at
    the same time. So an unnumbered name is a signup running one table, and answering that from the name
    costs nothing where counting the family costs a query per pod."""
    return POD_INDEX_RE.search(name or "") is not None


def confirmed_first_roster_sync(event_id: str) -> list[Signup]:
    """The pod's signups in the order the plan seats them: everyone who confirmed, then everyone who said
    Yes and has not. Maybes are left out, since the plan never seats them."""
    with SessionLocal() as session:
        signal = session.execute(
            select(PodSignal).where(PodSignal.event_id == event_id)
        ).scalar_one_or_none()
        if signal is None:
            return []
        rows = session.execute(
            select(
                PodSignalMember.discord_user_id, PodSignalMember.display_name,
                PodSignalMember.rsvp, PodSignalMember.confirmed_at,
            )
            .where(PodSignalMember.signal_id == signal.id, PodSignalMember.rsvp == RSVP_YES)
            .order_by(PodSignalMember.created_at)
        ).all()
    confirmed = [Signup(row[0], row[1], True) for row in rows if row[3] is not None]
    unconfirmed = [Signup(row[0], row[1], False) for row in rows if row[3] is None]
    return confirmed + unconfirmed


@dataclass(frozen=True)
class FamilyPod:
    """One pod of a family: the pods a single signup split into, sharing a name and a start time.

    `seated` is the Yes roster, which is who the pod pings and plans around, and `capacity` is the table
    that roster currently asks for."""

    event_id: str
    name: str
    index: int
    thread_id: str | None
    session_id: str
    seated: int
    capacity: int
    member_ids: frozenset[str]
    member_names: tuple[str, ...] = ()
    maybe_names: tuple[str, ...] = ()


def pod_family_sync(event_id: str) -> list[FamilyPod]:
    """Every pod sharing this one's name and start time, in pod order.

    A signup that never split is a family of one, so a caller reads the same shape either way and decides
    for itself whether one pod is worth saying anything about."""
    with SessionLocal() as session:
        event = session.get(PodDraftEvent, event_id)
        if event is None:
            return []
        base = pod_base_name(event.name)
        events = [
            sibling for sibling in session.execute(
                select(PodDraftEvent).where(
                    PodDraftEvent.event_time == event.event_time,
                    or_(PodDraftEvent.name == base, PodDraftEvent.name.ilike(f"{base} %")),
                )
            ).scalars().all()
            if pod_base_name(sibling.name) == base
        ]
        rosters = _family_rosters(session, [sibling.id for sibling in events])
        family = [_family_pod(sibling, rosters.get(sibling.id, [])) for sibling in events]
    family.sort(key=lambda pod: pod.index)
    return family


@dataclass(frozen=True)
class SeatOffer:
    """Where a Join Draft press is sent. `switched` is the press landing on a table other than the one it
    was made in, which is the only case the answer has to explain itself."""

    pod: FamilyPod
    switched: bool


def take_seat_sync(session_id: str, discord_id: str, display_name: str) -> SeatOffer | None:
    """Seat whoever pressed Join Draft, and count the press as a confirmation.

    Pressing is the strongest answer there is: at ten to nine nobody asks for a link to a draft they are
    not about to play. So a press confirms a signup that never did, and seats a walk-in who never signed
    up at all, which is what makes the seat counts the room reads actually true.

    The table is the one already holding them, else the first one with a seat left. Filling in press order
    is what rewards confirming early: the people who answered first are on the table that starts soonest,
    and nobody is ever handed a link to a room that is full. None when no pod owns this session, where the
    button answers with the link it already carries."""
    with SessionLocal() as session:
        event = session.execute(
            select(PodDraftEvent).where(PodDraftEvent.draftmancer_session == session_id)
        ).scalars().first()
        if event is None:
            return None
        clicked_event_id = event.id
    family = pod_family_sync(clicked_event_id)
    if not family:
        return None
    pod = _first_seat_for(family, discord_id)
    confirm_seat_sync(pod.event_id, discord_id, display_name)
    return SeatOffer(pod, switched=pod.event_id != clicked_event_id)


def _first_seat_for(family: list[FamilyPod], discord_id: str) -> FamilyPod:
    """The table holding this player, else the first with room once the plan is asked to seat one
    more. Planning for the extra body is what keeps a table of six from turning anyone away while the plan
    it belongs to would have made it a table of eight.

    Every seat handed out is checked against the session as well as the plan. A plan wanting more tables
    than the family has runs out of sizes to read, and the walk-ins after that all piled onto the last
    table with nothing counting them: a release at sixteen finished 9 + 11, and eleven cannot draft in a
    room that holds ten. Once every table is at the size the plan gives it, the seat goes to the first
    table with a room seat left.

    A family already full at ten on every table has nowhere to put anybody, and there is no answer that
    seats them. The emptiest table is the least wrong one, and it is said out loud, because what the room
    actually needs then is another table."""
    for pod in family:
        if discord_id in pod.member_ids:
            return pod
    plan = plan_tables(sum(pod.seated for pod in family) + 1)
    for index, pod in enumerate(family):
        planned = plan.tables[index].capacity if index < len(plan.tables) else pod.capacity
        if pod.seated < min(planned, SESSION_SEATS):
            return pod
    for pod in family:
        if pod.seated < SESSION_SEATS:
            return pod
    emptiest = family[0]
    for pod in family[1:]:
        if pod.seated < emptiest.seated:
            emptiest = pod
    log.warning(
        f"pod-staging: every table of {emptiest.name} is full at {SESSION_SEATS}; "
        f"seating {discord_id} on table {emptiest.index} anyway"
    )
    return emptiest


def confirm_seat_sync(event_id: str, discord_id: str, display_name: str) -> None:
    """Record the press on this table's roster: a confirmation for a signup, a confirmed signup for a
    walk-in. Someone who turns up at the last minute means to play, so nothing asks them to confirm."""
    with SessionLocal() as session:
        signal = session.execute(
            select(PodSignal).where(PodSignal.event_id == event_id)
        ).scalar_one_or_none()
        if signal is None:
            return
        member = session.execute(
            select(PodSignalMember).where(
                PodSignalMember.signal_id == signal.id,
                PodSignalMember.discord_user_id == discord_id,
            )
        ).scalar_one_or_none()
        if member is None:
            session.add(PodSignalMember(
                signal_id=signal.id, discord_user_id=discord_id, display_name=display_name,
                rsvp=RSVP_YES, confirmed_at=datetime.now(timezone.utc),
            ))
        else:
            member.rsvp = RSVP_YES
            if member.confirmed_at is None:
                member.confirmed_at = datetime.now(timezone.utc)
        session.commit()


def _family_rosters(session: Session, event_ids: list[str]) -> dict[str, list[tuple[str, str, str]]]:
    """Every pod's roster in one query, as (rsvp, discord_id, display_name) in signup order. A read per
    sibling turned the family into as many round trips as the family has tables, on a path several things
    run for every press."""
    rows = session.execute(
        select(
            PodSignal.event_id, PodSignalMember.rsvp,
            PodSignalMember.discord_user_id, PodSignalMember.display_name,
        )
        .join(PodSignalMember, PodSignalMember.signal_id == PodSignal.id)
        .where(PodSignal.event_id.in_(event_ids))
        .order_by(PodSignalMember.created_at)
    ).all()
    rosters: dict[str, list[tuple[str, str, str]]] = {}
    for event_id, rsvp, discord_id, display_name in rows:
        rosters.setdefault(event_id, []).append((rsvp, discord_id, display_name))
    return rosters


def _family_pod(event: PodDraftEvent, roster: list[tuple[str, str, str]]) -> FamilyPod:
    playing = [(discord_id, name) for rsvp, discord_id, name in roster if rsvp == RSVP_YES]
    maybes = [name for rsvp, _, name in roster if rsvp == RSVP_MAYBE]
    plan = plan_tables(len(playing))
    return FamilyPod(
        event_id=event.id,
        name=event.name,
        index=pod_index(event.name),
        thread_id=event.discord_thread_id,
        session_id=event.draftmancer_session,
        seated=len(playing),
        capacity=plan.tables[0].capacity if plan.tables else MIN_POD_SIZE,
        member_ids=frozenset(discord_id for discord_id, _ in playing),
        member_names=tuple(name for _, name in playing),
        maybe_names=tuple(maybes),
    )


def move_players_sync(family_event_ids: list[str], target_event_id: str, discord_ids: list[str]) -> int:
    """Put these players on one table of a family and take them off every other, and say how many moved.

    The organizer's answer, not a player's, so it lands as confirmed: they are being placed on a table
    because somebody in the room knows they are coming to it. Display names are carried across from the
    row being taken away, so a move never invents a name the pod has not seen."""
    wanted = set(discord_ids)
    if not wanted:
        return 0
    now = datetime.now(timezone.utc)
    with SessionLocal() as session:
        signals = session.execute(
            select(PodSignal).where(PodSignal.event_id.in_(family_event_ids))
        ).scalars().all()
        target = next((signal for signal in signals if signal.event_id == target_event_id), None)
        if target is None:
            return 0
        moved = 0
        names: dict[str, str] = {}
        for signal in signals:
            members = session.execute(
                select(PodSignalMember).where(
                    PodSignalMember.signal_id == signal.id,
                    PodSignalMember.discord_user_id.in_(wanted),
                )
            ).scalars().all()
            for member in members:
                names[member.discord_user_id] = member.display_name
                if signal.id == target.id:
                    member.rsvp = RSVP_YES
                    member.confirmed_at = member.confirmed_at or now
                else:
                    session.delete(member)
                    moved += 1
        session.flush()
        seated = {
            row[0] for row in session.execute(
                select(PodSignalMember.discord_user_id)
                .where(PodSignalMember.signal_id == target.id)
            ).all()
        }
        for discord_id in wanted - seated:
            session.add(PodSignalMember(
                signal_id=target.id, discord_user_id=discord_id,
                display_name=names.get(discord_id, discord_id), rsvp=RSVP_YES, confirmed_at=now,
            ))
        session.commit()
        return moved


def hand_over_members_sync(source_event_id: str, moved: list[Signup]) -> int:
    """Take the players now belonging to another pod off this one's roster.

    Only the signal roster moves. Thread membership is left alone on purpose: nobody is removed from a
    conversation they were already part of, so a player sits in both threads and picks. Returns how many
    rows actually moved. Maybe rows are left alone whatever the deal says, since the plan seats nobody who
    has not committed."""
    return _take_off_roster(source_event_id, moved, only_maybes=False)


def hand_over_maybes_sync(source_event_id: str, maybes: list[Signup]) -> int:
    """Take the signup's maybes off it, for the table they are being handed to. They belong to one table at
    a time, else they read as spare capacity on two."""
    return _take_off_roster(source_event_id, maybes, only_maybes=True)


def _take_off_roster(source_event_id: str, signups: list[Signup], *, only_maybes: bool) -> int:
    if not signups:
        return 0
    ids = {signup.discord_id for signup in signups}
    answer = PodSignalMember.rsvp == RSVP_MAYBE if only_maybes else PodSignalMember.rsvp != RSVP_MAYBE
    with SessionLocal() as session:
        signal = session.execute(
            select(PodSignal).where(PodSignal.event_id == source_event_id)
        ).scalar_one_or_none()
        if signal is None:
            return 0
        members = session.execute(
            select(PodSignalMember).where(
                PodSignalMember.signal_id == signal.id,
                PodSignalMember.discord_user_id.in_(ids),
                answer,
            )
        ).scalars().all()
        for member in members:
            session.delete(member)
        session.commit()
        return len(members)
