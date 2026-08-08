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
    ROSTER_REMINDER_HEADLINE,
    ROSTER_REMINDER_MARK,
    ROSTER_REMINDER_TITLE,
)
from bot.commands.messages import (
    MSG_CONFIRM_LOCK_IN,
    MSG_CONFIRM_LOCK_IN_TABLE,
    MSG_CONFIRM_SIGNUP_BUTTON,
    MSG_CONFIRM_SIGNUP_TALLY,
    MSG_CONFIRM_SIGNUP_TALLY_MAYBE,
)
from bot.services.pod_confirm import (
    CONFIRMED,
    Attendance,
    TablePlan,
    card_plan,
    plan_tables,
)
from bot.services.pod_roster_fields import add_roster_fields, add_table_plan_fields
from bot.services.pod_signals import RSVP_MAYBE, RSVP_YES


REMINDER_LEAD_MIN = 10
ROSTER_REMINDER_LEAD_MIN = 60
ROSTER_SEARCH_LIMIT = 50
ROSTER_CATCHUP_DELAY_S = 30
BURIED_AFTER_MESSAGES = 10

_messages_since_card: dict[int, int] = {}



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
    """Arm the roster card an hour out, or straight away for a pod born inside that hour.

    A pod that fires at T-50 and then fills to twenty is exactly the case this card exists for, so
    skipping it there withholds the table board from the only room that needs one. The catch-up still
    stops once the lobby is about to open, where a card minutes before the link is noise on top of it."""
    now = datetime.now(timezone.utc)
    run_at = event_time - timedelta(minutes=ROSTER_REMINDER_LEAD_MIN)
    job_id = f"pod-roster-{event_id}"
    if run_at <= now:
        if event_time - now <= timedelta(minutes=REMINDER_LEAD_MIN):
            with contextlib.suppress(Exception):
                scheduler.remove_job(job_id)
            return
        run_at = now + timedelta(seconds=ROSTER_CATCHUP_DELAY_S)
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
        event_time = event.event_time

    if event_time <= datetime.now(timezone.utc):
        log.info(f"fire_roster_reminder: event {event_id} already started; skipping")
        return

    await repost_roster_reminder(event_id)


def note_thread_message(thread_id: int) -> None:
    """Count a message posted in a pod thread, so `!confirm` knows whether the roster card has been
    buried without asking Discord. Counting what arrives is free; reading history back on every call is
    not, and the answer is only ever used to decide between an edit and a repost."""
    if thread_id in _messages_since_card:
        _messages_since_card[thread_id] += 1


def card_is_buried(thread_id: int) -> bool:
    """Whether enough has been said since the card went up to be worth moving it.

    An unknown thread counts as not buried. That is the state after a restart, and the safe reading: an
    unnecessary repost churns a thread people are reading, while a missed one costs an edit in place that
    still shows the right roster."""
    return _messages_since_card.get(thread_id, 0) >= BURIED_AFTER_MESSAGES


async def refresh_or_repost_roster_reminder(event_id: str) -> None:
    """Put the roster card in front of the pod again, moving it only when it needs moving. A burst of
    confirmations one after another edits one card in place; a card that chat has pushed away gets
    reposted at the bottom.

    An edit that found nothing to edit falls through to posting. A pod whose card the bot cannot locate
    has, as far as anyone reading the thread is concerned, no card at all: that is every pod whose card
    predates a restart, since the id is what survives one and the buried count is not."""
    thread_id = await asyncio.to_thread(load_event_thread_id_for_roster_sync, event_id)
    if thread_id is not None and not card_is_buried(thread_id):
        if await refresh_roster_reminder_for_event(event_id):
            return
    await repost_roster_reminder(event_id)


