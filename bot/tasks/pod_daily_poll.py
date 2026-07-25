"""Daily Pod Launcher — the always-forward-looking "who's playing next" signup surface.

Posts every day at 11:00 ET with the same two columns (Early 14:00, Late 20:00). Each lazy slot fires a
bot-native pod once it reaches the threshold, graduating into a scheduled RSVP card.

Each column rolls on its own clock: the moment its pod is played, the column opens the next day's slot and
stacks the played pod above it, so the board never offers a slot that already happened and interest never
resets overnight. A slot whose start passes unfired rolls the same way. Overnight signups are held, not
fired — a slot graduates only once its own day is the live one, which the morning post re-checks. The
morning post adopts the slots a rolled column already opened, so the fresh board carries what accumulated
instead of starting at zero, and the old message retires to its On This Day history.

A slot whose time already carries a locked scheduled pod is reflected, not reopened: it renders a Yes/No
toggle that writes to that pod's scheduled card and creates no signal of its own, so the launcher and the
card are two live windows on one roster and never a duplicate. The launcher message is the single RSVP
surface for its lazy slots — buttons carry static custom_ids and PodPollView re-attaches on restart, and a
column carries one button whichever of its stacked slots is the joinable one.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import date, datetime, timedelta, timezone

import discord
from discord.ext import commands

from bot import emojis
from bot.commands.messages import (
    MSG_DRAFT_STARTS,
    MSG_FORMAT_PREFERENCE_BUTTON,
    MSG_YOUR_CUBES_LINE,
    MSG_YOUR_SETS_LINE,
)
from bot.commands.pod_queue import queue_role_mention
from bot.commands.pod_rsvp import (
    ReminderRsvpButton,
    apply_card_rsvp,
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
    announce_pod_grant,
    register_format_preference_opener,
    send_join_confirmation_card,
    slot_grant_ping,
    spec_named,
)
from bot.services.pod_launcher_copy import (
    ARCHIVE_INTRO,
    CONFIRM_SLOT_LABEL,
    CUBE_SELECT_PLACEHOLDER,
    INTEREST_DESC_CUBE,
    INTEREST_DESC_FLASHBACK,
    INTEREST_PLACEHOLDER,
    MARKER_CLOSED,
    MSG_INTEREST_PROMPT,
    MSG_INTEREST_SAVED,
    MSG_POLL_INACTIVE,
    MSG_RANK_EMPTY,
    MSG_SLOT_ADDED,
    MSG_SLOT_CLOSED,
    MSG_SLOT_REMOVED,
    PLAY_AGAIN_BUTTON,
    PLAY_AGAIN_CONFIRM,
    PLAY_AGAIN_INTRO,
    PLAY_AGAIN_LOVE_EMOJI,
    POLL_FORMAT_SINGLE,
    POLL_FORMATS,
    POLL_INTRO,
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
from bot.services.pod_roles import find_role, grant_pod_drafters, grant_role
from bot.services.pod_signals import (
    ALL_BUCKETS,
    RSVP_NO,
    RSVP_YES,
    SCHEDULE_TZ,
    STATUS_EXPIRED,
    POST_HOUR_ET,
    bucket_by_key,
    bucket_role_name,
    format_of,
    lane_of,
    named_bucket_key,
    slot_can_fire,
    slot_role_name_for_event_time,
    time_key_of,
)
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


async def post_launcher(
    bot: commands.Bot, channel: "discord.abc.Messageable", signal_date: date,
) -> discord.Message | None:
    """Render and post the day's launcher, bind a lazy signal per open slot and arm its expiry and underfill
    beats, then re-render and graduate whatever arrived overnight. Shared by the daily cron and `!test poll`
    so both drive the identical surface.

    Binding adopts the slots a rolled column already opened for today, so the fresh board carries the
    signups collected since yesterday and the first render (which runs before binding, off an empty board)
    is corrected by the re-render right after."""
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
        if not await asyncio.to_thread(pod_launch.claim_fire_sync, state.signal_id):
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
    and Next sections. `closed` renders the terminal state as a compact On This Day history list in the
    description instead of columns, so a reader scrolling up sees the day's results with no empty column
    space."""
    slot_times = [slot.slot_time for slot in slots if slot.slot_time is not None]
    earliest = min(slot_times) if slot_times else None
    day = earliest.astimezone(SCHEDULE_TZ) if earliest else None
    title = f"{POLL_TITLE} - {day:%b %-d}" if day else POLL_TITLE
    heading = f"## {NBSP * 2}🚀 {title}"
    if closed:
        return _archive_embed(slots, guild, heading)
    intro = POLL_INTRO.format(
        threshold=settings.pod_signal_fire_threshold, lead=pod_launch.REMINDER_LEAD_MIN,
    )
    description = f"{heading}\n{intro}\n{_formats_intro(slots, guild)}"
    embed = discord.Embed(description=description, color=discord.Color.green())
    columns = [_lane_slots(slots, lane) for lane in _lane_order(slots)]
    pad = _finished_pad(columns)
    for column in columns:
        value = _column_value(column, guild, pad)
        if value:
            embed.add_field(name=ZWSP, value=value, inline=True)
    return embed


