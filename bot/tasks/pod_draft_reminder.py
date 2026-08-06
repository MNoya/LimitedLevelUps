"""Roster reminder and team-vote offer jobs fired by APScheduler, plus the shared roster reads.

Reads the latest Yes / Maybe rosters off the pod's signal and renders the thread reminders. The
lobby-open post itself lives in open_ondemand_lobby (bot/services/pod_launch.py).
"""
from __future__ import annotations

import asyncio
import contextlib
import logging
from datetime import datetime, timedelta, timezone
from typing import Callable

import discord
from discord.ext import commands
from sqlalchemy import select

from bot import emojis
from bot.database import SessionLocal
from bot.discord_helpers import BLANK_LINE
from bot.models import PodDraftEvent, PodSignal, PodSignalMember
from bot.services.championship_roster_card import (
    ChampionshipRoster,
    add_championship_roster_fields,
    championship_roster_for_event_sync,
)
from bot.services.pod_active import ACTIVE_POD_MANAGERS
from bot.services.pod_reminder_copy import (
    LOBBY_OPEN,
    LOBBY_OPEN_HEADLINE,
    ROSTER_REMINDER_LINE,
    ROSTER_REMINDER_TITLE,
)
from bot.services.pod_roster_fields import add_roster_fields
from bot.services.pod_signals import RSVP_MAYBE, RSVP_YES
from bot.services.pod_drafts import load_event_pairing_mode_sync
from bot.services.pod_team_vote import (
    build_team_vote_offer_embed,
    build_team_vote_view,
    find_team_vote_card,
)


REMINDER_LEAD_MIN = 10
ROSTER_REMINDER_LEAD_MIN = 60
ROSTER_SEARCH_LIMIT = 50


log = logging.getLogger(__name__)

_bot: commands.Bot | None = None

ReminderViewBuilder = Callable[[str, bool], "discord.ui.View"]
_reminder_view_builder: ReminderViewBuilder | None = None


def init_reminder(bot: commands.Bot) -> None:
    """Wire the bot reference so the APScheduler callback can dispatch Discord work."""
    global _bot
    _bot = bot


def register_reminder_view_builder(builder: ReminderViewBuilder) -> None:
    """Inject the roster reminder's button view (Sign Up / Can't / Format Preference). It is built in
    pod_daily_poll, which owns the RSVP buttons and the preference picker; registering it keeps this
    module clear of that import cycle."""
    global _reminder_view_builder
    _reminder_view_builder = builder


def schedule_roster_reminder(scheduler, event_id: str, event_time: datetime) -> None:
    """Arm the early roster reminder. A past lead time is skipped, not caught up — a heads-up that lands
    minutes before start is noise, and the T-10 lobby reminder already covers the imminent case."""
    now = datetime.now(timezone.utc)
    run_at = event_time - timedelta(minutes=ROSTER_REMINDER_LEAD_MIN)
    job_id = f"pod-roster-{event_id}"
    if run_at <= now:
        with contextlib.suppress(Exception):
            scheduler.remove_job(job_id)
        return
    scheduler.add_job(
        fire_roster_reminder,
        "date",
        run_date=run_at,
        args=[event_id],
        id=job_id,
        replace_existing=True,
    )
    log.info(f"scheduled roster reminder for event {event_id} at {run_at.isoformat()}")


async def fire_roster_reminder(event_id: str) -> None:
    """Early courtesy reminder posted in the event thread with the confirmed and maybe rosters.

    Leaves socket_status untouched so the authoritative T-10 lobby reminder still fires and the startup
    sweep still re-arms both on a restart.
    """
    if _bot is None:
        log.error(f"fire_roster_reminder for {event_id}: bot reference is not initialised")
        return

    with SessionLocal() as session:
        event = session.get(PodDraftEvent, event_id)
        if event is None:
            log.warning(f"fire_roster_reminder: pod_draft_event {event_id} not found")
            return
        if event.socket_status != "pending":
            log.info(f"fire_roster_reminder: event {event_id} is {event.socket_status}; skipping")
            return
        thread_id = int(event.discord_thread_id)
        event_time = event.event_time
        event_name = event.name

    if event_time <= datetime.now(timezone.utc):
        log.info(f"fire_roster_reminder: event {event_id} already started; skipping")
        return

    thread = await _fetch_thread(thread_id)
    if thread is None:
        log.warning(f"fire_roster_reminder: could not fetch thread {thread_id}")
        return

    rosters, roster_interests = await event_rsvp_rosters(event_id)
    championship_roster = await asyncio.to_thread(championship_roster_for_event_sync, event_id, rosters)
    embed = build_roster_embed(
        event_name, event_time, rosters, roster_interests, championship_roster,
    )
    format_locked = await asyncio.to_thread(signal_format_locked_sync, event_id)
    view = _reminder_view_builder(event_id, format_locked) if _reminder_view_builder is not None else None
    try:
        await thread.send(embed=embed, view=view, allowed_mentions=discord.AllowedMentions.none())
    except discord.HTTPException:
        log.warning(f"fire_roster_reminder: could not post in thread {thread_id}", exc_info=True)
    await maybe_offer_prelobby_team_vote(thread, event_id, len(rosters.get(RSVP_YES, [])))


