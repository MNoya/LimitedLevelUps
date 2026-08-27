"""A pod's public status message in pod-draft-chat: one living post per pod, driven by APScheduler date
jobs and by RSVP changes as they land.

The check offsets live in POD_UNDERFILL_CHECK_HOURS (default 3, 2, 1). T-3h posts a silent status in the
pod-draft-chat channel carrying the signup link back to the RSVP message; T-2h is the catch-up beat for
a pod born after T-3h; T-1h (the min offset) deletes and reposts it so it resurfaces near the event, and
pings the slot role when the pod is close to the number it is chasing — see `_nudge_ping_role`. Every
other post stays silent. Each check re-reads the Yes list off the pod's signal at fire time.

Unfired launcher slots run the same beats through `fire_slot_underfill`, linking to the launcher, which is
the slot's signup surface until it fires. The T-1h beat first asks the launcher whether the slot can open a
pod on the short threshold, since a slot that has sat at four all afternoon has nobody left to press it in.
On fire the message is not deleted: `hand_slot_nudge_to_card` rewrites it against the new card, so one
message carries a pod from its first signup to its lobby. That is the moment the pod most needs a status
up, since reaching the floor means the draft is on and still short of a full table.

The copy asks for one number at a time (`build_recruiting_message`): the floor while the draft is not yet
on, the aim once it is, and its Yes and Maybe counts once it is full. It is never deleted on a player
count, so an 8 -> 7 drop flips the text back to asking for one more instead of vanishing. It is deleted
when the draft starts and `mark_underfill_fired` reposts it as a fired record at the bottom of the channel,
when the pod is canceled via `clear_underfill_nudge`, or when a launcher slot expires
unfired via `clear_slot_nudge`. An edit re-carries any role mention the message
already holds so a player pinged at T-1h still sees why when the text later flips; the edit never re-pings.
The message is located by scanning channel history for the bot's own post carrying the signup link (plus
the pod name for launcher slots, which share one launcher URL) — nothing is persisted.

A pod pushes at most one last-call ping, claimed on `pod_signals.last_call_pinged_at`, so a caught-up
T-1h beat after a restart can never ping the slot role twice.
"""
from __future__ import annotations

import asyncio
import contextlib
import logging
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import discord
from discord.ext import commands
from sqlalchemy import select, update

from bot.config import settings
from bot.database import SessionLocal
from bot.discord_helpers import resolve_pod_chat_channel
from bot.models import PodDraftEvent, PodSignal
from bot.services.pod_drafts import is_championship
from bot.services.pod_roles import find_role
from bot.services.pod_draft_manager import set_underfill_fired_hook
from bot.services.pod_schedule import (
    CHAT_ANNOUNCE_MARKER,
    build_recruiting_message,
    build_underfill_fired_message,
    short_event_name,
)
from bot.services.pod_signals import KIND_SCHEDULED, STATUS_OPEN, slot_role_name_for_event_time
from bot.services.pod_slot import pod_display_name
from bot.sets import active_set_code
from bot.tasks.pod_draft_reminder import event_rsvps


NUDGE_SEARCH_LIMIT = 100
CATCH_UP_DELAY_S = 5

log = logging.getLogger(__name__)

_bot: commands.Bot | None = None

ShortFire = Callable[[str], Awaitable[bool]]
_short_fire: ShortFire | None = None


def register_short_fire_hook(hook: ShortFire) -> None:
    """Wire the launcher's short-threshold fire. The beat runs at the hour a thin pick-2 slot may open its
    thread, and the launcher task owns that graduation; registering it keeps this module clear of the
    import cycle between the two."""
    global _short_fire
    _short_fire = hook


def init_underfill(bot: commands.Bot) -> None:
    """Wire the bot reference so the APScheduler callbacks can dispatch Discord work."""
    global _bot
    _bot = bot
    set_underfill_fired_hook(mark_underfill_fired)