def _finished_pad(columns: list[list[pod_launch.LauncherSlot]]) -> int:
    """The tallest Played section among columns that also have a Next, so shorter columns can pad to it
    and the Next rows line up across the two side-by-side columns. Columns without a Next are ignored."""
    pad = 0
    for column in columns:
        finished = sum(1 for slot in column if slot.committed)
        gathering = any(not slot.committed for slot in column)
        if finished and gathering:
            pad = max(pad, finished)
    return pad


def _formats_intro(slots: list[pod_launch.LauncherSlot], guild: discord.Guild | None) -> str:
    """Names the formats on offer. A board that only offers the latest set drops the numbering and the
    sign-up-for-both line, since there is no second format to choose between. Per-slot schedules can put
    different second formats on one board, so every distinct one is listed."""
    seconds = []
    for slot in slots:
        if slot.other_format and slot.other_format not in seconds:
            seconds.append(slot.other_format)
    latest = active_set_code()
    main = f"{_named_pod_emoji(latest)} {pod_format.format_name(latest)}"
    if not seconds:
        return POLL_FORMAT_SINGLE.format(main=main)
    return POLL_FORMATS.format(
        main=main, second=", ".join(_format_intro_name(code, guild) for code in seconds),
    )


def _format_intro_name(code: str, guild: discord.Guild | None) -> str:
    """The format's name followed by the role that gets pinged for it, so the kind of format reads off the
    role instead of being spelled into the name."""
    role = _other_format_role_label(guild, code)
    return f"{_named_pod_emoji(code)} {pod_format.format_name_link(code)} {role}"


def _archive_embed(
    slots: list[pod_launch.LauncherSlot], guild: discord.Guild | None, heading: str,
) -> discord.Embed:
    """The retired card: On This Day plus one line per finished pod, all in the description, so it reads
    as a compact day-history with no empty column space. A second table adds its own line."""
    lines = [_finished_line(slot, guild, full_name=True) for slot in slots if slot.committed]
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


def _representative_slot(
    slots: list[pod_launch.LauncherSlot], lane: str,
) -> pod_launch.LauncherSlot | None:
    """The slot a lane's single launcher button acts on: the open gathering slot when one exists (the
    joinable one, today's or the next day's), otherwise the committed pod, otherwise an expired slot. A
    lane carries one button even while its column stacks a finished pod above a gathering one."""
    lane_slots = _lane_slots(slots, lane)
    for slot in lane_slots:
        if not slot.committed and slot.status != STATUS_EXPIRED:
            return slot
    for slot in lane_slots:
        if slot.committed:
            return slot
    return lane_slots[-1] if lane_slots else None


def _column_value(
    bucket_slots: list[pod_launch.LauncherSlot], guild: discord.Guild | None, pad_finished: int = 0,
) -> str:
    """One bucket column. Championship lanes and plain gathering columns render as familiar single
    blocks. A column that stacks a pod whose lobby already opened above a still-gathering slot leads with
    one slot-name header, then a Played (or Playing) section listing those pods, then a Next section with
    the upcoming date and roster, so the slot name and date are never doubled.

    Reaching the threshold does not hoist a pod up there. A pod keeps taking signups until its lobby
    opens, so it stays a full roster block with its thread link until then; only a fully locked slot moves."""
    if any(slot.championship for slot in bucket_slots):
        blocks = [block for block in (_slot_block(slot, guild) for slot in bucket_slots) if block]
        return f"\n{NBSP}\n".join(blocks) if blocks else "-"
    finished = [slot for slot in bucket_slots if _slot_fully_locked(slot)]
    gathering = [slot for slot in bucket_slots if not _slot_fully_locked(slot)]
    if not finished:
        blocks = [block for block in (_slot_block(slot, guild) for slot in gathering) if block]
        return f"\n{NBSP}\n".join(blocks) if blocks else "-"
    sections: list[str] = []
    finished_lines = [line for line in (_finished_line(slot, guild, full_name=False) for slot in finished) if line]
    if finished_lines:
        blanks = [NBSP] * max(0, pad_finished - len(finished_lines))
        sections.append("\n".join(finished_lines + blanks))
    for slot in gathering:
        relative = f"<t:{int(slot.slot_time.timestamp())}:R>" if slot.slot_time else ""
        next_label = " ".join(part for part in (emojis.get(NEXT_EMOJI), SECTION_NEXT, relative) if part)
        when = _slot_when_line(slot)
        count = f"**({slot.count})**" if slot.count else ""
        date_line = " ".join(part for part in (when, count) if part)
        body = _gathering_body(slot, guild)
        sections.append(f"{next_label}\n{date_line}\n{body}" if date_line else f"{next_label}\n{body}")
    lead = gathering[0] if gathering else finished[0]
    header = _slot_name_only(lead, guild)
    if not gathering:
        start = _slot_start_time(finished[0])
        header = f"{header}{NBSP}{NBSP}{start}" if start else header
    return f"{header}\n" + f"\n{NBSP}\n".join(sections)