def _prelobby_team_vote_size(yes_count: int) -> int | None:
    """The Team-Draft vote size when the Yes roster is auto-offer eligible at the T-60 reminder — exactly
    six, a clean 3v3. A full pod plays a bracket; anything else is left alone."""
    return 6 if yes_count == 6 else None


async def maybe_offer_prelobby_team_vote(thread: discord.Thread, event_id: str, yes_count: int) -> None:
    """At the T-60 roster reminder, offer Team Draft when the Yes roster settled small and even, so the pod
    decides the pairing before the lobby opens. A separate call-to-action card whose tally lives on the
    message, so it needs no live manager; the T-10 lobby adopts the same card."""
    size = _prelobby_team_vote_size(yes_count)
    if size is None:
        return
    pairing = await asyncio.to_thread(load_event_pairing_mode_sync, event_id)
    if pairing == "team":
        return
    if await find_team_vote_card(thread, event_id) is not None:
        return
    try:
        await thread.send(embed=build_team_vote_offer_embed([], [], size), view=build_team_vote_view(event_id))
    except discord.HTTPException:
        log.warning(f"fire_roster_reminder: could not post team offer in thread {thread.id}", exc_info=True)


def schedule_team_vote_offer(scheduler, event_id: str, event_time: datetime) -> None:
    """Arm the at-start Team-Draft offer check. A past start time is skipped — the offer only makes sense
    while the lobby is still gathering at o'clock."""
    now = datetime.now(timezone.utc)
    job_id = f"pod-teamvote-{event_id}"
    if event_time <= now:
        with contextlib.suppress(Exception):
            scheduler.remove_job(job_id)
        return
    scheduler.add_job(
        fire_team_vote_offer, "date", run_date=event_time,
        args=[event_id], id=job_id, replace_existing=True,
    )
    log.info(f"scheduled team-vote offer for event {event_id} at {event_time.isoformat()}")


async def fire_team_vote_offer(event_id: str) -> None:
    """At the scheduled start time, offer Team Draft when the lobby settled small and even (four to six
    players). The manager is already live from the T-10 lobby reminder; a full, odd, or empty lobby is
    left alone until a later join makes it eligible, and offer_team_vote no-ops if the pod already
    started or is already a team draft."""
    manager = ACTIVE_POD_MANAGERS.get(event_id)
    if manager is None:
        log.info(f"fire_team_vote_offer: no live manager for {event_id}; skipping")
        return
    await manager.offer_team_vote_if_eligible()


async def refresh_roster_reminder_for_event(event_id: str) -> None:
    """Re-render the posted roster reminder in place off the current signal roster."""
    loaded = await asyncio.to_thread(_load_event_for_roster_by_id, event_id)
    if loaded is None:
        return
    thread_id, event_time, event_name, status = loaded
    if status != "pending":
        return
    rosters, roster_interests = await event_rsvp_rosters(event_id)
    await _edit_roster_reminder(event_id, thread_id, event_name, event_time, rosters, roster_interests)


async def _edit_roster_reminder(
    event_id: str, thread_id: int, event_name: str, event_time: datetime,
    rosters: dict[str, list[str]],
    roster_interests: dict[str, list[tuple[str, tuple[str, ...]]]] | None,
) -> None:
    thread = await _fetch_thread(thread_id)
    if thread is None:
        return
    reminder = await _find_roster_reminder(thread)
    if reminder is None:
        return
    championship_roster = await asyncio.to_thread(championship_roster_for_event_sync, event_id, rosters)
    embed = build_roster_embed(
        event_name, event_time, rosters, roster_interests, championship_roster,
    )
    format_locked = await asyncio.to_thread(signal_format_locked_sync, event_id)
    view = _reminder_view_builder(event_id, format_locked) if _reminder_view_builder is not None else None
    try:
        await reminder.edit(embed=embed, view=view, allowed_mentions=discord.AllowedMentions.none())
    except discord.HTTPException:
        log.warning(f"could not edit roster reminder {reminder.id}", exc_info=True)


def _load_event_for_roster_by_id(event_id: str) -> tuple[int, datetime, str, str] | None:
    with SessionLocal() as session:
        event = session.get(PodDraftEvent, event_id)
        if event is None:
            return None
        return int(event.discord_thread_id), event.event_time, event.name, event.socket_status


async def _find_roster_reminder(thread: discord.Thread) -> discord.Message | None:
    """The bot's own roster reminder in a thread, located by its embed title."""
    try:
        async for message in thread.history(limit=ROSTER_SEARCH_LIMIT):
            if message.author.id != _bot.user.id:
                continue
            for embed in message.embeds:
                if embed.title == ROSTER_REMINDER_TITLE:
                    return message
    except discord.HTTPException:
        log.warning(f"could not scan thread {thread.id} for the roster reminder", exc_info=True)
    return None