async def repost_roster_reminder(event_id: str) -> "discord.Message | None":
    """Put the roster card at the bottom of the pod thread, replacing whichever copy is already there.

    Delete-then-post rather than an in-place edit, because the point of this card is to be seen: one
    edited in place stays wherever chat buried it. The new card goes up before the old one comes down, so
    a failed send leaves the thread with the card it already had.
    """
    if _bot is None:
        log.error(f"repost_roster_reminder for {event_id}: bot reference is not initialised")
        return None
    loaded = await asyncio.to_thread(_load_event_for_roster_by_id, event_id)
    if loaded is None:
        return None
    thread_id, event_time, event_name, status = loaded
    if status != "pending":
        log.info(f"repost_roster_reminder: event {event_id} is {status}; skipping")
        return None
    thread = await _fetch_thread(thread_id)
    if thread is None:
        log.warning(f"repost_roster_reminder: could not fetch thread {thread_id}")
        return None
    rosters, roster_interests = await event_rsvp_rosters(event_id)
    championship_roster = await asyncio.to_thread(championship_roster_for_event_sync, event_id, rosters)
    embed = reminder_embed(event_name, event_time, rosters, roster_interests, championship_roster)
    view = _build_reminder_view(event_id, championship_roster)
    existing = await _find_roster_reminder(thread, event_id) or await _scan_for_roster_reminder(thread)
    try:
        posted = await thread.send(embed=embed, view=view, allowed_mentions=discord.AllowedMentions.none())
    except discord.HTTPException:
        log.warning(f"repost_roster_reminder: could not post in thread {thread_id}", exc_info=True)
        return None
    _messages_since_card[thread.id] = 0
    await asyncio.to_thread(_remember_confirm_card_sync, event_id, str(posted.id))
    if existing is not None:
        with contextlib.suppress(discord.HTTPException):
            await existing.delete()
    return posted


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


async def refresh_roster_reminder_for_event(event_id: str) -> bool:
    """Re-render the posted roster reminder in place off the current signal roster.

    False when there was nothing to re-render, so a caller that wants the card seen can post one. A pod
    past gathering answers True: its card is a record rather than a question, and reposting it would put
    a stale ask under a thread that has moved on."""
    loaded = await asyncio.to_thread(_load_event_for_roster_by_id, event_id)
    if loaded is None:
        return True
    thread_id, event_time, event_name, status = loaded
    if status != "pending":
        return True
    rosters, roster_interests = await event_rsvp_rosters(event_id)
    return await _edit_roster_reminder(
        event_id, thread_id, event_name, event_time, rosters, roster_interests,
    )


def reminder_embed(
    event_name: str, event_time: datetime, rosters: dict[str, list[str]],
    roster_interests: dict[str, list[tuple[str, tuple[str, ...]]]] | None,
    championship_roster: ChampionshipRoster | None,
) -> discord.Embed:
    """The roster as the tables it makes, at every size.

    One column per table with a mark against every name, rather than a Confirmed column beside a Yes one.
    Both said the same thing twice and neither showed the table anybody is sitting at, which is the thing
    the hour before a draft is about. A championship keeps its own seeded columns, since its Yes list is a
    queue for eight seats rather than a roster to seat."""
    if championship_roster is not None:
        return build_roster_embed(event_name, event_time, rosters, roster_interests, championship_roster)
    attendance = attendance_of(rosters)
    return build_table_plan_embed(event_name, event_time, attendance, card_plan(attendance))


def _build_reminder_view(
    event_id: str, championship_roster: ChampionshipRoster | None,
) -> "discord.ui.View | None":
    """The reminder's buttons. The seat button is Confirm on every pod that has a roster to confirm, busy
    or not: the ask is what turns a signup from days ago into a seat somebody has answered for, and a pod
    of six needs that answer as much as a pod of thirteen. A championship runs its own invite wave and is
    never asked to confirm."""
    if _reminder_view_builder is None:
        return None
    return _reminder_view_builder(event_id, championship_roster is None)


async def _edit_roster_reminder(
    event_id: str, thread_id: int, event_name: str, event_time: datetime,
    rosters: dict[str, list[str]],
    roster_interests: dict[str, list[tuple[str, tuple[str, ...]]]] | None,
) -> bool:
    thread = await _fetch_thread(thread_id)
    if thread is None:
        return False
    reminder = await _find_roster_reminder(thread, event_id)
    if reminder is None:
        return False
    championship_roster = await asyncio.to_thread(championship_roster_for_event_sync, event_id, rosters)
    embed = reminder_embed(event_name, event_time, rosters, roster_interests, championship_roster)
    view = _build_reminder_view(event_id, championship_roster)
    try:
        await reminder.edit(embed=embed, view=view, allowed_mentions=discord.AllowedMentions.none())
    except discord.HTTPException:
        await asyncio.to_thread(_remember_confirm_card_sync, event_id, None)
        log.warning(f"could not edit roster reminder {reminder.id}", exc_info=True)
        return False
    return True


