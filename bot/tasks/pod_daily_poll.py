"""Daily Pod Launcher — the always-forward-looking "who's playing next" signup surface.

Posts every day at 11:00 ET with the same two columns (Early 14:00, Late 20:00). A slot offers one pod per
format the day carries (`pod_format_schedule`), each with its own signal, roster, quorum and lifecycle, and
each with its own button naming the format it joins. A pod fires once it reaches the threshold, graduating
into a scheduled RSVP card on its own format. Nothing here reads a stored player preference: a press says
which pod it joins, so no format is ever inferred.

Each column rolls on its own clock: the moment its pod is played, the column opens the next day's pods and
stacks the played one above them, so the board never offers a slot that already happened and interest never
resets overnight. A slot whose start passes unfired rolls the same way. Overnight signups are held, not
fired — a pod graduates only once its own day is the live one, which the morning post re-checks. The morning
post adopts the pods a rolled column already opened, so the fresh board carries what accumulated instead of
starting at zero, and the old message retires to its On This Day history.

A format whose pod already exists is reflected, not reopened: it renders a Yes/No toggle that writes to that
pod's scheduled card and creates no signal of its own, so the launcher and the card are two live windows on
one roster and never a duplicate. The other formats at that slot keep gathering behind their own buttons.
Reaching the threshold does not close a pod and neither does its lobby opening: it keeps its full joinable
block until the draft starts, and only then collapses to one line. Every button is a DynamicItem, so a board
that outlives a restart keeps working without a fixed set of keys to pre-register.
"""
from __future__ import annotations

import asyncio
import logging
import re
from datetime import date, datetime, time, timedelta, timezone

import discord
from discord.ext import commands

from bot import emojis
from bot.commands.messages import (
    MSG_DRAFT_STARTS,
    MSG_FORMAT_PREFERENCE_BUTTON,
    MSG_POD_ADDED,
    MSG_YOUR_CUBES_LINE,
    MSG_YOUR_SETS_LINE,
)
from bot.commands.pod_queue import queue_role_mention
from bot.commands.pod_rsvp import (
    ReminderRsvpButton,
    apply_card_rsvp,
    pod_removed_embed,
    post_scheduled_card,
    refresh_event_rsvp_surfaces,
    register_launcher_refresh,
)
from bot.config import settings
from bot.discord_helpers import NBSP, ZWSP
from bot.services import pod_format
from bot.services import pod_format_interest as fi
from bot.services import pod_format_poll
from bot.services import pod_launch
from bot.services.pod_active import set_pod_complete_hook
from bot.services.ping_roles import (
    NOTICE_GRANT,
    SET_CHAMPION_ROLE_NAME,
    announce_pod_grant,
    organizer_mention,
    pod_role_grant_text,
    register_format_preference_opener,
    send_join_confirmation_card,
    slot_grant_ping,
    spec_named,
)
from bot.services.pod_launcher_copy import (
    ARCHIVE_INTRO,
    CUBE_SELECT_PLACEHOLDER,
    INTEREST_DESC_CUBE,
    INTEREST_DESC_FLASHBACK,
    INTEREST_PLACEHOLDER,
    MARKER_CLOSED,
    MSG_INTEREST_PROMPT,
    MSG_INTEREST_SAVED,
    MSG_FIRST_POD_TO_FILL,
    MSG_ON_BOTH_PODS,
    MSG_ON_SEVERAL_PODS,
    MSG_POLL_INACTIVE,
    MSG_RANK_EMPTY,
    MSG_SLOT_CLOSED,
    PLAY_AGAIN_BUTTON,
    PLAY_AGAIN_INTRO,
    PLAY_AGAIN_LOVE_EMOJI,
    POLL_FORMAT_SEVERAL,
    POLL_INTRO_TIME_AND_FORMAT,
    POLL_INTRO_TIME_ONLY,
    POLL_MECHANICS,
    POLL_NEXT_LAUNCHER,
    POLL_TITLE,
    RANK_BUTTON_EMOJI,
    RANK_BUTTON_LABEL,
    RANK_MODAL_EXPLAINER,
    RANK_MODAL_FIELD,
    RANK_MODAL_PLACEHOLDER,
    FINISHED_MARK,
    NEXT_EMOJI,
    PLAYING_MARK,
    RANK_MODAL_TITLE,
    SAVE_BUTTON_EMOJI,
    SAVE_BUTTON_LABEL,
    SECTION_NEXT,
)
from bot.services.pod_reminder_copy import SLOT_FIRE_PING
from bot.services.pod_roles import find_role, grant_pod_drafters, grant_role, role_mention
from bot.services.pod_signals import (
    RSVP_NO,
    RSVP_YES,
    SCHEDULE_TZ,
    STATUS_EXPIRED,
    POST_HOUR_ET,
    bucket_by_key,
    bucket_role_name,
    format_of,
    lane_of,
    should_fire,
    slot_can_fire,
    slot_role_name_for_event_time,
    time_key_of,
)
from bot.services.pod_drafts import TABLE_SUFFIX_RE
from bot.services.pod_slot import pod_display_name
from bot.sets import active_set_code, set_name_for
from bot.slug import slugify
from bot.tasks.pod_draft_reminder import register_reminder_view_builder
from bot.tasks.pod_underfill import clear_slot_nudge, refresh_slot_nudge, schedule_slot_underfill_checks


log = logging.getLogger(__name__)

_bot: commands.Bot | None = None

LAUNCHER_CLOSE_LOOKBACK_DAYS = 3
PLAY_AGAIN_DELAY_MIN = 5

CHAMPIONSHIP_SLOT_LABEL = "Set Championship"
CHAMPIONSHIP_CROWN = "👑"
CHAMPIONSHIP_POINTER_TOP = 8

COLUMN_FIT_BUDGET = 35
EMOJI_UNITS = 3
WINNER_GAP_UNITS = 2 + EMOJI_UNITS
WINNER_MIN_CHARS = 6
ELLIPSIS = "…"
ORDINAL_SUFFIXES = {1: "st", 2: "nd", 3: "rd"}
NAME_DATE_RE = re.compile(r"\s(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec) \d{1,2}\b")


def init_daily_poll(bot: commands.Bot) -> None:
    global _bot
    _bot = bot
    register_launcher_refresh(refresh_launcher_for_date)
    set_pod_complete_hook(roll_lane_after_pod)
    pod_launch.set_slot_roll_hook(roll_lane_after_expired_slot)
    bot.pod_scheduler.add_job(
        fire_daily_poll, "cron", hour=POST_HOUR_ET, minute=0,
        timezone=SCHEDULE_TZ, id="pod-daily-poll", replace_existing=True,
    )
    log.info(f"scheduled daily pod launcher at {POST_HOUR_ET:02d}:00 ET")


def _poll_channel(bot: commands.Bot) -> "discord.abc.Messageable | None":
    """The launcher lives in the coordination channel, not pod-draft-chat, so a busy chat can't bury
    it. Both the post and every re-render resolve through here so they never drift apart."""
    return bot.get_channel(settings.pod_draft_channel_id)


async def fire_daily_poll() -> None:
    if _bot is None:
        return
    today = datetime.now(SCHEDULE_TZ).date()
    if await asyncio.to_thread(pod_launch.poll_exists_for_date_sync, today):
        log.info(f"daily launcher already posted for {today}; skipping")
        return
    channel = _poll_channel(_bot)
    if channel is None:
        log.warning("fire_daily_poll: coordination channel unresolved")
        return
    message = await post_launcher(_bot, channel, today)
    if message is not None:
        log.info(f"posted daily pod launcher for {today} as message {message.id}")
    await close_recent_launchers(_bot, today)
    await pod_launch.close_past_pod_cards()


async def catch_up_daily_poll(bot: commands.Bot) -> None:
    """Startup safety net for the 11:00 post. The cron is re-armed for its next future fire every start, so a
    bot that was down at the post hour skips that day's post altogether, and the morning post is the only
    thing that graduates the pods that filled overnight: without this they sit full until their slot time
    passes and expires. Posts the missing board, or runs the graduation pass when the board is already up."""
    now = datetime.now(SCHEDULE_TZ)
    if now.hour < POST_HOUR_ET:
        return
    today = now.date()
    if not await asyncio.to_thread(pod_launch.poll_exists_for_date_sync, today):
        log.info(f"catching up the daily launcher for {today}, missed at the post hour")
        await fire_daily_poll()
        return
    board = await asyncio.to_thread(pod_launch.live_launcher_board_sync)
    if board is None:
        return
    _guild_id, _channel_id, message_id, _board_date = board
    await _graduate_held_slots(bot, message_id, today)