def schedule_underfill_checks(scheduler, event_id: str, event_time: datetime, created_at: datetime) -> None:
    """Arm the scheduled card's T-3h / T-2h / T-1h checks — see `_arm_underfill_beats`."""
    _arm_underfill_beats(scheduler, fire_underfill, event_id, "pod-underfill", event_time, created_at)


def schedule_slot_underfill_checks(scheduler, signal_id: str, slot_time: datetime, created_at: datetime) -> None:
    """Arm an unfired launcher slot's T-3h / T-2h / T-1h checks — see `_arm_underfill_beats`."""
    _arm_underfill_beats(scheduler, fire_slot_underfill, signal_id, "pod-slot-underfill", slot_time, created_at)


def _arm_underfill_beats(
    scheduler, fire, key: str, id_prefix: str, event_time: datetime, created_at: datetime,
) -> None:
    """Arm the T-3h / T-2h / T-1h checks, firing an immediate catch-up for any beat missed to downtime.

    A past beat is only caught up when the pod predates it (`created_at <= run_at`): that means the
    beat was missed to downtime, not that the pod was created short-notice. A short-notice pod born after
    T-3h simply skips the silent step it was never around for and picks up its first future beat.

    The catch-up carries the most recent missed beat's offset, so it inherits that beat's ping behaviour,
    but it never resurfaces: a restart cannot tell a beat missed to downtime from one that already ran, and
    reposting on every deploy puts a fresh unread status in pod chat for a pod nobody's status changed on.
    It edits the standing message instead, and only posts, and can ping, when no message is up.
    """
    check_hours = settings.pod_underfill_check_hours_tuple
    now = datetime.now(timezone.utc)
    resurface_hours = min(check_hours)
    catch_up_hours: int | None = None
    for hours in check_hours:
        run_at = event_time - timedelta(hours=hours)
        job_id = f"{id_prefix}{hours}-{key}"
        if run_at <= now:
            with contextlib.suppress(Exception):
                scheduler.remove_job(job_id)
            if event_time > now and created_at <= run_at:
                catch_up_hours = hours
            continue
        scheduler.add_job(
            fire,
            "date",
            run_date=run_at,
            args=[key, hours, hours == resurface_hours],
            id=job_id,
            replace_existing=True,
        )
        log.info(f"scheduled T-{hours}h underfill check for {key} at {run_at.isoformat()}")

    if catch_up_hours is not None:
        scheduler.add_job(
            fire,
            "date",
            run_date=now + timedelta(seconds=CATCH_UP_DELAY_S),
            args=[key, catch_up_hours, False],
            id=f"{id_prefix}-catchup-{key}",
            replace_existing=True,
        )
        log.info(f"scheduled T-{catch_up_hours}h catch-up underfill check for {key} (missed to downtime)")


async def fire_underfill(event_id: str, hours_before: int, resurface: bool = False) -> None:
    if _bot is None:
        log.error(f"fire_underfill for {event_id}: bot reference is not initialised")
        return

    with SessionLocal() as session:
        event = session.get(PodDraftEvent, event_id)
        if event is None:
            log.warning(f"fire_underfill: pod_draft_event {event_id} not found")
            return
        if event.socket_status != "pending":
            log.info(f"fire_underfill: event {event_id} is {event.socket_status}; skipping")
            return
        if is_championship(event.name):
            log.info(f"fire_underfill: {event_id} is a championship, which recruits nobody; skipping")
            return
        event_time = event.event_time
        name = event.name

    if event_time <= datetime.now(timezone.utc):
        log.info(f"fire_underfill: event {event_id} already started; skipping")
        return

    rsvps = await event_rsvps(event_id)
    jump_url = await asyncio.to_thread(_card_jump_url, event_id)
    if jump_url is None:
        log.info(f"fire_underfill: no scheduled card for event {event_id}; skipping")
        return
    yes_count = len(rsvps[0])
    maybe_count = len(rsvps[1])
    floor = settings.pod_signal_fire_threshold
    aim = settings.pod_draft_target_players

    channel = await _nudge_channel()
    if channel is None:
        log.warning("fire_underfill: pod-draft-chat channel unavailable")
        return

    nudge = await _find_nudge(channel, jump_url)

    body = build_recruiting_message(name, yes_count, floor, aim, event_time, jump_url, maybe_count)
    if resurface and nudge is not None:
        await _safe_delete(nudge)
        nudge = None
    if nudge is not None:
        await _safe_edit(nudge, body)
    else:
        signal_id = await asyncio.to_thread(_scheduled_signal_id, event_id)
        role = await _claimed_ping_role(channel, signal_id, event_time, yes_count, floor, aim, hours_before)
        post_body = f"{body} {role.mention}" if role is not None else body
        await _safe_post(channel, post_body, mention_role=role is not None)
    log.info(f"T-{hours_before}h underfill nudge for {event_id}: {yes_count}/{aim} Yes")


