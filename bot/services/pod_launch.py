"""Bot-native on-demand pod creation, shared by the daily poll and /pod-queue.

Two layers:
  - sync SQLAlchemy CRUD over pod_signals / pod_signal_members (run via asyncio.to_thread)
  - async Discord orchestration: create the thread + PodDraftEvent and open the Draftmancer lobby
    (now, or armed for a slot time) without any sesh coupling.

open_ondemand_lobby posts the lobby, reading the roster off the signal. Fire is claimed atomically
(UPDATE … WHERE status='open') so concurrent clicks or a restart mid-fire can't create two pods for
one slot.

Signals never close to signups while a pod can still happen: a fired signal keeps accepting joins
(over-signups cover unexpected drops), and only an expired one — its slot time passed unfired —
refuses, enforced here in the DB so a persistent button that outlives it is inert on click.
"""
from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import Awaitable, Callable, Iterable
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

import discord
from discord.ext import commands
from sqlalchemy import delete, func, or_, select, update
from sqlalchemy.orm import Session

from bot.config import PRODUCTION_GUILD_ID, settings
from bot.discord_helpers import snowflake_or_none
from bot.database import SessionLocal
from bot.models import Player, PodDraftEvent, PodDraftMatch, PodDraftParticipant, PodSignal, PodSignalMember
from bot.services import pod_event_settings
from bot.services import pod_format_interest as fi
from bot.services import pod_signals
from bot.services import pod_team
from bot.services.pod_confirm import CONFIRM_WINDOW_MINUTES, SESSION_SEATS, attendance_for_event_sync
from bot.services.pod_staging import (
    confirmed_first_roster_sync,
    pod_base_name,
    pod_index,
    pod_is_numbered,
    signup_thread_once_family_drafted_sync,
)
from bot.services.pod_draft_manager import (
    PodDraftManager,
    set_card_close_hook,
    set_pod_cancel_hook,
    start_manager,
)
from bot.services.pod_drafts import (
    build_ondemand_session,
    draftmancer_url_for,
    get_cube_choices,
    get_flashback_ranking,
    get_format_interests,
    is_championship,
    new_drafter_column,
    normalize_player_name,
    record_ondemand_event,
    set_cube_choices,
    set_flashback_ranking,
    set_format_interests,
    strip_arena_suffix,
    table_base_name,
)
from bot.services.pod_join_button import build_join_view
from bot.services.pod_registration_embed import closed_registered_embed
from bot.services.pod_link_dm import send_lobby_link_dms
from bot.services import championship as championship_seeds
from bot.services import championship_copy
from bot.services.championship import frozen_seeds_by_player
from bot.services.player_stats import rank_ordered_names
from bot.services import pod_active
from bot.services.pod_active import ACTIVE_POD_MANAGERS
from bot.services.pod_signals import SCHEDULE_TZ, slot_event_time
from bot.services.pod_format_schedule import formats_on, latest_on
from bot.services.pod_slot import COLLISION_INDEX_RE, next_collision_index, pod_display_name, pod_event_date
from bot.sets import active_set_code
from bot.tasks.pod_draft_reminder import (
    build_attendance_hold_body,
    build_lobby_open_body,
    build_lobby_open_split_body,
    refresh_roster_reminder_for_event,
    repost_roster_reminder,
    schedule_roster_reminder,
    signal_rsvps_sync,
)
from bot.tasks.pod_underfill import (
    clear_slot_nudge,
    clear_underfill_nudge,
    schedule_slot_underfill_checks,
    schedule_underfill_checks,
)


log = logging.getLogger(__name__)

StagePodsHook = Callable[[commands.Bot, str], Awaitable[None]]
_stage_pods_hook: StagePodsHook | None = None

_holding: dict[str, bool] = {}
"""Pods that have held, against whether they are still waiting. Kept in memory rather than on the row.

The hold lasts ten minutes and nothing outside this process asks about it, so a column would be written
and read by one module inside one window. A restart inside those ten minutes forgets, which costs the
pod one repeated ping when the re-armed T-10 job lands.

A released pod stays in here as False, which is what lets its card show the organizer controls greyed out
instead of dropping them: a control that vanishes reads as one that was never there.
"""

REMINDER_LEAD_MIN = 10
CARD_CLOSE_WINDOW_H = 48
LANE_LOOKAHEAD_DAYS = 1
"""How far past its own day a launcher column looks for a pod already committed at its slot. One day, so the
board points at tomorrow's Set Championship the evening before without carrying it all five days it exists."""


@dataclass(frozen=True)
class SignalState:
    signal_id: str
    kind: str
    bucket: str
    status: str
    count: int
    slot_time: datetime | None
    event_id: str | None
    set_code: str | None
    created_at: datetime | None = None
    opened_by: str | None = None
    notify_role: str | None = None
    description: str | None = None
    format_locked: bool = False


@dataclass(frozen=True)
class ToggleResult:
    state: SignalState
    names: list[str]
    joined: bool
    changed: bool
    closed: bool


@dataclass(frozen=True)
class LeftSlot:
    """One gathering pod a player was just dropped from, named so the answer can list what it undid."""
    signal_id: str
    bucket_key: str
    slot_time: datetime | None


@dataclass(frozen=True)
class LeaveResolution:
    """Outcome of the last-player Leave confirmation. `cancelled` when the confirmer was still the only
    member and the queue was closed; `left` when others joined during the prompt so the confirmer was
    just removed and the queue stays open; `gone` when the signal had already closed. `names`, `set_code`,
    `created_at`, `opened_by`, `notify_role`, and `description` re-render the still-open card on the
    `left` path."""
    outcome: str
    names: list[str]
    set_code: str | None
    created_at: datetime | None
    opened_by: str | None
    notify_role: str | None = None
    description: str | None = None


LEAVE_CANCELLED = "cancelled"
LEAVE_LEFT = "left"
LEAVE_GONE = "gone"


@dataclass(frozen=True)
class RsvpResult:
    """`event_name` and `event_time` are the pod's identity, read on the write's own session. The presser's
    acknowledgement names the pod it landed on, and querying that separately put a whole round trip between
    the click and its answer.

    `confirmed` is whether the write stamped a confirmation, which the caller cannot work out for itself: a
    Yes inside the last hour confirms without anybody asking it to.

    `started` is a confirmation the pod is past taking, which wrote nothing."""
    state: SignalState
    rosters: dict[str, list[str]]
    rsvp: str | None
    joined: bool
    closed: bool
    yes_changed: bool = False
    roster_interests: dict[str, list[tuple[str, tuple[str, ...]]]] | None = None
    event_name: str | None = None
    event_time: datetime | None = None
    confirmed: bool = False
    started: bool = False
    new_drafters: frozenset[str] = frozenset()


@dataclass(frozen=True)
class LauncherSlot:
    """One pod the launcher offers: a time slot plus the one format it opens on, carried in `bucket_key` and
    spelled out in `set_code`. A slot time offering two formats is two of these, each with its own signal,
    roster, quorum and lifecycle.

    `committed` is a pod that exists: `count`/`thread_id`/`slot_time` are read off the event, `names`
    projects the card's Yes roster, and `card_message_id` is the scheduled card its button writes to. A
    gathering pod carries its own poll `signal_id`, roster `names`, and `status`.

    `finished` is the played pod, so the render marks it with a trophy rather than the playing mark even
    when it has no single winner. `winner_slug` is the winner's seat on the website pod page, absent for a
    team draft (which credits its winning side) and for an unlinked player."""
    bucket_key: str
    committed: bool
    status: str
    count: int
    slot_time: datetime | None
    names: list[str]
    thread_id: str | None
    signal_id: str | None
    thread_message_id: str | None = None
    card_message_id: str | None = None
    card_channel_id: str | None = None
    thread_name: str | None = None
    set_code: str | None = None
    championship: bool = False
    finished: bool = False
    winner: str | None = None
    winner_slug: str | None = None
    locked: bool = False
    """Whether the draft itself started, the one state that collapses a pod to a single line. Reaching the
    threshold does not lock it and neither does the lobby opening: a pod takes signups until the first pack
    is passed, so it keeps a full joinable block until then."""
    created_at: datetime | None = None
    """When the pod's row was written, which orders an extra table after the pod it spun off."""


def create_poll_signals(
    session: Session, *, guild_id: str, channel_id: str, message_id: str, signal_date: date,
) -> list[tuple[str, datetime]]:
    """Bind a lazy poll row to this launcher message per (slot, format) the day offers; return (signal_id,
    slot_time) per row so the caller arms expiry and underfill beats for each. This is the only place the
    format schedule is read: from here on the signals are the truth for what a slot offers, so a moderator
    who retargets one is not overwritten by the table on the next render.

    A row a rolled column already opened for this day is adopted, not duplicated: it keeps the signups it
    gathered overnight and moves to the fresh message. A format whose pod already exists at that slot time
    gets no signal — the launcher reflects that pod's card instead of doubling it — while the other formats
    there still open. A slot that already closed unfired gets none either: its window is over, so a second
    row records nothing the closed one does not and only collides once a repost sweeps the earlier board's
    rows onto this message."""
    bound: list[tuple[str, datetime]] = []
    for bucket in pod_signals.poll_buckets_for(signal_date):
        slot_time = slot_event_time(signal_date, bucket.key)
        covered = _event_formats_for_slot(session, slot_time)
        for set_code in formats_on(signal_date, bucket.lane):
            if set_code in covered:
                continue
            signal = _open_poll_signal_for_slot(session, bucket.key, set_code, signal_date)
            if signal is None:
                if _expired_poll_signal_exists(session, bucket.key, set_code, signal_date):
                    continue
                signal = PodSignal(
                    kind=pod_signals.KIND_POLL,
                    bucket=pod_signals.named_bucket_key(bucket.key, set_code),
                    guild_id=guild_id,
                    channel_id=channel_id,
                    message_id=message_id,
                    signal_date=signal_date,
                    slot_time=slot_time,
                    set_code=set_code,
                )
                session.add(signal)
            else:
                signal.channel_id = channel_id
                signal.message_id = message_id
            session.flush()
            bound.append((signal.id, slot_time))
    return bound


def create_poll_signals_sync(
    *, guild_id: str, channel_id: str, message_id: str, signal_date: date,
) -> list[tuple[str, datetime]]:
    with SessionLocal() as session:
        created = create_poll_signals(
            session, guild_id=guild_id, channel_id=channel_id, message_id=message_id, signal_date=signal_date,
        )
        session.commit()
        return created


def rebind_launcher_rows_sync(old_message_id: str, new_message_id: str) -> int:
    """Move every poll row hanging on one launcher message onto another, and return how many moved.

    `create_poll_signals` adopts by day, which covers the board's own slots and misses a column already
    gathering for tomorrow: a lane rolls forward the moment its pod finishes, and the row it opens is bound
    to the message that was live then. A board reposted mid-day would render without that column.

    A row the target already carries for the same slot and day stays where it is. One (message, bucket, day)
    is unique, so moving it raised mid-repost and left the day holding two boards: the fresh one posted, and
    the one it was meant to replace still up and still signable."""
    with SessionLocal() as session:
        taken = {
            (bucket, signal_date) for bucket, signal_date in session.execute(
                select(PodSignal.bucket, PodSignal.signal_date).where(
                    PodSignal.kind == pod_signals.KIND_POLL,
                    PodSignal.message_id == new_message_id,
                )
            ).all()
        }
        rows = session.execute(
            select(PodSignal).where(
                PodSignal.kind == pod_signals.KIND_POLL,
                PodSignal.message_id == old_message_id,
            )
        ).scalars().all()
        moved = 0
        for signal in rows:
            if (signal.bucket, signal.signal_date) in taken:
                log.warning(
                    f"launcher row {signal.id} stays on {old_message_id}: "
                    f"{signal.bucket} on {signal.signal_date} is already on {new_message_id}"
                )
                continue
            signal.message_id = new_message_id
            moved += 1
        session.commit()
        return moved


def _open_poll_signal_for_slot(
    session: Session, time_key: str, set_code: str, signal_date: date,
) -> PodSignal | None:
    """The still-gathering poll row for one format of one slot of one day, whichever message it currently
    hangs on — the row a fresh launcher adopts and a roll re-uses. A fired or expired row is never returned:
    it belongs to the pod it already made.

    A row keyed on the bare time slot is adopted as the latest set's and rewritten to the named key, so the
    signups a board collected before named formats shipped survive the first post that binds them."""
    named_key = pod_signals.named_bucket_key(time_key, set_code)
    keys = [named_key, time_key] if set_code == latest_on(signal_date) else [named_key]
    for key in keys:
        signals = session.execute(
            select(PodSignal)
            .where(
                PodSignal.kind == pod_signals.KIND_POLL,
                PodSignal.bucket == key,
                PodSignal.signal_date == signal_date,
            )
            .order_by(PodSignal.created_at)
        ).scalars().all()
        for signal in signals:
            if signal.status == pod_signals.STATUS_OPEN:
                signal.bucket = named_key
                signal.set_code = set_code
                return signal
    return None


def _expired_poll_signal_exists(
    session: Session, time_key: str, set_code: str, signal_date: date,
) -> bool:
    """Whether this format of this slot already closed unfired on that day, on whichever message it hangs.
    A fired row is not this: its pod can be canceled, and the slot then re-opens on a fresh row."""
    return session.execute(
        select(PodSignal.id).where(
            PodSignal.kind == pod_signals.KIND_POLL,
            PodSignal.bucket == pod_signals.named_bucket_key(time_key, set_code),
            PodSignal.signal_date == signal_date,
            PodSignal.status == pod_signals.STATUS_EXPIRED,
        ).limit(1)
    ).scalar_one_or_none() is not None


def roll_slot_forward_sync(
    *, lane: str, from_day: date, guild_id: str, channel_id: str, message_id: str,
) -> list[tuple[str, str, datetime]]:
    """Open the next day's pods for a lane whose current pod is done, and bind them to the launcher message
    that is already posted so their buttons have a home right away. Returns (signal_id, bucket_key,
    slot_time) per format the next day offers, empty when a pod already covers every one of them.

    Idempotent: a second table finishing after the first, or a restart, re-uses the rows already opened."""
    day = from_day + timedelta(days=1)
    bucket = pod_signals.bucket_for_lane(day, lane)
    if bucket is None:
        return []
    slot_time = slot_event_time(day, bucket.key)
    rolled: list[tuple[str, str, datetime]] = []
    with SessionLocal() as session:
        covered = _event_formats_for_slot(session, slot_time)
        for set_code in formats_on(day, lane):
            if set_code in covered:
                continue
            signal = _open_poll_signal_for_slot(session, bucket.key, set_code, day)
            if signal is None:
                signal = PodSignal(
                    kind=pod_signals.KIND_POLL,
                    bucket=pod_signals.named_bucket_key(bucket.key, set_code),
                    guild_id=guild_id,
                    channel_id=channel_id,
                    message_id=message_id,
                    signal_date=day,
                    slot_time=slot_time,
                    set_code=set_code,
                )
                session.add(signal)
            else:
                signal.channel_id = channel_id
                signal.message_id = message_id
            session.flush()
            rolled.append((signal.id, signal.bucket, slot_time))
        session.commit()
    return rolled