async def post_launcher(
    bot: commands.Bot, channel: "discord.abc.Messageable", signal_date: date,
) -> discord.Message | None:
    """Render and post the day's launcher, bind a lazy signal per open slot and arm its expiry and underfill
    beats, then re-render and graduate whatever arrived overnight. Shared by the daily cron and `!test poll`
    so both drive the identical surface.

    Binding adopts the slots a rolled column already opened for today, so the fresh board carries the
    signups collected since yesterday and the first render (which runs before binding, off an empty board)
    is corrected by the re-render right after.

    A slot whose time already passed is closed and rolled here rather than armed: an expiry job dated in the
    past is a misfire APScheduler drops, which would leave the column offering a dead slot until a restart
    swept it. Reached whenever a board is posted late in the day, by the startup catch-up after downtime or
    by `!test poll`, and it runs before graduation so a slot full but already started never fires a pod into
    the past."""
    guild = getattr(channel, "guild", None)
    guild_id = str(guild.id) if guild else ""
    slots = await asyncio.to_thread(pod_launch.launcher_snapshot_sync, "", signal_date)
    message = await channel.send(
        content=poll_ping_line(guild), embed=build_poll_embed(slots, guild),
        view=PodPollView(slots, guild), allowed_mentions=discord.AllowedMentions(roles=True),
    )
    bound = await asyncio.to_thread(
        pod_launch.create_poll_signals_sync,
        guild_id=guild_id, channel_id=str(channel.id), message_id=str(message.id), signal_date=signal_date,
    )
    posted_at = datetime.now(timezone.utc)
    for signal_id, slot_time in bound:
        if slot_time <= posted_at:
            await pod_launch.fire_slot_expiry(signal_id)
            continue
        pod_launch.arm_slot_expiry(bot, signal_id, slot_time)
        schedule_slot_underfill_checks(bot.pod_scheduler, signal_id, slot_time, posted_at)
    await _rerender_poll(bot, str(message.id), signal_date, channel)
    await _graduate_held_slots(bot, str(message.id), signal_date)
    return message


async def _graduate_held_slots(bot: commands.Bot, message_id: str, signal_date: date) -> None:
    """Fire the slots that reached the threshold before their day arrived. A rolled column collects signups
    all evening but holds, so the morning post is where a full slot finally graduates into a pod."""
    candidates = await asyncio.to_thread(pod_launch.slot_fire_candidates_sync, message_id, signal_date)
    for state in candidates:
        if not await asyncio.to_thread(pod_launch.claim_slot_fire_sync, state.signal_id):
            continue
        log.info(f"graduating held slot {state.signal_id} at the daily post with {state.count} signups")
        await _launch_slot(bot, state, message_id)


def poll_ping_line(guild: discord.Guild | None) -> str | None:
    return queue_role_mention(guild)


def build_poll_embed(
    slots: list[pod_launch.LauncherSlot], guild: discord.Guild | None = None, closed: bool = False,
) -> discord.Embed:
    """One inline field per bucket, so the two slots read as two columns and each column stacks its slots
    by time: a finished pod above the next day's gathering slot, under one slot-name header with Played
    and Next sections. The description carries only the choice a reader has to make, and the mechanics
    follow the columns as a full-width field: an embed renders every field after its description, so a
    field is the only way to seat that copy below the board. `closed` renders the terminal state as a
    compact On This Day history list in the description instead of columns, so a reader scrolling up sees
    the day's results with no empty column space."""
    slot_times = [slot.slot_time for slot in slots if slot.slot_time is not None]
    earliest = min(slot_times) if slot_times else None
    day = earliest.astimezone(SCHEDULE_TZ) if earliest else None
    title = f"{POLL_TITLE} - {day:%b %-d}" if day else POLL_TITLE
    heading = f"## {NBSP * 2}🚀 {title}"
    if closed:
        return _archive_embed(slots, guild, heading)
    codes = _offered_formats(slots)
    several = len(codes) > 1
    intro = POLL_INTRO_TIME_AND_FORMAT if several else POLL_INTRO_TIME_ONLY
    parts = (heading, intro, _format_legend(codes, guild))
    description = "\n".join(part for part in parts if part)
    embed = discord.Embed(description=description, color=discord.Color.green())
    columns = [_lane_slots(slots, lane) for lane in _lane_order(slots)]
    pad = _finished_pad(columns)
    for column in columns:
        value = _column_value(column, guild, pad)
        if value:
            embed.add_field(name=ZWSP, value=value, inline=True)
    embed.add_field(name=ZWSP, value=_mechanics_note(slots, several), inline=False)
    return embed


def _next_launcher_note(slots: list[pod_launch.LauncherSlot]) -> str:
    """The extra mechanics bullet for a board carrying a slot on a later day. Such a pod holds at quorum until the
    next launcher graduates it, so the plain threshold line alone would promise a thread that cannot open yet.
    Counts down to that post instead of explaining the hold, since what a reader wants from a slot they cannot
    fire is when it becomes live. Only rendered when a later day is on the board, where it is the answer, and
    not on a board carrying today alone, where it is noise."""
    days = [slot.slot_time.astimezone(SCHEDULE_TZ).date() for slot in slots if slot.slot_time is not None]
    now = datetime.now(SCHEDULE_TZ)
    if not any(day > now.date() for day in days):
        return ""
    post_today = datetime.combine(now.date(), time(POST_HOUR_ET), tzinfo=SCHEDULE_TZ)
    next_post = post_today if post_today > now else post_today + timedelta(days=1)
    return POLL_NEXT_LAUNCHER.format(unix=int(next_post.timestamp()))


def _finished_pad(columns: list[list[pod_launch.LauncherSlot]]) -> int:
    """The tallest Played section among columns that also have a Next, so shorter columns can pad to it
    and the Next rows line up across the two side-by-side columns. Columns without a Next are ignored."""
    pad = 0
    for column in columns:
        groups = _time_groups(column)
        played = sum(len(group) for group in groups if _group_locked(group))
        gathering = any(not _group_locked(group) for group in groups)
        if played and gathering:
            pad = max(pad, played)
    return pad


def _offered_formats(slots: list[pod_launch.LauncherSlot]) -> list[str]:
    """The distinct formats a reader can still join, latest set first then in column order. Per-slot
    schedules can put different formats on one board, so every one is collected."""
    codes = []
    for slot in slots:
        if slot.championship or slot.locked or not slot.set_code or slot.set_code in codes:
            continue
        codes.append(slot.set_code)
    latest = active_set_code()
    if latest in codes:
        codes = [latest] + [code for code in codes if code != latest]
    return codes


def _format_legend(codes: list[str], guild: discord.Guild | None) -> str:
    """One line per format the board offers: the full name glossing the abbreviated code a column header
    carries, a cube's CubeCobra link, and the role that gets pinged for it.

    Deliberately not a numbered list of choices: lanes can sit on different days carrying different formats,
    and a numbered slate would then claim a pod is on offer tonight when it is tomorrow's. Which format is
    where stays the columns' job."""
    lines = []
    for code in codes:
        name = pod_format.format_name_link(code)
        if not pod_format.is_custom(code):
            name = f"**{name}**"
        lines.append(f"{fi.format_emoji(code)} {name} {_format_role_label(guild, code)}")
    return "\n".join(lines)


def _mechanics_note(slots: list[pod_launch.LauncherSlot], several: bool) -> str:
    """How a pod works, seated below the board because it only matters once a reader has picked a time. The
    first-to-fill line closes it, next to the marker it explains, and only when there is more than one
    format, since a single-format board never renders that marker."""
    mechanics = POLL_MECHANICS.format(
        threshold=settings.pod_signal_fire_threshold, lead=pod_launch.REMINDER_LEAD_MIN,
    )
    lines = [mechanics, _next_launcher_note(slots)]
    if several:
        lines.append(POLL_FORMAT_SEVERAL)
    return "\n".join(line for line in lines if line)


def _archive_embed(
    slots: list[pod_launch.LauncherSlot], guild: discord.Guild | None, heading: str,
) -> discord.Embed:
    """The retired card: On This Day plus one line per finished pod, all in the description, so it reads
    as a compact day-history with no empty column space. A second table adds its own line."""
    lines = [_finished_line(slot, guild) for slot in slots if slot.committed]
    body = "\n".join(line for line in lines if line) if lines else "-"
    return discord.Embed(
        description=f"{heading}\n{ARCHIVE_INTRO}\n{body}", color=discord.Color.dark_grey(),
    )


def _lane_order(slots: list[pod_launch.LauncherSlot]) -> list[str]:
    """Lanes in first-seen order, so each lane renders as one column in the order slots arrive. A lane is
    the column a slot belongs to for life, so a slot that rolled from a weekday to a weekend stays in the
    column it started in instead of opening a third one."""
    order: list[str] = []
    for slot in slots:
        lane = lane_of(slot.bucket_key)
        if lane is not None and lane not in order:
            order.append(lane)
    return order


def _lane_slots(slots: list[pod_launch.LauncherSlot], lane: str) -> list[pod_launch.LauncherSlot]:
    """A lane's slots stacked earliest first, so today's block sits above the next day's in the column."""
    matches = [slot for slot in slots if lane_of(slot.bucket_key) == lane]
    return sorted(matches, key=lambda slot: slot.slot_time or datetime.max.replace(tzinfo=timezone.utc))


def _time_groups(
    bucket_slots: list[pod_launch.LauncherSlot],
) -> list[list[pod_launch.LauncherSlot]]:
    """A column's pods grouped by start time, earliest first. A group renders as one dated block, so a slot
    offering two formats reads as two format blocks under one header rather than as two slots."""
    groups: dict[datetime, list[pod_launch.LauncherSlot]] = {}
    far_future = datetime.max.replace(tzinfo=timezone.utc)
    for slot in bucket_slots:
        groups.setdefault(slot.slot_time or far_future, []).append(slot)
    return [groups[slot_time] for slot_time in sorted(groups)]


def _group_locked(group: list[pod_launch.LauncherSlot]) -> bool:
    """Whether every pod at this slot time has started drafting, the only case where the whole group
    collapses to compact lines. One format drafting leaves the other a full joinable block."""
    return all(slot.locked for slot in group)