async def fire_slot_underfill(signal_id: str, hours_before: int, resurface: bool = False) -> None:
    """The launcher-slot twin of `fire_underfill`, running while the slot is still open: same two numbers,
    with the launcher as the signup link. A fired or expired slot is skipped — a fired slot's message has
    already been handed to its card, whose own checks carry it from there. An empty slot stays silent: there
    is no pod-in-waiting to rally around, and the launcher already advertises the open slot."""
    if _bot is None:
        log.error(f"fire_slot_underfill for {signal_id}: bot reference is not initialised")
        return
    slot = await asyncio.to_thread(_load_slot_for_nudge, signal_id)
    if slot is None:
        log.warning(f"fire_slot_underfill: pod_signal {signal_id} not found")
        return
    if slot.status != STATUS_OPEN:
        log.info(f"fire_slot_underfill: slot {signal_id} is {slot.status}; skipping")
        return
    if slot.slot_time <= datetime.now(timezone.utc):
        return
    if _short_fire is not None and await _short_fire(signal_id):
        return
    floor = settings.pod_signal_fire_threshold
    aim = settings.pod_draft_target_players
    if slot.count == 0:
        log.info(f"fire_slot_underfill: slot {signal_id} has no signups; skipping")
        return

    channel = await _nudge_channel()
    if channel is None:
        log.warning("fire_slot_underfill: pod-draft-chat channel unavailable")
        return

    nudge = await _find_nudge(channel, slot.jump_url, marker=_name_marker(slot.name))

    body = build_recruiting_message(slot.name, slot.count, floor, aim, slot.slot_time, slot.jump_url)
    if resurface and nudge is not None:
        await _safe_delete(nudge)
        nudge = None
    if nudge is not None:
        await _safe_edit(nudge, body)
    else:
        role = await _claimed_ping_role(
            channel, signal_id, slot.slot_time, slot.count, floor, aim, hours_before,
        )
        post_body = f"{body} {role.mention}" if role is not None else body
        await _safe_post(channel, post_body, mention_role=role is not None)
    log.info(f"T-{hours_before}h slot underfill nudge for {signal_id}: {slot.count} signed up")


async def _nudge_channel() -> discord.abc.Messageable | None:
    """The nudge channel, held until the guild cache is populated. Every channel lookup is a pure cache
    read, and a catch-up beat is armed from `setup_hook` and fires seconds later, before the gateway
    connects: without the wait the beat missed to downtime resolves nothing and is dropped a second time."""
    await _bot.wait_until_ready()
    return resolve_pod_chat_channel(_bot)


async def refresh_underfill_nudge_for_event(
    bot: commands.Bot, event_id: str, yes_count: int, maybe_count: int = 0,
) -> None:
    """Edit the live underfill nudge in place, fed the Yes and Maybe counts by the RSVP card handler.
    The format split on the overflow line is read only when the counts reach it."""
    loaded = await asyncio.to_thread(_load_event_by_id_for_nudge, event_id)
    if loaded is None:
        return
    jump_url = await asyncio.to_thread(_card_jump_url, event_id)
    if jump_url is None:
        return
    await _sync_nudge(bot, loaded, jump_url, yes_count, maybe_count)