def _slot_block(slot: pod_launch.LauncherSlot, guild: discord.Guild | None) -> str | None:
    """One full self-contained block for a single slot: header, date, then roster or link-and-winner.
    Used for the championship lane and a plain gathering column, where each slot renders on its own."""
    bucket = bucket_by_key(slot.bucket_key)
    if bucket is None:
        return None
    if slot.championship:
        when = _slot_when_line(slot)
        symbol = emojis.get(slot.set_code.lower()) if slot.set_code else ""
        label = f"**{CHAMPIONSHIP_SLOT_LABEL}**"
        title_line = " ".join(part for part in (CHAMPIONSHIP_CROWN, symbol, label) if part)
        header = f"{title_line}\n{when}" if when else title_line
        return f"{header}\n{_championship_body(slot, guild)}"
    body = _finished_line(slot, guild, full_name=False) if _slot_fully_locked(slot) else _gathering_body(slot, guild)
    return f"{_slot_head(slot, guild)}\n{body}"


def _slot_head(slot: pod_launch.LauncherSlot, guild: discord.Guild | None) -> str:
    when = _slot_when_line(slot)
    header = _slot_header_line(slot, guild)
    return f"{header}\n{when}" if when else header


def _slot_header_line(slot: pod_launch.LauncherSlot, guild: discord.Guild | None) -> str:
    count = f"**({slot.count})**" if slot.count and not _slot_fully_locked(slot) else ""
    return " ".join(part for part in (_slot_name_only(slot, guild), count) if part)


def _slot_name_only(slot: pod_launch.LauncherSlot, guild: discord.Guild | None) -> str:
    bucket = bucket_by_key(slot.bucket_key)
    slot_emoji = emojis.resolve(bucket.emoji) if bucket else None
    role = find_role(guild, bucket_role_name(slot.bucket_key) or "")
    label = role.mention if role else (bucket.name if bucket else slot.bucket_key)
    return " ".join(part for part in (slot_emoji, label) if part)


def _named_pod_emoji(code: str) -> "discord.Emoji | str":
    """A format's glyph for a button's emoji slot or an f-string, which take the object. A cube has no set
    symbol, so it falls back to the cube glyph rather than the flashback one. Never pass this into
    `str.join`: an Emoji is not a str, which is how the first named-pod render crashed."""
    symbol = emojis.set_symbol(code)
    if symbol is not None:
        return symbol
    return fi.cube_emoji() if pod_format.is_custom(code) else fi.flashback_emoji()


def _slot_when_line(slot: pod_launch.LauncherSlot) -> str:
    return f"<t:{int(slot.slot_time.timestamp())}:F>" if slot.slot_time else ""


def _slot_start_time(slot: pod_launch.LauncherSlot) -> str:
    """Clock-only start time for a column whose pods have all started, where no Next section carries the
    full date and the column would otherwise say nothing about when the pod ran."""
    return f"<t:{int(slot.slot_time.timestamp())}:t>" if slot.slot_time else ""


def _finished_line(slot: pod_launch.LauncherSlot, guild: discord.Guild | None, *, full_name: bool) -> str:
    """One line for a finished or in-progress pod: a trophy once the pod is played (else a playing mark),
    the pod name linking to its Discord thread, then the LLU glyph and the bold winner name after a
    two-space gap, linking to that player's seat on the website pod page. The launcher column strips the
    slot name so the pod reads "MSH Jul 24"; the archive keeps the full name to tell Early from Late. A
    team draft is credited to its winning side, which has no seat, so its name links nowhere and a draw
    carries no name."""
    mark = FINISHED_MARK if slot.finished else PLAYING_MARK
    text = _finished_link_text(slot, full_name)
    card_url = _card_url(guild, slot)
    pod_link = f"[__**{text}**__]({card_url})" if card_url and text else text
    winner = ""
    if slot.winner:
        seat_url = _winner_seat_url(slot)
        name = f"[__**{slot.winner}**__]({seat_url})" if seat_url else f"__**{slot.winner}**__"
        winner = f"{NBSP}{NBSP}{emojis.prefix('llu')}{name}"
    head = f"{mark} {pod_link}" if pod_link else mark
    return f"{head}{winner}"


def _finished_link_text(slot: pod_launch.LauncherSlot, full_name: bool) -> str:
    """The pod link text: the full event name in the archive, or set and date once the slot name is
    stripped for the launcher column, so it reads "MSH Jul 24"."""
    name = slot.thread_name or ""
    if full_name:
        return name
    bucket = bucket_by_key(slot.bucket_key)
    return name.replace(f" {bucket.name}", "") if bucket else name


def _winner_seat_url(slot: pod_launch.LauncherSlot) -> str | None:
    """The winner's seat on the pod's website page, mirroring the frontend's `/pods/<event>/<player>` route
    built from the event name and the winner's player slug. Without a slug it points at the pod page
    itself, which is where a team draft and an unlinked winner land."""
    if not slot.thread_name:
        return None
    base = f"{settings.public_site_url.rstrip('/')}/pods/{slugify(slot.thread_name)}"
    return f"{base}/{slot.winner_slug}" if slot.winner_slug else base


def _gathering_body(slot: pod_launch.LauncherSlot, guild: discord.Guild | None) -> str:
    """A pod that already has a thread but is still taking signups shows its link above the format block
    it is playing, so the link reads as belonging to that format rather than to the whole slot."""
    if slot.status == STATUS_EXPIRED:
        return MARKER_CLOSED
    link = _committed_card_link(guild, slot) if slot.committed else None
    return _roster_lines(
        slot.names, slot.interests, link, _slot_pod_format(slot), guild, slot.other_format,
        locked_formats=slot.locked_formats, locked_line=_locked_line(slot, guild))


