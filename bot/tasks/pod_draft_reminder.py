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

from bot.database import SessionLocal
from bot.discord_helpers import BLANK_LINE, EM_SPACE, NBSP
from bot.models import PodDraftEvent, PodSignal, PodSignalMember
from bot.services.championship_roster_card import (
    ChampionshipRoster,
    add_championship_roster_fields,
    championship_roster_for_event_sync,
)
from bot.services.pod_reminder_copy import (
    ATTENDANCE_HOLD,
    ATTENDANCE_HOLD_MAYBE,
    LOBBY_OPEN,
    LOBBY_OPEN_HEADLINE,
    LOBBY_OPEN_TABLE,
    ROSTER_REMINDER_HEADLINE,
    ROSTER_REMINDER_HEADLINE_COUNT,
    ROSTER_REMINDER_MARK,
    ROSTER_REMINDER_TITLE,
)
from bot.commands.messages import (
    MSG_CONFIRM_BUTTON,
    MSG_CONFIRM_LOCK_IN,
    MSG_CONFIRM_MORE_TO_ADD,
    MSG_CONFIRM_MORE_TO_FILL,
    MSG_CONFIRM_MORE_TO_SPLIT,
    MSG_CONFIRM_TALLY_ALL,
    MSG_CONFIRM_TALLY_CONFIRMED,
    MSG_JOIN_DRAFT_BUTTON,
)
from bot.services.pod_confirm import (
    CONFIRMED,
    MIN_TABLE,
    attendance_of,
    card_tables,
    Attendance,
    TablePlan,
    seating_plan,
    plan_tables,
)
from bot.services.pod_roster_fields import add_roster_fields, add_table_plan_fields
from bot.services.pod_signals import RSVP_MAYBE, RSVP_NO, RSVP_YES


REMINDER_LEAD_MIN = 10
ROSTER_REMINDER_LEAD_MIN = 60
ROSTER_SEARCH_LIMIT = 50
ROSTER_CATCHUP_DELAY_S = 30
BURIED_AFTER_MESSAGES = 10
WIDE_GAP = EM_SPACE * 4

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
    thread_id, event_time, event_name, status, set_code = loaded
    if status != "pending":
        log.info(f"repost_roster_reminder: event {event_id} is {status}; skipping")
        return None
    thread = await _fetch_thread(thread_id)
    if thread is None:
        log.warning(f"repost_roster_reminder: could not fetch thread {thread_id}")
        return None
    rosters, roster_interests = await event_rsvp_rosters(event_id)
    championship_roster = await asyncio.to_thread(championship_roster_for_event_sync, event_id, rosters)
    embed = reminder_embed(
        event_name, event_time, rosters, roster_interests, championship_roster, set_code,
    )
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


async def refresh_roster_reminder_for_event(event_id: str) -> bool:
    """Re-render the posted roster reminder in place off the current signal roster.

    False when there was nothing to re-render, so a caller that wants the card seen can post one. A pod
    past gathering answers True: its card is a record rather than a question, and reposting it would put
    a stale ask under a thread that has moved on."""
    loaded = await asyncio.to_thread(_load_event_for_roster_by_id, event_id)
    if loaded is None:
        return True
    thread_id, event_time, event_name, status, set_code = loaded
    if status != "pending":
        return True
    rosters, roster_interests = await event_rsvp_rosters(event_id)
    return await _edit_roster_reminder(
        event_id, thread_id, event_name, event_time, rosters, roster_interests, set_code,
    )


def reminder_embed(
    event_name: str, event_time: datetime, rosters: dict[str, list[str]],
    roster_interests: dict[str, list[tuple[str, tuple[str, ...]]]] | None,
    championship_roster: ChampionshipRoster | None, set_code: str = "",
) -> discord.Embed:
    """The roster as the tables it makes, at every size.

    One column per table with a mark against every name, rather than a Confirmed column beside a Yes one.
    Both said the same thing twice and neither showed the table anybody is sitting at, which is the thing
    the hour before a draft is about. A championship keeps its own seeded columns, since its Yes list is a
    queue for eight seats rather than a roster to seat."""
    if championship_roster is not None:
        return build_roster_embed(event_name, event_time, rosters, roster_interests, championship_roster)
    attendance = attendance_of(rosters)
    plan, seat_pending = card_tables(attendance)
    return build_table_plan_embed(event_name, event_time, attendance, plan, seat_pending, set_code)


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
    set_code: str = "",
) -> bool:
    thread = await _fetch_thread(thread_id)
    if thread is None:
        return False
    reminder = await _find_roster_reminder(thread, event_id)
    if reminder is None:
        return False
    championship_roster = await asyncio.to_thread(championship_roster_for_event_sync, event_id, rosters)
    embed = reminder_embed(
        event_name, event_time, rosters, roster_interests, championship_roster, set_code,
    )
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