def joined_formats_at_slot_sync(
    message_id: str, slot_time: datetime | None, discord_user_id: str,
) -> list[str]:
    """The formats this player is signed up for at one slot time, in the day's render order. Only pods still
    gathering count: one that fired already settled who plays in it, so a choice is only pending among these."""
    if slot_time is None:
        return []
    with SessionLocal() as session:
        signals = session.execute(
            select(PodSignal)
            .join(PodSignalMember, PodSignalMember.signal_id == PodSignal.id)
            .where(
                PodSignal.kind == pod_signals.KIND_POLL,
                PodSignal.status == pod_signals.STATUS_OPEN,
                PodSignal.message_id == message_id,
                PodSignal.slot_time == slot_time,
                PodSignalMember.discord_user_id == discord_user_id,
            )
        ).scalars().all()
        codes = [code for code in (_signal_format(signal) for signal in signals) if code]
    return sorted(codes, key=format_order_key)


def join_slot_signal_sync(
    signal_id: str, discord_user_id: str, display_name: str,
) -> bool:
    """Add one player to a pre-opened slot, the write behind the Play Again button. False when the slot is
    gone or no longer gathering, or the player is already on it.

    Someone who declined is not on it, so their kept row is put back to Yes instead of refusing them. That
    row is the whole point of keeping a decline: pressing Leave and signing up again returns the player to
    the place their original signup time earns them."""
    with SessionLocal() as session:
        signal = session.get(PodSignal, signal_id)
        if signal is None or signal.status != pod_signals.STATUS_OPEN:
            return False
        existing = session.execute(
            select(PodSignalMember).where(
                PodSignalMember.signal_id == signal_id,
                PodSignalMember.discord_user_id == discord_user_id,
            )
        ).scalar_one_or_none()
        if existing is not None and existing.rsvp != pod_signals.RSVP_NO:
            return False
        if existing is not None:
            existing.rsvp = pod_signals.RSVP_YES
            existing.display_name = display_name
        else:
            session.add(PodSignalMember(
                signal_id=signal_id, discord_user_id=discord_user_id, display_name=display_name,
                format_interest=get_format_interests(session, discord_user_id),
            ))
        signal.last_activity_at = datetime.now(timezone.utc)
        session.commit()
        return True


def leave_board_slots_sync(message_id: str, discord_user_id: str) -> list[LeftSlot]:
    """Drop the player from every pod still gathering on one board, newest slot last. The board's Leave
    button is the one place a signup is taken back, so it acts on the whole board: a player on two formats of
    one slot means two rows, and leaving one of them while the other still holds them is not what the button
    says. A pod that already fired is not touched here — its roster lives on its card."""
    with SessionLocal() as session:
        rows = session.execute(
            select(PodSignal, PodSignalMember)
            .join(PodSignalMember, PodSignalMember.signal_id == PodSignal.id)
            .where(
                PodSignal.kind == pod_signals.KIND_POLL,
                PodSignal.status == pod_signals.STATUS_OPEN,
                PodSignal.message_id == message_id,
                PodSignalMember.discord_user_id == discord_user_id,
            )
        ).all()
        left = [LeftSlot(signal.id, signal.bucket, signal.slot_time) for signal, _member in rows]
        for _signal, member in rows:
            session.delete(member)
        session.commit()
    return sorted(left, key=lambda slot: (slot.slot_time is None, slot.slot_time))


def open_slot_for_bucket_sync(bucket_key: str, now: datetime) -> tuple[str, str, datetime] | None:
    """(signal_id, launcher message_id, slot_time) of the soonest still-gathering slot of a bucket, for a
    surface that knows its slot only by name — the Play Again button in a finished pod's thread. None when
    that slot has no open row, so a stale button says so instead of joining a dead slot."""
    with SessionLocal() as session:
        signal = session.execute(
            select(PodSignal)
            .where(
                PodSignal.kind == pod_signals.KIND_POLL,
                PodSignal.bucket == bucket_key,
                PodSignal.status == pod_signals.STATUS_OPEN,
                PodSignal.slot_time > now,
            )
            .order_by(PodSignal.slot_time)
            .limit(1)
        ).scalars().first()
        if signal is None:
            return None
        return signal.id, signal.message_id, signal.slot_time


def create_queue_signal_sync(
    *, guild_id: str, channel_id: str, message_id: str, signal_date: date, opened_by: str,
    set_code: str | None = None, pairing_mode: str | None = None, seating_mode: str | None = None,
    pick_timer: int | None = None, notify_role: str | None = None, description: str | None = None,
) -> str:
    with SessionLocal() as session:
        signal = PodSignal(
            kind=pod_signals.KIND_QUEUE,
            bucket=pod_signals.QUEUE_BUCKET,
            guild_id=guild_id,
            channel_id=channel_id,
            message_id=message_id,
            signal_date=signal_date,
            opened_by=opened_by,
            set_code=set_code,
            pairing_mode=pairing_mode,
            seating_mode=seating_mode,
            pick_timer=pick_timer,
            notify_role=notify_role,
            description=description,
            format_locked=True,
        )
        session.add(signal)
        session.commit()
        return signal.id


@dataclass(frozen=True)
class QueuePresets:
    set_code: str | None
    pairing_mode: str | None
    seating_mode: str | None
    pick_timer: int | None


def queue_presets_sync(signal_id: str) -> QueuePresets:
    """The set + pairing / seating / pick-timer chosen in the /draft launcher, applied to the pod once
    its queue fires. All None when the pod was opened without presets (defaults to the active set)."""
    with SessionLocal() as session:
        signal = session.get(PodSignal, signal_id)
        if signal is None:
            return QueuePresets(None, None, None, None)
        return QueuePresets(
            signal.set_code, signal.pairing_mode, signal.seating_mode, signal.pick_timer,
        )


def queue_opener_sync(signal_id: str) -> tuple[datetime | None, str | None]:
    """(opened_at, opened_by) for a queue signal, so a closed card can still credit who opened it."""
    with SessionLocal() as session:
        signal = session.get(PodSignal, signal_id)
        if signal is None:
            return None, None
        return signal.created_at, signal.opened_by


def queue_member_names_sync(signal_id: str) -> list[str]:
    """Display names still in the queue, so a timed-out card keeps showing who was around."""
    with SessionLocal() as session:
        return _member_names(session, signal_id)


def set_discussion_thread_sync(signal_id: str, thread_id: str) -> None:
    with SessionLocal() as session:
        signal = session.get(PodSignal, signal_id)
        if signal is not None:
            signal.discussion_thread_id = thread_id
            session.commit()


def discussion_thread_id_sync(message_id: str) -> str | None:
    """The standalone discussion thread's id for a queue card, keyed by the card message id."""
    with SessionLocal() as session:
        return session.execute(
            select(PodSignal.discussion_thread_id).where(
                PodSignal.message_id == message_id,
                PodSignal.bucket == pod_signals.QUEUE_BUCKET,
            )
        ).scalar_one_or_none()


@dataclass(frozen=True)
class JoinableSignal:
    kind: str
    channel_id: str
    message_id: str
    slot_time: datetime | None
    count: int
    set_code: str | None


def joinable_signals_sync(guild_id: str, *, now: datetime,
                          within: timedelta | None = None) -> list[JoinableSignal]:
    """Open queues and still-to-fire poll slots in the guild — what a caller could join instead of starting
    a fresh pod. `within` bounds how far ahead a slot may start, for a surface offering to divert someone
    who wants to draft now; no bound reports every slot still open on the board."""
    with SessionLocal() as session:
        signals = session.execute(
            select(PodSignal).where(
                PodSignal.guild_id == guild_id,
                PodSignal.status == pod_signals.STATUS_OPEN,
                PodSignal.kind.in_([pod_signals.KIND_QUEUE, pod_signals.KIND_POLL]),
            ).order_by(PodSignal.created_at)
        ).scalars().all()
        joinable: list[JoinableSignal] = []
        for signal in signals:
            if signal.slot_time is not None and signal.slot_time <= now:
                continue
            if signal.slot_time is not None and within is not None and signal.slot_time > now + within:
                continue
            joinable.append(JoinableSignal(
                signal.kind, signal.channel_id, signal.message_id, signal.slot_time, len(signal.members),
                signal.set_code,
            ))
        return joinable


def create_scheduled_signal_sync(
    *, guild_id: str, channel_id: str, message_id: str, event_time: datetime,
    pick_timer: int | None = None, format_locked: bool = True, opened_by: str | None = None,
) -> str:
    """A scheduled pod's signal is born fired with the caller linking its event right after: RSVPs
    stay open forever for over-signups and expiry never applies. Pairing and seating live on the
    event; only the pick timer rides the signal, since it is live-only and applied at lobby open.

    `format_locked` is the default: a /draft card, a championship, or a mock draft each carry a set the
    organizer chose, so the Latest/Flashback preference system never applies. Only a graduated launcher
    slot opts out, since it is the flex surface that resolves its format from the roster's preferences.

    `opened_by` is only set for a pod someone scheduled by hand with /draft, which is what lets the card
    credit an organizer that no schedule chose."""
    with SessionLocal() as session:
        signal = PodSignal(
            kind=pod_signals.KIND_SCHEDULED,
            bucket=pod_signals.SCHEDULED_BUCKET,
            guild_id=guild_id,
            channel_id=channel_id,
            message_id=message_id,
            signal_date=event_time.astimezone(SCHEDULE_TZ).date(),
            slot_time=event_time,
            status=pod_signals.STATUS_FIRED,
            pick_timer=pick_timer,
            format_locked=format_locked,
            opened_by=opened_by,
        )
        session.add(signal)
        session.commit()
        return signal.id


def scheduled_pick_timer_for_event_sync(event_id: str) -> int | None:
    with SessionLocal() as session:
        return session.execute(
            select(PodSignal.pick_timer).where(
                PodSignal.event_id == event_id, PodSignal.kind == pod_signals.KIND_SCHEDULED
            )
        ).scalar_one_or_none()


def set_rsvp(
    session: Session, message_id: str, discord_user_id: str, display_name: str, rsvp: str,
    confirming: bool = False,
) -> RsvpResult | None:
    """RSVP on a scheduled card: the member moves to whichever state they pressed, including No.

    A decline keeps the row so the signup time survives it. Pressing Leave by mistake and signing up
    again then costs nothing, where deleting the row sent that player to the back of a queue ordered by
    `created_at`. It also gives the roster card a decline to show, which is the answer worth the most to
    the plan. Confirming and then declining clears the confirmation, so a decline never counts toward the
    players a table is built around.

    Clicking the state they already hold is a no-op. `joined` is True only when the member freshly
    entered Yes. Scheduled signals are born fired and never expire, so only a stray expired row refuses.
    Does not commit.

    A confirmation the pod is already past writes nothing. The tables were dealt at the start time and the
    room opened against the answers held then, so a later one moves nothing except the player's own place
    on the pods it clashes with. The card it was pressed on may be minutes stale in a client that never
    took the render greying it, which is why the refusal lives here and not on the button. Signing up is
    untouched: a pod one player short takes a walk-in at any point, and Leave stays open to the end."""
    signal = _scheduled_signal_by_surface(session, message_id)
    if signal is None:
        return None
    if signal.status == pod_signals.STATUS_EXPIRED:
        rosters, new_drafters = _members_by_rsvp(session, signal.id)
        yes_count = len(rosters[pod_signals.RSVP_YES])
        return RsvpResult(
            _state(signal, yes_count), rosters, rsvp=None, joined=False, closed=True,
            roster_interests=_render_interests(session, signal), new_drafters=new_drafters,
        )

    event = session.get(PodDraftEvent, signal.event_id) if signal.event_id is not None else None
    if confirming and event is not None and event.event_time <= datetime.now(timezone.utc):
        rosters, new_drafters = _members_by_rsvp(session, signal.id)
        yes_count = len(rosters[pod_signals.RSVP_YES])
        return RsvpResult(
            _state(signal, yes_count), rosters, rsvp=None, joined=False, closed=False, started=True,
            roster_interests=_render_interests(session, signal), new_drafters=new_drafters,
            event_name=event.name, event_time=event.event_time,
        )
    existing = session.execute(
        select(PodSignalMember).where(
            PodSignalMember.signal_id == signal.id,
            PodSignalMember.discord_user_id == discord_user_id,
        )
    ).scalar_one_or_none()
    was_yes = existing is not None and existing.rsvp == pod_signals.RSVP_YES
    confirming = confirming or _inside_confirmation_window(event, rsvp)
    confirmed_at = datetime.now(timezone.utc) if confirming else None
    joined = False
    if existing is not None:
        if existing.rsvp != rsvp:
            joined = rsvp == pod_signals.RSVP_YES
            existing.rsvp = rsvp
        if confirming:
            existing.confirmed_at = confirmed_at
        elif rsvp in (pod_signals.RSVP_MAYBE, pod_signals.RSVP_NO):
            existing.confirmed_at = None
        existing.display_name = display_name
    elif rsvp != pod_signals.RSVP_NO:
        session.add(PodSignalMember(
            signal_id=signal.id, discord_user_id=discord_user_id, display_name=display_name, rsvp=rsvp,
            format_interest=get_format_interests(session, discord_user_id), confirmed_at=confirmed_at,
        ))
        signal.last_activity_at = datetime.now(timezone.utc)
        joined = rsvp == pod_signals.RSVP_YES
    session.flush()
    rosters, new_drafters = _members_by_rsvp(session, signal.id)
    roster_interests = _render_interests(session, signal)
    yes_count = len(rosters[pod_signals.RSVP_YES])
    yes_changed = was_yes != (rsvp == pod_signals.RSVP_YES)
    return RsvpResult(
        _state(signal, yes_count), rosters, rsvp=rsvp, joined=joined, closed=False,
        yes_changed=yes_changed, roster_interests=roster_interests, new_drafters=new_drafters,
        event_name=event.name if event is not None else None,
        event_time=event.event_time if event is not None else None,
        confirmed=confirming and rsvp == pod_signals.RSVP_YES,
    )


def _inside_confirmation_window(event: PodDraftEvent | None, rsvp: str) -> bool:
    """Whether saying Yes right now counts as confirming on its own.

    Inside the hour before the draft a fresh Yes is a confirmation by definition: nobody signs up at ten
    to nine for a pod they are not about to play. Asking those people to press a second button would only
    catch out the ones who answered latest and are surest."""
    if rsvp != pod_signals.RSVP_YES or event is None or event.event_time is None:
        return False
    remaining = event.event_time - datetime.now(timezone.utc)
    return timedelta(0) <= remaining <= timedelta(minutes=CONFIRM_WINDOW_MINUTES)


def set_rsvp_sync(
    message_id: str, discord_user_id: str, display_name: str, rsvp: str, confirming: bool = False,
) -> RsvpResult | None:
    with SessionLocal() as session:
        result = set_rsvp(session, message_id, discord_user_id, display_name, rsvp, confirming=confirming)
        session.commit()
        return result