def _slot_fully_locked(slot: pod_launch.LauncherSlot) -> bool:
    """Whether every format this slot offers is locked in, the only case where the whole slot collapses to
    one line. A slot whose other format is still joinable keeps its full block."""
    if not slot.committed or not slot.locked_formats:
        return False
    offered = {active_set_code()}
    if slot.other_format:
        offered.add(slot.other_format)
    return offered <= set(slot.locked_formats)


def _locked_line(slot: pod_launch.LauncherSlot, guild: discord.Guild | None) -> str | None:
    return _finished_line(slot, guild, full_name=False) if slot.locked_formats else None


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


def _roster_lines(
    names: list[str], interests: tuple[tuple[str, ...], ...],
    thread_link: str | None = None, pod_format: str = fi.LATEST, guild: discord.Guild | None = None,
    other_format: str | None = None, locked_formats: tuple[str, ...] = (), locked_line: str | None = None,
) -> str:
    """The slot's roster sorted into format teams, each under an emoji-and-count header. Dedicated picks
    anchor their team, Any players fill whichever team is closer to a table, no-preference rides with
    Latest. Names and interests share the created-at order, so the pairs line up. A committed pod's thread
    link sits directly above the team block playing its format.

    Every format the day offers keeps its block whether or not anyone is in it, so an untouched slot shows
    what it is offering rather than a bare dash. A day with no second format still shows one block."""
    paired = []
    for index, name in enumerate(names):
        codes = interests[index] if index < len(interests) else ()
        display = f"{fi.FLEXIBLE_MARKER} {name}" if fi.is_flexible(codes) else name
        paired.append((display, codes))
    latest_team, flashback_team = fi.format_teams(paired)
    latest_label = _format_role_label(guild, fi.LATEST_SET_ROLE_NAME)
    flashback_label = _format_role_label(guild, fi.FLASHBACK_ROLE_NAME)
    flashback_icon = fi.flashback_emoji()
    flashback_gap = ""
    if other_format:
        flashback_label = f"**{other_format}** {_other_format_role_label(guild, other_format)}"
        flashback_icon = _named_pod_emoji(other_format)
        flashback_gap = " "
    latest_block = _team_block(fi.latest_emoji(), latest_label, latest_team)
    show_flashback = bool(other_format) or bool(flashback_team)
    flashback_block = (
        _team_block(flashback_icon, flashback_label, flashback_team, flashback_gap)
        if show_flashback else None
    )
    if locked_line:
        if other_format and other_format in locked_formats:
            flashback_block = locked_line
        if active_set_code() in locked_formats:
            latest_block = locked_line
    if thread_link and not locked_line:
        if flashback_block is not None and (pod_format == fi.FLASHBACK or latest_block is None):
            flashback_block = f"{thread_link}\n{flashback_block}"
        else:
            latest_block = f"{thread_link}\n{latest_block}"
    blocks = [block for block in (latest_block, flashback_block) if block]
    return f"\n> {NBSP}\n".join(blocks)


def _slot_pod_format(slot: pod_launch.LauncherSlot) -> str:
    if slot.set_code and slot.set_code != active_set_code():
        return fi.FLASHBACK
    return fi.LATEST


def _format_role_label(guild: discord.Guild | None, role_name: str) -> str:
    role = find_role(guild, role_name)
    return role.mention if role else role_name


def _other_format_role_label(guild: discord.Guild | None, code: str) -> str:
    """A cube pings Cube and a past set pings Flashback. A cube is drafted out of the latest set's client,
    so it is not a flashback, and the two crowds are not the same people."""
    role_name = fi.CUBE_ROLE_NAME if pod_format.is_custom(code) else fi.FLASHBACK_ROLE_NAME
    return _format_role_label(guild, role_name)


def _team_block(icon: object, label: str, team: list[str], gap: str = "") -> str:
    """A format's block. An empty one still renders its header over a dash, so a slot nobody has joined yet
    still advertises both formats on offer instead of collapsing to a bare dash. The count is dropped at
    zero, matching the slot header, which also only counts once someone is in. `gap` separates a set symbol
    from the format name, which the role-name-only headers do not want."""
    count = f" **({len(team)})**" if team else ""
    lines = [f"> {name}" for name in team] or ["> -"]
    return "\n".join([f"> {icon}{gap}{label}{count}"] + lines)


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


def build_play_again_prompt(bucket_key: str) -> tuple[str, "PlayAgainView"]:
    """The next-day re-signup prompt posted into a finished pod's thread: a thank-you and a button that
    signs the clicker up for the same slot on the next day."""
    bucket = bucket_by_key(bucket_key)
    slot_label = bucket.name if bucket else bucket_key
    content = PLAY_AGAIN_INTRO.format(love=emojis.get(PLAY_AGAIN_LOVE_EMOJI), slot=slot_label)
    return content, PlayAgainView(bucket_key)


class PlayAgainView(discord.ui.View):
    """Persistent. One button that signs the clicker up for the same slot on the next day; with no bucket
    (the startup registration) it carries one per bucket so a restart re-attaches the handler to whichever
    prompt is live in a thread."""

    def __init__(self, bucket_key: str | None = None) -> None:
        super().__init__(timeout=None)
        keys = [bucket.key for bucket in ALL_BUCKETS] if bucket_key is None else [bucket_key]
        for key in keys:
            self.add_item(_PlayAgainButton(key))