async def clear_underfill_nudge(bot: commands.Bot, event_id: str) -> None:
    """Delete a still-recruiting underfill nudge when its pod is canceled. A fired nudge carries no
    signup link, so `_find_nudge` cannot match it and the fired record survives the cancel. No-op when
    no recruiting nudge is up."""
    jump_url = await asyncio.to_thread(_jump_url_for_event, event_id)
    if jump_url is None:
        return
    channel = resolve_pod_chat_channel(bot)
    if channel is None:
        return
    nudge = await _find_nudge(channel, jump_url)
    if nudge is not None:
        await _safe_delete(nudge)


async def mark_underfill_fired(
    bot: commands.Bot, event_id: str, player_count: int, thread_url: str,
) -> None:
    """Post the fired record at the bottom of pod-chat at draft start, dropping the recruiting nudge it
    replaces.

    Reposted instead of edited in place for the reason `!pod` reposts: an edit lands wherever the nudge
    landed, so a pod that recruited for an hour announces its start above an hour of conversation, and the
    channel asks whether the draft began while the answer sits unread above them.

    Posts even when no nudge is up, so a pod that filled before its first recruiting beat still announces
    itself."""
    loaded = await asyncio.to_thread(_load_event_by_id_for_nudge, event_id)
    if loaded is None:
        return
    name, _event_time, _status = loaded
    channel = resolve_pod_chat_channel(bot)
    if channel is None:
        return
    signup_url = await asyncio.to_thread(_jump_url_for_event, event_id)
    if signup_url is not None:
        nudge = await _find_nudge(channel, signup_url)
        if nudge is not None:
            await _safe_delete(nudge)
    body = build_underfill_fired_message(name, player_count, thread_url)
    await _safe_post(channel, body)


async def refresh_slot_nudge(bot: commands.Bot, signal_id: str) -> None:
    """Edit the live slot nudge in place when launcher signups change, keeping the count current
    between beats. Only ever edits an existing message — `fire_slot_underfill` owns creation and
    `clear_slot_nudge` owns removal."""
    slot = await asyncio.to_thread(_load_slot_for_nudge, signal_id)
    if slot is None or slot.status != STATUS_OPEN:
        return
    channel = resolve_pod_chat_channel(bot)
    if channel is None:
        return
    nudge = await _find_nudge(channel, slot.jump_url, marker=_name_marker(slot.name))
    if nudge is None:
        return
    body = build_recruiting_message(
        slot.name, slot.count, settings.pod_signal_fire_threshold, settings.pod_draft_target_players,
        slot.slot_time, slot.jump_url,
    )
    await _safe_edit(nudge, body)


async def hand_slot_nudge_to_card(bot: commands.Bot, signal_id: str, event_id: str) -> None:
    """Move a slot's standing status message onto the pod it just fired into, and post one when the slot
    never had a message up.

    Firing used to delete the slot's message, and the card's own beats posted a fresh one hours later. That
    left the pod with no public status at the very moment it gained one: the draft is on, the thread is open,
    and it is still short of a full table. One message carries the pod through instead, so a player watching
    pod chat sees the same line count up rather than vanish at six."""
    channel = resolve_pod_chat_channel(bot)
    if channel is None:
        return
    slot = await asyncio.to_thread(_load_slot_for_nudge, signal_id)
    nudge = None
    if slot is not None:
        nudge = await _find_nudge(channel, slot.jump_url, marker=_name_marker(slot.name))
    body = await _card_status_body(event_id)
    if body is None:
        return
    if nudge is not None:
        await _safe_edit(nudge, body)
    else:
        await _safe_post(channel, body)