def _column_value(
    bucket_slots: list[pod_launch.LauncherSlot], guild: discord.Guild | None, pad_finished: int = 0,
) -> str:
    """One lane column. Championship lanes and plain gathering columns render as familiar single blocks. A
    column that stacks a slot whose pods all started above a still-gathering slot leads with one slot-name
    header, then a Played (or Playing) section listing those pods, then a Next section with the upcoming
    date and rosters, so the slot name and date are never doubled.

    Reaching the threshold does not hoist a pod up there, and neither does its lobby opening. A pod keeps
    taking signups until the draft starts, so it stays a full roster block with its thread link until then."""
    if any(slot.championship for slot in bucket_slots):
        blocks = [block for block in (_championship_block(slot, guild) for slot in bucket_slots) if block]
        return f"\n{NBSP}\n".join(blocks) if blocks else "-"
    groups = _time_groups(bucket_slots)
    played = [group for group in groups if _group_locked(group)]
    gathering = [group for group in groups if not _group_locked(group)]
    if not played:
        blocks = []
        for index, group in enumerate(gathering):
            block = _group_block(group, guild, named=index == 0)
            if block:
                blocks.append(block)
        return f"\n{NBSP}\n".join(blocks) if blocks else "-"
    sections: list[str] = []
    played_lines = [_finished_column_line(slot, guild) for group in played for slot in group]
    if played_lines:
        blanks = [NBSP] * max(0, pad_finished - len(played_lines))
        sections.append("\n".join(played_lines + blanks))
    for group in gathering:
        lead = group[0]
        relative = f"<t:{int(lead.slot_time.timestamp())}:R>" if lead.slot_time else ""
        next_label = " ".join(part for part in (emojis.get(NEXT_EMOJI), SECTION_NEXT, relative) if part)
        when = _slot_when_line(lead)
        body = _group_body(group, guild)
        sections.append(f"{next_label}\n{when}\n{body}" if when else f"{next_label}\n{body}")
    lead = gathering[0][0] if gathering else played[0][0]
    header = _slot_name_only(lead, guild)
    if not gathering:
        start = _slot_start_time(played[0][0])
        header = f"{header}{NBSP}{NBSP}{start}" if start else header
    return f"{header}\n" + f"\n{NBSP}\n".join(sections)


def _group_block(
    group: list[pod_launch.LauncherSlot], guild: discord.Guild | None, named: bool = True,
) -> str | None:
    """One full self-contained block for a slot time: the date, then a block per format the slot carries.

    The lane name leads the column's first block only. A later dated block is another time in the same
    column, a pod moved off its slot or a day this column rolled to, and repeating the name there reads as a
    second slot. The Played and Next sections do the same, heading the column once."""
    if bucket_by_key(group[0].bucket_key) is None:
        return None
    parts = [_slot_name_only(group[0], guild)] if named else []
    when = _slot_when_line(group[0])
    if when:
        parts.append(when)
    parts.append(_group_body(group, guild))
    return "\n".join(parts)


def _group_body(group: list[pod_launch.LauncherSlot], guild: discord.Guild | None) -> str:
    """The slot's pods in the day's format order, whatever state each is in, so a format holds its place in
    the column from the moment it is offered until it is played."""
    blocks = [block for block in (_pod_block(slot, guild) for slot in group) if block]
    return f"\n> {NBSP}\n".join(blocks) if blocks else "-"


def _pod_block(slot: pod_launch.LauncherSlot, guild: discord.Guild | None) -> str | None:
    """One pod inside its slot: a compact line once its draft started, otherwise its format header over its
    roster, with a fired pod's thread link above it so the link reads as belonging to that format. The
    compact line is quoted here, unlike in a Played section, so a slot mixing a drafting pod with a
    gathering one reads as one block."""
    if slot.locked:
        return f"> {_finished_column_line(slot, guild)}"
    if slot.set_code is None:
        return None
    block = _roster_block(slot, guild)
    link = _committed_card_link(guild, slot) if slot.committed else None
    return f"{link}\n{block}" if link else block


def _championship_block(slot: pod_launch.LauncherSlot, guild: discord.Guild | None) -> str | None:
    """The championship lane's own block: crown, set symbol, the role at stake, date, then the thread link
    and top RSVPs. The header names `@Set Champion` rather than the event, so the column says what the pod
    is played for. The button below it keeps the event name, since a button label cannot carry a mention."""
    if bucket_by_key(slot.bucket_key) is None:
        return None
    when = _slot_when_line(slot)
    symbol = emojis.get(slot.set_code.lower()) if slot.set_code else ""
    label = role_mention(guild, SET_CHAMPION_ROLE_NAME)
    title_line = " ".join(part for part in (CHAMPIONSHIP_CROWN, symbol, label) if part)
    header = f"{title_line}\n{when}" if when else title_line
    return f"{header}\n{_championship_body(slot, guild)}"


def _slot_name_only(slot: pod_launch.LauncherSlot, guild: discord.Guild | None) -> str:
    """The lane header wears its ping role, so the colored pill both names the column and shows the role a
    player joins to be pinged for it. Weekend lanes keep their own `Weekend` roles: the day a pod runs on is
    worth spelling out, and they carry their weekday counterpart's color so early and late stay one hue."""
    bucket = bucket_by_key(slot.bucket_key)
    slot_emoji = emojis.resolve(bucket.emoji) if bucket else None
    role = find_role(guild, bucket_role_name(slot.bucket_key) or "")
    label = role.mention if role else (bucket.name if bucket else slot.bucket_key)
    return " ".join(part for part in (slot_emoji, label) if part)


def _slot_when_line(slot: pod_launch.LauncherSlot) -> str:
    return f"<t:{int(slot.slot_time.timestamp())}:F>" if slot.slot_time else ""


def _slot_start_time(slot: pod_launch.LauncherSlot) -> str:
    """Clock-only start time for a column whose pods have all started, where no Next section carries the
    full date and the column would otherwise say nothing about when the pod ran."""
    return f"<t:{int(slot.slot_time.timestamp())}:t>" if slot.slot_time else ""


def _finished_line(slot: pod_launch.LauncherSlot, guild: discord.Guild | None) -> str:
    """The archive form: a full-width line, so the event name and the winner both run at full length."""
    return _finished_row(slot, guild, _finished_link_text(slot, full_name=True), slot.winner or "")


def _finished_column_line(slot: pod_launch.LauncherSlot, guild: discord.Guild | None) -> str:
    """The column form, shrunk to fit a third of the embed width. A row that wraps in one column while its
    neighbour holds one line pushes every row below it out of level, so the row gives up the date first,
    which the card title and the Next section both still carry, and cuts the winner's name only when that
    is not enough. Discord wraps on a pixel width no bot can measure, so the budget is a character
    estimate calibrated against a live card."""
    text, winner = _fit_row(_finished_link_text(slot, full_name=False), slot.winner or "")
    return _finished_row(slot, guild, text, winner)


def _finished_row(
    slot: pod_launch.LauncherSlot, guild: discord.Guild | None, text: str, winner: str,
) -> str:
    """A trophy once the pod is played (else a playing mark), the pod name linking to its Discord thread,
    then the LLU glyph and the winner linking to that player's seat on the website pod page. A team draft
    is credited to its winning side, which has no seat, so that name links nowhere."""
    mark = FINISHED_MARK if slot.finished else PLAYING_MARK
    card_url = _card_url(guild, slot)
    pod_link = f"[__**{text}**__]({card_url})" if card_url and text else text
    parts = [f"{mark} {pod_link}" if pod_link else mark]
    if winner:
        seat_url = _winner_seat_url(slot)
        name = f"[__**{winner}**__]({seat_url})" if seat_url else f"__**{winner}**__"
        parts.append(f"{emojis.prefix('llu')}{name}")
    return f"{NBSP}{NBSP}".join(parts)


def _fit_row(text: str, winner: str) -> tuple[str, str]:
    """The pod name and the winner cut down to the budget: the date goes first, then the winner's name."""
    if _row_units(text, winner) > COLUMN_FIT_BUDGET:
        text = _without_date(text)
    room = COLUMN_FIT_BUDGET - _row_units(text, "") - WINNER_GAP_UNITS
    return text, _clipped(winner, room) if winner and len(winner) > room else winner


def _row_units(text: str, winner: str) -> int:
    """The row's width in characters, an emoji counting as several since it renders wider than a glyph."""
    units = EMOJI_UNITS + 1 + len(text)
    return units + WINNER_GAP_UNITS + len(winner) if winner else units


def _without_date(text: str) -> str:
    return NAME_DATE_RE.sub("", text, count=1)


def _clipped(winner: str, room: int) -> str:
    keep = max(room - len(ELLIPSIS), WINNER_MIN_CHARS)
    return winner if keep >= len(winner) else f"{winner[:keep].rstrip()}{ELLIPSIS}"


def _finished_link_text(slot: pod_launch.LauncherSlot, full_name: bool) -> str:
    """The archive keeps the full event name to tell Early from Late; a column already carries the slot
    name in its header, so it drops to set and date, and a split table to its ordinal."""
    name = slot.thread_name or ""
    if full_name:
        return name
    bucket = bucket_by_key(slot.bucket_key)
    if bucket:
        name = name.replace(f" {bucket.name}", "")
    return TABLE_SUFFIX_RE.sub(lambda match: f" {_ordinal(int(match.group(1)))}", name)


def _ordinal(number: int) -> str:
    if 11 <= number % 100 <= 13:
        return f"{number}th"
    return f"{number}{ORDINAL_SUFFIXES.get(number % 10, 'th')}"


def _winner_seat_url(slot: pod_launch.LauncherSlot) -> str | None:
    """The winner's seat on the pod's website page, mirroring the frontend's `/pods/<event>/<player>` route
    built from the event name and the winner's player slug. Without a slug it points at the pod page
    itself, which is where a team draft and an unlinked winner land."""
    if not slot.thread_name:
        return None
    base = f"{settings.public_site_url.rstrip('/')}/pods/{slugify(slot.thread_name)}"
    return f"{base}/{slot.winner_slug}" if slot.winner_slug else base


