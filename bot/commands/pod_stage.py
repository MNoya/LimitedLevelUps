"""Turning the table plan into real pods, at the moment the attendance hold releases.

Sits above `bot/services/pod_staging.py`, which decides who belongs to each pod. This does the Discord and
database side: creates the sibling pod, hands its players over, and renumbers the pod they came from.
Design in `spec/pod-staging.md`.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime

import discord
from discord.ext import commands

from bot import audit
from bot.commands.messages import MSG_STAGED_POD_SEATS
from bot.commands.pod_rsvp import post_scheduled_card, render_pod_board
from bot.database import SessionLocal
from bot.discord_helpers import resolve_pod_chat_channel
from bot.models import PodDraftEvent
from bot.services.pod_drafts import load_event_thread_id_sync
from bot.services.pod_schedule import build_staged_table_message
from bot.services.pod_staging import (
    MIN_POD_SIZE,
    Signup,
    confirmed_first_roster_sync,
    display_pod_name,
    family_state_sync,
    hand_over_members_sync,
    numbered_pod_name,
    pod_base_name,
    pod_numeral,
    pods_at_release,
    split_for_staging,
)

log = logging.getLogger(__name__)


async def stage_pods(bot: commands.Bot, event_id: str) -> None:
    """Open every further pod the accounted-for players need, one at a time.

    Called once, when the attendance hold releases. Nothing here decides whether to split: the count is
    settled by then, and a pod opened while people are still arriving locks the shape before anyone knows
    it, which is the whole reason the hold exists.

    The count is read across every pod sharing this start time, never off this one alone, so a pod that
    already handed six players to a sibling does not read as a pod of six. Only the source's own players
    can move, so a release wanting more tables than its roster can fill opens what it can.

    Creating is one-way. A pod that empties out afterwards is cancelled by hand, like any other."""
    source = await asyncio.to_thread(_load_source, event_id)
    if source is None:
        return
    async with _family_lock(source.base_name):
        family = await asyncio.to_thread(family_state_sync, event_id)
        staged = family.staged
        wanted = pods_at_release(family.attendance)
        if wanted <= staged:
            return
        roster = await asyncio.to_thread(confirmed_first_roster_sync, event_id)
        groups = split_for_staging(roster, wanted - staged + 1)
        for offset, members in enumerate(groups[1:], start=1):
            await _open_pod(bot, event_id, source, members, staged + offset)


_family_locks: dict[str, asyncio.Lock] = {}


def _family_lock(base_name: str) -> asyncio.Lock:
    """One lock per family of pods, so two releases landing together cannot both open the next table.

    Keyed on the name these pods share, not the one that was released: an organizer locking the count and
    the scheduled release can arrive at the same moment, from either pod. Reading how many tables exist
    and writing the next one have to be one step, and the read behind it holds no lock of its own."""
    lock = _family_locks.get(base_name)
    if lock is None:
        lock = asyncio.Lock()
        _family_locks[base_name] = lock
    return lock


async def _open_pod(
    bot: commands.Bot, source_event_id: str, source: "_Source", members: list, index: int,
) -> None:
    """Create one sibling pod carrying the source's start time, seeded with the players the plan put on
    it. `post_scheduled_card` builds the whole ordinary pod: event, signal, card, thread, and every timed
    job including its own T-10 lobby. Nothing here is special-cased afterwards."""
    channel = await _card_channel(bot, source)
    if channel is None:
        log.warning(f"pod-stage: no channel to open pod {index} off {source_event_id}")
        return
    await _renumber_source(bot, source)
    name = numbered_pod_name(source.base_name, index)
    preseed = [(signup.discord_id, signup.display_name) for signup in members if signup.discord_id.isdigit()]
    new_event_id = await post_scheduled_card(
        bot, channel, set_code=source.set_code, event_time=source.event_time,
        name=name, preseed_yes=preseed, ping_role=False,
    )
    if new_event_id is None:
        log.warning(f"pod-stage: could not open pod {index} off {source_event_id}")
        return
    moved = await asyncio.to_thread(hand_over_members_sync, source_event_id, members)
    await _name_the_players_seated_here(bot, new_event_id, index, members)
    await _ask_for_the_missing_players(bot, new_event_id, name, source.event_time, len(members))
    await render_pod_board(bot, source_event_id)
    audit.event(
        "pod_staged", source_event_id=source_event_id, event_id=new_event_id, index=index, moved=moved,
    )
    log.info(
        f"pod-stage: opened {name} event={new_event_id} off {source_event_id} "
        f"seeded={len(preseed)} moved={moved}"
    )


async def _name_the_players_seated_here(
    bot: commands.Bot, event_id: str, index: int, members: list[Signup],
) -> None:
    """Tell the players the plan put here that this table is theirs, in the thread it just made for them.

    By mention, because a new thread in the sidebar says nothing about whether it is yours. The plan
    decided where everyone drafts and this is the only moment that decision reaches the person it is
    about. It stays a statement rather than an instruction: anyone can walk to the other table."""
    mentions = " ".join(f"<@{signup.discord_id}>" for signup in members if signup.discord_id.isdigit())
    if not mentions:
        return
    thread_id = await asyncio.to_thread(load_event_thread_id_sync, event_id)
    if not thread_id or thread_id == "pending":
        return
    thread = bot.get_channel(int(thread_id))
    if not isinstance(thread, discord.Thread):
        return
    try:
        await thread.send(
            MSG_STAGED_POD_SEATS.format(numeral=pod_numeral(index), mentions=mentions),
            allowed_mentions=discord.AllowedMentions(users=True),
        )
    except discord.HTTPException:
        log.warning(f"pod-stage: could not name the players on table {index}", exc_info=True)


async def _ask_for_the_missing_players(
    bot: commands.Bot, event_id: str, name: str, event_time: datetime, seated: int,
) -> None:
    """Ask the room for the players a new table is short of, once, the moment it opens.

    A table created minutes before the draft is under every recruiting beat it would have used: they are
    armed hours ahead and a pod born after them skips all of them, so without this the short table asks
    nobody and waits for a person who was never told.

    It posts in pod chat and points at the table's own thread, since the player who fills that seat is by
    definition not in the pod yet. Nothing is pinged: the ask is for whoever is already reading."""
    needed = MIN_POD_SIZE - seated
    if needed <= 0:
        return
    thread_id = await asyncio.to_thread(load_event_thread_id_sync, event_id)
    if not thread_id or thread_id == "pending":
        return
    thread = bot.get_channel(int(thread_id))
    if not isinstance(thread, discord.Thread):
        return
    channel = resolve_pod_chat_channel(bot)
    if channel is None:
        return
    body = build_staged_table_message(display_pod_name(name), needed, event_time, thread.jump_url)
    try:
        await channel.send(body, allowed_mentions=discord.AllowedMentions.none())
    except discord.HTTPException:
        log.warning(f"pod-stage: could not ask pod chat for {needed} more on {name}", exc_info=True)


async def _renumber_source(bot: commands.Bot, source: "_Source") -> None:
    """Give the original pod its number, the first time a sibling appears. It is born without one and
    only becomes pod 1 once there is a pod 2 to tell it apart from."""
    if source.numbered:
        return
    numbered = numbered_pod_name(source.base_name, 1)
    with SessionLocal() as session:
        event = session.get(PodDraftEvent, source.event_id)
        if event is not None:
            event.name = numbered
            session.commit()
    source.numbered = True
    thread_id = await asyncio.to_thread(load_event_thread_id_sync, source.event_id)
    if thread_id and thread_id != "pending":
        thread = bot.get_channel(int(thread_id))
        if isinstance(thread, discord.Thread):
            try:
                await thread.edit(name=display_pod_name(numbered)[:100])
            except discord.HTTPException:
                log.warning(f"pod-stage: could not rename thread {thread_id}", exc_info=True)


class _Source:
    __slots__ = ("event_id", "base_name", "numbered", "set_code", "event_time", "card_channel_id")

    def __init__(self, event: PodDraftEvent) -> None:
        self.event_id = event.id
        self.base_name = pod_base_name(event.name)
        self.numbered = event.name != self.base_name
        self.set_code = event.set_code
        self.event_time = event.event_time
        self.card_channel_id = event.card_channel_id


def _load_source(event_id: str) -> "_Source | None":
    with SessionLocal() as session:
        event = session.get(PodDraftEvent, event_id)
        if event is None or event.socket_status not in ("pending", "reminded"):
            return None
        return _Source(event)


async def _card_channel(bot: commands.Bot, source: "_Source") -> "discord.TextChannel | None":
    if source.card_channel_id:
        channel = bot.get_channel(int(source.card_channel_id))
        if isinstance(channel, discord.TextChannel):
            return channel
    thread_id = await asyncio.to_thread(load_event_thread_id_sync, source.event_id)
    if not thread_id or thread_id == "pending":
        return None
    thread = bot.get_channel(int(thread_id))
    parent = getattr(thread, "parent", None)
    return parent if isinstance(parent, discord.TextChannel) else None
