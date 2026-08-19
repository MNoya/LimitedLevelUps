"""The minute tick that acts as the table's organizer, from the lobby opening until the draft starts.

One job for every live pod, not one job per pod: the managers in ACTIVE_POD_MANAGERS are the pods with a
lobby open, and a restart rebuilds that registry on its own. Each pass reads the room, asks
`pod_table_organizer.decide` what is worth saying, and says at most one thing.

Every message it sends is sent once. The players who never showed are named once, the Pick 2 and Team Draft
offers are posted once each, and no card is ever reposted because the situation changed. `!pod` in the
thread is the only thing that moves a card, since that is a player asking rather than the bot repeating
itself.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone

from discord.ext import commands

from bot.services import pod_format
from bot.services.pod_active import ACTIVE_POD_MANAGERS
from bot.services.pod_launch import fetch_pod_thread
from bot.services.pod_table_organizer import (
    CALL_MISSING,
    OFFER_PICK_2_LOBBY,
    OFFER_PICK_2_SIGNUPS,
    OFFER_TEAM_DRAFT,
    TableSnapshot,
    decide,
    name_list,
)
from bot.services.pod_team_vote import TEAM_VOTE_POD_SIZE


TICK_SECONDS = 60
MSG_WAITING_ON = "⌛ Waiting on {names}"

log = logging.getLogger(__name__)


@dataclass
class _Watch:
    """What the tick remembers between passes: the lobby count and when it last moved."""

    count: int
    since: datetime
    missing_called: bool = False


_watched: dict[str, _Watch] = {}


def init_table_organizer(bot: commands.Bot) -> None:
    bot.pod_scheduler.add_job(
        run_table_organizer, "interval", seconds=TICK_SECONDS, args=[bot],
        id="pod-table-organizer", replace_existing=True,
    )
    log.info(f"scheduled the table organizer every {TICK_SECONDS}s")


async def run_table_organizer(bot: commands.Bot) -> None:
    for event_id in [event_id for event_id in _watched if event_id not in ACTIVE_POD_MANAGERS]:
        del _watched[event_id]
    for manager in list(ACTIVE_POD_MANAGERS.values()):
        try:
            await organize_pod(bot, manager)
        except Exception:
            log.warning(f"[ORGANIZER] tick_failed event={manager.event_id}", exc_info=True)


async def organize_pod(bot: commands.Bot, manager) -> None:
    """One pod's pass: promote a card the room has caught up with, then say the one thing worth saying."""
    if manager.kind == "mock" or manager.drafting or manager.draft_complete:
        return
    if manager.ready_check_active or manager.scheduled_start is None:
        return
    await manager.promote_round_robin_offer()
    watch = _settled(manager)
    snapshot = _snapshot(manager, watch)
    action = decide(snapshot)
    if action == CALL_MISSING:
        watch.missing_called = True
        await _call_missing(bot, manager)
    elif action == OFFER_PICK_2_SIGNUPS:
        log.info(f"[ORGANIZER] pick_2_signups event={manager.event_id} ceiling={snapshot.ceiling}")
        await manager.offer_round_robin_vote(pod_size=snapshot.ceiling, from_signups=True)
    elif action == OFFER_PICK_2_LOBBY:
        log.info(f"[ORGANIZER] pick_2_lobby event={manager.event_id}")
        await manager.offer_round_robin_vote()
    elif action == OFFER_TEAM_DRAFT:
        log.info(f"[ORGANIZER] team_draft event={manager.event_id}")
        await manager.offer_team_vote(TEAM_VOTE_POD_SIZE)


async def _call_missing(bot: commands.Bot, manager) -> None:
    """Name the players who said yes and are not in the lobby, while there is still time for them to walk
    in. Nothing is posted when everybody is already here, and the call is never made twice."""
    missing = await manager.waiting_on_mentions()
    if not missing:
        return
    thread = await fetch_pod_thread(bot, manager.thread_id)
    if thread is None:
        return
    log.info(f"[ORGANIZER] calling {len(missing)} missing event={manager.event_id}")
    await thread.send(MSG_WAITING_ON.format(names=name_list(missing)))


def _settled(manager) -> _Watch:
    count = len(manager.player_session_users())
    watch = _watched.get(manager.event_id)
    if watch is None:
        watch = _Watch(count=count, since=datetime.now(timezone.utc))
        _watched[manager.event_id] = watch
    elif watch.count != count:
        watch.count = count
        watch.since = datetime.now(timezone.utc)
    return watch


def _snapshot(manager, watch: _Watch) -> TableSnapshot:
    now = datetime.now(timezone.utc)
    roster = len(manager.rsvps_yes) + len(manager.rsvps_unconfirmed) + len(manager.rsvps_maybe)
    return TableSnapshot(
        in_draftmancer=watch.count,
        ceiling=max(watch.count, roster),
        minutes_to_start=(manager.scheduled_start - now).total_seconds() / 60,
        settled_minutes=(now - watch.since).total_seconds() / 60,
        pick_2_set=pod_format.pick_2_offered_for(manager.set_code) and manager.pairing_mode != "roundrobin",
        pick_2_offered=manager.round_robin_vote_offered,
        team_offered=(
            manager.team_vote_offered or manager.pairing_mode == "team" or manager.pairing_set_by_user
        ),
        missing_called=watch.missing_called,
    )