class _PlayAgainButton(discord.ui.Button):
    """The slot it writes to is resolved at click time, not at post time: the prompt outlives the day it
    was posted on, and the soonest open slot of that bucket is always the one the launcher is offering."""

    def __init__(self, bucket_key: str) -> None:
        bucket = bucket_by_key(bucket_key)
        super().__init__(
            label=PLAY_AGAIN_BUTTON, style=discord.ButtonStyle.success,
            emoji=emojis.resolve(bucket.emoji) if bucket else None,
            custom_id=f"pod_play_again:{bucket_key}",
        )
        self.bucket_key = bucket_key

    async def callback(self, interaction: discord.Interaction) -> None:
        await _handle_play_again_click(interaction, self.bucket_key)


async def _handle_play_again_click(interaction: discord.Interaction, bucket_key: str) -> None:
    bucket = bucket_by_key(bucket_key)
    slot_label = bucket.name if bucket else bucket_key
    await interaction.response.defer(ephemeral=True, thinking=True)
    ref = await asyncio.to_thread(
        pod_launch.open_slot_for_bucket_sync, bucket_key, datetime.now(timezone.utc),
    )
    if ref is None:
        await interaction.followup.send(MSG_SLOT_CLOSED, ephemeral=True)
        return
    signal_id, launcher_message_id, slot_time = ref
    joined = await asyncio.to_thread(
        pod_launch.join_slot_signal_sync, signal_id, str(interaction.user.id), interaction.user.display_name,
    )
    await interaction.followup.send(
        PLAY_AGAIN_CONFIRM.format(slot=slot_label, unix=int(slot_time.timestamp())), ephemeral=True,
    )
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
    """Persistent. With no slots (the startup registration) it carries every bucket's lazy-toggle and
    committed-RSVP button so a restart re-attaches the handler for whichever slots a live message shows.
    Built from a snapshot it carries the day's surface: a lazy slot renders its join toggle, a committed
    slot renders a Yes/No toggle that writes to its scheduled card. A slot offering a second format carries
    one button per format, so the press itself says which pod it joins and no stored preference is
    consulted. Bucket emoji are application emoji that can't render in label text, so each button gets its
    glyph in the emoji slot."""

    def __init__(
        self, slots: list[pod_launch.LauncherSlot] | None = None, guild: discord.Guild | None = None,
    ) -> None:
        super().__init__(timeout=None)
        if slots is None:
            for bucket in ALL_BUCKETS:
                self.add_item(_slot_toggle_button(bucket.key))
                self.add_item(_slot_rsvp_button(bucket.key))
            return
        for lane in _lane_order(slots):
            slot = _representative_slot(slots, lane)
            bucket = bucket_by_key(slot.bucket_key) if slot else None
            if bucket is None:
                continue
            if slot.committed and slot.championship and slot.thread_id:
                self.add_item(discord.ui.Button(
                    style=discord.ButtonStyle.link,
                    url=_jump_url(guild, slot.thread_id, slot.thread_message_id),
                    label=CHAMPIONSHIP_SLOT_LABEL, emoji=CHAMPIONSHIP_CROWN,
                ))
            elif slot.committed and slot.card_message_id:
                self.add_item(_slot_rsvp_button(
                    slot.bucket_key, slot.set_code if slot.other_format else None))
            elif slot.committed and slot.thread_id:
                self.add_item(discord.ui.Button(
                    style=discord.ButtonStyle.link,
                    url=_jump_url(guild, slot.thread_id, slot.thread_message_id),
                    label=bucket.name, emoji=emojis.resolve(bucket.emoji),
                ))
            elif not slot.committed:
                for key in _slot_button_keys(slot):
                    self.add_item(_slot_toggle_button(key, closed=slot.status == STATUS_EXPIRED))


def _slot_button_keys(slot: pod_launch.LauncherSlot) -> list[str]:
    """One key per pod a gathering slot offers. A day with no second format keeps the plain slot key, so
    its launcher is identical to one that never had a second offer; a day that offers two carries a named
    key per format, and the labels name the format a press commits to."""
    if not slot.other_format:
        return [slot.bucket_key]
    return [named_bucket_key(slot.bucket_key, code) for code in (active_set_code(), slot.other_format)]


def _named_pod_label(bucket_key: str, code: str | None = None) -> str:
    """`Early NEO`, the shortest label that names both the time and the format a press commits to. A
    committed pod passes its own `code`, since its key is the plain slot and carries no format."""
    code = code or format_of(bucket_key)
    short = _slot_short_name(time_key_of(bucket_key))
    return f"{short} {code}" if code else short


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
    """A picker opened from a committed pod (`event_id` set) carries no per-slot Confirm buttons — the
    player is already in that pod, so it saves the preference only and re-renders that pod's surfaces."""
    user_id = str(interaction.user.id)
    current = await asyncio.to_thread(pod_launch.player_interest_sync, user_id)
    ranking = await asyncio.to_thread(pod_launch.player_flashback_ranking_sync, user_id)
    cubes = await asyncio.to_thread(pod_launch.player_cube_choices_sync, user_id)
    if event_id is None:
        slots = await asyncio.to_thread(pod_launch.launcher_snapshot_sync, launcher_message_id, signal_date)
        slot_states = _confirm_slot_states(slots)
    else:
        slot_states = []
    view = InterestPromptView(
        launcher_message_id, signal_date, current, ranking, cubes, slot_states, event_id,
    )
    await interaction.followup.send(view=view, ephemeral=True)


