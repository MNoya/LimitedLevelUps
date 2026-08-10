"""Resolution and copy behind `!pod` — the rally a player posts outside a pod thread.

Answers one question: which pod is happening now, and which number is real for it. A pod whose Draftmancer
lobby is open is counted off the live socket, because the RSVP list stopped being true the moment the lobby
opened and only the people who actually opened the tab can fill the table. A second table collecting claims
is counted off its card, which is the only place it exists until it fires. A pod still gathering has no
session to read, so it falls back to its RSVP counts and reuses the line the scheduled nudge already posts.

Discord belongs to the command module; everything here reads state and returns strings.
"""
from __future__ import annotations

import asyncio
import re
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from bot import emojis
from bot.config import settings
from bot.database import SessionLocal
from bot.discord_helpers import plural
from bot.models import PodDraftEvent
from bot.services import pod_format, pod_launch
from bot.services.pod_active import ACTIVE_POD_MANAGERS, ACTIVE_TABLE_VIEWS
from bot.services.pod_drafts import draftmancer_url_for
from bot.services.pod_reminder_copy import RALLY_LOBBY, RALLY_LOBBY_WAITING, RALLY_QUEUE, RALLY_TABLE
from bot.services.pod_schedule import (
    SCHEDULE_TZ,
    build_recruiting_message,
    build_underfill_fired_message,
    render_pod_name,
)
from bot.services.pod_signals import KIND_QUEUE
from bot.services.pod_slot import pod_display_name, queue_display_name
from bot.sets import CUBE_CODE, active_set_code


KIND_LOBBY = "lobby"
KIND_STARTED = "started"
KIND_GATHERING = "gathering"
KIND_QUEUE_SIGNAL = "queue"
KIND_TABLE = "table"

LATE_GRACE = timedelta(minutes=30)
PENDING_STATUSES = ("pending", "reminded")

UNREADABLE_CODES = frozenset({"ONE"})


@dataclass(frozen=True)
class RallyTarget:
    """One pod the rally reports. `seated` is live Draftmancer occupancy and is meaningful only for an open
    lobby; `yes` and `maybe` count RSVPs, or claims on a second table's card, and are meaningful only before
    one exists. `event_id` is what lets a posted rally be found again when its pod starts drafting, and a
    second table has none until its card fires."""
    kind: str
    name: str
    url: str
    seated: int = 0
    yes: int = 0
    maybe: int = 0
    event_time: datetime | None = None
    session_id: str | None = None
    event_id: str | None = None
    set_code: str = ""


async def resolve_target(guild_id: str, set_codes: Sequence[str] = ()) -> RallyTarget | None:
    """The one pod `!pod` reports, restricted to the formats the caller named. Each is tried in the order it
    was written, and one nobody is drafting right now falls through to the next, then to the general pick, so
    a caller who asks for a format still learns which pod is live instead of hearing nothing."""
    for set_code in set_codes:
        asked = await _resolve_target(guild_id, set_code)
        if asked is not None:
            return asked
    return await _resolve_target(guild_id, None)


def set_keywords(text: str) -> list[str]:
    """Every set or cube named anywhere in `!pod any BRO enjoyers tonight?`, in the order written. The whole
    message is read because the format is as likely to land mid-sentence as first, and a word that only
    happens to spell a set code costs nothing: it has no pod, so it falls through to the next name.

    `UNREADABLE_CODES` is the exception, for a code so ordinary a word that reading it as a format is wrong
    more often than right. Only the rally reads a code out of prose, so the set stays selectable everywhere
    a player picks one from a list."""
    codes = []
    for word in re.findall(r"[A-Za-z0-9]+", text):
        code = pod_format.resolve_format_code(word)
        if code is not None and code not in UNREADABLE_CODES and code not in codes:
            codes.append(code)
    return codes


def live_lobby_targets(guild_id: str) -> list[RallyTarget]:
    """Every live pod holding a Draftmancer session. Mocks are left out: `!mock` already reposts their
    card, and a mock is not a pod anyone is trying to fill."""
    targets = []
    for manager in ACTIVE_POD_MANAGERS.values():
        if manager.kind == "mock" or manager.draft_complete:
            continue
        seated = len(manager.player_session_users())
        url = thread_url(guild_id, manager.thread_id)
        set_code = (manager.set_code or "").upper()
        if manager.drafting:
            targets.append(RallyTarget(
                KIND_STARTED, manager.event_name, url, seated=seated, event_id=manager.event_id,
                set_code=set_code,
            ))
            continue
        targets.append(RallyTarget(
            KIND_LOBBY, manager.event_name, url, seated=seated, session_id=manager.session_id,
            event_id=manager.event_id, set_code=set_code,
        ))
    targets.sort(key=_recruitable_first)
    return targets


def forming_table_targets() -> list[RallyTarget]:
    """Every second table still collecting claims on its join card, closest to firing first. A claim card
    lives only in memory until it fires, so no DB-backed lookup here can see one."""
    targets = []
    for source_event_id, view in ACTIVE_TABLE_VIEWS.items():
        if view.materialized or view.superseded or view.claim_message is None:
            continue
        targets.append(RallyTarget(
            KIND_TABLE, view.table_name, view.claim_message.jump_url, yes=len(view.claims),
            set_code=_table_set_code(view, source_event_id),
        ))
    targets.sort(key=_most_claims_first)
    return targets