def set_membership(
    session: Session, message_id: str, bucket: str, discord_user_id: str, display_name: str,
    action: str = "join",
) -> ToggleResult | None:
    """Put the user on a bucket or take them off it. Returns None when no such signal exists; a closed
    result (no mutation) when the signal has expired. A fired signal still accepts joins — over-signups
    ride along and are in the roster when the lobby opens. `joined` is True only on a fresh add; `changed`
    is True when the roster actually moved. Bumps last_activity_at on an add so queue teardown resets.
    A player holding a decline counts as off the bucket, so joining puts their kept row back to Yes.
    Does not commit.

    Every surface names the action it takes. A press whose meaning depended on membership the presser could
    not see read as a dead button when it was slow, and the second press they gave it undid the first."""
    signal = _signal_by_message_bucket(session, message_id, bucket)
    if signal is None:
        return None
    now = datetime.now(timezone.utc)
    if _lazy_status(signal.status, signal.slot_time, now) == pod_signals.STATUS_EXPIRED:
        names = _member_names(session, signal.id)
        return ToggleResult(_state(signal, len(names)), names, joined=False, changed=False, closed=True)

    existing = session.execute(
        select(PodSignalMember).where(
            PodSignalMember.signal_id == signal.id,
            PodSignalMember.discord_user_id == discord_user_id,
        )
    ).scalar_one_or_none()
    add = action == "join"
    declined = existing is not None and existing.rsvp == pod_signals.RSVP_NO
    joined = changed = False
    if add and declined:
        existing.rsvp = pod_signals.RSVP_YES
        existing.display_name = display_name
        signal.last_activity_at = datetime.now(timezone.utc)
        joined = changed = True
    elif add and existing is None:
        session.add(PodSignalMember(
            signal_id=signal.id, discord_user_id=discord_user_id, display_name=display_name,
            format_interest=get_format_interests(session, discord_user_id),
        ))
        signal.last_activity_at = datetime.now(timezone.utc)
        joined = changed = True
    elif not add and existing is not None:
        session.delete(existing)
        changed = True
    session.flush()
    names = _member_names(session, signal.id)
    return ToggleResult(_state(signal, len(names)), names, joined=joined, changed=changed, closed=False)


def set_membership_sync(
    message_id: str, bucket: str, discord_user_id: str, display_name: str, action: str = "join",
) -> ToggleResult | None:
    with SessionLocal() as session:
        result = set_membership(session, message_id, bucket, discord_user_id, display_name, action)
        session.commit()
        return result


def queue_member_count(session: Session, message_id: str, discord_user_id: str) -> tuple[bool, int] | None:
    """(is_member, count) for an open queue by its card message id, or None if the signal is gone or
    closed — lets the Leave button decide whether the click would empty the queue."""
    signal = _signal_by_message_bucket(session, message_id, pod_signals.QUEUE_BUCKET)
    if signal is None or signal.status != pod_signals.STATUS_OPEN:
        return None
    member_ids = session.execute(
        select(PodSignalMember.discord_user_id).where(PodSignalMember.signal_id == signal.id)
    ).scalars().all()
    return discord_user_id in member_ids, len(member_ids)


def queue_member_count_sync(message_id: str, discord_user_id: str) -> tuple[bool, int] | None:
    with SessionLocal() as session:
        return queue_member_count(session, message_id, discord_user_id)


def resolve_last_leave(session: Session, message_id: str, discord_user_id: str) -> LeaveResolution:
    """Settle a confirmed last-player Leave. Cancels the queue only if the confirmer is still the sole
    member; if anyone joined during the prompt the confirmer is just removed and the queue stays open.
    Does not commit."""
    signal = _signal_by_message_bucket(session, message_id, pod_signals.QUEUE_BUCKET)
    if signal is None or signal.status != pod_signals.STATUS_OPEN:
        return LeaveResolution(LEAVE_GONE, [], None, None, None)
    member_ids = session.execute(
        select(PodSignalMember.discord_user_id).where(PodSignalMember.signal_id == signal.id)
    ).scalars().all()
    if discord_user_id in member_ids and len(member_ids) > 1:
        session.execute(
            delete(PodSignalMember).where(
                PodSignalMember.signal_id == signal.id,
                PodSignalMember.discord_user_id == discord_user_id,
            )
        )
        session.flush()
        names = _member_names(session, signal.id)
        return LeaveResolution(
            LEAVE_LEFT, names, signal.set_code, signal.created_at, signal.opened_by,
            signal.notify_role, signal.description,
        )
    signal.status = pod_signals.STATUS_EXPIRED
    return LeaveResolution(
        LEAVE_CANCELLED, [], signal.set_code, signal.created_at, signal.opened_by,
        signal.notify_role, signal.description,
    )


def resolve_last_leave_sync(message_id: str, discord_user_id: str) -> LeaveResolution:
    with SessionLocal() as session:
        resolution = resolve_last_leave(session, message_id, discord_user_id)
        session.commit()
        return resolution


def claim_fire(session: Session, signal_id: str) -> bool:
    """Atomically flip status open→fired; True only for the caller that won the race. No commit."""
    result = session.execute(
        update(PodSignal)
        .where(PodSignal.id == signal_id, PodSignal.status == pod_signals.STATUS_OPEN)
        .values(status=pod_signals.STATUS_FIRED)
    )
    return result.rowcount == 1


def claim_fire_sync(signal_id: str) -> bool:
    with SessionLocal() as session:
        claimed = claim_fire(session, signal_id)
        session.commit()
        return claimed


def claim_slot_fire_sync(signal_id: str) -> bool:
    """Claim a launcher slot's fire, but only while it still holds a full pod: signups can leave between the
    press that filled it and this claim."""
    with SessionLocal() as session:
        signal = session.get(PodSignal, signal_id)
        if signal is None:
            return False
        threshold = pod_signals.fire_threshold_for(
            signal.slot_time, signal.set_code, datetime.now(timezone.utc), settings.pod_signal_fire_threshold,
        )
        if not pod_signals.should_fire(len(signal.members), threshold):
            return False
        claimed = claim_fire(session, signal_id)
        session.commit()
        return claimed


def slot_fire_state_sync(signal_id: str) -> tuple[SignalState, str] | None:
    """An open launcher slot as (state, launcher message id), or None when it is gone or already fired."""
    with SessionLocal() as session:
        signal = session.get(PodSignal, signal_id)
        if signal is None or signal.status != pod_signals.STATUS_OPEN or signal.message_id is None:
            return None
        return _state(signal, len(_member_names(session, signal.id))), signal.message_id


def _fire_order(state: SignalState) -> tuple[int, tuple[int, str]]:
    """The order full pods graduate in: the fullest first, then the day's format order."""
    return (-state.count, format_order_key(state.set_code))


def release_fire_sync(signal_id: str) -> None:
    """Revert a claimed fire back to open when pod creation fails, so it can fire again."""
    with SessionLocal() as session:
        session.execute(
            update(PodSignal)
            .where(PodSignal.id == signal_id, PodSignal.status == pod_signals.STATUS_FIRED)
            .values(status=pod_signals.STATUS_OPEN)
        )
        session.commit()


def claim_one_more_ping_sync(signal_id: str, quiet_minutes: int) -> bool:
    """Atomically claim the one one-short-of-firing ping a queue gets. True only for a still-open
    signal that is older than the quiet window and hasn't pinged yet, so fast-filling queues stay
    silent and concurrent joins can't double-ping."""
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=quiet_minutes)
    with SessionLocal() as session:
        result = session.execute(
            update(PodSignal)
            .where(
                PodSignal.id == signal_id,
                PodSignal.status == pod_signals.STATUS_OPEN,
                PodSignal.one_more_pinged_at.is_(None),
                PodSignal.created_at <= cutoff,
            )
            .values(one_more_pinged_at=datetime.now(timezone.utc))
        )
        session.commit()
        return result.rowcount == 1


def link_event_sync(signal_id: str, event_id: str) -> None:
    with SessionLocal() as session:
        session.execute(
            update(PodSignal).where(PodSignal.id == signal_id).values(event_id=event_id)
        )
        session.commit()


def expire_signal_sync(signal_id: str) -> bool:
    """Flip an open signal to expired; True only if it was still open."""
    with SessionLocal() as session:
        result = session.execute(
            update(PodSignal)
            .where(PodSignal.id == signal_id, PodSignal.status == pod_signals.STATUS_OPEN)
            .values(status=pod_signals.STATUS_EXPIRED)
        )
        session.commit()
        return result.rowcount == 1


def fired_slot_for_pod_sync(event_id: str) -> str | None:
    """The launcher slot a pod fired out of, or None for a pod no slot owns. Matched on the slot's time and
    format: firing hands the `event_id` to the scheduled card's own row, so the poll row it came from is
    never linked to the pod and this is the only way back to it."""
    with SessionLocal() as session:
        event = session.get(PodDraftEvent, event_id)
        if event is None:
            return None
        slots = session.execute(
            select(PodSignal).where(
                PodSignal.kind == pod_signals.KIND_POLL,
                PodSignal.status == pod_signals.STATUS_FIRED,
                PodSignal.slot_time == event.event_time,
            )
        ).scalars().all()
        wanted = event.set_code or active_set_code()
        for slot in slots:
            if _signal_format(slot) == wanted:
                return slot.id
        return None


@dataclass(frozen=True)
class PodResetResult:
    signals: int = 0
    members: int = 0
    events: int = 0
    thread_ids: tuple[int, ...] = ()
    card_refs: tuple[tuple[int, int], ...] = ()


def reset_ondemand_signals_sync(guild_id: str) -> PodResetResult:
    """Test-only: clear every on-demand pod signal (poll / queue / scheduled) and its members for a
    guild, plus the pods they staged, so the `!test` surfaces start from a clean slate. Reflection reads
    events by slot time, so a stale event row keeps reflecting as a committed slot until it is dropped
    too. Every unfinalized pod goes, plus every pod dated today however far it got, so a test pod played
    through to finalization stops carrying its points and its slot into the next run. Finalized pods from
    earlier days are left as leaderboard history.

    Returns the Discord threads and channel cards the dropped pods and signals owned, for the caller to
    delete. In-thread mirrors need no ref of their own; they go with their thread.

    The event delete is global (pods carry no guild), so this refuses outright unless it is scoped to a
    known non-production guild: an empty guild or the production guild is a hard no-op, guarding against
    ever wiping real pods from the prod deployment."""
    if not guild_id or guild_id == str(PRODUCTION_GUILD_ID):
        return PodResetResult()
    today = datetime.now(SCHEDULE_TZ).date()
    with SessionLocal() as session:
        signals = list(session.execute(select(PodSignal).where(PodSignal.guild_id == guild_id)).scalars())
        doomed = list(
            session.execute(
                select(PodDraftEvent).where(
                    or_(PodDraftEvent.finalized_at.is_(None), PodDraftEvent.event_date == today)
                )
            ).scalars()
        )
        thread_ids = _reset_thread_ids(signals, doomed)
        card_refs = _reset_card_refs(signals)
        signal_ids = [signal.id for signal in signals]
        members = 0
        if signal_ids:
            members = session.execute(
                delete(PodSignalMember).where(PodSignalMember.signal_id.in_(signal_ids))
            ).rowcount
        deleted_signals = session.execute(delete(PodSignal).where(PodSignal.guild_id == guild_id)).rowcount
        deleted_events = 0
        if doomed:
            deleted_events = session.execute(
                delete(PodDraftEvent).where(PodDraftEvent.id.in_([event.id for event in doomed]))
            ).rowcount
        session.commit()
        return PodResetResult(deleted_signals, members, deleted_events, thread_ids, card_refs)


async def delete_reset_cards(card_refs: Iterable[tuple[int, int]]) -> int:
    """Delete the channel cards and launcher boards the reset dropped the rows for, so no surface is
    left holding buttons that resolve to nothing. Test-only, alongside reset_ondemand_signals_sync."""
    if _bot is None:
        return 0
    deleted = 0
    for channel_id, message_id in card_refs:
        channel = await _resolve_channel(channel_id)
        if channel is None:
            continue
        try:
            await channel.get_partial_message(message_id).delete()
        except discord.NotFound:
            continue
        except discord.HTTPException as e:
            log.warning(f"test reset: delete card {message_id} failed: {e}")
            continue
        deleted += 1
    return deleted


def _reset_thread_ids(signals: list[PodSignal], events: list[PodDraftEvent]) -> tuple[int, ...]:
    raw_ids: list[str | None] = [signal.discussion_thread_id for signal in signals]
    for event in events:
        raw_ids += [event.discord_thread_id, event.team_a_thread_id, event.team_b_thread_id]
    ordered: list[int] = []
    seen: set[int] = set()
    for raw in raw_ids:
        thread_id = snowflake_or_none(raw)
        if thread_id is None:
            continue
        if thread_id not in seen:
            seen.add(thread_id)
            ordered.append(thread_id)
    return tuple(ordered)


def _reset_card_refs(signals: list[PodSignal]) -> tuple[tuple[int, int], ...]:
    ordered: list[tuple[int, int]] = []
    seen: set[tuple[int, int]] = set()
    for signal in signals:
        ref = (int(signal.channel_id), int(signal.message_id))
        if ref not in seen:
            seen.add(ref)
            ordered.append(ref)
    return tuple(ordered)


def poll_exists_for_date_sync(signal_date: date) -> bool:
    """Whether a launcher was already posted for this day. Keyed on each board's own day, not on any slot
    it carries: yesterday's board opens today's rolled slots, and that must not read as today's post."""
    return _board_for_date(signal_date) is not None


def launcher_message_id_for_date_sync(signal_date: date) -> str | None:
    """The launcher message posted that day, if any. None means no launcher was posted (a card can exist
    without one)."""
    board = _board_for_date(signal_date)
    return board[1] if board else None


def past_launcher_boards_sync(before_date: date, since_date: date) -> list[tuple[str, str, date]]:
    """(channel_id, message_id, posting day) per launcher board posted in [since_date, before_date) — the
    recently-posted launchers a new day's post closes out. Bounded to a short window so each daily post
    re-touches only a handful, never the full history.

    Every board of a day, not the newest of each: a day that ended up holding two boards must not leave the
    older one live with working buttons, which nothing else would ever come back for."""
    return [board for board in _launcher_boards() if since_date <= board[2] < before_date]


def launcher_ref_for_date_sync(signal_date: date) -> tuple[str, str] | None:
    """(channel_id, message_id) of the launcher posted that day, if any. Resolving the channel off the
    signal rather than a fixed setting keeps `!test` (posted in the test channel) and prod correct."""
    board = _board_for_date(signal_date)
    return (board[0], board[1]) if board else None


def launcher_date_for_message_sync(message_id: str) -> date | None:
    """The day a launcher message was posted for — the earliest day its slots cover, since a rolled column
    carries the next day on the same message. `!test poll` posts tomorrow's launcher once today's slots
    have passed, so the message timestamp is not a safe date source."""
    with SessionLocal() as session:
        return session.execute(
            select(func.min(PodSignal.signal_date)).where(
                PodSignal.kind == pod_signals.KIND_POLL, PodSignal.message_id == message_id
            )
        ).scalar_one_or_none()