def _championship_body(slot: pod_launch.LauncherSlot, guild: discord.Guild | None) -> str:
    """The championship lane on the launcher: a link into the thread and the current top Yes RSVPs,
    read-only. Signup happens in the thread, so this lane carries no join toggle."""
    lines: list[str] = []
    link = _committed_card_link(guild, slot)
    if link:
        lines.append(link)
    for index, name in enumerate(slot.names[:CHAMPIONSHIP_POINTER_TOP], 1):
        lines.append(f"> {index}. {name}")
    return "\n".join(lines) if lines else "-"


def _roster_block(slot: pod_launch.LauncherSlot, guild: discord.Guild | None) -> str:
    """One pod's block: the words its own button carries, over its own roster, so a press lands on a block a
    reader recognizes. A member who also signed up for another format at this slot carries the flexible
    marker, so the crowd that will play either reads at a glance. An empty pod still renders its header over
    a dash, so a slot nobody joined yet keeps advertising every format it offers. A closed slot says so in
    place of the roster."""
    icon = fi.format_emoji(slot.set_code)
    label = f"**{_named_pod_label(slot.bucket_key, slot.set_code)}**"
    closed = slot.status == STATUS_EXPIRED and not slot.committed
    count = f" **({slot.count})**" if slot.count and not closed else ""
    if closed:
        lines = [f"> {MARKER_CLOSED}"]
    else:
        lines = [f"> {_marked_name(name, slot.shared_names)}" for name in slot.names] or ["> -"]
    return "\n".join([f"> {icon} {label}{count}"] + lines)


def _marked_name(name: str, shared_names: tuple[str, ...]) -> str:
    return f"{fi.FLEXIBLE_MARKER} {name}" if name in shared_names else name


def _format_role_name(code: str) -> str:
    """The role a format pings: the latest set pings Latest Set, a cube pings Cube, a past set pings
    Flashback. A cube is drafted out of the latest set's client, so it is not a flashback, and the two
    crowds are not the same people."""
    if code == active_set_code():
        return fi.LATEST_SET_ROLE_NAME
    if pod_format.is_custom(code):
        return fi.CUBE_ROLE_NAME
    return fi.FLASHBACK_ROLE_NAME


def _format_role_label(guild: discord.Guild | None, code: str) -> str:
    return role_mention(guild, _format_role_name(code))


def _jump_url(guild: discord.Guild | None, channel_id: str, message_id: str | None = None) -> str:
    scope = guild.id if guild is not None else "@me"
    base = f"https://discord.com/channels/{scope}/{channel_id}"
    return f"{base}/{message_id}" if message_id else base


def _card_url(guild: discord.Guild | None, slot: pod_launch.LauncherSlot) -> str | None:
    """A committed pod's jump URL: its coordination card when tracked, else its thread. A card jump link
    survives thread archiving where a `<#thread>` mention renders as #unknown."""
    if slot.card_channel_id and slot.card_message_id:
        return _jump_url(guild, slot.card_channel_id, slot.card_message_id)
    if slot.thread_id:
        return _jump_url(guild, slot.thread_id, slot.thread_message_id)
    return None


def _committed_card_link(guild: discord.Guild | None, slot: pod_launch.LauncherSlot) -> str | None:
    """A committed pod's full-name link to its coordination card, for the championship lane."""
    if not slot.thread_name:
        return None
    url = _card_url(guild, slot)
    return f"[__**{slot.thread_name}**__]({url})" if url else None


def build_play_again_prompt(bucket_keys: list[str]) -> tuple[discord.Embed, "PlayAgainView"]:
    """The next-day re-signup prompt posted into a finished pod's thread: a thank-you over one button per pod
    the same slot offers tomorrow. An embed, so the thank-you carries as a heading and the prompt reads as its
    own card in a thread full of match reports.

    The buttons name tomorrow's formats, not the one just played: a group that drafted a cube tonight is still
    the group to invite back when tomorrow's slot runs a past set, and picking one of the formats on offer for
    them would decide something they can decide themselves."""
    body = PLAY_AGAIN_INTRO.format(
        love=emojis.get(PLAY_AGAIN_LOVE_EMOJI),
        next=emojis.get(NEXT_EMOJI),
        slot=_slot_short_name(time_key_of(bucket_keys[0])),
    )
    return discord.Embed(description=body, color=discord.Color.green()), PlayAgainView(bucket_keys)


class PlayAgainView(discord.ui.View):
    """One button per pod the slot offers on the next day."""

    def __init__(self, bucket_keys: list[str]) -> None:
        super().__init__(timeout=None)
        for bucket_key in bucket_keys:
            self.add_item(PlayAgainButton(bucket_key))


PLAY_AGAIN_PREFIX = "pod_play_again"


class PlayAgainButton(
    discord.ui.DynamicItem[discord.ui.Button],
    template=rf"{PLAY_AGAIN_PREFIX}:(?P<bucket>.+)",
):
    """The pod it writes to is resolved at click time, not at post time: the prompt outlives the day it was
    posted on, and the soonest open pod of that slot and format is always the one the launcher is offering.
    Dynamic so the key can name the format, which no startup registration could enumerate."""

    def __init__(self, bucket_key: str) -> None:
        super().__init__(discord.ui.Button(
            label=PLAY_AGAIN_BUTTON.format(pod=_named_pod_label(bucket_key)),
            style=discord.ButtonStyle.success, emoji=_slot_button_emoji(bucket_key),
            custom_id=f"{PLAY_AGAIN_PREFIX}:{bucket_key}",
        ))
        self.bucket_key = bucket_key

    @classmethod
    async def from_custom_id(cls, interaction, item, match):
        return cls(match["bucket"])

    async def callback(self, interaction: discord.Interaction) -> None:
        await _handle_play_again_click(interaction, self.bucket_key)


async def _handle_play_again_click(interaction: discord.Interaction, bucket_key: str) -> None:
    await interaction.response.defer(ephemeral=True, thinking=True)
    ref = await asyncio.to_thread(
        pod_launch.open_slot_for_bucket_sync, bucket_key, datetime.now(timezone.utc),
    )
    if ref is None:
        await interaction.followup.send(_organizer_notice(MSG_SLOT_CLOSED, interaction.guild), ephemeral=True)
        return
    signal_id, launcher_message_id, slot_time = ref
    joined = await asyncio.to_thread(
        pod_launch.join_slot_signal_sync, signal_id, str(interaction.user.id), interaction.user.display_name,
    )
    await interaction.followup.send(_slot_effect_lead(bucket_key, slot_time), ephemeral=True)
    if not joined:
        return
    if isinstance(interaction.user, discord.Member):
        await grant_pod_drafters(interaction.user)
        await _grant_slot_role(interaction.user, bucket_key)
    board_date = await asyncio.to_thread(pod_launch.launcher_date_for_message_sync, launcher_message_id)
    if board_date is not None:
        await _rerender_poll(interaction.client, launcher_message_id, board_date)
    await refresh_slot_nudge(interaction.client, signal_id)


class PodPollView(discord.ui.View):
    """The day's surface, one button per pod: a gathering pod renders its join toggle, a pod that fired
    renders a Yes/No toggle writing to its scheduled card, and a pod whose draft started renders nothing —
    its own line already links to it. Each button names the format it joins, so the press itself says which
    pod it commits to and no stored preference is consulted. Every button is a DynamicItem, so a board that
    outlives a restart keeps working without a fixed set of keys to pre-register. Bucket emoji are
    application emoji that can't render in label text, so each button gets its glyph in the emoji slot."""

    def __init__(
        self, slots: list[pod_launch.LauncherSlot], guild: discord.Guild | None = None,
    ) -> None:
        super().__init__(timeout=None)
        for lane in _lane_order(slots):
            for slot in _lane_slots(slots, lane):
                item = _slot_item(slot, guild)
                if item is not None:
                    self.add_item(item)


def _slot_item(
    slot: pod_launch.LauncherSlot, guild: discord.Guild | None,
) -> "discord.ui.Item | None":
    if bucket_by_key(slot.bucket_key) is None:
        return None
    if slot.championship:
        if not slot.thread_id:
            return None
        return discord.ui.Button(
            style=discord.ButtonStyle.link,
            url=_jump_url(guild, slot.thread_id, slot.thread_message_id),
            label=CHAMPIONSHIP_SLOT_LABEL, emoji=CHAMPIONSHIP_CROWN,
        )
    if slot.locked or slot.set_code is None:
        return None
    if slot.committed:
        if slot.card_message_id:
            return SlotRsvpButton(slot.bucket_key)
        if slot.thread_id:
            return discord.ui.Button(
                style=discord.ButtonStyle.link,
                url=_jump_url(guild, slot.thread_id, slot.thread_message_id),
                label=_named_pod_label(slot.bucket_key), emoji=_slot_button_emoji(slot.bucket_key),
            )
        return None
    return SlotToggleButton(slot.bucket_key, closed=slot.status == STATUS_EXPIRED)


def _named_pod_label(bucket_key: str, set_code: str | None = None) -> str:
    """`Early NEO`, the shortest label that names both the time and the format a press commits to, and the
    same words that pod's roster block heads itself with. `set_code` names the format for a slot whose key
    does not carry one; with neither, the label falls back to the slot's own name."""
    code = format_of(bucket_key) or set_code
    short = _slot_short_name(time_key_of(bucket_key))
    return f"{short} {code}" if code else short


