"""Resolution and copy behind `!pod` — the rally a player posts outside a pod thread.

Answers one question: which pod is happening now, and which number is real for it. A pod whose Draftmancer
lobby is open is counted off the live socket, because the RSVP list stopped being true the moment the lobby
opened and only the people who actually opened the tab can fill the table. A pod still gathering has no
session to read, so it falls back to its RSVP counts and reuses the line the scheduled nudge already posts.

Discord belongs to the command module; everything here reads state and returns strings.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from bot import emojis
from bot.config import settings
from bot.database import SessionLocal
from bot.models import PodDraftEvent
from bot.services import pod_launch
from bot.services.pod_active import ACTIVE_POD_MANAGERS
from bot.services.pod_drafts import draftmancer_url_for
from bot.services.pod_reminder_copy import RALLY_LOBBY, RALLY_LOBBY_WAITING, RALLY_QUEUE
from bot.services.pod_schedule import (
    SCHEDULE_TZ,
    build_recruiting_message,
    build_underfill_fired_message,
)
from bot.services.pod_signals import KIND_QUEUE
from bot.services.pod_slot import pod_display_name, queue_display_name
from bot.sets import active_set_code


KIND_LOBBY = "lobby"
KIND_STARTED = "started"
KIND_GATHERING = "gathering"
KIND_QUEUE_SIGNAL = "queue"

GATHERING_WINDOW = timedelta(hours=6)
LATE_GRACE = timedelta(minutes=30)
PENDING_STATUSES = ("pending", "reminded")


@dataclass(frozen=True)
class RallyTarget:
    """One pod the rally reports. `seated` is live Draftmancer occupancy and is meaningful only for an open
    lobby; `yes` and `maybe` are RSVP counts and are meaningful only before one exists. `event_id` is what
    lets a posted rally be found again when its pod starts drafting."""
    kind: str
    name: str
    url: str
    seated: int = 0
    yes: int = 0
    maybe: int = 0
    event_time: datetime | None = None
    session_id: str | None = None
    event_id: str | None = None


async def resolve_target(guild_id: str) -> RallyTarget | None:
    """The one pod `!pod` reports. Naming two asks the reader to choose instead of to fill a seat, so only
    the most recruitable is posted: an open lobby over a pod gathering for later, and among lobbies the one
    closest to a full table, which is the one a reader arriving now can still rescue."""
    live = live_lobby_targets(guild_id)
    if live:
        return live[0]
    gathering = await asyncio.to_thread(gathering_targets_sync, guild_id)
    return gathering[0] if gathering else None


def live_lobby_targets(guild_id: str) -> list[RallyTarget]:
    """Every live pod holding a Draftmancer session. Mocks are left out: `!mock` already reposts their
    card, and a mock is not a pod anyone is trying to fill."""
    targets = []
    for manager in ACTIVE_POD_MANAGERS.values():
        if manager.kind == "mock" or manager.draft_complete:
            continue
        seated = len(manager.player_session_users())
        url = thread_url(guild_id, manager.thread_id)
        if manager.drafting:
            targets.append(RallyTarget(
                KIND_STARTED, manager.event_name, url, seated=seated, event_id=manager.event_id,
            ))
            continue
        targets.append(RallyTarget(
            KIND_LOBBY, manager.event_name, url, seated=seated, session_id=manager.session_id,
            event_id=manager.event_id,
        ))
    targets.sort(key=_recruitable_first)
    return targets


def gathering_targets_sync(guild_id: str) -> list[RallyTarget]:
    """Pods and open slots still collecting signups, soonest first. Read only when no lobby is open."""
    now = datetime.now(timezone.utc)
    targets = _pending_pod_targets_sync(guild_id, now)
    for signal in pod_launch.joinable_signals_sync(guild_id, now=now, within=GATHERING_WINDOW):
        targets.append(_signal_target(guild_id, signal))
    targets.sort(key=_soonest_first)
    return targets


def build_rally_line(target: RallyTarget) -> str:
    """One line for one pod, in whichever shape its state has a number for."""
    floor = settings.pod_signal_fire_threshold
    aim = settings.pod_draft_target_players
    if target.kind == KIND_STARTED:
        return build_underfill_fired_message(target.name, target.seated, target.url)
    if target.kind == KIND_GATHERING:
        return build_recruiting_message(
            target.name, target.yes, floor, aim, target.event_time, target.url, target.maybe,
        )
    if target.kind == KIND_QUEUE_SIGNAL:
        needed = max(1, floor - target.yes)
        return RALLY_QUEUE.format(
            hello=emojis.prefix("chordoHello"), name=target.name, needed=needed,
            plural=_plural(needed), seated=target.yes,
            manat=emojis.get("manat"), jump_url=target.url,
        )
    return _lobby_line(target, aim)


def lobby_is_full(target: RallyTarget) -> bool:
    """Whether an open lobby has nothing left to recruit. A rally has no ask to make of a full table, so
    the command answers the caller privately instead of posting one."""
    return target.kind == KIND_LOBBY and target.seated >= settings.pod_draft_target_players


def thread_url(guild_id: str, thread_id: int | str) -> str:
    return f"https://discord.com/channels/{guild_id}/{thread_id}"


def message_url(guild_id: str, channel_id: str, message_id: str) -> str:
    return f"https://discord.com/channels/{guild_id}/{channel_id}/{message_id}"


def _lobby_line(target: RallyTarget, aim: int) -> str:
    """An empty lobby drops the occupancy clause: `0 waiting` reads as a fault, and the seats needed
    already say the table is empty."""
    needed = max(1, aim - target.seated)
    waiting = RALLY_LOBBY_WAITING.format(seated=target.seated) if target.seated else ""
    return RALLY_LOBBY.format(
        thread_url=target.url,
        waiting=waiting,
        needed=needed,
        plural=_plural(needed),
        manat=emojis.get("manat"),
        session_url=draftmancer_url_for(target.session_id or ""),
    )


def _plural(count: int) -> str:
    return "" if count == 1 else "s"


def _recruitable_first(target: RallyTarget) -> tuple[int, int]:
    """Lobbies before drafts already running, and among lobbies the one closest to a full table first: that
    is the pod a reader can still rescue, and it is the one whose Join button the rally carries."""
    if target.kind != KIND_LOBBY:
        return (2, 0)
    needed = settings.pod_draft_target_players - target.seated
    if needed <= 0:
        return (1, -target.seated)
    return (0, needed)


def _soonest_first(target: RallyTarget) -> tuple[int, float]:
    """A dated slot before an open-ended queue, and the earliest start first."""
    if target.event_time is None:
        return (1, 0.0)
    return (0, target.event_time.timestamp())


def _pending_pod_targets_sync(guild_id: str, now: datetime) -> list[RallyTarget]:
    """Pods with a card up and no lobby yet. A start that has just passed still counts: the lobby opens a
    few minutes late often enough that dropping it would blank the rally exactly when it is wanted."""
    with SessionLocal() as session:
        rows = session.execute(
            select(PodDraftEvent.id, PodDraftEvent.name, PodDraftEvent.event_time)
            .where(
                PodDraftEvent.socket_status.in_(PENDING_STATUSES),
                PodDraftEvent.event_time > now - LATE_GRACE,
            )
            .order_by(PodDraftEvent.event_time)
        ).all()
    targets = []
    for event_id, name, event_time in rows:
        card = pod_launch.pod_card_ref_sync(event_id)
        if card is None:
            continue
        channel_id, message_id, _ = card
        targets.append(RallyTarget(
            KIND_GATHERING, name, message_url(guild_id, channel_id, message_id),
            yes=len(pod_launch.roster_for_event_sync(event_id)),
            maybe=len(pod_launch.maybe_roster_for_event_sync(event_id)),
            event_time=event_time,
            event_id=event_id,
        ))
    return targets


def _signal_target(guild_id: str, signal: pod_launch.JoinableSignal) -> RallyTarget:
    set_code = (signal.set_code or active_set_code()).upper()
    url = message_url(guild_id, signal.channel_id, signal.message_id)
    if signal.kind == KIND_QUEUE or signal.slot_time is None:
        name = queue_display_name(set_code, datetime.now(SCHEDULE_TZ))
        return RallyTarget(KIND_QUEUE_SIGNAL, name, url, yes=signal.count)
    return RallyTarget(
        KIND_GATHERING, pod_display_name(set_code, signal.slot_time), url,
        yes=signal.count, event_time=signal.slot_time,
    )