def launcher_channel_for_message_sync(message_id: str) -> str | None:
    """The channel a launcher board was posted in, read off its own rows. A re-render that assumes the
    coordination channel silently 404s on a board posted anywhere else, which is where `!test launcher`
    puts one, so the board stops tracking its pods from the first click."""
    with SessionLocal() as session:
        return session.execute(
            select(PodSignal.channel_id)
            .where(PodSignal.kind == pod_signals.KIND_POLL, PodSignal.message_id == message_id)
            .limit(1)
        ).scalar_one_or_none()


def latest_launcher_sync() -> tuple[str, date] | None:
    """The newest launcher's (message_id, posting day), for surfaces that open the preference picker
    without a launcher message in hand."""
    boards = _launcher_boards()
    if not boards:
        return None
    newest = boards[-1]
    return newest[1], newest[2]


def live_launcher_board_sync() -> tuple[str, str, str, date] | None:
    """(guild_id, channel_id, message_id, posting day) of the newest launcher board — the live surface a
    rolled slot binds to and re-renders on.

    Newest is by when the board was posted, never by the days its slots cover. A board that has rolled a lane
    forward carries next-day rows, and a fresh board posted the same day adopts only the rows dated for its
    own day, so the older board is left holding the later dates. Ranking on those dates handed the roll a
    retired message: the live board kept its dead slot, its buttons stayed closed, and the column never
    reached tomorrow."""
    with SessionLocal() as session:
        row = session.execute(
            select(
                PodSignal.guild_id, PodSignal.channel_id, PodSignal.message_id,
                func.min(PodSignal.signal_date),
            )
            .where(PodSignal.kind == pod_signals.KIND_POLL)
            .group_by(PodSignal.guild_id, PodSignal.channel_id, PodSignal.message_id)
            .order_by(func.max(PodSignal.created_at).desc())
            .limit(1)
        ).first()
    return (row[0], row[1], row[2], row[3]) if row else None


def _launcher_boards() -> list[tuple[str, str, date]]:
    """(channel_id, message_id, posting day) per launcher board, oldest first. A board's day is the
    earliest day its slots cover, so a rolled column's next-day rows never re-date the board."""
    with SessionLocal() as session:
        rows = session.execute(
            select(PodSignal.channel_id, PodSignal.message_id, func.min(PodSignal.signal_date))
            .where(PodSignal.kind == pod_signals.KIND_POLL)
            .group_by(PodSignal.channel_id, PodSignal.message_id)
            .order_by(func.min(PodSignal.signal_date), func.max(PodSignal.created_at))
        ).all()
    return [(channel_id, message_id, day) for channel_id, message_id, day in rows]


def _board_for_date(signal_date: date) -> tuple[str, str, date] | None:
    """The newest board posted for this day, or None. Repeated `!test poll` runs leave several; the last
    one posted is the live board."""
    match = None
    for board in _launcher_boards():
        if board[2] == signal_date:
            match = board
    return match


def event_thread_id_sync(event_id: str) -> str | None:
    with SessionLocal() as session:
        event = session.get(PodDraftEvent, event_id)
        return event.discord_thread_id if event else None


def signal_message_ref_sync(signal_id: str) -> tuple[str, str] | None:
    with SessionLocal() as session:
        row = session.execute(
            select(PodSignal.channel_id, PodSignal.message_id).where(PodSignal.id == signal_id)
        ).first()
    return (row[0], row[1]) if row else None


def slot_occupied_by_any_pod_sync(slot_time: datetime) -> bool:
    """Whether a pod of any set already sits at this slot, so an auto-scheduler stands down instead of
    stacking a second pod onto the same window."""
    with SessionLocal() as session:
        return _event_id_for_slot(session, slot_time) is not None


def slot_lane_ref_sync(signal_id: str) -> tuple[str, date] | None:
    """(lane, the day the slot sat on) for a poll signal, so a caller can roll its column forward."""
    with SessionLocal() as session:
        signal = session.get(PodSignal, signal_id)
        if signal is None:
            return None
        lane = pod_signals.lane_of(signal.bucket)
        return (lane, signal.signal_date) if lane else None


def event_lane_ref_sync(event_id: str) -> tuple[str, date] | None:
    """(lane, the day the pod played) for a pod sitting at a launcher slot, or None for an off-grid pod that
    no column owns. Keyed on the slot the launcher reflects, so a postponed pod still rolls the column it was
    gathered in."""
    with SessionLocal() as session:
        slot_time = _pod_slot_time(session, event_id)
    if slot_time is None:
        return None
    local = slot_time.astimezone(SCHEDULE_TZ)
    for bucket in pod_signals.poll_buckets_for(local.date()):
        if bucket.start.hour == local.hour and bucket.start.minute == local.minute:
            return bucket.lane, local.date()
    return None


def play_again_slots_sync(event_id: str, now: datetime) -> list[str] | None:
    """Bucket keys the finished pod's Play Again prompt offers: every still-open slot sharing the start time
    closest to a day after the pod played, so an off-grid pod no column owns is still invited back to the
    slot nearest its own hour. None for a mock draft, which has no group to invite back and gets no prompt at
    all; empty when no later slot is open, which signs the thread off without a button."""
    with SessionLocal() as session:
        event = session.get(PodDraftEvent, event_id)
        if event is None or event.kind == "mock":
            return None
        played_at = _pod_slot_time(session, event_id)
        rows = session.execute(
            select(PodSignal.bucket, PodSignal.slot_time)
            .where(
                PodSignal.kind == pod_signals.KIND_POLL,
                PodSignal.status == pod_signals.STATUS_OPEN,
                PodSignal.slot_time > now,
            )
            .order_by(PodSignal.bucket)
        ).all()
    target = played_at + timedelta(days=1)
    nearest = None
    for _bucket, slot_time in rows:
        if nearest is None or abs(slot_time - target) < abs(nearest - target):
            nearest = slot_time
    return [bucket for bucket, slot_time in rows if slot_time == nearest]


def event_finalized_at_sync(event_id: str) -> datetime | None:
    with SessionLocal() as session:
        return session.execute(
            select(PodDraftEvent.finalized_at).where(PodDraftEvent.id == event_id)
        ).scalar_one_or_none()


def _pod_slot_time(session: Session, event_id: str) -> datetime | None:
    """When the pod sat: the slot its card signal carries, else the event's own time. A postponed pod keeps
    the slot it was gathered in, which is what ties it to a launcher column."""
    slot_time = session.execute(
        select(PodSignal.slot_time).where(
            PodSignal.event_id == event_id, PodSignal.kind == pod_signals.KIND_SCHEDULED
        )
    ).scalar_one_or_none()
    if slot_time is not None:
        return slot_time
    event = session.get(PodDraftEvent, event_id)
    return event.event_time if event else None


def slot_fire_candidates_sync(message_id: str, signal_date: date) -> list[SignalState]:
    """The board's still-open slots already at or above the fire threshold — the overnight signups a rolled
    column collected, ready to graduate now that their day is the live one. Read at the morning post, since
    a slot on a later day holds instead of firing.

    Fullest pod first, ties to Format 1. Two full pods at one slot can rarely both seat a table, so the order
    decides which format runs: demand decides it, and a tie goes to the latest set instead of to whatever
    order the rows came back in."""
    threshold = settings.pod_signal_fire_threshold
    candidates: list[SignalState] = []
    with SessionLocal() as session:
        signals = session.execute(
            select(PodSignal).where(
                PodSignal.kind == pod_signals.KIND_POLL,
                PodSignal.message_id == message_id,
                PodSignal.signal_date == signal_date,
                PodSignal.status == pod_signals.STATUS_OPEN,
            )
        ).scalars().all()
        for signal in signals:
            count = len(_member_names(session, signal.id))
            if pod_signals.should_fire(count, threshold):
                candidates.append(_state(signal, count))
    return sorted(candidates, key=_fire_order)


def launcher_snapshot_sync(message_id: str, signal_date: date) -> list[LauncherSlot]:
    """The board's launcher slots lane by lane, each resolved to committed / lazy / expired.

    A lane stacks every pod already locked at its slot — a second table is its own slot — above the
    gathering slot the lane has rolled to, so a column can play today while the other gathers tomorrow.
    A slot whose scheduled card carries this exact slot time reflects it: count, thread, and real start
    time are read off the event (the card is the truth; a little render-time staleness is fine).
    Otherwise the slot is lazy — its own poll signal, or an empty open slot before signals exist.
    Committed wins outright, so a lazy slot that fires and posts its card renders as committed next pass."""
    with SessionLocal() as session:
        return _board_slots(session, _launcher_signals(session, message_id), signal_date)


def launcher_snapshot_for_message_sync(
    message_id: str, fallback_date: date,
) -> tuple[date, list[LauncherSlot]]:
    """The board's day and its slots together, for a click that needs both. The day is the minimum of the
    signal rows the snapshot already loads, so resolving it here costs nothing where `launcher_date_for_
    message_sync` costs a second connection checkout in front of the presser's answer. `fallback_date`
    stands in for a message with no signals on record."""
    with SessionLocal() as session:
        signals = _launcher_signals(session, message_id)
        days = [signal.signal_date for signal in signals]
        board_date = min(days) if days else fallback_date
        return board_date, _board_slots(session, signals, board_date)


def _launcher_signals(session: Session, message_id: str) -> list[PodSignal]:
    return list(session.execute(
        select(PodSignal).where(
            PodSignal.kind == pod_signals.KIND_POLL, PodSignal.message_id == message_id
        )
    ).scalars().all())


def _board_slots(session: Session, signals: list[PodSignal], signal_date: date) -> list[LauncherSlot]:
    now = datetime.now(timezone.utc)
    slots: list[LauncherSlot] = []
    for lane in pod_signals.LANE_ORDER:
        slots.extend(_lane_snapshot(session, signals, lane, signal_date, now))
    return slots


def _lane_snapshot(
    session: Session, signals: list[PodSignal], lane: str, board_date: date, now: datetime,
) -> list[LauncherSlot]:
    """One launcher column, earliest day first: the board's own day plus every later day this lane has
    rolled to, and within a day one entry per pod the slot carries.

    A lane reaches a later day through the signals it opened, so it also always walks tomorrow: a day whose
    slot the format schedule closes opens no signal, and that is exactly the day the Set Championship sits on.
    The loop appends nothing for a day carrying neither a pod nor a signal, so this costs an empty read on an
    ordinary day and shows a pod committed ahead of time on the eve, which is when players read the board.
    The board's own day carries an empty slot before its signals are bound, which is what the first render of
    a fresh post draws. A day the schedule offers no format on carries none: nothing is going to bind there,
    so the column would offer a pod that never opens."""
    lane_signals = [signal for signal in signals if pod_signals.lane_of(signal.bucket) == lane]
    rolled_days = {signal.signal_date for signal in lane_signals if signal.signal_date > board_date}
    lane_slots: list[LauncherSlot] = []
    for day in sorted({board_date, board_date + timedelta(days=LANE_LOOKAHEAD_DAYS)} | rolled_days):
        bucket = pod_signals.bucket_for_lane(day, lane)
        if bucket is None:
            continue
        slot_time = slot_event_time(day, bucket.key)
        day_signals = [signal for signal in lane_signals if signal.signal_date == day]
        pods = _slot_pods(session, bucket.key, slot_time, day_signals, now)
        lane_slots += pods
        if not pods and day == board_date and formats_on(day, lane):
            lane_slots.append(LauncherSlot(
                bucket.key, committed=False,
                status=_lazy_status(pod_signals.STATUS_OPEN, slot_time, now),
                count=0, slot_time=slot_time, names=[], thread_id=None, signal_id=None,
            ))
    return _without_rolled_past_slots(lane_slots)


def _slot_pods(
    session: Session, time_key: str, slot_time: datetime, day_signals: list[PodSignal], now: datetime,
) -> list[LauncherSlot]:
    """Every pod at one slot time in the day's format order: the pods that exist, then one entry per format
    still gathering. A pod that exists covers its own format only, so the signal it fired on and any other
    signal on that format drop out here while the rest of the slot keeps gathering, and a locked pod never
    hides the table beside it. The pods hold the day's format order whatever state each is in, so a format
    keeps its place in the column and on the button row from the moment it is offered to the moment it is
    played."""
    event_ids = _event_ids_for_slot(session, slot_time)
    committed = [_committed_slot(session, time_key, event_id) for event_id in event_ids]
    covered = {slot.set_code for slot in committed}
    gathering = [
        _gathering_slot(session, signal, now) for signal in day_signals
        if signal.event_id not in event_ids and _signal_format(signal) not in covered
    ]
    return sorted(committed + gathering, key=_format_order)


def _gathering_slot(session: Session, signal: PodSignal, now: datetime) -> LauncherSlot:
    rows = _member_rows(session, signal.id)
    return LauncherSlot(
        signal.bucket, committed=False, status=_gathering_status(signal, now),
        count=len(rows), slot_time=signal.slot_time, names=[name for _id, name in rows],
        thread_id=None, signal_id=signal.id, set_code=_signal_format(signal),
    )


def _gathering_status(signal: PodSignal, now: datetime) -> str:
    """A row still gathering that already fired has lost the pod it fired: the pod was canceled, or its
    format was switched and the row no longer matches it. A slot cannot fire twice, so the slot is closed
    whatever the cause, and the board stops offering the roster it fired on.

    Kept out of `_lazy_status` on purpose: `set_membership` shares that function, and a fired signal must
    keep accepting the over-signups that ride along into the lobby.
    """
    if signal.status == pod_signals.STATUS_FIRED:
        return pod_signals.STATUS_EXPIRED
    return _lazy_status(signal.status, signal.slot_time, now)


def _format_order(slot: LauncherSlot) -> tuple[int, str]:
    """A slot time renders its pods in one fixed order however their rows come back, and whatever state each
    is in: the latest set first, matching the numbering of the formats on offer, then the rest by code. A
    format keeps its place in the column and on the button row from the moment it is offered until it is
    played. The rows of one launcher post share a created_at, so creation order cannot be the tiebreak, and
    an order read off the schedule would shift the moment a signup updates a row."""
    return format_order_key(slot.set_code)


def format_order_key(set_code: str | None) -> tuple[int, str]:
    """The day's format order as a sort key: the latest set is Format 1, the rest follow by code."""
    code = set_code or ""
    return (0 if code == active_set_code() else 1, code)


def _signal_format(signal: PodSignal) -> str:
    """The format a poll signal opens on: off its key, then off its own column. A row carrying neither is a
    slot keyed before named formats shipped, when a slot was always the latest set, so reading it as that
    keeps a board posted by the old code rendering and joinable until the next morning post renames it."""
    return pod_signals.format_of(signal.bucket) or signal.set_code or active_set_code()


def _without_rolled_past_slots(lane_slots: list[LauncherSlot]) -> list[LauncherSlot]:
    """Drop a closed slot the lane has already rolled past: a slot whose time passed unfired belongs to
    nobody, so the column shows the day it rolled to instead of a dead one. Played pods always stay."""
    rolled_to = None
    for slot in lane_slots:
        if not slot.committed and slot.status != pod_signals.STATUS_EXPIRED and slot.slot_time is not None:
            rolled_to = slot.slot_time
    if rolled_to is None:
        return lane_slots
    kept: list[LauncherSlot] = []
    for slot in lane_slots:
        expired_and_passed = (
            not slot.committed
            and slot.status == pod_signals.STATUS_EXPIRED
            and slot.slot_time is not None
            and slot.slot_time < rolled_to
        )
        if not expired_and_passed:
            kept.append(slot)
    return kept