def _load_event_for_roster_by_id(event_id: str) -> tuple[int, datetime, str, str, str] | None:
    with SessionLocal() as session:
        event = session.get(PodDraftEvent, event_id)
        if event is None:
            return None
        return (int(event.discord_thread_id), event.event_time, event.name, event.socket_status,
                event.set_code)


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
    """Interest-carrying twin of `signal_rsvps_sync`: Yes / Maybe / No rosters off the signal that created
    the pod, each member paired with the format interest they signed up with, so the reminder can group
    by format the same way the card does. The interests are None for a format-locked pod, which renders
    a plain Yes / Maybe pair; None overall when the pod has no signal.

    A decline outranks any confirmation the row still carries, matching `attendance_for_event_sync`."""
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
    interests: dict[str, list[tuple[str, tuple[str, ...]]]] = {
        RSVP_YES: [], RSVP_MAYBE: [], RSVP_NO: [], CONFIRMED: [],
    }
    for state, name, interest, confirmed_at in rows:
        if state == RSVP_NO:
            bucket = RSVP_NO
        else:
            bucket = CONFIRMED if confirmed_at is not None else state
        if bucket in interests:
            interests[bucket].append((name, tuple(interest or ())))
    rosters = {state: [name for name, _ in members] for state, members in interests.items()}
    return rosters, (None if format_locked else interests)


def build_lobby_open_body(draftmancer_url: str, mention_block: str, numbered: bool = False) -> str:
    """The lobby-open post from open_ondemand_lobby.

    Every table drafts in a thread holding only its own players, so the link is safe to post: nobody
    reading it belongs at another table. A split pod names the button too, since the two doors differ
    once there are several rooms — the link opens this table, the button hands back a personal link and
    routes to whichever table still has a seat.

    Nothing here explains Arena names. That is caught downstream by the lobby card and the ready check,
    so saying it here would spend two lines on every pod for something one player does occasionally."""
    mentions = f"\n\n{mention_block}" if mention_block else ""
    if numbered:
        body = LOBBY_OPEN_TABLE.format(
            headline=LOBBY_OPEN_HEADLINE, url=draftmancer_url,
            button=MSG_JOIN_DRAFT_BUTTON, mentions=mentions,
        )
    else:
        body = LOBBY_OPEN.format(
            headline=LOBBY_OPEN_HEADLINE, url=draftmancer_url, mentions=mentions,
        )
    return f"{body}\n{BLANK_LINE}"


MENTIONS_PER_ROW = 8


def build_attendance_hold_body(count: int, yes: list[str], maybe: list[str]) -> str:
    """The message above the roster card when a pod holds at T-10, and the only ping the hold sends.

    Mentions wrap at eight a row, since a line of twenty is a wall nobody finds their own name in. Maybes
    get rows of their own and are pinged like everyone else: a maybe usually means someone who will play
    if the room needs them, and this is when the room finds out whether it does."""
    rows = _mention_rows(yes)
    rows += [ATTENDANCE_HOLD_MAYBE.format(mentions=row) for row in _mention_rows(maybe)]
    block = "\n".join(rows)
    return ATTENDANCE_HOLD.format(
        count=count, button=MSG_CONFIRM_BUTTON, gap=NBSP * 3,
        mentions=f"\n\n{block}" if block else "",
    )


def _mention_rows(mentions: list[str]) -> list[str]:
    return [
        " ".join(mentions[start:start + MENTIONS_PER_ROW])
        for start in range(0, len(mentions), MENTIONS_PER_ROW)
    ]