def load_event_thread_id_for_roster_sync(event_id: str) -> int | None:
    loaded = _load_event_for_roster_by_id(event_id)
    return loaded[0] if loaded is not None else None


def _load_event_for_roster_by_id(event_id: str) -> tuple[int, datetime, str, str] | None:
    with SessionLocal() as session:
        event = session.get(PodDraftEvent, event_id)
        if event is None:
            return None
        return int(event.discord_thread_id), event.event_time, event.name, event.socket_status


def _remember_confirm_card_sync(event_id: str, message_id: str | None) -> None:
    with SessionLocal() as session:
        signal = session.execute(
            select(PodSignal).where(PodSignal.event_id == event_id)
        ).scalar_one_or_none()
        if signal is None:
            return
        signal.confirm_card_message_id = message_id
        session.commit()


def _confirm_card_id_sync(event_id: str) -> str | None:
    with SessionLocal() as session:
        return session.execute(
            select(PodSignal.confirm_card_message_id).where(PodSignal.event_id == event_id)
        ).scalar_one_or_none()


async def _find_roster_reminder(thread: discord.Thread, event_id: str) -> discord.Message | None:
    """The pod's roster card, by the id recorded when it was posted.

    Never by reading the thread. A player pressing Confirm Seat should not wait on a fifty-message
    history scan for a message the bot posted itself, and the recorded id survives the restarts a scan
    was there to cover. A pod with nothing recorded has no card to edit, and the repost path posts one."""
    remembered = await asyncio.to_thread(_confirm_card_id_sync, event_id)
    if remembered is not None:
        return thread.get_partial_message(int(remembered))
    return None


async def _scan_for_roster_reminder(thread: discord.Thread) -> discord.Message | None:
    """The cold path, run only by the reposting job: find a card left by a pod that never recorded one.

    The card carries no title, so it is recognised by the mark its headline opens with, and a titled card
    from before that change still matches on the title."""
    try:
        async for message in thread.history(limit=ROSTER_SEARCH_LIMIT):
            if message.author.id != _bot.user.id:
                continue
            for embed in message.embeds:
                if embed.title == ROSTER_REMINDER_TITLE or (
                    embed.description or ""
                ).startswith(ROSTER_REMINDER_MARK):
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
    pod has no signal. Poll and queue members are implicit Yes.

    Confirming does not move anyone out of Yes here. The split into a Confirmed column is a reading aid on
    the reminder card, and every caller of this reads the roster to act on it: who to ping, who to pull
    into a thread, who the pod is still short of."""
    loaded = signal_rsvp_rosters_sync(event_id)
    if loaded is None:
        return None
    rosters, _ = loaded
    return rosters[CONFIRMED] + rosters[RSVP_YES], rosters[RSVP_MAYBE]


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
            select(
                PodSignalMember.rsvp, PodSignalMember.display_name, PodSignalMember.format_interest,
                PodSignalMember.confirmed_at,
            )
            .where(PodSignalMember.signal_id == signal.id)
            .order_by(PodSignalMember.created_at)
        ).all()
        format_locked = signal.format_locked
    interests: dict[str, list[tuple[str, tuple[str, ...]]]] = {RSVP_YES: [], RSVP_MAYBE: [], CONFIRMED: []}
    for state, name, interest, confirmed_at in rows:
        bucket = CONFIRMED if confirmed_at is not None else state
        if bucket in interests:
            interests[bucket].append((name, tuple(interest or ())))
    rosters = {state: [name for name, _ in members] for state, members in interests.items()}
    return rosters, (None if format_locked else interests)


def build_lobby_open_body(draftmancer_url: str, mention_block: str) -> str:
    """The lobby-open post from open_ondemand_lobby. The lobby is joinable the moment the link posts
    and the start is gated on the ready-check, so the headline is 'Lobby opened', with no countdown."""
    mentions = f"\n\n{mention_block}" if mention_block else ""
    body = LOBBY_OPEN.format(
        draftmancer=emojis.get("draftmancer"), headline=LOBBY_OPEN_HEADLINE, url=draftmancer_url,
        mentions=mentions,
    )
    return f"{body}\n{BLANK_LINE}"


def attendance_of(rosters: dict[str, list[str]]) -> Attendance:
    """The reminder's roster read as the three answers the confirmation window cares about."""
    return Attendance(
        confirmed=tuple(rosters.get(CONFIRMED) or ()),
        yes=tuple(rosters.get(RSVP_YES) or ()),
        maybe=tuple(rosters.get(RSVP_MAYBE) or ()),
    )