def _lazy_status(status: str, slot_time: datetime | None, now: datetime) -> str:
    """An open slot past its time is closed even if its expiry job never fired, so the render never
    offers a join the toggle would refuse."""
    if status == pod_signals.STATUS_OPEN and slot_time is not None and slot_time <= now:
        return pod_signals.STATUS_EXPIRED
    return status


def _committed_slot(session: Session, time_key: str, event_id: str) -> LauncherSlot:
    """The launcher entry for a pod that exists, keyed on the format it plays. A pod with no scheduled card
    of its own — an extra table spun off at draft start — counts as locked: it has no roster surface and
    nothing to RSVP to, so it belongs on one line from the moment it appears."""
    event = session.get(PodDraftEvent, event_id)
    set_code = event.set_code if event else None
    bucket_key = pod_signals.named_bucket_key(time_key, set_code) if set_code else time_key
    signal = session.execute(
        select(PodSignal).where(
            PodSignal.event_id == event_id, PodSignal.kind == pod_signals.KIND_SCHEDULED
        )
    ).scalar_one_or_none()
    yes_roster = _members_by_rsvp_with_interest(session, signal.id)[pod_signals.RSVP_YES] if signal else []
    yes_names = [name for name, _ in yes_roster]
    championship = is_championship(event.name if event else None)
    if championship and yes_names:
        frozen = frozen_seeds_by_player(session, event_id)
        yes_names = rank_ordered_names(session, yes_names, frozen)
    finished = event is not None and event.finalized_at is not None
    winner, winner_slug = _pod_winner(session, event) if finished else (None, None)
    return LauncherSlot(
        bucket_key, committed=True, status=pod_signals.STATUS_FIRED, count=len(yes_names),
        slot_time=event.event_time if event else None,
        names=yes_names, thread_id=event.discord_thread_id if event else None, signal_id=None,
        thread_message_id=signal.thread_message_id if signal else None,
        card_message_id=signal.message_id if signal else None,
        card_channel_id=signal.channel_id if signal else None,
        thread_name=event.name if event else None,
        set_code=set_code,
        championship=championship, finished=finished, winner=winner, winner_slug=winner_slug,
        created_at=event.created_at if event else None,
        locked=finished or signal is None or (event is not None and _draft_started(event)),
    )


def _draft_started(event: PodDraftEvent) -> bool:
    """Whether the first pack is already being passed, the point a pod stops taking signups. The live manager
    is the only place that knows it: `socket_status` goes to `connected` when the lobby opens, ten minutes
    before the draft, and covers both waiting and drafting. A pod with no manager left fell back on its
    status, which reaches `draft_done` once the draft is over."""
    manager = ACTIVE_POD_MANAGERS.get(event.id)
    if manager is not None:
        return bool(manager.drafting or manager.draft_complete)
    return event.socket_status == "draft_done"


def _pod_winner(session: Session, event: PodDraftEvent) -> tuple[str | None, str | None]:
    """Who a played pod is credited to on the launcher, and the seat on its website page to link: the
    champion and their player slug for a solo pod, the winning side's label with no seat for a team draft.
    (None, None) for a team draw or a pod whose placements never landed."""
    if event.pairing_mode == "team":
        return _winning_team_label(session, event.id), None
    row = session.execute(
        select(PodDraftParticipant.display_name, Player.display_name, Player.slug)
        .outerjoin(Player, Player.id == PodDraftParticipant.player_id)
        .where(PodDraftParticipant.event_id == event.id, PodDraftParticipant.placement == 1)
        .order_by(PodDraftParticipant.display_name)
        .limit(1)
    ).first()
    if row is None:
        return None, None
    participant_name, player_name, slug = row
    return strip_arena_suffix(player_name or participant_name), slug


def _winning_team_label(session: Session, event_id: str) -> str | None:
    """The team a finished team draft went to, by match wins; None on a draw."""
    teams = {}
    rows = session.execute(
        select(PodDraftParticipant.draftmancer_name, PodDraftParticipant.display_name, PodDraftParticipant.team)
        .where(PodDraftParticipant.event_id == event_id, PodDraftParticipant.team.is_not(None))
    ).all()
    for draftmancer_name, display_name, team in rows:
        name = draftmancer_name or display_name
        if name:
            teams[normalize_player_name(name)] = team
    winners = session.execute(
        select(PodDraftMatch.winner_name).where(
            PodDraftMatch.event_id == event_id, PodDraftMatch.winner_name.is_not(None)
        )
    ).scalars().all()
    a_wins, b_wins = pod_team.team_match_wins(
        [(normalize_player_name(name), "") for name in winners], teams,
    )
    side = pod_team.team_winner(a_wins, b_wins)
    return pod_team.team_label(side) if side else None


def card_rsvp_for_user_sync(card_message_id: str, discord_user_id: str) -> str | None:
    """The member's current RSVP on a scheduled card, None when they have not signed up — what the
    launcher's committed-slot button toggles against. The card is named by the slot the board is showing,
    so a rolled column never has to re-derive which day its pod sits on."""
    with SessionLocal() as session:
        signal = _scheduled_signal_by_surface(session, card_message_id)
        if signal is None:
            return None
        return session.execute(
            select(PodSignalMember.rsvp).where(
                PodSignalMember.signal_id == signal.id,
                PodSignalMember.discord_user_id == discord_user_id,
            )
        ).scalar_one_or_none()


def roster_for_event_sync(event_id: str) -> list[tuple[str, str]]:
    """(discord_user_id, display_name) of the Yes roster for the signal that created this pod, in
    join order. Poll and queue members are implicit Yes."""
    return _roster_for_event_sync(event_id, pod_signals.RSVP_YES)


def maybe_roster_for_event_sync(event_id: str) -> list[tuple[str, str]]:
    """(discord_user_id, display_name) of the Maybe roster for the signal that created this pod, in
    join order."""
    return _roster_for_event_sync(event_id, pod_signals.RSVP_MAYBE)


def _roster_for_event_sync(event_id: str, rsvp: str) -> list[tuple[str, str]]:
    with SessionLocal() as session:
        signal = session.execute(
            select(PodSignal).where(PodSignal.event_id == event_id)
        ).scalar_one_or_none()
        if signal is None:
            return []
        rows = session.execute(
            select(PodSignalMember.discord_user_id, PodSignalMember.display_name)
            .where(
                PodSignalMember.signal_id == signal.id,
                PodSignalMember.rsvp == rsvp,
            )
            .order_by(PodSignalMember.created_at)
        ).all()
        return [(did, name) for did, name in rows]


def rsvp_state_by_user_sync(event_id: str) -> dict[str, str]:
    """{discord_user_id: rsvp_state} for everyone who has answered this pod's signal, any state, so a
    caller can tell who already RSVP'd."""
    with SessionLocal() as session:
        signal = session.execute(
            select(PodSignal).where(PodSignal.event_id == event_id)
        ).scalar_one_or_none()
        if signal is None:
            return {}
        rows = session.execute(
            select(PodSignalMember.discord_user_id, PodSignalMember.rsvp)
            .where(PodSignalMember.signal_id == signal.id)
        ).all()
        return {discord_user_id: rsvp for discord_user_id, rsvp in rows}


def poll_yes_members_sync(signal_id: str) -> list[tuple[str, str]]:
    """(discord_user_id, display_name) of a poll slot's signups, in join order. Poll members are all
    implicit Yes, so this is the set to carry over when the slot graduates to an RSVP card."""
    with SessionLocal() as session:
        rows = session.execute(
            select(PodSignalMember.discord_user_id, PodSignalMember.display_name)
            .where(PodSignalMember.signal_id == signal_id)
            .order_by(PodSignalMember.created_at)
        ).all()
        return [(did, name) for did, name in rows]


def seed_members_sync(
    signal_id: str, members: list[tuple[str, str]], rsvp: str, confirmed: bool = False,
) -> None:
    """Insert a batch of members onto a fresh signal at one answer. Skips anyone already present so a retry
    is idempotent. `confirmed` stamps them confirmed, for a roster handed over having already confirmed"""
    confirmed_at = datetime.now(timezone.utc) if confirmed else None
    with SessionLocal() as session:
        present = set(session.execute(
            select(PodSignalMember.discord_user_id).where(PodSignalMember.signal_id == signal_id)
        ).scalars())
        for user_id, display_name in members:
            if user_id in present:
                continue
            session.add(PodSignalMember(
                signal_id=signal_id, discord_user_id=user_id, display_name=display_name,
                rsvp=rsvp, format_interest=get_format_interests(session, user_id),
                confirmed_at=confirmed_at,
            ))
        session.commit()


def yes_maybe_roster_sync(event_id: str) -> list[tuple[str, str]]:
    """(discord_user_id, display_name) of the Yes then Maybe roster for the scheduled card that created
    this pod, Yes first and each in join order. Empty for poll/queue pods and for tables, which carry no
    standing roster of their own."""
    with SessionLocal() as session:
        signal = session.execute(
            select(PodSignal).where(
                PodSignal.event_id == event_id, PodSignal.kind == pod_signals.KIND_SCHEDULED
            )
        ).scalar_one_or_none()
        if signal is None:
            return []
        rows = session.execute(
            select(PodSignalMember.discord_user_id, PodSignalMember.display_name, PodSignalMember.rsvp)
            .where(
                PodSignalMember.signal_id == signal.id,
                PodSignalMember.rsvp.in_([pod_signals.RSVP_YES, pod_signals.RSVP_MAYBE]),
            )
            .order_by(PodSignalMember.created_at)
        ).all()
    rank = {pod_signals.RSVP_YES: 0, pod_signals.RSVP_MAYBE: 1}
    ordered = sorted(rows, key=lambda row: rank.get(row[2], 2))
    return [(did, name) for did, name, _ in ordered]


def scheduled_card_ref_sync(event_id: str) -> tuple[str, str, str, datetime | None] | None:
    """(signal_id, channel_id, message_id, slot_time) of the scheduled card that created this pod.
    slot_time keeps the original slot through postpones, so slot-keyed rendering stays stable."""
    with SessionLocal() as session:
        row = session.execute(
            select(PodSignal.id, PodSignal.channel_id, PodSignal.message_id, PodSignal.slot_time).where(
                PodSignal.event_id == event_id, PodSignal.kind == pod_signals.KIND_SCHEDULED
            )
        ).first()
    return (row[0], row[1], row[2], row[3]) if row else None


def move_scheduled_card_sync(event_id: str, message_id: str, thread_id: str) -> None:
    """Point a pod at a new card and a new thread. The signal's message id is what an RSVP press
    resolves through, so this is what makes the new card the live one.

    The thread being left behind is kept on the signal, which is the only row that still knows it once the
    pointer moves. Nothing named it before, so a split pod's signup thread outlived the nightly cleanup
    that archives every other pod thread."""
    with SessionLocal() as session:
        event = session.get(PodDraftEvent, event_id)
        signal = session.execute(
            select(PodSignal).where(
                PodSignal.event_id == event_id, PodSignal.kind == pod_signals.KIND_SCHEDULED,
            )
        ).scalar_one_or_none()
        if signal is not None:
            signal.message_id = message_id
            signal.thread_message_id = None
            if event is not None and event.discord_thread_id:
                signal.discussion_thread_id = event.discord_thread_id
        if event is not None:
            event.discord_thread_id = thread_id
        session.commit()


def scheduled_card_opener_sync(event_id: str) -> str | None:
    """The discord user id of whoever scheduled this pod with /draft, so a full card re-render keeps
    crediting them. None for every pod the launcher or a job created."""
    with SessionLocal() as session:
        row = session.execute(
            select(PodSignal.opened_by).where(
                PodSignal.event_id == event_id, PodSignal.kind == pod_signals.KIND_SCHEDULED
            )
        ).first()
    return row[0] if row else None


def pod_card_ref_sync(event_id: str) -> tuple[str, str, datetime | None] | None:
    """(channel_id, message_id, slot_time) of the card this pod renders on: the scheduled signal's, else
    the one a queue or table pod posted for itself. Only a signal carries a slot_time."""
    signal_card = scheduled_card_ref_sync(event_id)
    if signal_card is not None:
        _, channel_id, message_id, slot_time = signal_card
        return channel_id, message_id, slot_time
    own_card = own_card_ref_sync(event_id)
    return (*own_card, None) if own_card else None


def own_card_ref_sync(event_id: str) -> tuple[str, str] | None:
    """A mock holds its reposted card in the same columns and renders it itself, so it never resolves
    here — a pod card rendered over one would replace the mock card with an RSVP card."""
    with SessionLocal() as session:
        row = session.execute(
            select(PodDraftEvent.card_channel_id, PodDraftEvent.card_message_id)
            .where(PodDraftEvent.id == event_id, PodDraftEvent.kind != "mock")
        ).first()
    if row is None or not row[0] or not row[1]:
        return None
    return row[0], row[1]


def record_pod_card_sync(event_id: str, channel_id: str, message_id: str) -> None:
    with SessionLocal() as session:
        session.execute(
            update(PodDraftEvent).where(PodDraftEvent.id == event_id)
            .values(card_channel_id=channel_id, card_message_id=message_id)
        )
        session.commit()


def set_thread_message_sync(signal_id: str, thread_message_id: str) -> None:
    with SessionLocal() as session:
        session.execute(
            update(PodSignal).where(PodSignal.id == signal_id).values(thread_message_id=thread_message_id)
        )
        session.commit()


def rsvp_rosters_with_interest_sync(
    message_id: str,
) -> dict[str, list[tuple[str, tuple[str, ...]]]] | None:
    """Each member's (display name, format-interest codes) per RSVP state for a scheduled card or its
    mirror, so the card render can group the roster by format. None when no surface matches."""
    with SessionLocal() as session:
        signal = _scheduled_signal_by_surface(session, message_id)
        if signal is None:
            return None
        return _members_by_rsvp_with_interest(session, signal.id)


def scheduled_event_for_message_sync(message_id: str) -> str | None:
    """The pod event behind an RSVP surface, from the card's or the mirror's message id."""
    with SessionLocal() as session:
        signal = _scheduled_signal_by_surface(session, message_id)
        return signal.event_id if signal else None


def ondemand_event_name_sync(set_code: str, event_time: datetime) -> str:
    """The `SET Mon Day Slot Pod` name, fixed at creation and never renumbered. The website's `#N`
    milestone is a separate execution-ordered projection in `public_pod_draft_events`, not baked in
    here, so a scheduled card posted days ahead can never carry an out-of-order number."""
    return pod_display_name(set_code, event_time)


def dedupe_thread_name(channel: discord.TextChannel, base_name: str) -> str:
    """`base_name`, or `base_name #N` when a live thread of the same name already exists in `channel`.

    Reads the guild's cached active threads only — no API call — and reuses the collision-index scheme
    behind ` - Table N`, so back-to-back queues for one slot stay distinguishable without ever
    renumbering past a finished, archived thread. Used for queue discussion threads, which carry no
    pod_draft_events row; pod events dedupe against the DB via `dedupe_pod_name`.
    """
    live = [
        thread.name for thread in channel.threads
        if not thread.archived and (thread.name == base_name or thread.name.startswith(f"{base_name} #"))
    ]
    if base_name not in live:
        return base_name
    return f"{base_name} #{next_collision_index(live, COLLISION_INDEX_RE)}"