def _slot_button_emoji(bucket_key: str) -> "discord.Emoji | str | None":
    """The format's glyph for a named pod's button, the slot's own for a key carrying no format."""
    code = format_of(bucket_key)
    if code:
        return fi.format_emoji(code)
    bucket = bucket_by_key(bucket_key)
    return emojis.resolve(bucket.emoji) if bucket else None


INTEREST_BUTTON_ID = "pod_poll_interest"


def interest_button() -> discord.ui.Button:
    """The preference picker as a button, kept for the future flashback-season surface. No live board
    carries it: the launcher names each pod's format on its own button, so a stored preference decides
    nothing about a signup. `InterestPromptView` and the four preference columns stay for that surface."""
    button = discord.ui.Button(
        label=MSG_FORMAT_PREFERENCE_BUTTON, style=discord.ButtonStyle.primary,
        custom_id=INTEREST_BUTTON_ID, emoji=fi.FLEXIBLE_EMOJI, row=4,
    )

    async def callback(interaction: discord.Interaction) -> None:
        await _open_interest_prompt(interaction)

    button.callback = callback
    return button


async def _launcher_signal_date(message: discord.Message) -> date:
    stored = await asyncio.to_thread(pod_launch.launcher_date_for_message_sync, str(message.id))
    return stored or message.created_at.astimezone(SCHEDULE_TZ).date()


async def _open_interest_prompt(interaction: discord.Interaction) -> None:
    """Open a per-user ephemeral picker seeded with the player's standing preference. The launcher board
    only changes once they confirm, so a mis-tap costs nothing."""
    await interaction.response.defer(ephemeral=True, thinking=True)
    launcher_message_id = str(interaction.message.id)
    signal_date = await _launcher_signal_date(interaction.message)
    await _send_interest_prompt(interaction, launcher_message_id, signal_date)


async def open_interest_prompt_from_card(interaction: discord.Interaction) -> None:
    """The picker opened from a grant card's Format Preference button, resolving the newest launcher so
    Confirm buttons target its slots. With no launcher on record the picker still saves the standing
    preference; its Confirm buttons refuse through the normal inactive-poll path."""
    await interaction.response.defer(ephemeral=True, thinking=True)
    launcher = await asyncio.to_thread(pod_launch.latest_launcher_sync)
    if launcher is not None:
        launcher_message_id, signal_date = launcher
    else:
        launcher_message_id, signal_date = "", datetime.now(SCHEDULE_TZ).date()
    await _send_interest_prompt(interaction, launcher_message_id, signal_date)


async def _send_interest_prompt(
    interaction: discord.Interaction, launcher_message_id: str, signal_date: date,
    event_id: str | None = None,
) -> None:
    """Save only. The picker records a standing preference and nothing else: every launcher pod names the
    format it plays on its own button, so no signup is ever inferred from what a player saved here."""
    user_id = str(interaction.user.id)
    current = await asyncio.to_thread(pod_launch.player_interest_sync, user_id)
    ranking = await asyncio.to_thread(pod_launch.player_flashback_ranking_sync, user_id)
    cubes = await asyncio.to_thread(pod_launch.player_cube_choices_sync, user_id)
    view = InterestPromptView(launcher_message_id, signal_date, current, ranking, cubes, event_id)
    await interaction.followup.send(view=view, ephemeral=True)


REMINDER_FORMAT_PREFIX = "podremindfmt"


class ReminderFormatPreferenceButton(
    discord.ui.DynamicItem[discord.ui.Button],
    template=rf"{REMINDER_FORMAT_PREFIX}:(?P<event_id>.+)",
):
    """Format Preference on the T-60 roster reminder. Opens the same picker as the launcher, minus the
    per-slot Confirm buttons, so there is only Save. The event id rides in the custom_id so Save can
    re-render this pod's card and reminder, and so it keeps working after a restart."""

    def __init__(self, event_id: str) -> None:
        super().__init__(discord.ui.Button(
            label=MSG_FORMAT_PREFERENCE_BUTTON, style=discord.ButtonStyle.primary,
            emoji=fi.FLEXIBLE_EMOJI, custom_id=f"{REMINDER_FORMAT_PREFIX}:{event_id}",
        ))
        self.event_id = event_id

    @classmethod
    async def from_custom_id(cls, interaction, item, match):
        return cls(match["event_id"])

    async def callback(self, interaction: discord.Interaction) -> None:
        await open_interest_prompt_from_reminder(interaction, self.event_id)


async def open_interest_prompt_from_reminder(interaction: discord.Interaction, event_id: str) -> None:
    """The picker opened from a pod's roster reminder: Save only, no per-slot Confirm. Resolves the day's
    launcher so Save still updates the launcher board and the player's standing preference, and carries
    the event id so Save re-renders this pod's card and reminder."""
    await interaction.response.defer(ephemeral=True, thinking=True)
    launcher = await asyncio.to_thread(pod_launch.latest_launcher_sync)
    if launcher is not None:
        launcher_message_id, signal_date = launcher
    else:
        launcher_message_id, signal_date = "", datetime.now(SCHEDULE_TZ).date()
    await _send_interest_prompt(interaction, launcher_message_id, signal_date, event_id=event_id)


def build_reminder_view(event_id: str, format_locked: bool = False) -> discord.ui.View:
    """The roster reminder's controls: Sign Up / Can't recording against the pod, and Format Preference
    opening the Save-only picker. All carry the event id so they resolve the pod after a restart. A
    format-locked pod drops Format Preference, since its set never resolves from the roster."""
    view = discord.ui.View(timeout=None)
    view.add_item(ReminderRsvpButton(RSVP_YES, event_id))
    view.add_item(ReminderRsvpButton(RSVP_NO, event_id))
    if not format_locked:
        view.add_item(ReminderFormatPreferenceButton(event_id))
    return view


register_format_preference_opener(open_interest_prompt_from_card)
register_reminder_view_builder(build_reminder_view)


def _slot_short_name(bucket_key: str) -> str:
    bucket = bucket_by_key(bucket_key)
    return bucket.name.replace(" Pod", "") if bucket else bucket_key