def _signup_tally(attendance: Attendance) -> str:
    """One line of arithmetic the reader would otherwise do by counting columns. Maybes are named only when
    there are some, since a nil beside a number reads as a problem rather than an absence."""
    tally = MSG_CONFIRM_SIGNUP_TALLY.format(yes=attendance.expected)
    if attendance.maybe:
        tally += MSG_CONFIRM_SIGNUP_TALLY_MAYBE.format(maybe=len(attendance.maybe))
    return tally


def confirm_ask_line(plan: TablePlan | None = None) -> str:
    """The ask under the headline. It names a table only when there is more than one to be on, since a pod
    running a single table has no spot to distinguish and the shorter line is the one people read."""
    template = MSG_CONFIRM_LOCK_IN_TABLE if plan is not None and plan.splits else MSG_CONFIRM_LOCK_IN
    return template.format(button=MSG_CONFIRM_SIGNUP_BUTTON)


def reminder_header(event_name: str, event_time: datetime, attendance: Attendance, plan: TablePlan) -> str:
    """The two lines every roster card opens with, shared by both shapes so the board of tables and the
    plain roster read as one surface.

    The first carries the whole state of the pod: which pod, when it starts, and how many are coming. It
    is the headline itself rather than an embed title, because a title sits in its own row above the body
    and splits one sentence across two lines on a phone."""
    headline = ROSTER_REMINDER_HEADLINE.format(name=event_name, unix=int(event_time.timestamp()))
    return f"{headline}{_signup_tally(attendance)}\n{confirm_ask_line(plan)}"


def build_table_plan_embed(
    event_name: str, event_time: datetime, attendance: Attendance, plan: TablePlan,
) -> discord.Embed:
    """The roster card as a board of tables. Nothing in the body explains the shape, because the columns
    are the shape: a reader sees which table they are on and what it still needs without parsing a
    sentence about it."""
    embed = discord.Embed(
        description=reminder_header(event_name, event_time, attendance, plan),
        color=discord.Color.green(),
    )
    add_table_plan_fields(embed, attendance, plan)
    return embed


def build_roster_embed(
    event_name: str, event_time: datetime, rosters: dict[str, list[str]],
    roster_interests: dict[str, list[tuple[str, tuple[str, ...]]]] | None = None,
    championship_roster: ChampionshipRoster | None = None,
) -> discord.Embed:
    """Same roster columns the scheduled card renders, so the T-60 reminder mirrors the card: a plain
    Yes / Maybe pair until a signup wants flashback, then a Latest Set / Flashback split.

    A championship mirrors the card the same way, by its seeded Top 8 / Alternates / Can't columns. Its Yes
    list is not a roster, it is a queue for eight seats, so a flat list of everyone who answered says nothing
    about who is playing an hour before the draft, and nobody is asked to confirm a seat the seeding has
    not given them yet."""
    if championship_roster is not None:
        embed = discord.Embed(
            description=ROSTER_REMINDER_HEADLINE.format(name=event_name, unix=int(event_time.timestamp())),
            color=discord.Color.green(),
        )
        add_championship_roster_fields(embed, championship_roster)
        return embed
    attendance = attendance_of(rosters)
    embed = discord.Embed(
        description=reminder_header(event_name, event_time, attendance, plan_tables(attendance.expected)),
        color=discord.Color.green(),
    )
    add_roster_fields(embed, rosters, roster_interests)
    return embed