def dedupe_pod_name_sync(base_name: str, live_names: list[str] | None = None, session: Session | None = None) -> str:
    """`base_name`, or `base_name #N` when a pod of that name already exists.

    Keys off persisted pod_draft_events names so a same-slot pod launched after the previous one's
    thread has archived still numbers correctly — the DB remembers finished pods that a live-thread
    scan cannot see. `live_names` folds in threads created this instant whose event row has not yet
    committed, covering pods that launch concurrently.
    """
    if session is None:
        with SessionLocal() as owned:
            return dedupe_pod_name_sync(base_name, live_names, session=owned)
    persisted = session.execute(
        select(PodDraftEvent.name).where(
            or_(PodDraftEvent.name == base_name, PodDraftEvent.name.like(f"{base_name} #%"))
        )
    ).scalars().all()
    taken = set(persisted)
    for name in live_names or []:
        if name == base_name or name.startswith(f"{base_name} #"):
            taken.add(name)
    if base_name not in taken:
        return base_name
    return f"{base_name} #{next_collision_index(taken, COLLISION_INDEX_RE)}"


async def dedupe_pod_name(channel: discord.TextChannel, base_name: str) -> str:
    live_names = [thread.name for thread in channel.threads if not thread.archived]
    return await asyncio.to_thread(dedupe_pod_name_sync, base_name, live_names)


async def launch_from_signal(
    bot: commands.Bot, signal_id: str, *, set_code: str, event_time: datetime,
    name: str, open_now: bool,
) -> str | None:
    """Create the thread + PodDraftEvent for a claimed signal, then open (or arm) the lobby. Returns
    the event id, or None if the coordination channel is unreachable. Participants are not pre-seeded:
    the live Draftmancer session is authoritative, matching record_mock_event.

    An open-now pod anchors its thread on a pod card of its own, so the pod still leaves standings in the
    channel. A scheduled pod anchors its thread on the message carrying the start time.

    The pairing and seating the opener picked in the launcher are written at insert, so the pod is born
    with them and every surface reads them on its first render with nothing to correct afterwards."""
    channel = await _fetch_text_channel(bot, settings.pod_draft_channel_id)
    if channel is None:
        log.error(f"launch_from_signal: coordination channel {settings.pod_draft_channel_id} unreachable")
        return None

    name = await dedupe_pod_name(channel, name)
    roster = await asyncio.to_thread(queue_member_names_sync, signal_id)
    try:
        if open_now:
            anchor = await pod_active.post_pod_card(
                channel, name=name, event_time=event_time, set_code=set_code, roster=roster,
            )
        else:
            unix = int(event_time.timestamp())
            anchor = await channel.send(f"🚀 **{name}** is set for <t:{unix}:F> (<t:{unix}:R>)")
        if anchor is None:
            thread = await channel.create_thread(name=name[:100], type=discord.ChannelType.public_thread)
        else:
            thread = await anchor.create_thread(name=name[:100])
    except discord.HTTPException:
        log.warning("launch_from_signal: could not create pod thread", exc_info=True)
        return None

    def _create() -> tuple[str, bool]:
        with SessionLocal() as session:
            event = record_ondemand_event(
                session, set_code=set_code, event_time=event_time, name=name,
                discord_thread_id=str(thread.id),
            )
            signal = session.get(PodSignal, signal_id)
            chose_pairing = signal is not None and bool(signal.pairing_mode)
            if signal is not None:
                event.description = signal.description
                if signal.pairing_mode:
                    event.pairing_mode = signal.pairing_mode
                if signal.seating_mode:
                    event.seating_mode = signal.seating_mode
            session.commit()
            return event.id, chose_pairing

    event_id, chose_pairing = await asyncio.to_thread(_create)
    await asyncio.to_thread(link_event_sync, signal_id, event_id)
    if open_now and anchor is not None:
        await asyncio.to_thread(record_pod_card_sync, event_id, str(channel.id), str(anchor.id))

    if open_now:
        await open_ondemand_lobby(bot, event_id, pairing_chosen=chose_pairing)
    else:
        _arm_open(bot, event_id, event_time)
    return event_id


async def open_ondemand_lobby(
    bot: commands.Bot, event_id: str, allow_hold: bool = True, *, pairing_chosen: bool = False,
) -> None:
    """Seat the bot in the Draftmancer session, then post the link and ping the roster. Draftmancer makes
    whoever enters an empty session first its owner, so the bot has to be holding ownership before any
    player can see the link. A session it could not own is abandoned for a fresh one, which makes the
    announced link always a session the bot controls.

    A pod expecting more players than one session seats holds instead, since opening a room is what
    commits the pod to a shape and nobody yet knows which shape the answers make. `allow_hold` is False
    on the release at the other end of that hold, which is this same path with the question settled.

    A table a split staged never holds, whatever it is carrying. The hold is the step that made it, so
    asking its players to confirm again re-opens a question they already answered, and a table wanting to
    split a second time five minutes out is `/pod-table` by hand.

    A table a split staged DMs the link to the players holding a seat on it, so nobody who left the
    confirmation unanswered is handed it ahead of the roster the table planned for. Its riders keep the
    link in the thread and are asked in by the rider window.

    Every other pod DMs its whole Yes roster, confirmed or not. One table short of firing needs every body
    it can reach, and there is no second table for a late arrival to take a seat away from."""
    with SessionLocal() as session:
        event = session.get(PodDraftEvent, event_id)
        if event is None:
            log.warning(f"open_ondemand_lobby: event {event_id} not found")
            return
        if event.socket_status not in ("pending", "reminded"):
            log.info(f"open_ondemand_lobby: event {event_id} is {event.socket_status}; skipping")
            return
        thread_id = int(event.discord_thread_id)
        session_id = event.draftmancer_session
        set_code = event.set_code
        event_name = event.name
        event_time = event.event_time

    roster = await asyncio.to_thread(roster_for_event_sync, event_id)
    single_table = await asyncio.to_thread(championship_seeds.rank_override_sync, event_id) is not None
    split = pod_is_numbered(event_name)
    if allow_hold and not single_table and not split and await _hold_for_attendance(
        bot, event_id, event_time, thread_id, roster,
    ):
        return
    if single_table:
        roster = await asyncio.to_thread(championship_seeds.playing_roster_sync, event_id, roster)
    rsvps = await asyncio.to_thread(signal_rsvps_sync, event_id)
    maybe_names = [] if single_table else (rsvps[1] if rsvps else [])
    maybe_roster = [] if single_table else await asyncio.to_thread(maybe_roster_for_event_sync, event_id)
    seated, unconfirmed = await _seated_and_unconfirmed(event_id, roster, single_table)
    display_names = [name for _, name in seated]
    unconfirmed_names = [name for _, name in unconfirmed]
    riders = unconfirmed + maybe_roster if split else []
    draftmancer_url = draftmancer_url_for(session_id)

    thread = await fetch_pod_thread(bot, thread_id)
    if thread is None:
        log.warning(f"open_ondemand_lobby: thread {thread_id} unreachable")
        return

    expected = len(display_names) + len(riders)
    seatable = len(seated) + len(unconfirmed) + len(maybe_roster)
    await asyncio.to_thread(pod_event_settings.size_room_sync, event_id, seatable)
    manager = await start_manager(
        bot, event_id, session_id, thread_id, set_code, expected,
        event_name=event_name, draftmancer_url=draftmancer_url,
        rsvps_yes=display_names, rsvps_unconfirmed=unconfirmed_names, rsvps_maybe=maybe_names,
        pairing_chosen=pairing_chosen,
    )
    if manager is not None and not await manager.await_ownership():
        manager, session_id = await _reseat_on_fresh_session(
            bot, event_id, manager, thread_id=thread_id, set_code=set_code, event_name=event_name,
            expected=expected, display_names=display_names, maybe_names=maybe_names,
            unconfirmed_names=unconfirmed_names,
        )
        draftmancer_url = draftmancer_url_for(session_id)

    mentions = _mentions(roster)
    if single_table:
        body = championship_copy.lobby_open_body(
            set_code=set_code, draftmancer_url=draftmancer_url, seat_mentions=mentions,
        )
    elif split:
        body = build_lobby_open_split_body(draftmancer_url, pod_index(event_name), _mentions(seated))
    else:
        body = build_lobby_open_body(draftmancer_url, " ".join(mentions))
    try:
        await thread.send(
            body, view=build_join_view(session_id),
            allowed_mentions=discord.AllowedMentions(users=True),
        )
    except discord.HTTPException:
        log.warning(f"open_ondemand_lobby: could not post in thread {thread_id}", exc_info=True)

    with SessionLocal() as session:
        event = session.get(PodDraftEvent, event_id)
        if event is not None and event.socket_status == "pending":
            event.socket_status = "reminded"
            session.commit()

    recipients = [(did, name, "yes") for did, name in (seated if split else roster)]
    if not single_table and not split:
        recipients += [(did, name, "maybe") for did, name in maybe_roster]
    await send_lobby_link_dms(
        bot, session_id=session_id, thread=thread, recipients=recipients,
    )

    if manager is not None:
        manager.open_rider_window(len(seated), _mentions(riders))
        await _apply_scheduled_pick_timer(event_id, manager)


async def _seated_and_unconfirmed(
    event_id: str, roster: list[tuple[str, str]], single_table: bool,
) -> tuple[list[tuple[str, str]], list[tuple[str, str]]]:
    """The players this table holds a seat for, and the ones who said Yes and never confirmed.

    The lobby waits on the first list and only names the second, since a seat held open for somebody who
    did not answer is the shape of every table that drafted one player short.

    A pod where nobody confirmed was never asked: the whole Yes roster is seated, and the answer degrades
    to the roster the lobby has always waited on."""
    if single_table:
        return roster, []
    signups = await asyncio.to_thread(confirmed_first_roster_sync, event_id)
    seated = [(signup.discord_id, signup.display_name) for signup in signups if signup.confirmed]
    if not seated:
        return roster, []
    unconfirmed = [
        (signup.discord_id, signup.display_name) for signup in signups if not signup.confirmed
    ]
    return seated, unconfirmed


def _mentions(roster: list[tuple[str, str]]) -> list[str]:
    """Mentions for real players, bold names for the fixture ids a `!test` pod seats, so a preview reads
    as the roster it built instead of dropping it or rendering a dead mention"""
    return [
        f"<@{discord_id}>" if discord_id.isdigit() else f"**{name}**"
        for discord_id, name in roster
    ]


async def _hold_for_attendance(
    bot: commands.Bot, event_id: str, event_time: datetime, thread_id: int,
    roster: list[tuple[str, str]],
) -> bool:
    """Hold a pod that expects more players than one Draftmancer session seats, and say whether it held.

    Ten seats is the whole session, so at ten or fewer opening the room is itself the attendance check:
    everyone who arrives has a seat and nothing needs deciding. Above ten the pod has to be split, and
    which split is right depends on answers it does not have yet. Opening a room first would commit it to
    a shape while the answers that pick the shape are still outstanding, which is how a pod ends up
    running eight while four more wanted in.

    So the last ten minutes go on collecting those answers. The thread keeps the one roster card it
    already has, moved to the bottom and carrying the ask, and the rooms open at the start time against
    what the pod knows by then. Everyone signed up is mentioned, including Maybe, because a Maybe who
    confirms is a player the plan seats."""
    attendance = await asyncio.to_thread(attendance_for_event_sync, event_id)
    if attendance.expected <= SESSION_SEATS:
        return False
    if _holding.get(event_id):
        log.info(f"attendance hold on {event_id}: already holding; not asking twice")
        return True
    _holding[event_id] = True
    maybe_roster = await asyncio.to_thread(maybe_roster_for_event_sync, event_id)
    thread = await fetch_pod_thread(bot, thread_id)
    if thread is not None:
        with contextlib.suppress(discord.HTTPException):
            await thread.send(
                build_attendance_hold_body(
                    attendance.signed_up,
                    [f"<@{discord_id}>" for discord_id, _name in roster],
                    [f"<@{discord_id}>" for discord_id, _name in maybe_roster],
                ),
                allowed_mentions=discord.AllowedMentions(users=True),
            )
    await repost_roster_reminder(event_id)
    _arm_release(bot, event_id, event_time)
    log.info(
        f"attendance hold on {event_id}: {attendance.expected} expected over {SESSION_SEATS} seats, "
        f"releasing at {event_time.isoformat()}"
    )
    return True


def _arm_release(bot: commands.Bot, event_id: str, event_time: datetime) -> None:
    scheduler = getattr(bot, "pod_scheduler", None)
    if scheduler is None:
        log.error(f"_arm_release: pod_scheduler missing; release for {event_id} lost")
        return
    now = datetime.now(timezone.utc)
    run_at = event_time if event_time > now else now + timedelta(seconds=2)
    scheduler.add_job(
        release_attendance_hold, "date", run_date=run_at, args=[bot, event_id],
        id=release_job_id(event_id), replace_existing=True,
    )
    log.info(f"armed attendance-hold release for {event_id} at {run_at.isoformat()}")


async def release_attendance_hold(bot: commands.Bot, event_id: str) -> None:
    """End the hold at the pod's start time and open the rooms the answers ask for.

    Staging runs first and to completion, so the room opened here is opened for this table's players
    rather than for everyone who signed up. The card is repainted before any of it, while the pod is
    still pending and will still take an edit, which is what greys out the organizer controls."""
    _holding[event_id] = False
    await refresh_roster_reminder_for_event(event_id)
    if _stage_pods_hook is not None:
        await _stage_pods_hook(bot, event_id)
    await open_ondemand_lobby(bot, event_id, allow_hold=False)


def is_holding(event_id: str) -> bool:
    """Whether this pod is still waiting out its attendance hold."""
    return _holding.get(event_id, False)


def forget_hold(event_id: str) -> None:
    """Drop what this process remembers about a pod's hold, for a sandbox starting the sequence over."""
    _holding.pop(event_id, None)


def has_held(event_id: str) -> bool:
    """Whether this pod ever held, which is what says its card should carry the organizer controls at
    all. Whether they are live is `is_holding`."""
    return event_id in _holding


def cancel_release(bot: commands.Bot, event_id: str) -> None:
    """Stand the scheduled release down, for a hold ended by hand before its start time."""
    scheduler = getattr(bot, "pod_scheduler", None)
    if scheduler is None:
        return
    with contextlib.suppress(Exception):
        scheduler.remove_job(release_job_id(event_id))


def register_stage_pods(hook: StagePodsHook) -> None:
    """The staging layer registers itself here so the hold can release into it without importing the
    command module, which imports this one back. Same reason as `set_second_table_hook`."""
    global _stage_pods_hook
    _stage_pods_hook = hook


async def _apply_scheduled_pick_timer(event_id: str, manager: PodDraftManager) -> None:
    """Push the timer the launcher card was created with, unless someone has since set one in Settings.
    The pod's own value is the later, more specific choice, and the manager already carries it."""
    stored = await asyncio.to_thread(pod_event_settings.stored_sync, event_id)
    if pod_event_settings.PICK_TIMER in stored:
        return
    pick_timer = await asyncio.to_thread(scheduled_pick_timer_for_event_sync, event_id)
    if pick_timer is not None:
        await manager.apply_pick_timer(pick_timer)


