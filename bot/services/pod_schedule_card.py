"""Build, post and refresh the pod format schedule card.

The embed and image builders are shared by the `/pod-schedule` command and the daily tick. The bot's own post
is matched by its heading marker and edited in place, posted and pinned when none is present, so the schedule
stays current without stacking duplicates. The view is passed in so this stays free of the button module that
imports it back.
"""
from __future__ import annotations

import asyncio
import io
import logging
from datetime import date, datetime

import discord

from bot import emojis
from bot.config import PRODUCTION_GUILD_ID, settings
from bot.database import SessionLocal
from bot.discord_helpers import EM_SPACE, NBSP, message_text
from bot.services import pod_format_interest as fi
from bot.services.championship_dates import championship_on
from bot.services.ping_roles import SET_CHAMPION_ROLE_NAME
from bot.services.pod_format_allocator import vote_results
from bot.services.pod_format_schedule import (
    calendar_days,
    latest_on,
    rotation_in,
    schedule_overlay,
    scheduled_formats,
    weeks_until_next_rotation,
)
from bot.services.pod_roles import role_mention
from bot.services.pod_schedule import SCHEDULE_TZ
from bot.services.pod_schedule_image import render_calendar_png
from bot.services.pod_signals import WEEKDAY_BUCKETS, next_slot_start
from bot.sets import active_set_code, release_instant, set_name_for

log = logging.getLogger(__name__)

MSG_HEADING = "## 🗓️ [Pod Draft Format Schedule]({url}) 🚀"
MSG_SLOT = "{emoji} {role} **<t:{unix}:t>**"
MSG_DAILY_SET = "{symbol} {role} **every day**"
MSG_FLASHBACK_SEASON = (
    "{flashback} {role} season is on! Two formats each day\n"
    "🗳️ **Vote Formats** to put yours on the calendar"
)
MSG_CHAMPIONSHIP = "👑 {role} <t:{unix}:R>"
MSG_ARRIVAL = "{symbol} **{name}** <t:{unix}:R>"
MSG_NO_VOTES = "No votes yet"
RESULTS_PER_ROW = 4

CHANNEL_URL = "https://discord.com/channels/{guild_id}/{channel_id}"
SCHEDULE_MARKER = "Pod Draft Format Schedule"

IMAGE_FILENAME = "pod-schedule.png"
IMAGE_URL = f"attachment://{IMAGE_FILENAME}"
DEFAULT_WEEKS = 4
MAX_WEEKS = 8
COLUMN_GAP = EM_SPACE * 2
LINE_GAP = "\n\n"


async def refresh_schedule_post(channel: discord.abc.Messageable, *, view: discord.ui.View | None = None) -> None:
    embed, file = await render_schedule(getattr(channel, "guild", None))
    message = await _existing_post(channel)
    if message is None:
        await _post_fresh(channel, embed, file, view)
        return
    try:
        await message.edit(embed=embed, attachments=[file], view=view)
    except discord.HTTPException:
        log.warning("pod-schedule card: could not edit the schedule message", exc_info=True)


async def repost_schedule_post(channel: discord.abc.Messageable, *, view: discord.ui.View | None = None) -> None:
    """Remove the pinned schedule card and post a fresh one, so a preview always surfaces a new message rather
    than editing the pin in place the way the daily tick does."""
    existing = await _existing_post(channel)
    if existing is not None:
        try:
            await existing.delete()
        except discord.HTTPException:
            log.warning("pod-schedule card: could not remove the old schedule", exc_info=True)
    embed, file = await render_schedule(getattr(channel, "guild", None))
    await _post_fresh(channel, embed, file, view)


async def render_schedule(
    guild: discord.Guild | None, weeks: int | None = None,
) -> tuple[discord.Embed, discord.File]:
    now = datetime.now(SCHEDULE_TZ)
    weeks = weeks if weeks is not None else weeks_until_next_rotation(now.date(), MAX_WEEKS)
    days = calendar_days(now.date(), weeks)
    with SessionLocal() as session, schedule_overlay(session, days[0], days[-1]):
        png = await asyncio.to_thread(render_calendar_png, now.date(), weeks)
        embed = build_schedule_embed(guild, now, weeks)
    return embed, discord.File(io.BytesIO(png), IMAGE_FILENAME)


async def _existing_post(channel: discord.abc.Messageable) -> discord.Message | None:
    if not isinstance(channel, discord.TextChannel):
        return None
    try:
        async for message in channel.pins():
            if message.author.bot and SCHEDULE_MARKER in message_text(message):
                return message
    except discord.HTTPException:
        log.warning("pod-schedule card: could not read pins", exc_info=True)
    return None