def _confirm_slot_states(
    slots: list[pod_launch.LauncherSlot],
) -> list[tuple[str, bool, str | None]]:
    """(bucket_key, joinable, scheduled-card message_id) per column, so the picker offers one Confirm per
    column and writes to whichever slot that column is currently offering. The card id is set only for a
    column whose pod already locked, where Confirm RSVPs on the card instead of the poll signal."""
    states: list[tuple[str, bool, str | None]] = []
    for lane in _lane_order(slots):
        slot = _representative_slot(slots, lane)
        if slot is None or bucket_by_key(slot.bucket_key) is None:
            continue
        states.append((slot.bucket_key, slot.status != STATUS_EXPIRED, slot.card_message_id))
    return states


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
    """Ephemeral preference picker opened from the launcher's Format Preference button. A Components V2
    layout: prompt, the interest select, and the Save / Confirm row. A Flashback pick inserts the ranking
    line above a Rank Sets button; a Cube pick inserts the chosen-cubes line above a Choose Cubes button
    that reveals the server cube list. Short-lived and per-user, so it carries no persistent custom_ids."""

    def __init__(
        self, launcher_message_id: str, signal_date: date, current: list[str], ranking: list[str],
        cubes: list[str], slot_states: list[tuple[str, bool, str | None]], event_id: str | None = None,
    ) -> None:
        super().__init__(timeout=300)
        self.launcher_message_id = launcher_message_id
        self.signal_date = signal_date
        self.values = fi.normalize(current)
        self.ranking = list(ranking)
        self.cubes = list(cubes)
        self.slot_states = slot_states
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
        for bucket_key, is_open, card_message_id in self.slot_states:
            bucket = bucket_by_key(bucket_key)
            if bucket is None:
                continue
            button = discord.ui.Button(
                label=CONFIRM_SLOT_LABEL.format(name=_slot_short_name(bucket_key)),
                style=discord.ButtonStyle.success if is_open else discord.ButtonStyle.secondary,
                emoji=emojis.resolve(bucket.emoji), disabled=not is_open,
            )
            if is_open:
                button.callback = self._make_confirm_slot(bucket_key, card_message_id)
            button_row.add_item(button)
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

    def _make_confirm_slot(self, bucket_key: str, card_message_id: str | None):
        async def callback(interaction: discord.Interaction) -> None:
            if card_message_id is not None:
                await self._on_confirm_committed(interaction, card_message_id)
            else:
                await self._on_confirm_slot(interaction, bucket_key)
        return callback

    async def _on_confirm_slot(self, interaction: discord.Interaction, bucket_key: str) -> None:
        """Save the preference and join the slot. The join feedback is the grant card or the full
        confirmation card out of `_apply_slot_join`, both of which carry the saved preference, so the
        picker itself closes silently instead of adding a second message."""
        await interaction.response.defer()
        await self._persist(interaction.user)
        launcher_message = await _fetch_launcher_message(interaction.channel, self.launcher_message_id)
        err = MSG_POLL_INACTIVE
        if launcher_message is not None:
            err, _ = await _apply_slot_join(
                interaction, launcher_message=launcher_message, signal_date=self.signal_date,
                bucket_key=bucket_key, action="join", notify_effect=True,
            )
        if err:
            await self._finish(interaction, err)
            return
        await self._dismiss(interaction)

    async def _on_confirm_committed(self, interaction: discord.Interaction, card_message_id: str) -> None:
        """A slot whose pod already committed joins through the pod's scheduled card, not the launcher
        poll signal, so the row lands on the live roster and the card, thread, and launcher re-render in
        step. Confirm always sets Yes; already-Yes stays Yes. `apply_card_rsvp` posts the join card and
        refreshes the board, so the picker deletes itself once done."""
        await self._persist(interaction.user)
        await apply_card_rsvp(interaction, card_message_id, RSVP_YES)
        await self._dismiss(interaction)


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


def _slot_toggle_button(bucket_key: str, closed: bool = False) -> discord.ui.Button:
    bucket = bucket_by_key(bucket_key)
    code = format_of(bucket_key)
    style = discord.ButtonStyle.secondary if closed else discord.ButtonStyle.success
    button = discord.ui.Button(
        label=_named_pod_label(bucket_key) if code else bucket.name, style=style, disabled=closed,
        custom_id=f"pod_poll:{bucket_key}",
        emoji=_named_pod_emoji(code) if code else emojis.resolve(bucket.emoji),
    )

    async def callback(interaction: discord.Interaction) -> None:
        await _handle_poll_click(interaction, bucket_key)

    button.callback = callback
    return button