async def _reseat_on_fresh_session(
    bot: commands.Bot, event_id: str, stale: PodDraftManager, *,
    thread_id: int, set_code: str, event_name: str, expected: int,
    display_names: list[str], maybe_names: list[str], unconfirmed_names: list[str],
) -> tuple[PodDraftManager | None, str]:
    """Abandon a Draftmancer session the bot could not own and reopen the pod on a fresh one. The session
    id exists for the ~hour between the card posting and the lobby opening, so anyone holding it can be
    sitting in the session first, and Draftmancer never hands ownership to a later arrival. Announcing a
    different session is the only way to guarantee the bot controls the one players get.

    Returns the live manager (None when the fresh session also failed) and the session id to announce.
    """
    await stale.abandon_session()
    session_id = await asyncio.to_thread(_mint_fresh_session_sync, event_id)
    if session_id is None:
        return None, stale.session_id
    log.warning(f"open_ondemand_lobby: {event_id} lost ownership; reseating on fresh session {session_id}")
    manager = await start_manager(
        bot, event_id, session_id, thread_id, set_code, expected,
        event_name=event_name, draftmancer_url=draftmancer_url_for(session_id),
        rsvps_yes=display_names, rsvps_unconfirmed=unconfirmed_names, rsvps_maybe=maybe_names,
    )
    if manager is not None:
        await manager.await_ownership()
    return manager, session_id


def _mint_fresh_session_sync(event_id: str) -> str | None:
    with SessionLocal() as session:
        event = session.get(PodDraftEvent, event_id)
        if event is None:
            return None
        session_id = build_ondemand_session(session, pod_event_date(event.event_time))
        event.draftmancer_session = session_id
        session.commit()
        return session_id


def arm_scheduled_pod_jobs(
    bot: commands.Bot, event_id: str, event_time: datetime, created_at: datetime,
) -> None:
    """Every timed job a scheduled card carries: T-10 lobby open, underfill checks, and the roster
    reminder. Creation, /pod-postpone, and the startup sweep all arm here."""
    _arm_open(bot, event_id, event_time)
    schedule_underfill_checks(bot.pod_scheduler, event_id, event_time, created_at)
    schedule_roster_reminder(bot.pod_scheduler, event_id, event_time)


def _arm_open(bot: commands.Bot, event_id: str, event_time: datetime) -> None:
    scheduler = getattr(bot, "pod_scheduler", None)
    if scheduler is None:
        log.error(f"_arm_open: pod_scheduler missing; open for {event_id} lost")
        return
    now = datetime.now(timezone.utc)
    run_at = event_time - timedelta(minutes=REMINDER_LEAD_MIN)
    if run_at < now:
        run_at = now + timedelta(seconds=2)
    scheduler.add_job(
        open_ondemand_lobby, "date", run_date=run_at, args=[bot, event_id],
        id=open_job_id(event_id), replace_existing=True,
    )
    log.info(f"armed on-demand lobby open for {event_id} at {run_at.isoformat()}")


def open_job_id(event_id: str) -> str:
    return f"pod-ondemand-open-{event_id}"


def release_job_id(event_id: str) -> str:
    return f"pod-hold-release-{event_id}"


def arm_slot_expiry(bot: commands.Bot, signal_id: str, slot_time: datetime) -> None:
    scheduler = getattr(bot, "pod_scheduler", None)
    if scheduler is None:
        return
    scheduler.add_job(
        fire_slot_expiry, "date", run_date=slot_time, args=[signal_id],
        id=f"pod-slot-expiry-{signal_id}", replace_existing=True,
    )


async def fire_slot_expiry(signal_id: str) -> None:
    """At slot time, close an unfired poll slot, drop its standing nudge, and roll the column to the next
    day — the recruiting window is over, and a slot nobody can join is not worth a column. The slot's
    button stays but set_membership_sync now refuses it, so a late click gets a graceful ephemeral and
    never joins a dead slot."""
    if await asyncio.to_thread(expire_signal_sync, signal_id):
        log.info(f"poll slot {signal_id} expired unfired")
        if _bot is not None:
            await clear_slot_nudge(_bot, signal_id)
            await notify_slot_rolled(_bot, signal_id)


def past_pod_cards_sync(now: datetime, since: datetime) -> list[tuple[str, str, str | None, str | None]]:
    """(card channel_id, card message_id, thread_id, thread-controls message_id) for scheduled pods
    whose real start is in (since, now] — the ones that have run since the last launcher. Keyed on the
    event's current start, so a pod rescheduled back into the future is skipped."""
    with SessionLocal() as session:
        rows = session.execute(
            select(PodSignal, PodDraftEvent)
            .join(PodDraftEvent, PodDraftEvent.id == PodSignal.event_id)
            .where(
                PodSignal.kind == pod_signals.KIND_SCHEDULED,
                PodDraftEvent.event_time > since,
                PodDraftEvent.event_time <= now,
            )
        ).all()
    return [(s.channel_id, s.message_id, e.discord_thread_id, s.thread_message_id) for s, e in rows]


def event_card_surfaces_sync(event_id: str) -> tuple[str, str, str | None, str | None] | None:
    """(card channel_id, card message_id, thread_id, thread-controls message_id) for one pod, or None
    when it has no card at all. A pod on its own card has no thread controls: nothing there takes
    signups."""
    with SessionLocal() as session:
        row = session.execute(
            select(
                PodSignal.channel_id, PodSignal.message_id, PodSignal.thread_message_id,
                PodDraftEvent.discord_thread_id,
            )
            .join(PodDraftEvent, PodDraftEvent.id == PodSignal.event_id)
            .where(PodSignal.event_id == event_id, PodSignal.kind == pod_signals.KIND_SCHEDULED)
        ).first()
    if row is not None:
        channel_id, message_id, thread_message_id, thread_id = row
        return channel_id, message_id, thread_id, thread_message_id
    own_card = own_card_ref_sync(event_id)
    if own_card is None:
        return None
    channel_id, message_id = own_card
    return channel_id, message_id, None, None


async def close_event_card(bot: commands.Bot, event_id: str) -> None:
    """Stand a pod's surfaces down the moment its draft finishes: the RSVP buttons on its card, and the
    thread a split gathered in once every table that split made is drafting too.

    The card stays live through lobby fill and the ready check — including a restart that reopens the
    lobby — and closes only at draft_done, the first state a restart can no longer revert. No-op for pods
    without a card."""
    await archive_signup_thread_if_drafted(bot, event_id)
    surfaces = await asyncio.to_thread(event_card_surfaces_sync, event_id)
    if surfaces is None or _bot is None:
        return
    channel_id, message_id, thread_id, thread_message_id = surfaces
    await _retire_message(int(channel_id), int(message_id))
    if thread_id and thread_message_id:
        await _retire_registered_message(int(thread_id), int(thread_message_id))


async def archive_signup_thread_if_drafted(bot: commands.Bot, event_id: str) -> None:
    """Archive the thread a split gathered in, once every table it made has finished drafting.

    All that thread holds by then is the map of the tables and everyone who ever signed up, and every
    table has moved out of it, so it is a room with nothing left to say sitting in everybody's sidebar.
    Archiving is reversible and a reply reopens it, which is what the nightly cleanup already relies on."""
    thread_id = await asyncio.to_thread(signup_thread_once_family_drafted_sync, event_id)
    if thread_id is None:
        return
    thread = await fetch_pod_thread(bot, int(thread_id))
    if thread is None or thread.archived:
        return
    try:
        await thread.edit(archived=True, reason="Every table finished drafting")
    except discord.HTTPException:
        log.warning(f"could not archive signup thread {thread_id} off {event_id}", exc_info=True)
        return
    log.info(f"archived signup thread {thread_id}: every table off {event_id} finished drafting")


CARD_CANCELED_MARKER = "🗑️ **Draft canceled**"


async def retire_canceled_pod(event_id: str) -> None:
    """Stand every surface of a canceled pod down: grey its card and stamp it canceled, drop the buttons on
    the thread mirror, close the native scheduled event it put on the server calendar, then roll the launcher
    column it sat in so the board offers the next day instead of a dead slot. Fired from `cancel_pod_event`
    before the event row is deleted, so each surface still resolves; the card and calendar steps are a no-op
    for pods without them. The slot row itself needs no write — a fired row with no pod covering it already
    renders closed."""
    if _bot is None:
        return
    await clear_underfill_nudge(_bot, event_id)
    surfaces = await asyncio.to_thread(event_card_surfaces_sync, event_id)
    if surfaces is not None:
        channel_id, message_id, thread_id, thread_message_id = surfaces
        await _mark_card_canceled(int(channel_id), int(message_id))
        if thread_id and thread_message_id:
            await _retire_registered_message(int(thread_id), int(thread_message_id))
    await close_native_event(event_id)
    signal_id = await asyncio.to_thread(fired_slot_for_pod_sync, event_id)
    if signal_id is not None:
        await notify_slot_rolled(_bot, signal_id)


async def close_native_event(event_id: str) -> None:
    """Take a canceled pod's native event off the calendar: canceled while upcoming, ended once live"""
    if _bot is None:
        return
    ref = await asyncio.to_thread(native_event_ref_sync, event_id)
    if ref is None:
        return
    native_event_id, thread_id = ref
    thread = await _resolve_channel(int(thread_id))
    guild = getattr(thread, "guild", None)
    if guild is None:
        return
    try:
        native = await guild.fetch_scheduled_event(int(native_event_id))
        if native.status is discord.EventStatus.scheduled:
            await native.cancel()
        elif native.status is discord.EventStatus.active:
            await native.end()
    except discord.NotFound:
        return
    except discord.HTTPException:
        log.warning(f"could not close native event {native_event_id} for pod {event_id}", exc_info=True)


def native_event_ref_sync(event_id: str) -> tuple[str, str] | None:
    """(native scheduled event id, thread id) for one pod, or None when it has no native event"""
    with SessionLocal() as session:
        row = session.execute(
            select(PodDraftEvent.discord_scheduled_event_id, PodDraftEvent.discord_thread_id)
            .where(PodDraftEvent.id == event_id)
        ).first()
    if row is None or not row[0] or not row[1] or row[1] == "pending":
        return None
    return row[0], row[1]


async def _mark_card_canceled(channel_id: int, message_id: int) -> None:
    """A canceled card keeps only its name and the canceled stamp: the RSVP columns and the start time
    are what someone reads to decide whether to join, and there is nothing left to join."""
    channel = await _resolve_channel(channel_id)
    if channel is None:
        return
    try:
        message = await channel.fetch_message(message_id)
    except discord.HTTPException:
        log.warning(f"could not fetch card {message_id} to cancel", exc_info=True)
        return
    embed = message.embeds[0] if message.embeds else None
    if embed is not None:
        title_line = (embed.description or "").split("\n", 1)[0]
        embed.color = discord.Color.dark_grey()
        embed.description = f"{title_line}\n{CARD_CANCELED_MARKER}"
        embed.clear_fields()
    try:
        await message.edit(content=None, embed=embed, view=None)
    except discord.HTTPException:
        log.warning(f"could not mark card {message_id} canceled", exc_info=True)


async def close_past_pod_cards() -> None:
    """Backstop for the per-draft close: sweep RSVP buttons off cards for pods that ran but never hit
    draft_done — cancelled or no-show pods whose `close_event_card` never fired — so no card outlives
    its pod indefinitely. Runs from the daily launcher post over pods started in the last window."""
    if _bot is None:
        return
    now = datetime.now(timezone.utc)
    since = now - timedelta(hours=CARD_CLOSE_WINDOW_H)
    cards = await asyncio.to_thread(past_pod_cards_sync, now, since)
    for channel_id, message_id, thread_id, thread_message_id in cards:
        await _retire_message(int(channel_id), int(message_id))
        if thread_id and thread_message_id:
            await _retire_registered_message(int(thread_id), int(thread_message_id))


async def _resolve_channel(channel_id: int) -> "discord.abc.Messageable | None":
    channel = _bot.get_channel(channel_id)
    if channel is None:
        try:
            channel = await _bot.fetch_channel(channel_id)
        except discord.HTTPException:
            return None
    return channel


async def _retire_registered_message(channel_id: int, message_id: int) -> None:
    """Retire the thread's registration embed: drop its controls and re-render it for a pod that no
    longer takes signups, so the card stops pointing at a Draftmancer link and a sign-up row that are
    both gone."""
    channel = await _resolve_channel(channel_id)
    if channel is None:
        return
    try:
        message = await channel.fetch_message(message_id)
        if message.embeds:
            await message.edit(content=None, embed=closed_registered_embed(message.embeds[0]), view=None)
        else:
            await message.edit(content=None, view=None)
    except discord.HTTPException:
        log.warning(f"could not retire registered message {message_id}", exc_info=True)


async def _retire_message(channel_id: int, message_id: int) -> None:
    """Drop a retired pod message's buttons and clear its content ping, so a finished card carries no
    live controls and no lingering role-mention highlight. The thread mirror has no content, so clearing
    it there is a no-op."""
    channel = await _resolve_channel(channel_id)
    if channel is None:
        return
    try:
        message = await channel.fetch_message(message_id)
        await message.edit(content=None, view=None)
    except discord.HTTPException:
        log.warning(f"could not retire message {message_id}", exc_info=True)


def arm_queue_teardown(bot: commands.Bot, signal_id: str, teardown_time: datetime) -> None:
    scheduler = getattr(bot, "pod_scheduler", None)
    if scheduler is None:
        return
    scheduler.add_job(
        fire_queue_teardown, "date", run_date=teardown_time, args=[signal_id],
        id=f"pod-queue-teardown-{signal_id}", replace_existing=True,
    )


async def fire_queue_teardown(signal_id: str) -> None:
    """Close an idle queue: swap the card for its closed state, which carries no buttons."""
    from bot.commands.pod_queue import PodQueueView, queue_inactivity_close_reason, queue_role_mention

    if not await asyncio.to_thread(expire_signal_sync, signal_id):
        return
    ref = await asyncio.to_thread(signal_message_ref_sync, signal_id)
    if ref is None or _bot is None:
        return
    channel_id, message_id = ref
    channel = await _fetch_text_channel(_bot, int(channel_id))
    if channel is None:
        return
    presets = await asyncio.to_thread(queue_presets_sync, signal_id)
    opened_at, opened_by = await asyncio.to_thread(queue_opener_sync, signal_id)
    names = await asyncio.to_thread(queue_member_names_sync, signal_id)
    try:
        message = await channel.fetch_message(int(message_id))
        closed_view = PodQueueView(
            names=names, role_mention=queue_role_mention(channel.guild),
            close_reason=queue_inactivity_close_reason(), set_code=presets.set_code,
            opened_at=opened_at, opened_by=opened_by,
        )
        await message.edit(view=closed_view)
    except discord.HTTPException:
        log.warning(f"fire_queue_teardown: could not edit queue message {message_id}", exc_info=True)