class InterestPromptView(discord.ui.LayoutView):
    """Ephemeral preference picker opened from the welcome card's Format Preference button. A Components V2
    layout: prompt, the interest select, and Save. A Flashback pick inserts the ranking line above a Rank Sets
    button; a Cube pick inserts the chosen-cubes line above a Choose Cubes button that reveals the server cube
    list. Short-lived and per-user, so it carries no persistent custom_ids."""

    def __init__(
        self, launcher_message_id: str, signal_date: date, current: list[str], ranking: list[str],
        cubes: list[str], event_id: str | None = None,
    ) -> None:
        super().__init__(timeout=300)
        self.launcher_message_id = launcher_message_id
        self.signal_date = signal_date
        self.values = fi.normalize(current)
        self.ranking = list(ranking)
        self.cubes = list(cubes)
        self.event_id = event_id
        self._rebuild()

    def _rebuild(self) -> None:
        self.clear_items()
        container = discord.ui.Container(accent_colour=discord.Color.green())
        container.add_item(discord.ui.TextDisplay(MSG_INTEREST_PROMPT))
        self.select = _interest_menu(self.values)
        self.select.callback = self._on_select
        select_row = discord.ui.ActionRow()
        select_row.add_item(self.select)
        container.add_item(select_row)
        if fi.FLASHBACK in self.values:
            if self.ranking:
                ranking_text = MSG_YOUR_SETS_LINE.format(ranking=fi.ranking_display(self.ranking))
            else:
                ranking_text = MSG_RANK_EMPTY
            container.add_item(discord.ui.TextDisplay(ranking_text))
            rank = discord.ui.Button(label=RANK_BUTTON_LABEL, style=discord.ButtonStyle.primary,
                                     emoji=RANK_BUTTON_EMOJI)
            rank.callback = self._on_rank
            rank_row = discord.ui.ActionRow()
            rank_row.add_item(rank)
            container.add_item(rank_row)
            container.add_item(discord.ui.Separator())
        if fi.CUBE in self.values:
            self._add_cube_section(container)
        button_row = discord.ui.ActionRow()
        save = discord.ui.Button(label=SAVE_BUTTON_LABEL, style=discord.ButtonStyle.success,
                                 emoji=SAVE_BUTTON_EMOJI)
        save.callback = self._on_save
        button_row.add_item(save)
        container.add_item(button_row)
        self.add_item(container)

    async def _on_select(self, interaction: discord.Interaction) -> None:
        self.values = fi.normalize(self.select.values)
        self._rebuild()
        await interaction.response.edit_message(view=self)

    async def _on_rank(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_modal(_RankModal(self))

    def _add_cube_section(self, container: discord.ui.Container) -> None:
        self.cube_select = _cube_menu(self.cubes)
        self.cube_select.callback = self._on_cube_select
        cube_row = discord.ui.ActionRow()
        cube_row.add_item(self.cube_select)
        container.add_item(cube_row)
        if self.cubes:
            container.add_item(discord.ui.TextDisplay(
                MSG_YOUR_CUBES_LINE.format(cubes=_cube_display(self.cubes))))
        container.add_item(discord.ui.Separator())

    async def _on_cube_select(self, interaction: discord.Interaction) -> None:
        picked = set(self.cube_select.values)
        self.cubes = [fmt.code for fmt in pod_format.custom_formats() if fmt.code in picked]
        self._rebuild()
        await interaction.response.edit_message(view=self)

    async def _persist(self, user: "discord.User | discord.Member") -> None:
        await asyncio.to_thread(
            pod_launch.set_launcher_interest_sync,
            self.launcher_message_id, str(user.id), getattr(user, "name", user.display_name),
            user.display_name, None, self.values, self.signal_date,
        )
        await asyncio.to_thread(pod_launch.set_flashback_ranking_sync, str(user.id), self.ranking)
        await asyncio.to_thread(pod_launch.set_cube_choices_sync, str(user.id), self.cubes)

    async def _finish(self, interaction: discord.Interaction, text: str) -> None:
        done = discord.ui.LayoutView(timeout=None)
        done.add_item(discord.ui.Container(
            discord.ui.TextDisplay(text), accent_colour=discord.Color.green(),
        ))
        await interaction.edit_original_response(view=done)
        self.stop()

    async def _dismiss(self, interaction: discord.Interaction) -> None:
        """Drop the picker without a closing message — for a Confirm whose grant card already carries
        the join confirmation and the saved preference, so the click ends with one message, not two."""
        try:
            await interaction.delete_original_response()
        except discord.HTTPException:
            log.warning("could not delete the preference picker", exc_info=True)
        self.stop()

    async def _on_save(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer()
        await self._persist(interaction.user)
        if self.event_id is not None:
            await self._finish(interaction, self._saved_text())
            await self._resync_committed_pod(interaction.client)
            return
        await _rerender_poll(
            interaction.client, self.launcher_message_id, self.signal_date, interaction.channel)
        await self._finish(interaction, self._saved_text())

    def _saved_text(self) -> str:
        saved = MSG_INTEREST_SAVED.format(choice=fi.preference_display(self.values))
        if fi.FLASHBACK in self.values and self.ranking:
            saved = f"{saved}\n{MSG_YOUR_SETS_LINE.format(ranking=fi.ranking_display(self.ranking))}"
        if fi.CUBE in self.values and self.cubes:
            saved = f"{saved}\n{MSG_YOUR_CUBES_LINE.format(cubes=_cube_display(self.cubes))}"
        return saved

    async def _resync_committed_pod(self, bot: commands.Bot) -> None:
        """Run after the Saved ack so the click never waits on the edits: re-render the launcher board and
        this pod's card and reminder off the fresh roster. Called only from the reminder's Save."""
        await asyncio.gather(
            _rerender_poll(bot, self.launcher_message_id, self.signal_date),
            refresh_event_rsvp_surfaces(bot, self.event_id),
        )


class _RankModal(discord.ui.Modal, title=RANK_MODAL_TITLE):
    codes = discord.ui.TextInput(
        label=RANK_MODAL_FIELD, placeholder=RANK_MODAL_PLACEHOLDER, required=False, max_length=100,
    )

    def __init__(self, view: "InterestPromptView") -> None:
        super().__init__()
        self.prompt = view
        self.codes.default = " ".join(view.ranking)
        self.remove_item(self.codes)
        self.add_item(discord.ui.TextDisplay(RANK_MODAL_EXPLAINER))
        self.add_item(self.codes)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        codes = pod_format_poll.normalize_write_ins(str(self.codes.value))
        self.prompt.ranking = codes[: fi.FLASHBACK_RANKING_MAX]
        self.prompt._rebuild()
        await interaction.response.edit_message(view=self.prompt)




def _interest_menu(selected: list[str]) -> discord.ui.Select:
    """A multi-select over the three interests, each an independent choice defaulted to the player's saved
    values. Picking several means "up for any of these"; picking latest and flashback both is the flexible
    crowd that fills either table."""
    chosen = set(fi.normalize(selected))
    options = [
        discord.SelectOption(
            label=fi.INTEREST_LABEL[fi.LATEST], value=fi.LATEST, emoji=fi.latest_emoji(),
            description=set_name_for(active_set_code()), default=fi.LATEST in chosen),
        discord.SelectOption(
            label=fi.INTEREST_LABEL[fi.FLASHBACK], value=fi.FLASHBACK, emoji=fi.flashback_emoji(),
            description=INTEREST_DESC_FLASHBACK, default=fi.FLASHBACK in chosen),
        discord.SelectOption(
            label=fi.INTEREST_LABEL[fi.CUBE], value=fi.CUBE, emoji=fi.interest_emoji(fi.CUBE),
            description=INTEREST_DESC_CUBE, default=fi.CUBE in chosen),
    ]
    return discord.ui.Select(
        placeholder=INTEREST_PLACEHOLDER, min_values=0, max_values=len(options), options=options,
    )


def _cube_menu(selected: list[str]) -> discord.ui.Select:
    """A multi-select over the server's registered cubes, defaulted to the player's saved choices."""
    chosen = set(selected)
    options = [
        discord.SelectOption(label=fmt.pick_label, value=fmt.code, emoji=fi.cube_emoji(), default=fmt.code in chosen)
        for fmt in pod_format.custom_formats()
    ]
    return discord.ui.Select(
        placeholder=CUBE_SELECT_PLACEHOLDER, min_values=0, max_values=len(options), options=options,
    )


def _cube_display(codes: list[str]) -> str:
    """The chosen cubes as bold underlined links to their CubeCobra pages, the cube glyph ahead of each,
    in registry order and spaced apart."""
    picked = set(codes)
    links = [
        f"{fi.cube_emoji()} [__**{fmt.link_text}**__]({fmt.url})"
        for fmt in pod_format.custom_formats() if fmt.code in picked
    ]
    return (NBSP * 3).join(links)


SLOT_TOGGLE_PREFIX = "pod_poll"
SLOT_RSVP_PREFIX = "pod_slot_rsvp"


class SlotToggleButton(
    discord.ui.DynamicItem[discord.ui.Button],
    template=rf"{SLOT_TOGGLE_PREFIX}:(?P<bucket>.+)",
):
    """Join or leave one named pod. The key carries the slot and the format, so there is no fixed set of
    keys a startup registration could enumerate and the button survives a restart on its own."""

    def __init__(self, bucket_key: str, closed: bool = False) -> None:
        super().__init__(discord.ui.Button(
            label=_named_pod_label(bucket_key),
            style=discord.ButtonStyle.secondary if closed else discord.ButtonStyle.success,
            disabled=closed, custom_id=f"{SLOT_TOGGLE_PREFIX}:{bucket_key}",
            emoji=_slot_button_emoji(bucket_key),
        ))
        self.bucket_key = bucket_key

    @classmethod
    async def from_custom_id(cls, interaction, item, match):
        return cls(match["bucket"])

    async def callback(self, interaction: discord.Interaction) -> None:
        await _handle_poll_click(interaction, self.bucket_key)


class SlotRsvpButton(
    discord.ui.DynamicItem[discord.ui.Button],
    template=rf"{SLOT_RSVP_PREFIX}:(?P<bucket>.+)",
):
    """The same toggle for a pod that already fired: it writes Yes or No on that pod's scheduled card. The
    key names the format, so a slot carrying two pods gets one button each instead of one ambiguous one."""

    def __init__(self, bucket_key: str) -> None:
        super().__init__(discord.ui.Button(
            label=_named_pod_label(bucket_key), style=discord.ButtonStyle.success,
            custom_id=f"{SLOT_RSVP_PREFIX}:{bucket_key}", emoji=_slot_button_emoji(bucket_key),
        ))
        self.bucket_key = bucket_key

    @classmethod
    async def from_custom_id(cls, interaction, item, match):
        return cls(match["bucket"])

    async def callback(self, interaction: discord.Interaction) -> None:
        await _handle_slot_rsvp_click(interaction, self.bucket_key)


async def _fetch_launcher_message(
    channel: "discord.abc.Messageable | None", message_id: str,
) -> "discord.Message | None":
    if channel is None:
        return None
    try:
        return await channel.fetch_message(int(message_id))
    except (discord.HTTPException, AttributeError):
        return None


async def _apply_slot_join(
    interaction: discord.Interaction, *, launcher_message: discord.Message, signal_date: date,
    bucket_key: str, action: str, notify_effect: bool = False,
) -> tuple[str | None, str | None]:
    """Join or toggle a launcher pod for the clicker, then run the shared fire, launcher re-render, role
    grant, announce, and nudge-refresh steps. Returns (error, notice): an error string when the pod is gone
    or closed, and the grant/welcome notice that was posted, so a caller with its own confirmation can skip
    it instead of doubling up.

    `notify_effect` confirms the add or the removal ephemerally. A join always gets that confirmation, even
    when a public welcome went to pod chat: the welcome is for the channel, and only the ephemeral says which
    pod the clicker is on, when it starts, and which slot role the click granted them. The one exception is
    the grant card, which already carries all of that folded in."""
    message_id = str(launcher_message.id)
    result = await asyncio.to_thread(
        pod_launch.toggle_member_sync,
        message_id, bucket_key, str(interaction.user.id), interaction.user.display_name, action,
    )
    if result is None:
        return _organizer_notice(MSG_POLL_INACTIVE, interaction.guild), None
    if result.closed:
        return _organizer_notice(MSG_SLOT_CLOSED, interaction.guild), None
    fired = (
        result.joined
        and should_fire(result.state.count, settings.pod_signal_fire_threshold)
        and result.state.slot_time is not None
        and slot_can_fire(result.state.slot_time, datetime.now(timezone.utc))
        and await asyncio.to_thread(pod_launch.claim_slot_fire_sync, result.state.signal_id)
    )
    guild = getattr(launcher_message.channel, "guild", None) or interaction.guild
    slots = await asyncio.to_thread(pod_launch.launcher_snapshot_sync, message_id, signal_date)
    try:
        await launcher_message.edit(embed=build_poll_embed(slots, guild), view=PodPollView(slots, guild))
    except discord.HTTPException:
        log.warning(f"could not re-render launcher message {message_id}", exc_info=True)
    granted_role = None
    spec = None
    first_pod = False
    if result.joined and isinstance(interaction.user, discord.Member):
        first_pod = await grant_pod_drafters(interaction.user)
        granted_role = await _grant_slot_role(interaction.user, bucket_key)
        if granted_role is not None:
            spec = spec_named(granted_role.name)
    ping = slot_grant_ping(spec) if spec is not None else None
    lead = None
    if result.joined:
        on_formats = await asyncio.to_thread(
            pod_launch.joined_formats_at_slot_sync,
            message_id, result.state.slot_time, str(interaction.user.id),
        )
        lead = _slot_effect_lead(bucket_key, result.state.slot_time, on_formats)
    notice = await announce_pod_grant(
        interaction, first_pod=first_pod, granted_role=granted_role, spec=spec, ping=ping,
        card_lead=lead,
    )
    if notify_effect and result.joined and notice != NOTICE_GRANT:
        if granted_role is not None and ping is not None:
            lead = f"{lead}\n{pod_role_grant_text(granted_role.mention, ping)}"
        await send_join_confirmation_card(interaction, lead=lead, accent=discord.Color.green())
    elif notify_effect and result.changed:
        await interaction.followup.send(
            embed=pod_removed_embed(_gathering_pod_name(bucket_key, result.state.slot_time)),
            ephemeral=True,
        )
    if fired:
        asyncio.create_task(_launch_slot(interaction.client, result.state, message_id))
    elif result.changed:
        await refresh_slot_nudge(interaction.client, result.state.signal_id)
    return None, notice


async def _handle_poll_click(interaction: discord.Interaction, bucket_key: str) -> None:
    await interaction.response.defer()
    signal_date = await _launcher_signal_date(interaction.message)
    err, _ = await _apply_slot_join(
        interaction, launcher_message=interaction.message, signal_date=signal_date,
        bucket_key=bucket_key, action="toggle", notify_effect=True,
    )
    if err:
        await interaction.followup.send(err, ephemeral=True)


async def _handle_slot_rsvp_click(interaction: discord.Interaction, bucket_key: str) -> None:
    """A fired pod's button toggles the clicker on its scheduled card: Yes when they were out or Maybe, No
    when they already held Yes. The card is read off the board's own snapshot by the key the button carries,
    so a slot holding two pods writes to the one that was pressed. The write and every follow-on run through
    the card's shared apply_card_rsvp, so the card, the launcher, and the native event re-render in step and
    the answer names the pod off its own event, reading the same as a press on a pod that has not fired."""
    signal_date = await _launcher_signal_date(interaction.message)
    slots = await asyncio.to_thread(
        pod_launch.launcher_snapshot_sync, str(interaction.message.id), signal_date,
    )
    slot = _slot_by_key(slots, bucket_key)
    if slot is None or slot.card_message_id is None:
        await interaction.response.send_message(_organizer_notice(MSG_SLOT_CLOSED, interaction.guild), ephemeral=True)
        return
    card_message_id = slot.card_message_id
    current = await asyncio.to_thread(
        pod_launch.card_rsvp_for_user_sync, card_message_id, str(interaction.user.id),
    )
    target = RSVP_NO if current == RSVP_YES else RSVP_YES
    launcher_message = interaction.message
    await apply_card_rsvp(interaction, card_message_id, target, refresh_launcher=False)
    guild = getattr(launcher_message.channel, "guild", None) or interaction.guild
    slots = await asyncio.to_thread(pod_launch.launcher_snapshot_sync, str(launcher_message.id), signal_date)
    try:
        await launcher_message.edit(embed=build_poll_embed(slots, guild), view=PodPollView(slots, guild))
    except discord.HTTPException:
        log.warning(f"could not re-render launcher message {launcher_message.id}", exc_info=True)


def _slot_by_key(
    slots: list[pod_launch.LauncherSlot], bucket_key: str,
) -> pod_launch.LauncherSlot | None:
    """The pod a press acts on, matched on the key the button carries. A rolled column stacks two days of one
    format on one board, so the soonest still-joinable one wins and a played pod stands in when none is."""
    matches = [slot for slot in slots if slot.bucket_key == bucket_key]
    for slot in matches:
        if not slot.locked:
            return slot
    return matches[-1] if matches else None


def _slot_effect_lead(
    bucket_key: str, slot_time: datetime | None, on_formats: list[str] | None = None,
) -> str:
    """The join confirmation as card text: folded into the grant card when a fresh role grant rides
    the same click, else the lead of the plain confirmation card.

    A clicker now on more than one pod of that slot is told which ones and what happens next. Nothing else on
    the surface explains what signing up twice does, and the click that just did it is when it matters."""
    lead = f"### {MSG_POD_ADDED.format(name=_gathering_pod_name(bucket_key, slot_time))}"
    if slot_time is not None:
        lead = f"{lead}\n{MSG_DRAFT_STARTS.format(unix=int(slot_time.timestamp()))}"
    if on_formats and len(on_formats) > 1:
        lead = f"{lead}\n{_several_pods_line(bucket_key, on_formats)}"
    return lead


def _organizer_notice(template: str, guild: discord.Guild | None) -> str:
    return template.format(organizer=organizer_mention(guild))


def _several_pods_line(bucket_key: str, on_formats: list[str]) -> str:
    """`You are on both Early Pods: MSH & Peasant Cube`, over the promise that decides where they play."""
    names = [pod_format.format_display(code) for code in on_formats]
    listed = f"{', '.join(names[:-1])} & {names[-1]}"
    slot = _slot_short_name(time_key_of(bucket_key))
    if len(names) == 2:
        pods = MSG_ON_BOTH_PODS.format(slot=slot, formats=listed)
    else:
        pods = MSG_ON_SEVERAL_PODS.format(count=len(names), slot=slot, formats=listed)
    return f"{pods}\n{MSG_FIRST_POD_TO_FILL}"


def _gathering_pod_name(bucket_key: str, slot_time: datetime | None) -> str:
    """The name a pod that has not fired yet will carry once it does, `PEASANT Jul 26 Early Pod`, so a signup
    on it is acknowledged by the same name its card, its thread and every later answer use. Falls back to the
    button's own label for a key with no format or a slot with no time to name."""
    code = format_of(bucket_key)
    if code is None or slot_time is None:
        return _named_pod_label(bucket_key)
    return pod_display_name(code, slot_time)


def _fire_announcement(
    guild: discord.Guild | None, slot_time: datetime, set_code: str,
) -> str | None:
    """The creation announcement carried on a fired slot's card, or None to post the card silently. Pings the
    slot's own role and the role for the format it drafts, so a player who follows only cubes or only the
    latest set hears about the pods they would actually join. Numberless, so it never goes stale as players
    join — the card's roster carries the count. Gated to a fire close to the draft time: an earlier fire posts
    silently and the underfill checks recruit the last seats near game time."""
    window = timedelta(hours=max(settings.pod_underfill_check_hours_tuple))
    if slot_time - datetime.now(timezone.utc) > window:
        return None
    slot_role = find_role(guild, slot_role_name_for_event_time(slot_time) or "")
    if slot_role is None:
        return None
    format_role = find_role(guild, _format_role_name(set_code))
    mentions = [slot_role.mention]
    if format_role is not None:
        mentions.append(format_role.mention)
    return SLOT_FIRE_PING.format(unix=int(slot_time.timestamp()), mention=" ".join(mentions))


async def _launch_slot(bot: commands.Bot, state, message_id: str, announce: bool = True) -> None:
    """A fired pod graduates into a scheduled RSVP card on its own format: the signups carry over as Yes, and
    the card gathers any late signups right up to the lobby open. The slot then reflects the card as a
    jump-link on the next render and its own nudge is cleared — the card's underfill checks recruit from here.
    Falls back to reopening the pod if the card can't be posted.

    The roster is settled first, so the members it shares with the other formats at this slot go where they
    are needed; whichever of those the release brings up to a full pod fires right after. Those keep their
    cards silent (`announce`): the first card already pinged the slot, and two pods graduating a second apart
    are one crowd, not two."""
    set_code = state.set_code or active_set_code()
    slot_time = state.slot_time
    name = await asyncio.to_thread(pod_launch.ondemand_event_name_sync, set_code, slot_time)
    kept, released = await asyncio.to_thread(pod_launch.allocate_fire_roster_sync, state.signal_id)
    if released:
        log.info(f"slot {state.signal_id} fires with {kept} and released {released} to the other formats")
    signups = await asyncio.to_thread(pod_launch.poll_yes_members_sync, state.signal_id)
    channel = _poll_channel(bot)
    event_id = None
    if isinstance(channel, discord.TextChannel):
        announcement = _fire_announcement(channel.guild, slot_time, set_code) if announce else None
        event_id = await post_scheduled_card(
            bot, channel, set_code=set_code, event_time=slot_time, name=name, preseed_yes=signups,
            ping_role=False, content_override=announcement,
        )
    if event_id is None:
        await asyncio.to_thread(pod_launch.release_fire_sync, state.signal_id)
        log.warning(f"slot fire for {state.signal_id} failed to launch; reverted to open")
    else:
        await clear_slot_nudge(bot, state.signal_id)
    await _rerender_board(bot, message_id, slot_time.astimezone(SCHEDULE_TZ).date())
    await _launch_ready_siblings(bot, state.signal_id, message_id)


async def _launch_ready_siblings(bot: commands.Bot, signal_id: str, message_id: str) -> None:
    """Fire the other formats at this slot that the release just brought up to a full pod. A sibling that
    fires runs this again, and an already-fired one never claims, so the pass settles the whole slot."""
    candidates = await asyncio.to_thread(pod_launch.sibling_fire_candidates_sync, signal_id)
    for state in candidates:
        if state.slot_time is None or not slot_can_fire(state.slot_time, datetime.now(timezone.utc)):
            continue
        if not await asyncio.to_thread(pod_launch.claim_slot_fire_sync, state.signal_id):
            continue
        log.info(f"firing {state.bucket} beside {signal_id} with {state.count} signups")
        await _launch_slot(bot, state, message_id, announce=False)


async def _grant_slot_role(member: discord.Member, bucket_key: str) -> discord.Role | None:
    """Returns the role only on a fresh grant, so the ephemeral confirmation fires once per member."""
    role_name = bucket_role_name(bucket_key)
    if role_name is None:
        return None
    role = find_role(member.guild, role_name)
    if role is None:
        return None
    granted = await grant_role(member, role)
    return role if granted else None


async def refresh_launcher_for_date(bot: commands.Bot, signal_date: date) -> None:
    """Re-render the launcher board carrying this day's slots, so a committed slot tracks late Yes/No churn
    on its scheduled card. The board is resolved by the days it covers, not the day it was posted: a rolled
    column puts tomorrow's slot on today's board, and today's slots sit on yesterday's board until the
    morning post.

    Staleness is measured against the live board, never against the calendar day. A board posted yesterday
    stays the live surface past midnight until the morning post replaces it, so closing on the date alone
    retires the board players are signing up on and leaves the hours until 11:00 with no launcher at all.
    Only a board older than the live one renders closed, which still keeps late churn from reopening a
    retired one."""
    board = await asyncio.to_thread(pod_launch.live_launcher_board_sync)
    if board is None:
        return
    _guild_id, _channel_id, message_id, board_date = board
    if signal_date < board_date:
        await close_launcher_for_date(bot, signal_date)
        return
    await _rerender_poll(bot, message_id, board_date)


async def roll_lane_after_pod(bot: commands.Bot, event_id: str) -> None:
    """Move the launcher column a played pod sat in to the next day, then invite that pod's players back a
    few minutes later. Fired once the pod is finalized, so a column can gather tomorrow while the other
    still plays today. No-op for an off-grid pod, which no column owns.

    Play Again then offers whatever the slot carries tomorrow, one button per format, so a group that drafted
    a cube tonight is invited back to the past set running at their time tomorrow."""
    ref = await asyncio.to_thread(pod_launch.event_lane_ref_sync, event_id)
    if ref is None:
        return
    lane, played_day = ref
    rolled = await _roll_lane(bot, lane, played_day)
    if rolled:
        _schedule_play_again(bot, event_id, [bucket_key for bucket_key, _slot_time in rolled])


async def roll_lane_after_expired_slot(bot: commands.Bot, signal_id: str) -> None:
    """Move a column past a slot whose start passed with no pod. The slot is dead, so the column offers the
    next day instead of a closed row."""
    ref = await asyncio.to_thread(pod_launch.slot_lane_ref_sync, signal_id)
    if ref is None:
        return
    lane, slot_day = ref
    await _roll_lane(bot, lane, slot_day)


async def reconcile_rolled_lanes(bot: commands.Bot) -> None:
    """Startup sweep: roll any column whose pod finished, or whose slot passed unfired, while the bot was
    down. A restart then never leaves the live board offering a slot nobody can join."""
    board = await asyncio.to_thread(pod_launch.live_launcher_board_sync)
    if board is None:
        return
    _guild_id, _channel_id, message_id, board_date = board
    slots = await asyncio.to_thread(pod_launch.launcher_snapshot_sync, message_id, board_date)
    for lane in _lane_order(slots):
        last = _time_groups(_lane_slots(slots, lane))[-1]
        if last[0].slot_time is None:
            continue
        settled = all(
            (slot.committed and slot.finished) or (not slot.committed and slot.status == STATUS_EXPIRED)
            for slot in last
        )
        if settled:
            await _roll_lane(bot, lane, last[0].slot_time.astimezone(SCHEDULE_TZ).date())


async def _roll_lane(
    bot: commands.Bot, lane: str, from_day: date,
) -> list[tuple[str, datetime]]:
    """Open the next day's pods for a lane, arm each one's beats, and re-render the live board so the column
    shows them. Returns (bucket_key, slot_time) per pod now gathering, empty when a pod already covers every
    format that slot offers."""
    board = await asyncio.to_thread(pod_launch.live_launcher_board_sync)
    if board is None:
        return []
    guild_id, channel_id, message_id, board_date = board
    rolled = await asyncio.to_thread(
        pod_launch.roll_slot_forward_sync,
        lane=lane, from_day=from_day, guild_id=guild_id, channel_id=channel_id, message_id=message_id,
    )
    await _rerender_poll(bot, message_id, board_date)
    opened: list[tuple[str, datetime]] = []
    for signal_id, bucket_key, slot_time in rolled:
        pod_launch.arm_slot_expiry(bot, signal_id, slot_time)
        schedule_slot_underfill_checks(bot.pod_scheduler, signal_id, slot_time, datetime.now(timezone.utc))
        log.info(f"rolled {lane} lane from {from_day} to {slot_time.isoformat()} as signal {signal_id}")
        opened.append((bucket_key, slot_time))
    return opened


def _schedule_play_again(bot: commands.Bot, event_id: str, bucket_keys: list[str]) -> None:
    """Post the next-day prompt a few minutes after the pod's result lands, so it never sits on top of the
    final game."""
    scheduler = getattr(bot, "pod_scheduler", None)
    if scheduler is None:
        return
    scheduler.add_job(
        post_play_again_prompt, "date",
        run_date=datetime.now(timezone.utc) + timedelta(minutes=PLAY_AGAIN_DELAY_MIN),
        args=[bot, event_id, bucket_keys],
        id=f"pod-play-again-{event_id}", replace_existing=True,
    )


async def post_play_again_prompt(bot: commands.Bot, event_id: str, bucket_keys: list[str]) -> None:
    """Post the Play Again prompt in the finished pod's own thread, where the players who just drafted
    together already are."""
    thread_id = await asyncio.to_thread(pod_launch.event_thread_id_sync, event_id)
    if thread_id is None:
        return
    thread = await pod_launch.fetch_pod_thread(bot, int(thread_id))
    if thread is None:
        return
    embed, view = build_play_again_prompt(bucket_keys)
    try:
        await thread.send(embed=embed, view=view, allowed_mentions=discord.AllowedMentions.none())
    except discord.HTTPException:
        log.warning(f"could not post the play again prompt in thread {thread_id}", exc_info=True)


async def close_recent_launchers(bot: commands.Bot, today: date) -> None:
    """Retire the last few days' launchers so a stale board can no longer be signed up on. Bounded to a
    short window and idempotent, so each daily post re-touches only a handful and an already-closed one
    is left untouched."""
    since = today - timedelta(days=LAUNCHER_CLOSE_LOOKBACK_DAYS)
    dates = await asyncio.to_thread(pod_launch.past_launcher_dates_sync, today, since)
    for signal_date in dates:
        await close_launcher_for_date(bot, signal_date)


async def close_launcher_for_date(bot: commands.Bot, signal_date: date) -> None:
    """Edit the day's launcher into its terminal state: signups closed, no buttons, no role ping (which
    also clears the gold mention tint), greyed. No-op when no launcher was posted or it is already
    closed."""
    ref = await asyncio.to_thread(pod_launch.launcher_ref_for_date_sync, signal_date)
    if ref is None:
        return
    channel_id, message_id = ref
    channel = bot.get_channel(int(channel_id))
    if channel is None:
        try:
            channel = await bot.fetch_channel(int(channel_id))
        except discord.HTTPException:
            return
    guild = getattr(channel, "guild", None)
    slots = await asyncio.to_thread(pod_launch.launcher_snapshot_sync, message_id, signal_date)
    try:
        message = await channel.fetch_message(int(message_id))
        if not message.components and not message.content:
            return
        await message.edit(content=None, embed=build_poll_embed(slots, guild, closed=True), view=None)
    except discord.HTTPException:
        log.warning(f"could not close launcher message {message_id}", exc_info=True)


async def _rerender_board(bot: commands.Bot, message_id: str, fallback_date: date) -> None:
    """Re-render a board when the caller knows a slot's day but not the board's own. A rolled board is
    older than the slots it carries, so rendering it against a slot's day would hide the pods it played."""
    board_date = await asyncio.to_thread(pod_launch.launcher_date_for_message_sync, message_id)
    await _rerender_poll(bot, message_id, board_date or fallback_date)


async def _rerender_poll(
    bot: commands.Bot, message_id: str, signal_date: date,
    channel: "discord.abc.Messageable | None" = None,
) -> None:
    """Repaint a live board in place, ping line included. Retiring a board drops that line, so a board that
    is retired and rendered live again comes back without its queue mention unless every render restates it.
    Discord notifies on the post, never on an edit, so restating it cannot ping the role a second time."""
    channel = channel or _poll_channel(bot)
    if channel is None:
        return
    guild = getattr(channel, "guild", None)
    slots = await asyncio.to_thread(pod_launch.launcher_snapshot_sync, message_id, signal_date)
    try:
        message = await channel.fetch_message(int(message_id))
        await message.edit(
            content=poll_ping_line(guild), embed=build_poll_embed(slots, guild),
            view=PodPollView(slots, guild), allowed_mentions=discord.AllowedMentions(roles=True),
        )
    except discord.HTTPException:
        log.warning(f"could not re-render launcher message {message_id}", exc_info=True)