def _slot_rsvp_button(bucket_key: str, set_code: str | None = None) -> discord.ui.Button:
    """`set_code` names the committed pod's own format, so on a day offering two the button reads `Late MSH`
    instead of a bare `Late Pod` that gives no clue which of the two it RSVPs to."""
    bucket = bucket_by_key(bucket_key)
    code = format_of(bucket_key) or set_code
    button = discord.ui.Button(
        label=_named_pod_label(bucket_key, code) if code else bucket.name,
        style=discord.ButtonStyle.success, custom_id=f"pod_slot_rsvp:{bucket_key}",
        emoji=_named_pod_emoji(code) if code else emojis.resolve(bucket.emoji),
    )

    async def callback(interaction: discord.Interaction) -> None:
        await _handle_slot_rsvp_click(interaction, bucket_key)

    button.callback = callback
    return button


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
    """Join or toggle a launcher slot for the clicker, then run the shared fire, launcher re-render, role
    grant, announce, and nudge-refresh steps. Returns (error, notice): an error string when the slot is
    gone or closed, and the grant/welcome notice that was posted, so a caller with its own confirmation
    can skip it instead of doubling up. Shared by the launcher slot buttons (toggle) and the Format
    Preference Confirm buttons (join). `notify_effect` confirms the add or removal ephemerally when no
    grant notice already did."""
    message_id = str(launcher_message.id)
    result = await asyncio.to_thread(
        pod_launch.toggle_member_sync,
        message_id, bucket_key, str(interaction.user.id), interaction.user.display_name, action,
    )
    if result is None:
        return MSG_POLL_INACTIVE, None
    if result.closed:
        return MSG_SLOT_CLOSED, None
    fired = (
        result.joined
        and result.composition is not None
        and fi.slot_fires_latest(result.composition, settings.pod_signal_fire_threshold)
        and result.state.slot_time is not None
        and slot_can_fire(result.state.slot_time, datetime.now(timezone.utc))
        and await asyncio.to_thread(pod_launch.claim_fire_sync, result.state.signal_id)
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
    card_lead = _slot_effect_lead(bucket_key, result.state.slot_time) if result.joined else None
    notice = await announce_pod_grant(
        interaction, first_pod=first_pod, granted_role=granted_role,
        welcome_role=granted_role, spec=spec, ping=ping, card_lead=card_lead,
    )
    if notify_effect and not notice:
        if result.joined and (result.changed or action == "join"):
            await send_join_confirmation_card(
                interaction, lead=_slot_effect_lead(bucket_key, result.state.slot_time),
                accent=discord.Color.green(),
            )
        elif result.changed:
            await interaction.followup.send(embed=_slot_removed_embed(bucket_key), ephemeral=True)
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
    """A committed slot's button toggles the clicker on its scheduled card: Yes when they were out or
    Maybe, No when they already held Yes. The card is read off the board's own snapshot, so a rolled column
    targets the pod it is showing. The write and every follow-on run through the card's shared
    apply_card_rsvp, so the card, the launcher, and the native event re-render in step."""
    signal_date = await _launcher_signal_date(interaction.message)
    slots = await asyncio.to_thread(
        pod_launch.launcher_snapshot_sync, str(interaction.message.id), signal_date,
    )
    slot = _representative_slot(slots, lane_of(bucket_key) or "")
    if slot is None or slot.card_message_id is None:
        await interaction.response.send_message(MSG_SLOT_CLOSED, ephemeral=True)
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


def _slot_effect_lead(bucket_key: str, slot_time: datetime | None) -> str:
    """The join confirmation as card text: folded into the grant card when a fresh role grant rides
    the same click, else the lead of the plain confirmation card."""
    bucket = bucket_by_key(bucket_key)
    name = bucket.name if bucket else bucket_key
    lead = f"### {MSG_SLOT_ADDED.format(name=name)}"
    if slot_time is not None:
        lead = f"{lead}\n{MSG_DRAFT_STARTS.format(unix=int(slot_time.timestamp()))}"
    return lead


def _slot_removed_embed(bucket_key: str) -> discord.Embed:
    """The bare red removal note, mirroring the scheduled card's No acknowledgement — the start time
    and the pod controls are moot once you're out. An add answers with the full confirmation card."""
    bucket = bucket_by_key(bucket_key)
    name = bucket.name if bucket else bucket_key
    return discord.Embed(title=MSG_SLOT_REMOVED.format(name=name), color=discord.Color.red())


def _fire_announcement(guild: discord.Guild | None, slot_time: datetime) -> str | None:
    """The @slot creation announcement carried on a fired slot's card, or None to post the card
    silently. Numberless, so it never goes stale as players join — the card's roster carries the count.
    Gated to a fire close to the draft time: an earlier fire posts silently and the underfill checks
    recruit the last seats near game time."""
    window = timedelta(hours=max(settings.pod_underfill_check_hours_tuple))
    if slot_time - datetime.now(timezone.utc) > window:
        return None
    role = find_role(guild, slot_role_name_for_event_time(slot_time) or "")
    if role is None:
        return None
    return SLOT_FIRE_PING.format(unix=int(slot_time.timestamp()), mention=role.mention)


async def _launch_slot(bot: commands.Bot, state, message_id: str) -> None:
    """A fired lazy slot graduates into a scheduled RSVP card: the signups carry over as Yes, and the
    card gathers any late signups right up to the lobby open. The slot then reflects the card as a
    jump-link on the next render and its own nudge is cleared — the card's underfill checks recruit
    from here. Falls back to reopening the slot if the card can't be posted."""
    set_code = active_set_code()
    slot_time = state.slot_time
    name = await asyncio.to_thread(pod_launch.ondemand_event_name_sync, set_code, slot_time)
    signups = await asyncio.to_thread(pod_launch.poll_yes_members_sync, state.signal_id)
    channel = _poll_channel(bot)
    event_id = None
    if isinstance(channel, discord.TextChannel):
        announcement = _fire_announcement(channel.guild, slot_time)
        event_id = await post_scheduled_card(
            bot, channel, set_code=set_code, event_time=slot_time, name=name, preseed_yes=signups,
            ping_role=False, content_override=announcement, format_locked=False,
        )
    if event_id is None:
        await asyncio.to_thread(pod_launch.release_fire_sync, state.signal_id)
        log.warning(f"slot fire for {state.signal_id} failed to launch; reverted to open")
    else:
        await clear_slot_nudge(bot, state.signal_id)
    await _rerender_board(bot, message_id, slot_time.astimezone(SCHEDULE_TZ).date())


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
    morning post. A day already past renders closed instead, so late churn can never reopen a retired
    board."""
    if signal_date < datetime.now(SCHEDULE_TZ).date():
        await close_launcher_for_date(bot, signal_date)
        return
    board = await asyncio.to_thread(pod_launch.live_launcher_board_sync)
    if board is None:
        return
    _guild_id, _channel_id, message_id, board_date = board
    if signal_date < board_date:
        return
    await _rerender_poll(bot, message_id, board_date)


async def roll_lane_after_pod(bot: commands.Bot, event_id: str) -> None:
    """Move the launcher column a played pod sat in to the next day, then invite that pod's players back a
    few minutes later. Fired once the pod is finalized, so a column can gather tomorrow while the other
    still plays today. No-op for an off-grid pod, which no column owns."""
    ref = await asyncio.to_thread(pod_launch.event_lane_ref_sync, event_id)
    if ref is None:
        return
    lane, played_day = ref
    rolled = await _roll_lane(bot, lane, played_day)
    if rolled is None:
        return
    bucket_key, _slot_time = rolled
    _schedule_play_again(bot, event_id, bucket_key)


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
        last = _lane_slots(slots, lane)[-1]
        if last.slot_time is None:
            continue
        played_out = last.committed and last.finished
        dead = not last.committed and last.status == STATUS_EXPIRED
        if played_out or dead:
            await _roll_lane(bot, lane, last.slot_time.astimezone(SCHEDULE_TZ).date())


async def _roll_lane(bot: commands.Bot, lane: str, from_day: date) -> tuple[str, datetime] | None:
    """Open the next day's slot for a lane, arm its beats, and re-render the live board so the column shows
    it. Returns (bucket_key, slot_time) of the slot now gathering, or None when the lane has nothing to roll
    to because a pod already holds that slot."""
    board = await asyncio.to_thread(pod_launch.live_launcher_board_sync)
    if board is None:
        return None
    guild_id, channel_id, message_id, board_date = board
    rolled = await asyncio.to_thread(
        pod_launch.roll_slot_forward_sync,
        lane=lane, from_day=from_day, guild_id=guild_id, channel_id=channel_id, message_id=message_id,
    )
    await _rerender_poll(bot, message_id, board_date)
    if rolled is None:
        return None
    signal_id, bucket_key, slot_time = rolled
    pod_launch.arm_slot_expiry(bot, signal_id, slot_time)
    schedule_slot_underfill_checks(bot.pod_scheduler, signal_id, slot_time, datetime.now(timezone.utc))
    log.info(f"rolled {lane} lane from {from_day} to {slot_time.isoformat()} as signal {signal_id}")
    return bucket_key, slot_time


def _schedule_play_again(bot: commands.Bot, event_id: str, bucket_key: str) -> None:
    """Post the next-day prompt a few minutes after the pod's result lands, so it never sits on top of the
    final game."""
    scheduler = getattr(bot, "pod_scheduler", None)
    if scheduler is None:
        return
    scheduler.add_job(
        post_play_again_prompt, "date",
        run_date=datetime.now(timezone.utc) + timedelta(minutes=PLAY_AGAIN_DELAY_MIN),
        args=[bot, event_id, bucket_key],
        id=f"pod-play-again-{event_id}", replace_existing=True,
    )


async def post_play_again_prompt(bot: commands.Bot, event_id: str, bucket_key: str) -> None:
    """Post the Play Again prompt in the finished pod's own thread, where the players who just drafted
    together already are."""
    thread_id = await asyncio.to_thread(pod_launch.event_thread_id_sync, event_id)
    if thread_id is None:
        return
    thread = await pod_launch.fetch_pod_thread(bot, int(thread_id))
    if thread is None:
        return
    content, view = build_play_again_prompt(bucket_key)
    try:
        await thread.send(content, view=view, allowed_mentions=discord.AllowedMentions.none())
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
    channel = channel or _poll_channel(bot)
    if channel is None:
        return
    guild = getattr(channel, "guild", None)
    slots = await asyncio.to_thread(pod_launch.launcher_snapshot_sync, message_id, signal_date)
    try:
        message = await channel.fetch_message(int(message_id))
        await message.edit(embed=build_poll_embed(slots, guild), view=PodPollView(slots, guild))
    except discord.HTTPException:
        log.warning(f"could not re-render launcher message {message_id}", exc_info=True)