async def _card_status_body(event_id: str) -> str | None:
    """A fired pod's status line, read off its card. None when the pod is gone or has no card to link."""
    loaded = await asyncio.to_thread(_load_event_by_id_for_nudge, event_id)
    jump_url = await asyncio.to_thread(_card_jump_url, event_id)
    if loaded is None or jump_url is None:
        return None
    name, event_time, _status = loaded
    rsvps = await event_rsvps(event_id)
    yes_count = len(rsvps[0])
    maybe_count = len(rsvps[1])
    return build_recruiting_message(
        name, yes_count, settings.pod_signal_fire_threshold, settings.pod_draft_target_players,
        event_time, jump_url, maybe_count,
    )


async def clear_slot_nudge(bot: commands.Bot, signal_id: str) -> None:
    """Delete a launcher slot's standing status when its start passes with no pod: nobody can join it and
    there is nothing left to advertise. A slot that fires hands its message to the card instead. No-op when
    no message is up."""
    slot = await asyncio.to_thread(_load_slot_for_nudge, signal_id)
    if slot is None:
        return
    channel = resolve_pod_chat_channel(bot)
    if channel is None:
        return
    nudge = await _find_nudge(channel, slot.jump_url, marker=_name_marker(slot.name))
    if nudge is not None:
        await _safe_delete(nudge)


async def _sync_nudge(
    bot: commands.Bot, loaded: tuple[str, datetime, str], jump_url: str, yes_count: int,
    maybe_count: int = 0,
) -> None:
    name, event_time, status = loaded
    if status != "pending":
        return

    channel = resolve_pod_chat_channel(bot)
    if channel is None:
        return

    nudge = await _find_nudge(channel, jump_url)
    if nudge is None:
        return

    body = build_recruiting_message(
        name, yes_count, settings.pod_signal_fire_threshold, settings.pod_draft_target_players,
        event_time, jump_url, maybe_count,
    )
    await _safe_edit(nudge, body)


@dataclass(frozen=True)
class _SlotNudgeContext:
    status: str
    slot_time: datetime
    count: int
    jump_url: str
    name: str


def _load_slot_for_nudge(signal_id: str) -> _SlotNudgeContext | None:
    """The slot's nudge context, named after the format it opens on: two pods can share one slot time and one
    launcher link, so the name is all that tells their nudges apart."""
    with SessionLocal() as session:
        signal = session.get(PodSignal, signal_id)
        if signal is None or signal.slot_time is None:
            return None
        jump_url = (
            f"https://discord.com/channels/{signal.guild_id}/{signal.channel_id}/{signal.message_id}"
        )
        name = pod_display_name(signal.set_code or active_set_code(), signal.slot_time)
        return _SlotNudgeContext(signal.status, signal.slot_time, len(signal.members), jump_url, name)


def _name_marker(name: str) -> str:
    """The bolded pod name as the nudge body renders it, disambiguating slot nudges that share the one
    launcher URL."""
    return f"**{short_event_name(name)}**"


def _load_event_by_id_for_nudge(event_id: str) -> tuple[str, datetime, str] | None:
    with SessionLocal() as session:
        event = session.get(PodDraftEvent, event_id)
        if event is None:
            return None
        return event.name, event.event_time, event.socket_status


async def _find_nudge(
    channel: discord.abc.Messageable, signup_url: str, marker: str | None = None,
) -> discord.Message | None:
    """The bot's own underfill nudge for a pod, located by the signup link it carries. `marker` narrows
    the match for launcher slots, whose nudges all link to the one launcher message. The `/draft`
    announcement carries the same link, so it is skipped and never edited into a nudge."""
    try:
        async for message in channel.history(limit=NUDGE_SEARCH_LIMIT):
            if message.author.id != _bot.user.id or signup_url not in message.content:
                continue
            if CHAT_ANNOUNCE_MARKER in message.content:
                continue
            if marker is None or marker in message.content:
                return message
    except discord.HTTPException:
        log.warning("could not scan pod-draft-chat channel for the underfill nudge", exc_info=True)
    return None