async def rearm_signals(bot: commands.Bot) -> None:
    """Startup sweep: re-arm slot expiries and underfill beats, on-demand lobby opens, and queue
    teardowns from the DB so a restart loses nothing. Past-due opens fire immediately; past-due open
    signals are expired, their standing nudges dropped, and their launcher column rolled forward."""
    now = datetime.now(timezone.utc)
    with SessionLocal() as session:
        signals = session.execute(
            select(PodSignal).where(PodSignal.status.in_([pod_signals.STATUS_OPEN, pod_signals.STATUS_FIRED]))
        ).scalars().all()
        pending = [
            (s.id, s.kind, s.status, s.slot_time, s.last_activity_at, s.event_id, s.created_at)
            for s in signals
        ]

    for signal_id, kind, status, slot_time, last_activity, event_id, created_at in pending:
        if status == pod_signals.STATUS_FIRED and event_id is not None:
            scheduled = kind == pod_signals.KIND_SCHEDULED
            if _rearm_open_if_pending(bot, event_id, with_fill_jobs=scheduled):
                continue
        if status != pod_signals.STATUS_OPEN:
            continue
        if kind == pod_signals.KIND_POLL and slot_time is not None:
            if slot_time <= now:
                if await asyncio.to_thread(expire_signal_sync, signal_id):
                    await clear_slot_nudge(bot, signal_id)
                    await notify_slot_rolled(bot, signal_id)
            else:
                arm_slot_expiry(bot, signal_id, slot_time)
                schedule_slot_underfill_checks(bot.pod_scheduler, signal_id, slot_time, created_at)
        elif kind == pod_signals.KIND_QUEUE:
            teardown = pod_signals.teardown_at(last_activity, settings.pod_queue_inactivity_minutes)
            if teardown <= now:
                await asyncio.to_thread(expire_signal_sync, signal_id)
            else:
                arm_queue_teardown(bot, signal_id, teardown)


def _rearm_open_if_pending(bot: commands.Bot, event_id: str, with_fill_jobs: bool = False) -> bool:
    """`with_fill_jobs` re-arms the underfill and roster-reminder jobs a scheduled card carries on
    top of the lobby open; poll and queue pods fire full by construction and skip them."""
    with SessionLocal() as session:
        event = session.get(PodDraftEvent, event_id)
        if event is None or event.socket_status not in ("pending", "reminded"):
            return False
        event_time = event.event_time
        created_at = event.created_at
    if with_fill_jobs:
        arm_scheduled_pod_jobs(bot, event_id, event_time, created_at)
    else:
        _arm_open(bot, event_id, event_time)
    return True


_bot: commands.Bot | None = None

_SLOT_ROLL_HOOK = None


def init_launch(bot: commands.Bot) -> None:
    """Wire the bot reference so scheduler callbacks (queue teardown) can edit Discord messages, and
    register the draft-done card close so the manager can fire it without importing this module."""
    global _bot
    _bot = bot
    set_card_close_hook(close_event_card)
    set_pod_cancel_hook(retire_canceled_pod)


def set_slot_roll_hook(callback) -> None:
    """The launcher task registers the roll here so a slot expiring in this module can move its column to
    the next day without the service layer importing the task."""
    global _SLOT_ROLL_HOOK
    _SLOT_ROLL_HOOK = callback


async def notify_slot_rolled(bot: commands.Bot, signal_id: str) -> None:
    """Roll the column a now-dead slot sat in (no-op if unset)."""
    if _SLOT_ROLL_HOOK is not None:
        await _SLOT_ROLL_HOOK(bot, signal_id)


def _signal_by_message_bucket(session: Session, message_id: str, bucket: str) -> PodSignal | None:
    """The signal a click on this surface acts on. A rolled launcher column carries two rows of one bucket
    on one message, so the soonest still-gathering row wins — the slot the column's button offers — and the
    last one stands in when none is open, so a late click gets the closed answer rather than nothing."""
    signals = session.execute(
        select(PodSignal)
        .where(PodSignal.message_id == message_id, PodSignal.bucket == bucket)
        .order_by(PodSignal.signal_date)
    ).scalars().all()
    if not signals:
        return None
    for signal in signals:
        if signal.status == pod_signals.STATUS_OPEN:
            return signal
    return signals[-1]


def _scheduled_signal_by_surface(session: Session, message_id: str) -> PodSignal | None:
    """The scheduled signal whose channel card or thread mirror is this message."""
    return session.execute(
        select(PodSignal).where(
            PodSignal.bucket == pod_signals.SCHEDULED_BUCKET,
            or_(PodSignal.message_id == message_id, PodSignal.thread_message_id == message_id),
        )
    ).scalar_one_or_none()


def _event_id_for_slot(session: Session, slot_time: datetime) -> str | None:
    """The locked pod the launcher reflects at this slot: the newest event whose scheduled-card signal
    carries this exact slot_time. A fired slot posts its card with slot_time set to the slot, and a
    reschedule leaves that slot_time intact, so the reflection stays put even after the pod's start
    moves. An off-grid /draft pod carries its own time that matches no slot, so it lives as its own card
    and is never swallowed into a launcher slot. Newest wins when repeated test runs leave several at one
    slot; a second table has no scheduled-card signal, so it never displaces the pod it spun off."""
    return session.execute(
        select(PodSignal.event_id)
        .join(PodDraftEvent, PodDraftEvent.id == PodSignal.event_id)
        .where(
            PodSignal.kind == pod_signals.KIND_SCHEDULED,
            PodSignal.slot_time == slot_time,
        )
        .order_by(PodDraftEvent.created_at.desc())
        .limit(1)
    ).scalar_one_or_none()


def _event_ids_for_slot(session: Session, slot_time: datetime) -> list[str]:
    """Every pod that exists at this slot, one per format that fired, each followed by the extra tables it
    spun off, so a slot offering two formats renders both and a pod that split renders one line per table. A
    table carries no scheduled card of its own, so it is found by the ` - Table N` name it inherits from the
    pod it spun off. Newest wins per format, so repeated test runs at one slot leave one signup each."""
    primaries = session.execute(
        select(PodDraftEvent)
        .join(PodSignal, PodSignal.event_id == PodDraftEvent.id)
        .where(
            PodSignal.kind == pod_signals.KIND_SCHEDULED,
            PodSignal.slot_time == slot_time,
        )
        .order_by(PodDraftEvent.created_at)
    ).scalars().unique().all()
    event_ids: list[str] = []
    for event in _newest_signup_per_format(list(primaries)):
        event_ids.append(event.id)
        base = table_base_name(event.name)
        tables = session.execute(
            select(PodDraftEvent.id)
            .where(PodDraftEvent.name.like(f"{base} - Table %"))
            .order_by(PodDraftEvent.created_at)
        ).scalars().all()
        event_ids += [table_id for table_id in tables if table_id not in event_ids]
    return event_ids


def _newest_signup_per_format(primaries: list[PodDraftEvent]) -> list[PodDraftEvent]:
    """The pods the format's most recent signup left at this slot, oldest first: every numbered table a
    split made, and the one pod where nothing split. Keyed on the name the family shares, so the tables of
    one signup stay together where a key of one pod would keep the last table and drop the pod it came
    from, while a later signup at the same slot still replaces the earlier one."""
    newest_family: dict[str | None, str] = {}
    for event in primaries:
        newest_family[event.set_code] = pod_base_name(event.name)
    return [event for event in primaries if pod_base_name(event.name) == newest_family.get(event.set_code)]


def _event_formats_for_slot(session: Session, slot_time: datetime) -> set[str]:
    """The formats already covered by a pod at this slot, so seeding a signal skips them and leaves the rest
    of the day's offer to gather."""
    formats: set[str] = set()
    for event_id in _event_ids_for_slot(session, slot_time):
        event = session.get(PodDraftEvent, event_id)
        if event is not None and event.set_code:
            formats.add(event.set_code)
    return formats


def _member_names(session: Session, signal_id: str) -> list[str]:
    return [name for _id, name in _member_rows(session, signal_id)]


def _member_rows(session: Session, signal_id: str) -> list[tuple[str, str]]:
    """(discord id, display name) per roster row in join order.

    A decline is kept on the signal so the signup time survives a misclick, which makes it the one state
    that is on the table and off the list. Every count and roster built from here means players who are
    coming, so it is filtered out at the source."""
    return [
        (row[0], row[1]) for row in session.execute(
            select(PodSignalMember.discord_user_id, PodSignalMember.display_name)
            .where(
                PodSignalMember.signal_id == signal_id,
                PodSignalMember.rsvp != pod_signals.RSVP_NO,
            )
            .order_by(PodSignalMember.created_at)
        ).all()
    ]


def player_interest_sync(discord_user_id: str) -> list[str]:
    with SessionLocal() as session:
        return get_format_interests(session, discord_user_id)


def player_flashback_ranking_sync(discord_user_id: str) -> list[str]:
    with SessionLocal() as session:
        return get_flashback_ranking(session, discord_user_id)


def set_flashback_ranking_sync(discord_user_id: str, ranking: list[str]) -> None:
    with SessionLocal() as session:
        set_flashback_ranking(session, discord_id=discord_user_id, ranking=ranking)
        session.commit()


def player_cube_choices_sync(discord_user_id: str) -> list[str]:
    with SessionLocal() as session:
        return get_cube_choices(session, discord_user_id)


def set_cube_choices_sync(discord_user_id: str, choices: list[str]) -> None:
    with SessionLocal() as session:
        set_cube_choices(session, discord_id=discord_user_id, choices=choices)
        session.commit()


def set_launcher_interest_sync(
    message_id: str, discord_user_id: str, discord_username: str, display_name: str,
    avatar_hash: str | None, interests: list[str], signal_date: date,
) -> bool:
    """Set the user's format interest on every slot the launcher shows — its own lazy signals plus the
    scheduled pods it reflects — and persist it as their standing preference so the next launcher opens
    pre-seeded. Returns whether any signup moved."""
    normalized = fi.normalize(interests)
    with SessionLocal() as session:
        signal_ids = _launcher_day_signal_ids(session, message_id, signal_date)
        members = session.execute(
            select(PodSignalMember).where(
                PodSignalMember.signal_id.in_(signal_ids),
                PodSignalMember.discord_user_id == discord_user_id,
            )
        ).scalars().all() if signal_ids else []
        for member in members:
            member.format_interest = normalized
        set_format_interests(
            session, discord_id=discord_user_id, discord_username=discord_username,
            display_name=display_name, avatar_hash=avatar_hash, interests=normalized,
        )
        session.commit()
        return bool(members)


def _launcher_day_signal_ids(session: Session, message_id: str, signal_date: date) -> list[str]:
    """Every signal the launcher writes a preference onto: its own poll rows plus the scheduled pods it
    reflects, across each day it covers — a rolled column reaches into the next day."""
    signals = session.execute(
        select(PodSignal).where(PodSignal.message_id == message_id)
    ).scalars().all()
    ids = [signal.id for signal in signals]
    days = {signal_date} | {
        signal.signal_date for signal in signals if signal.kind == pod_signals.KIND_POLL
    }
    for day in sorted(days):
        for bucket in pod_signals.poll_buckets_for(day):
            event_id = _event_id_for_slot(session, slot_event_time(day, bucket.key))
            if event_id is None:
                continue
            scheduled_id = session.execute(
                select(PodSignal.id).where(
                    PodSignal.event_id == event_id, PodSignal.kind == pod_signals.KIND_SCHEDULED
                )
            ).scalar_one_or_none()
            if scheduled_id is not None:
                ids.append(scheduled_id)
    return ids


def _members_by_rsvp(session: Session, signal_id: str) -> tuple[dict[str, list[str]], frozenset[str]]:
    """Display names per RSVP state, plus the names among them who have never finished a pod.

    The marker rides the roster load rather than a lookup of its own: one outer join on the unique index
    over players.discord_id, so a card repaint costs exactly the statement it already cost."""
    rows = session.execute(
        select(PodSignalMember.rsvp, PodSignalMember.display_name, new_drafter_column())
        .outerjoin(Player, Player.discord_id == PodSignalMember.discord_user_id)
        .where(PodSignalMember.signal_id == signal_id)
        .order_by(PodSignalMember.created_at)
    ).all()
    rosters: dict[str, list[str]] = {state: [] for state in pod_signals.RSVP_STATES}
    new_drafters: set[str] = set()
    for state, name, new_drafter in rows:
        rosters.setdefault(state, []).append(name)
        if new_drafter:
            new_drafters.add(name)
    return rosters, frozenset(new_drafters)


def _members_by_rsvp_with_interest(
    session: Session, signal_id: str,
) -> dict[str, list[tuple[str, tuple[str, ...]]]]:
    """Each member's (display name, format-interest codes) per RSVP state, so the card can group the
    roster by format. Same rows as `_members_by_rsvp`, carrying the interest the member signed up with."""
    rows = session.execute(
        select(PodSignalMember.rsvp, PodSignalMember.display_name, PodSignalMember.format_interest)
        .where(PodSignalMember.signal_id == signal_id)
        .order_by(PodSignalMember.created_at)
    ).all()
    rosters: dict[str, list[tuple[str, tuple[str, ...]]]] = {state: [] for state in pod_signals.RSVP_STATES}
    for state, name, interest in rows:
        rosters.setdefault(state, []).append((name, tuple(interest or ())))
    return rosters


def _render_interests(
    session: Session, signal: PodSignal,
) -> dict[str, list[tuple[str, tuple[str, ...]]]] | None:
    """Per-member format interests for the card render, or None when the pod is format-locked so the
    card drops the Latest/Flashback split and shows a plain Yes / Maybe roster."""
    if signal.format_locked:
        return None
    return _members_by_rsvp_with_interest(session, signal.id)


def format_locked_for_event_sync(event_id: str) -> bool:
    """Whether the pod behind this event locked its format at creation, so every preference surface
    (card columns, the roster reminder's Format Preference button, the in-lobby flashback vote, the
    second-table format split) stays off. False when the pod has no signal."""
    with SessionLocal() as session:
        locked = session.execute(
            select(PodSignal.format_locked).where(PodSignal.event_id == event_id)
        ).scalar_one_or_none()
        return bool(locked)


def _state(signal: PodSignal, count: int) -> SignalState:
    return SignalState(
        signal.id, signal.kind, signal.bucket, signal.status, count, signal.slot_time, signal.event_id,
        signal.set_code, signal.created_at, signal.opened_by, signal.notify_role, signal.description,
        signal.format_locked,
    )


async def fetch_pod_thread(bot: commands.Bot, thread_id: int) -> discord.Thread | None:
    try:
        channel = await bot.fetch_channel(thread_id)
    except discord.HTTPException as e:
        log.warning(f"fetch_channel({thread_id}) failed: {e}")
        return None
    return channel if isinstance(channel, discord.Thread) else None


async def _fetch_text_channel(bot: commands.Bot, channel_id: int) -> discord.TextChannel | None:
    channel = bot.get_channel(channel_id)
    if channel is None:
        try:
            channel = await bot.fetch_channel(channel_id)
        except discord.HTTPException as e:
            log.warning(f"fetch_channel({channel_id}) failed: {e}")
            return None
    return channel if isinstance(channel, discord.TextChannel) else None