def gathering_targets_sync(guild_id: str) -> list[RallyTarget]:
    """Pods and open slots still collecting signups, soonest first. Read only when no lobby is open.

    Every slot still open on the launcher counts, however far off it starts: only one target is ever posted
    and the soonest wins, so a later slot answers only when nothing nearer exists. A distance bound here hid
    the day's own Early slot all morning, which is exactly when someone asks for it."""
    now = datetime.now(timezone.utc)
    targets = _pending_pod_targets_sync(guild_id, now)
    for signal in pod_launch.joinable_signals_sync(guild_id, now=now):
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
            hello=emojis.prefix("chordoHello"), name=render_pod_name(target.name), needed=needed,
            plural=plural(needed), seated=target.yes,
            manat=emojis.get("manat"), jump_url=target.url,
        )
    if target.kind == KIND_TABLE:
        needed = max(1, settings.pod_table_open_threshold - target.yes)
        return RALLY_TABLE.format(
            hello=emojis.prefix("chordoHello"), name=render_pod_name(target.name), needed=needed,
            plural=plural(needed), seated=target.yes,
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


async def _resolve_target(guild_id: str, set_code: str | None) -> RallyTarget | None:
    """Naming two pods asks the reader to choose instead of to fill a seat, so only the most recruitable is
    posted: an open lobby with seats left, then a second table collecting claims, then a pod gathering for
    later. A full lobby and a draft already running come last, so the pod that filled up never hides the
    table its leftovers are trying to fire."""
    live = _for_set(live_lobby_targets(guild_id), set_code)
    if live and live[0].kind == KIND_LOBBY and not lobby_is_full(live[0]):
        return live[0]
    tables = _for_set(forming_table_targets(), set_code)
    if tables:
        return tables[0]
    gathering = _for_set(await asyncio.to_thread(gathering_targets_sync, guild_id), set_code)
    if gathering:
        return gathering[0]
    return live[0] if live else None


def _for_set(targets: list[RallyTarget], set_code: str | None) -> list[RallyTarget]:
    """`CUBE` asks for whichever cube is being drafted, since a pod carries the cube's own code and nobody
    writing `!pod cube` knows or cares which one the day offers."""
    if not set_code:
        return targets
    if set_code == CUBE_CODE:
        return [target for target in targets if pod_format.is_custom(target.set_code)]
    return [target for target in targets if target.set_code == set_code]


def _lobby_line(target: RallyTarget, aim: int) -> str:
    """An empty lobby drops the occupancy clause: `0 waiting` reads as a fault, and the seats needed
    already say the table is empty."""
    needed = max(1, aim - target.seated)
    waiting = RALLY_LOBBY_WAITING.format(seated=target.seated) if target.seated else ""
    return RALLY_LOBBY.format(
        thread_url=target.url,
        waiting=waiting,
        needed=needed,
        plural=plural(needed),
        manat=emojis.get("manat"),
        session_url=draftmancer_url_for(target.session_id or ""),
    )


def _recruitable_first(target: RallyTarget) -> tuple[int, int]:
    """Lobbies before drafts already running, and among lobbies the one closest to a full table first: that
    is the pod a reader can still rescue, and it is the one whose Join button the rally carries."""
    if target.kind != KIND_LOBBY:
        return (2, 0)
    needed = settings.pod_draft_target_players - target.seated
    if needed <= 0:
        return (1, -target.seated)
    return (0, needed)


def _most_claims_first(target: RallyTarget) -> int:
    return -target.yes


def _table_set_code(view, source_event_id: str) -> str:
    """A second table's format, which it inherits from the pod it split off unless it was opened on another
    one. A table has no event row until it fires, so the source manager is the only place to read it."""
    if view.format_code:
        return view.format_code.upper()
    source = ACTIVE_POD_MANAGERS.get(source_event_id)
    if source is None:
        return ""
    return (source.set_code or "").upper()


def _soonest_first(target: RallyTarget) -> tuple[int, float, int, int]:
    """A dated slot before an open-ended queue, the earliest start first, then between two pods starting at
    the same time a pod still short of a table before one that already has one, and among those the fuller.
    One slot offering two formats is the common case: the pod holding signups is the one a reader can fill,
    but past a full table it has nothing left to ask for and would hide the pod that does."""
    dated = 0 if target.event_time is not None else 1
    start = target.event_time.timestamp() if target.event_time is not None else 0.0
    short_of_a_table = 0 if target.yes < settings.pod_draft_target_players else 1
    return (dated, start, short_of_a_table, -target.yes)


def _pending_pod_targets_sync(guild_id: str, now: datetime) -> list[RallyTarget]:
    """Pods with a card up and no lobby yet. A start that has just passed still counts: the lobby opens a
    few minutes late often enough that dropping it would blank the rally exactly when it is wanted."""
    with SessionLocal() as session:
        rows = session.execute(
            select(PodDraftEvent.id, PodDraftEvent.name, PodDraftEvent.event_time, PodDraftEvent.set_code)
            .where(
                PodDraftEvent.socket_status.in_(PENDING_STATUSES),
                PodDraftEvent.event_time > now - LATE_GRACE,
            )
            .order_by(PodDraftEvent.event_time)
        ).all()
    targets = []
    for event_id, name, event_time, set_code in rows:
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
            set_code=(set_code or "").upper(),
        ))
    return targets


def _signal_target(guild_id: str, signal: pod_launch.JoinableSignal) -> RallyTarget:
    set_code = (signal.set_code or active_set_code()).upper()
    url = message_url(guild_id, signal.channel_id, signal.message_id)
    if signal.kind == KIND_QUEUE or signal.slot_time is None:
        name = queue_display_name(set_code, datetime.now(SCHEDULE_TZ))
        return RallyTarget(KIND_QUEUE_SIGNAL, name, url, yes=signal.count, set_code=set_code)
    return RallyTarget(
        KIND_GATHERING, pod_display_name(set_code, signal.slot_time), url,
        yes=signal.count, event_time=signal.slot_time, set_code=set_code,
    )