async def _claimed_ping_role(
    channel: discord.abc.Messageable, signal_id: str | None, event_time: datetime, yes_count: int,
    floor: int, aim: int, hours_before: int,
) -> discord.Role | None:
    """`_nudge_ping_role` with the last-call claim on top: the role only survives when this signal has
    not pinged before. A missing signal_id pings unclaimed."""
    role = _nudge_ping_role(channel, event_time, yes_count, floor, aim, hours_before)
    if role is None:
        return None
    if signal_id is not None and not await asyncio.to_thread(claim_last_call_ping_sync, signal_id):
        return None
    return role


def _nudge_ping_role(
    channel: discord.abc.Messageable, event_time: datetime, yes_count: int, floor: int, aim: int,
    hours_before: int,
) -> discord.Role | None:
    """The slot role to ping on a fresh nudge, or None to stay silent.

    Pinging is gated to the check hours in POD_UNDERFILL_PING_HOURS and to a pod that is close to the
    number it is currently chasing — the floor while the draft is not yet on, the aim once it is. It needs
    at most POD_UNDERFILL_PING_CLOSE_GAP more to get there. A pod still far from that number, or one already
    past the aim, stays silent. The role resolves off the daily poll buckets, so weekly and launcher slots
    both ping; an off-grid custom time resolves no role and stays silent.
    """
    if hours_before not in settings.pod_underfill_ping_hours_set:
        return None
    chasing = floor if yes_count < floor else aim
    needed = chasing - yes_count
    if needed <= 0 or needed > settings.pod_underfill_ping_close_gap:
        return None
    role_name = slot_role_name_for_event_time(event_time)
    if role_name is None:
        return None
    guild = getattr(channel, "guild", None)
    return find_role(guild, role_name)


def claim_last_call_ping_sync(signal_id: str) -> bool:
    """Atomically claim the one last-call ping a signal gets, so a caught-up or re-armed T-1h beat can
    never ping the slot role twice for one pod."""
    with SessionLocal() as session:
        result = session.execute(
            update(PodSignal)
            .where(PodSignal.id == signal_id, PodSignal.last_call_pinged_at.is_(None))
            .values(last_call_pinged_at=datetime.now(timezone.utc))
        )
        session.commit()
        return result.rowcount == 1


def _scheduled_signal_id(event_id: str) -> str | None:
    with SessionLocal() as session:
        return session.execute(
            select(PodSignal.id).where(
                PodSignal.event_id == event_id, PodSignal.kind == KIND_SCHEDULED
            )
        ).scalar_one_or_none()


async def _safe_post(
    channel: discord.abc.Messageable, body: str, *, mention_role: bool = False,
) -> None:
    allowed = discord.AllowedMentions(roles=True) if mention_role else discord.AllowedMentions.none()
    try:
        await channel.send(body, allowed_mentions=allowed)
    except discord.HTTPException:
        log.warning("could not post underfill nudge", exc_info=True)


_ROLE_MENTION = re.compile(r"<@&\d+>")


async def _safe_edit(message: discord.Message, body: str) -> None:
    match = _ROLE_MENTION.search(message.content)
    new_content = f"{body} {match.group()}" if match is not None else body
    try:
        await message.edit(content=new_content, allowed_mentions=discord.AllowedMentions.none())
    except discord.HTTPException:
        log.warning(f"could not edit underfill nudge {message.id}", exc_info=True)


async def _safe_delete(message: discord.Message) -> None:
    with contextlib.suppress(discord.HTTPException):
        await message.delete()


def _jump_url_for_event(event_id: str) -> str | None:
    """The scheduled card the event's nudge links to, or None when the pod has no card."""
    return _card_jump_url(event_id)


def _card_jump_url(event_id: str) -> str | None:
    """Jump link to the scheduled card that created this pod, or None for a pod with no card."""
    with SessionLocal() as session:
        row = session.execute(
            select(PodSignal.guild_id, PodSignal.channel_id, PodSignal.message_id).where(
                PodSignal.event_id == event_id, PodSignal.kind == KIND_SCHEDULED
            )
        ).first()
    if row is None:
        return None
    guild_id, channel_id, message_id = row
    return f"https://discord.com/channels/{guild_id}/{channel_id}/{message_id}"
