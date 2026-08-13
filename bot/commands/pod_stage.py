"""Turning the table plan into real pods, at the moment the attendance hold releases.

Sits above `bot/services/pod_staging.py`, which decides who belongs to each pod. This does the Discord and
database side: creates the sibling pod, hands its players over, and renumbers the pod they came from.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime

import discord
from discord.ext import commands

from bot import audit
from bot.commands.pod_rsvp import (
    move_pod_to_its_own_card,
    post_scheduled_card,
    render_pod_overview,
)
from bot.database import SessionLocal
from bot.discord_helpers import resolve_pod_chat_channel
from bot.models import PodDraftEvent
from bot.services import pod_event_settings
from bot.services.pod_drafts import load_event_thread_id_sync
from bot.services.pod_confirm import seating_plan, table_capacity_for
from bot.services.pod_launch import (
    fetch_pod_thread,
    maybe_roster_for_event_sync,
    register_stage_pods,
    scheduled_card_ref_sync,
)
from bot.services.pod_hold_view import build_tables_map_items
from bot.services.pod_link_dm import pod_thread_link
from bot.services.pod_reminder_copy import STAGED_TABLES_ROW, STAGED_TABLES_TITLE
from bot.services.pod_schedule import build_staged_table_message
from bot.services.pod_staging import (
    MIN_POD_SIZE,
    FamilyPod,
    Signup,
    confirmed_first_roster_sync,
    family_state_sync,
    hand_over_maybes_sync,
    hand_over_members_sync,
    numbered_pod_name,
    pod_base_name,
    pod_family_sync,
    deal_into_plan,
)
from bot.tasks.pod_draft_reminder import close_roster_reminder

log = logging.getLogger(__name__)


async def stage_pods(bot: commands.Bot, event_id: str) -> None:
    """Open every further pod the accounted-for players need, one at a time.

    Called once, when the attendance hold releases. Nothing here decides whether to split: the count is
    settled by then, and a pod opened while people are still arriving locks the shape before anyone knows
    it, which is the whole reason the hold exists.

    The count is read across every pod sharing this start time, never off this one alone, so a pod that
    already handed six players to a sibling does not read as a pod of six. Only the source's own players
    can move, so a release wanting more tables than its roster can fill opens what it can.

    Every handover runs before any card is posted, so table 1 draws its own six rather than all thirteen
    and then correcting itself. Table 1 takes its card first, so the tables land in the channel in the
    order they are numbered.

    The maybes go with the last table, and so does anyone who signed up Yes and never confirmed. That is
    where a player dropping out costs a draft, and where a body walking in late is worth having.

    Creating is one-way. A pod that empties out afterwards is cancelled by hand, like any other."""
    source = await asyncio.to_thread(_load_source, event_id)
    if source is None:
        return
    signup_thread = await _pod_thread(bot, event_id)
    signup_card = await asyncio.to_thread(scheduled_card_ref_sync, event_id)
    async with _family_lock(source.base_name):
        family = await asyncio.to_thread(family_state_sync, event_id)
        staged = family.staged
        plan = seating_plan(family.attendance)
        if len(plan.tables) <= staged:
            return
        roster = await asyncio.to_thread(confirmed_first_roster_sync, event_id)
        groups = deal_into_plan([signup for signup in roster if signup.confirmed], plan)
        unconfirmed = [signup for signup in roster if not signup.confirmed] if len(groups) > 1 else []
        maybes = await _maybes_for_the_last_table(event_id, groups)
        if groups:
            await asyncio.to_thread(_size_the_room, event_id, table_capacity_for(len(groups[0])))
        await asyncio.to_thread(_renumber_source, source)
        moved = [
            await asyncio.to_thread(hand_over_members_sync, event_id, members)
            for members in groups[1:]
        ]
        await asyncio.to_thread(hand_over_members_sync, event_id, unconfirmed)
        await asyncio.to_thread(hand_over_maybes_sync, event_id, maybes)
        await _give_table_one_its_own_card(bot, source)
        for offset, members in enumerate(groups[1:], start=1):
            index = staged + offset
            last = offset == len(groups) - 1
            await _open_pod(
                bot, event_id, source, members, index,
                moved[offset - 1], maybes if last else [], unconfirmed if last else [],
            )
    if signup_card is not None:
        await render_pod_overview(bot, event_id, signup_card[2])
    family = await asyncio.to_thread(pod_family_sync, event_id)
    if len(family) < 2 or signup_thread is None:
        return
    await _point_at_the_tables(event_id, family, signup_thread)
    await close_roster_reminder(signup_thread, event_id)


async def _maybes_for_the_last_table(event_id: str, groups: list[list[Signup]]) -> list[Signup]:
    """The signup's maybes, in signup order, for the last table a split makes.

    They follow that table whatever shape the split came out as, since a full table losing one at five to
    nine is exactly the table a maybe rescues. Never table 1, which starts on its own."""
    if len(groups) < 2:
        return []
    roster = await asyncio.to_thread(maybe_roster_for_event_sync, event_id)
    return [Signup(discord_id, display_name, False) for discord_id, display_name in roster]


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
    moved: int, maybes: list[Signup], unconfirmed: list[Signup],
) -> None:
    """Create one sibling pod carrying the source's start time, seeded with the players the plan put on
    it. `post_scheduled_card` builds the whole ordinary pod: event, signal, card, thread, and every timed
    job including its own T-10 lobby. Nothing here is special-cased afterwards.

    Every dealt player is seeded, real id or not: the handover has already taken them off the source, so
    filtering here dropped them off both rosters instead of one. `add_members_to_thread` leaves an id it
    cannot resolve out of the thread on its own. `maybes` and `unconfirmed` ride along on the last table
    only. The dealt players are seeded confirmed, which is what they were on the pod they came from."""
    channel = await _card_channel(bot, source)
    if channel is None:
        log.warning(f"pod-stage: no channel to open pod {index} off {source_event_id}")
        return
    await asyncio.to_thread(_renumber_source, source)
    name = numbered_pod_name(source.base_name, index)
    preseed = [(signup.discord_id, signup.display_name) for signup in members]
    new_event_id = await post_scheduled_card(
        bot, channel, set_code=source.set_code, event_time=source.event_time, name=name,
        preseed_confirmed=preseed,
        preseed_yes=[(u.discord_id, u.display_name) for u in unconfirmed],
        preseed_maybe=[(m.discord_id, m.display_name) for m in maybes],
        ping_role=False,
    )
    if new_event_id is None:
        log.warning(f"pod-stage: could not open pod {index} off {source_event_id}")
        return
    seats = table_capacity_for(len(preseed) + len(unconfirmed) + len(maybes))
    await asyncio.to_thread(_size_the_room, new_event_id, seats)
    await _ask_for_the_missing_players(bot, new_event_id, name, source.event_time, len(members))
    audit.event(
        "pod_staged", source_event_id=source_event_id, event_id=new_event_id, index=index, moved=moved,
    )
    log.info(
        f"pod-stage: opened {name} event={new_event_id} off {source_event_id} "
        f"seeded={len(preseed)} moved={moved}"
    )


def _size_the_room(event_id: str, seats: int) -> None:
    """Open this table's Draftmancer room at the size the plan drew it, since the room otherwise defaults
    to eight and a planned table of ten could never seat its last two.

    Sized for everyone the table carries, riders included, so a rider who finds the link never takes a seat
    the confirmed roster needs. Which of those seats survive is settled by the rider window, not here.
    Written as the pod setting the Settings button offers, so anyone can widen a table that needs it."""
    pod_event_settings.store_sync(event_id, max_players=seats)


async def _give_table_one_its_own_card(bot: commands.Bot, source: "_Source") -> None:
    """Move the first table onto a card and a thread of its own, the pair every other table gets.

    Thread membership never shrinks, so the signup thread holds everyone who was ever on the pod. Left
    there, table 1 would draft in front of the players now on table 2. What stays behind becomes what it
    now is: a card showing every table, on the thread everybody is in."""
    name = numbered_pod_name(source.base_name, 1)
    thread = await move_pod_to_its_own_card(
        bot, source.event_id, name, source.event_time, source.set_code,
    )
    if thread is None:
        log.warning(f"pod-stage: could not move table 1 of {source.base_name} onto its own card")


async def _point_at_the_tables(
    source_event_id: str, family: list[FamilyPod], thread: discord.Thread,
) -> None:
    """Name every table and link to it, once, in the thread the signup gathered in.

    Every table has moved out of that thread by now, which leaves it holding everyone who was ever on the
    pod and nobody's draft. That is the one place a map belongs. Each table separately names its own
    players in its own thread, which is the same news addressed to one table."""
    if thread.guild is None:
        return
    rows = [
        STAGED_TABLES_ROW.format(link=pod_thread_link(thread.guild.id, pod))
        for pod in family if pod.thread_id
    ]
    embed = discord.Embed(
        description="\n".join([STAGED_TABLES_TITLE.format(count=len(family))] + rows),
        color=discord.Color.green(),
    )
    view = discord.ui.View(timeout=None)
    for item in build_tables_map_items(source_event_id):
        view.add_item(item)
    try:
        await thread.send(embed=embed, view=view, allowed_mentions=discord.AllowedMentions.none())
    except discord.HTTPException:
        log.warning(f"pod-stage: could not point at the tables off {source_event_id}", exc_info=True)


async def _pod_thread(bot: commands.Bot, event_id: str) -> "discord.Thread | None":
    """Fetched rather than read off the cache, which drops a thread once Discord archives it and made the
    map of the tables go missing on exactly the pods that had been gathering longest."""
    thread_id = await asyncio.to_thread(load_event_thread_id_sync, event_id)
    if not thread_id or thread_id == "pending":
        return None
    return await fetch_pod_thread(bot, int(thread_id))


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
    thread = await _pod_thread(bot, event_id)
    if thread is None:
        return
    channel = resolve_pod_chat_channel(bot)
    if channel is None:
        return
    body = build_staged_table_message(name, needed, event_time, thread.jump_url)
    try:
        await channel.send(body, allowed_mentions=discord.AllowedMentions.none())
    except discord.HTTPException:
        log.warning(f"pod-stage: could not ask pod chat for {needed} more on {name}", exc_info=True)


def _renumber_source(source: "_Source") -> None:
    """Give the original pod its number, the first time a sibling appears. It is born without one and
    only becomes pod 1 once there is a pod 2 to tell it apart from.

    The thread it is sitting in keeps its own name. Table 1 is about to move into a thread of its own
    carrying the numbered name, and the one left behind goes back to being the pod everybody signed up
    to rather than any one table."""
    if source.numbered:
        return
    with SessionLocal() as session:
        event = session.get(PodDraftEvent, source.event_id)
        if event is not None:
            event.name = numbered_pod_name(source.base_name, 1)
            session.commit()
    source.numbered = True


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


async def setup(bot: commands.Bot) -> None:
    register_stage_pods(stage_pods)