def _signup_tally(attendance: Attendance) -> str:
    """How many have confirmed, which is the one number the columns do not already carry.

    It wears the same ✅ the seat rows wear, so a number in the header and a mark beside a name can never
    mean different things. The header used to render expected turnout behind a ✅ that meant confirmed one
    line below, and a pod was started early on the strength of it.

    Pending is not counted here. It has a column with its count in the header, so saying it again above
    is the same number twice on one card. Empty for a pod nobody has signed up to."""
    if not attendance.signed_up:
        return ""
    if not attendance.yes:
        return MSG_CONFIRM_TALLY_ALL.format(count=len(attendance.confirmed))
    return MSG_CONFIRM_TALLY_CONFIRMED.format(count=len(attendance.confirmed))


def confirm_ask_line() -> str:
    """The ask under the headline, the same on every pod. It used to name a table on a pod running more
    than one, which the table columns underneath already show better than a sentence can."""
    return MSG_CONFIRM_LOCK_IN.format(button=MSG_CONFIRM_BUTTON)


def reminder_header(
    event_name: str, event_time: datetime, attendance: Attendance, plan: TablePlan,
    seat_pending: bool = False,
) -> str:
    """The lines the roster card opens with. The headline is the body rather than an embed title, which
    would sit in its own row and split one sentence across two on a phone.

    A pod running one table says how many are coming on that headline and nothing else. There is one
    table and everybody is on it, so a count broken into confirmed and pending, a line naming the shape
    and a line asking for the next one are three answers to questions nobody has yet. They appear when
    the pod is big enough to split, which is when they start deciding something."""
    unix = int(event_time.timestamp())
    if seat_pending:
        headline = ROSTER_REMINDER_HEADLINE_COUNT.format(
            name=event_name, unix=unix, count=attendance.expected,
        ) if attendance.expected else ROSTER_REMINDER_HEADLINE.format(name=event_name, unix=unix)
        return f"{headline}\n{confirm_ask_line()}"
    lines = [ROSTER_REMINDER_HEADLINE.format(name=event_name, unix=unix), confirm_ask_line()]
    tally = _signup_tally(attendance)
    ask = _next_table_ask(attendance, plan)
    if tally and ask:
        lines.append(f"{tally}{WIDE_GAP}{ask}")
    elif tally or ask:
        lines.append(tally or ask)
    return "\n".join(lines)


def _next_table_ask(attendance: Attendance, plan: TablePlan) -> str:
    """What the outstanding answers would buy the room, as a number somebody can act on. A maybe counts
    alongside a pending yes, since anyone the pod has not heard a no from can still confirm.

    Silent on a pod with no table yet, where the empty seats under the header are the same ask drawn
    rather than counted, and silent when even every outstanding answer would not be enough."""
    seated = [table for table in plan.tables if table.seated >= MIN_TABLE]
    if not seated:
        return ""
    outstanding = attendance.yes + attendance.maybe
    if len(plan.tables) > 1 and outstanding:
        for table in plan.tables:
            if table.empty_seats:
                return MSG_CONFIRM_MORE_TO_FILL.format(count=table.empty_seats, size=table.capacity)
    for more in range(1, len(outstanding) + 1):
        grown = seating_plan(Attendance(confirmed=attendance.confirmed + outstanding[:more]))
        if len([table for table in grown.tables if table.seated >= MIN_TABLE]) > len(seated):
            template = MSG_CONFIRM_MORE_TO_SPLIT if len(seated) == 1 else MSG_CONFIRM_MORE_TO_ADD
            return template.format(count=more)
    return ""


def build_table_plan_embed(
    event_name: str, event_time: datetime, attendance: Attendance, plan: TablePlan,
    seat_pending: bool = False, set_code: str = "",
) -> discord.Embed:
    """The roster card as a board of tables. Nothing in the body explains the shape, because the columns
    are the shape: a reader sees which table they are on and what it still needs without parsing a
    sentence about it."""
    embed = discord.Embed(
        description=reminder_header(event_name, event_time, attendance, plan, seat_pending),
        color=discord.Color.green(),
    )
    add_table_plan_fields(embed, attendance, plan, seat_pending, set_code)
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