async def _post_fresh(
    channel: discord.abc.Messageable, embed: discord.Embed, file: discord.File, view: discord.ui.View | None,
) -> None:
    try:
        message = await channel.send(
            embed=embed, file=file, view=view, allowed_mentions=discord.AllowedMentions.none(),
        )
    except discord.HTTPException:
        log.warning("pod-schedule card: could not post the schedule", exc_info=True)
        return
    try:
        await message.pin()
    except discord.HTTPException:
        log.warning("pod-schedule card: could not pin the schedule", exc_info=True)


def build_schedule_embed(guild: discord.Guild | None, now: datetime, weeks: int) -> discord.Embed:
    days = calendar_days(now.date(), weeks)
    lines = [slot_line(guild, now), formats_line(guild, days)]
    arrival = arrival_line(guild, days, now)
    if arrival:
        lines.append(arrival)
    championship = championship_line(guild, days, now)
    if championship:
        lines.append(championship)
    heading = MSG_HEADING.format(url=coordination_url(guild))
    embed = discord.Embed(description=f"{heading}\n{LINE_GAP.join(lines)}", color=discord.Color.green())
    embed.set_image(url=IMAGE_URL)
    return embed


def build_vote_results_embed() -> discord.Embed:
    today = datetime.now(SCHEDULE_TZ).date()
    with SessionLocal() as session:
        kept = vote_results(session, today)
    tiers: dict[int, list[str]] = {}
    for code, votes, days in kept:
        if days == 0:
            continue
        icon = emojis.set_symbol(code) or fi.flashback_emoji()
        tiers.setdefault(days, []).append(f"{icon} **{code}** {votes}")
    sections = []
    for days in sorted(tiers, reverse=True):
        label = f"{days} days" if days != 1 else "1 day"
        entries = tiers[days]
        gap = NBSP * 3
        rows = [gap.join(entries[i:i + RESULTS_PER_ROW]) for i in range(0, len(entries), RESULTS_PER_ROW)]
        sections.append(f"### {label}\n" + "\n".join(rows))
    heading = f"### {fi.flashback_emoji()} Format Vote Results"
    body = "\n".join(sections) if sections else MSG_NO_VOTES
    return discord.Embed(description=f"{heading}\n\n{body}", color=discord.Color.green())


def coordination_url(guild: discord.Guild | None) -> str:
    """The heading links to the channel the pods actually run in, which is the one route out of the schedule
    that survives a pin preview: those render the embed but drop any button under it. A DM carries no guild
    of its own, so it lands on the production server."""
    guild_id = guild.id if guild is not None else PRODUCTION_GUILD_ID
    return CHANNEL_URL.format(guild_id=guild_id, channel_id=settings.pod_draft_channel_id)


def slot_line(guild: discord.Guild | None, now: datetime) -> str:
    """Both slots on one row, each naming the role to hold and when it next drafts."""
    slots = []
    for bucket in WEEKDAY_BUCKETS:
        start = next_slot_start(bucket.slot_key, now)
        if start is None:
            continue
        slots.append(MSG_SLOT.format(
            emoji=bucket.emoji, role=role_mention(guild, bucket.role_name), unix=int(start.timestamp()),
        ))
    return COLUMN_GAP.join(slots)


def formats_line(guild: discord.Guild | None, days: list[date]) -> str:
    """What a day carries. Inside a set's own run every day drafts the latest set, named by its ping role so
    the line survives a rotation. Once the community schedule fills days with a second format the line states
    the two-a-day shape and leaves which formats to the calendar image."""
    for day in days:
        if len(scheduled_formats(day)) > 1:
            return MSG_FLASHBACK_SEASON.format(
                flashback=fi.flashback_emoji(), role=role_mention(guild, fi.FLASHBACK_ROLE_NAME),
            )
    code = active_set_code()
    return MSG_DAILY_SET.format(symbol=fi.format_emoji(code), role=role_mention(guild, fi.LATEST_SET_ROLE_NAME))


def arrival_line(guild: discord.Guild | None, days: list[date], now: datetime) -> str:
    """The next set arriving inside the span, empty once its rotation has passed. A rotation stays in the span
    for the rest of its week and a long span can hold a second one, so the one already made is skipped."""
    arrival = rotation_in(days, now)
    if arrival is None:
        return ""
    incoming = latest_on(arrival)
    return MSG_ARRIVAL.format(
        symbol=fi.format_emoji(incoming), name=set_name_for(incoming),
        unix=int(release_instant(arrival).timestamp()),
    )


def championship_line(guild: discord.Guild | None, days: list[date], now: datetime) -> str:
    """The next championship the span holds. Empty in a span with none left: a played one keeps its calendar
    crown but leaves this line, where its relative timestamp would read as upcoming."""
    for day in days:
        starts_at = championship_on(day)
        if starts_at is not None and starts_at > now:
            return MSG_CHAMPIONSHIP.format(
                role=role_mention(guild, SET_CHAMPION_ROLE_NAME), unix=int(starts_at.timestamp()),
            )
    return ""