async def _fetch_thread(thread_id: int) -> discord.Thread | None:
    try:
        channel = await _bot.fetch_channel(thread_id)
    except discord.HTTPException as e:
        log.warning(f"fetch_channel({thread_id}) failed: {e}")
        return None
    return channel if isinstance(channel, discord.Thread) else None


async def event_rsvps(event_id: str) -> tuple[list[str], list[str]]:
    """Latest Yes / Maybe rosters for an event, read off the signal that created it."""
    rsvps = await asyncio.to_thread(signal_rsvps_sync, event_id)
    return rsvps or ([], [])


async def event_rsvp_rosters(
    event_id: str,
) -> tuple[dict[str, list[str]], dict[str, list[tuple[str, tuple[str, ...]]]] | None]:
    """The reminder's roster in the shape the shared field renderer wants: (names-only rosters,
    interest-carrying rosters). The interests are None when the pod has no signal, which renders a
    plain Yes / Maybe pair instead of a format split."""
    loaded = await asyncio.to_thread(signal_rsvp_rosters_sync, event_id)
    if loaded is None:
        return {RSVP_YES: [], RSVP_MAYBE: []}, None
    return loaded


def signal_rsvps_sync(event_id: str) -> tuple[list[str], list[str]] | None:
    """Yes / Maybe display names off the signal that created this pod, in join order; None when the
    pod has no signal. Poll and queue members are implicit Yes."""
    loaded = signal_rsvp_rosters_sync(event_id)
    if loaded is None:
        return None
    rosters, _ = loaded
    return rosters[RSVP_YES], rosters[RSVP_MAYBE]


def signal_rsvp_rosters_sync(
    event_id: str,
) -> tuple[dict[str, list[str]], dict[str, list[tuple[str, tuple[str, ...]]]] | None] | None:
    """Interest-carrying twin of `signal_rsvps_sync`: Yes / Maybe rosters off the signal that created
    the pod, each member paired with the format interest they signed up with, so the reminder can group
    by format the same way the card does. The interests are None for a format-locked pod, which renders
    a plain Yes / Maybe pair; None overall when the pod has no signal."""
    with SessionLocal() as session:
        signal = session.execute(
            select(PodSignal).where(PodSignal.event_id == event_id)
        ).scalar_one_or_none()
        if signal is None:
            return None
        rows = session.execute(
            select(PodSignalMember.rsvp, PodSignalMember.display_name, PodSignalMember.format_interest)
            .where(PodSignalMember.signal_id == signal.id)
            .order_by(PodSignalMember.created_at)
        ).all()
        format_locked = signal.format_locked
    interests: dict[str, list[tuple[str, tuple[str, ...]]]] = {RSVP_YES: [], RSVP_MAYBE: []}
    for state, name, interest in rows:
        if state in interests:
            interests[state].append((name, tuple(interest or ())))
    rosters = {state: [name for name, _ in members] for state, members in interests.items()}
    return rosters, (None if format_locked else interests)


def signal_format_locked_sync(event_id: str) -> bool:
    """Whether the pod behind this event locked its format at creation, so the roster reminder drops
    the Format Preference button and the second-table format split never arms. False when no signal."""
    with SessionLocal() as session:
        locked = session.execute(
            select(PodSignal.format_locked).where(PodSignal.event_id == event_id)
        ).scalar_one_or_none()
        return bool(locked)


def build_lobby_open_body(draftmancer_url: str, mention_block: str) -> str:
    """The lobby-open post from open_ondemand_lobby. The lobby is joinable the moment the link posts
    and the start is gated on the ready-check, so the headline is 'Lobby opened', with no countdown."""
    mentions = f"\n\n{mention_block}" if mention_block else ""
    body = LOBBY_OPEN.format(
        draftmancer=emojis.get("draftmancer"), headline=LOBBY_OPEN_HEADLINE, url=draftmancer_url,
        mentions=mentions,
    )
    return f"{body}\n{BLANK_LINE}"


def build_roster_embed(
    event_name: str, event_time: datetime, rosters: dict[str, list[str]],
    roster_interests: dict[str, list[tuple[str, tuple[str, ...]]]] | None = None,
    championship_roster: ChampionshipRoster | None = None,
) -> discord.Embed:
    """Same roster columns the scheduled card renders, so the T-60 reminder mirrors the card: a plain
    Yes / Maybe pair until a signup wants flashback, then a Latest Set / Flashback split.

    A championship mirrors the card the same way, by its seeded Top 8 / Alternates / Can't columns. Its Yes
    list is not a roster, it is a queue for eight seats, so a flat list of everyone who answered says nothing
    about who is playing an hour before the draft."""
    unix = int(event_time.timestamp())
    embed = discord.Embed(
        title=ROSTER_REMINDER_TITLE,
        description=ROSTER_REMINDER_LINE.format(name=event_name, unix=unix),
        color=discord.Color.green(),
    )
    if championship_roster is not None:
        add_championship_roster_fields(embed, championship_roster)
    else:
        add_roster_fields(embed, rosters, roster_interests)
    return embed
