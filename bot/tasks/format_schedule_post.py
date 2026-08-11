"""Scribe-driven format-schedule tick — fires at the few daily windows when MTGA queues open.

Each tick reads the bundled MTG Scribe calendar once and, per channel, (1) re-renders the pinned /event-scribe
in place so it never goes stale across a rotation, and (2) announces events that went live since the
previous window. Windows are Pacific (MTGA's clock), so an announcement lands right as the queue opens
and tracks DST. A channel can hold more than one pin (Quick Draft and Flashback share one), so a pin is
matched by its title rather than just authorship; announcement dedup scans recent channel history, so
no table is needed and a restart never double-announces.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

import discord
from discord.ext import commands
from sqlalchemy import func, select

from bot.commands.event_scribe import (
    build_announcement,
    build_competitive_reminder,
    build_schedule_payload,
    schedule_title_marker,
    select_groups,
    select_season_groups,
)
from bot.commands.leaderboard import build_set_send_off_embeds
from bot.config import settings
from bot.database import SessionLocal
from bot.discord_helpers import message_text
from bot.models import MagicSet
from bot.services import mtgscribe
from bot.services.format_schedule import (
    ANNOUNCE_COMPETITIVE,
    ANNOUNCE_NONE,
    ANNOUNCE_WINDOWS,
    ARCHIVE_TIME,
    DEDUP_LOOKBACK,
    FORMAT_ARCHIVE_CATEGORY,
    OPEN_TZ,
    SCHEDULE_PINS,
    SchedulePin,
    active_set_seed,
    already_announced,
    announcement_format,
    archive_candidates,
    channel_for_set,
    newly_opened,
    next_rotation,
    previous_window_start,
    set_pin_frozen,
    set_seed_for_channel,
)
from bot.services.server_guide import stripped_channel_name
from bot.sets import RELEASE_TIME, RELEASE_TZ

HISTORY_SCAN_LIMIT = 100
RELATIVE_TIMESTAMP = "<t:"

log = logging.getLogger(__name__)

_bot: commands.Bot | None = None


def init_format_schedule(bot: commands.Bot) -> None:
    global _bot
    _bot = bot
    if not settings.format_schedule_enabled:
        log.info("FORMAT_SCHEDULE_ENABLED=false; format-schedule tick disabled")
        return
    for window in ANNOUNCE_WINDOWS:
        bot.pod_scheduler.add_job(
            fire_window,
            "cron",
            hour=window.hour,
            minute=window.minute,
            timezone=OPEN_TZ,
            id=f"format-schedule-{window.hour:02d}{window.minute:02d}",
            replace_existing=True,
        )
    bot.pod_scheduler.add_job(
        fire_rotation,
        "cron",
        hour=RELEASE_TIME.hour,
        minute=RELEASE_TIME.minute,
        timezone=RELEASE_TZ,
        id="format-schedule-rotation",
        replace_existing=True,
    )
    bot.pod_scheduler.add_job(
        fire_archive,
        "cron",
        hour=ARCHIVE_TIME.hour,
        minute=ARCHIVE_TIME.minute,
        timezone=RELEASE_TZ,
        id="format-schedule-archive",
        replace_existing=True,
    )
    windows = ", ".join(f"{w.hour:02d}:{w.minute:02d}" for w in ANNOUNCE_WINDOWS)
    log.info(f"format-schedule armed: {windows} {OPEN_TZ.key}; "
             f"send-off {RELEASE_TIME.hour:02d}:{RELEASE_TIME.minute:02d}, "
             f"archive {ARCHIVE_TIME.hour:02d}:{ARCHIVE_TIME.minute:02d} {RELEASE_TZ.key}")


def _guild() -> discord.Guild | None:
    if _bot is None:
        log.error("format-schedule: bot reference is not initialised")
        return None
    guild = _bot.get_guild(settings.discord_guild_id) if settings.discord_guild_id else None
    if guild is None:
        log.warning("format-schedule: guild unavailable; skipping tick")
    return guild


async def fire_rotation() -> None:
    """The outgoing set's send-off standings, on their own cron at the noon-ET release instant. Archiving
    is a separate job ``ARCHIVE_DELAY`` later, so the final boards sit in the channel players are already
    reading for an hour before it moves out of MTG Strategy."""
    guild = _guild()
    if guild is None:
        return
    for channel in archive_candidates(guild.text_channels):
        await _post_send_off(channel)


async def fire_archive() -> None:
    """Archive what the rotation left behind, an hour after its send-off. The announce tick re-runs this as
    an idempotent fallback: an archived channel is no longer a candidate, so a second pass does nothing."""
    guild = _guild()
    if guild is not None:
        await _archive_stale_channels(guild)


async def fire_window() -> None:
    guild = _guild()
    if guild is None:
        return

    now = datetime.now(timezone.utc)
    since = previous_window_start(now)
    events = mtgscribe.load_events()
    emojis = {emoji.name: emoji for emoji in await _bot.fetch_application_emojis()}

    for pin in SCHEDULE_PINS:
        channel = _resolve_channel(guild, pin)
        if channel is None:
            continue
        if pin.maintain_pin:
            in_progress, upcoming, scope = select_pin(events, pin)
            archival = _archives_set_pin(pin, now)
            if archival:
                in_progress, upcoming = select_season_groups(events, scope), []
            if not (archival and await _pin_already_archival(channel, scope)):
                await _refresh_pin(channel, scope, in_progress, upcoming, emojis,
                                   create_if_missing=pin.auto_pin, archival=archival)
        if pin.announce != ANNOUNCE_NONE:
            scheduled = announce_groups(events, pin)
            fresh = newly_opened(scheduled, since, now)
            await _announce(channel, pin, fresh, scheduled, emojis)

    await _archive_stale_channels(guild)


async def _archive_stale_channels(guild: discord.Guild) -> None:
    """Move each outgoing set channel to the Format Archive and tell the admin channel. The new set's
    channel is mod-created during preview season and coexists with the outgoing one until the leaderboard
    rotates — the bot only archives what the rotation left behind, never creates. No guide page is synced
    here: channel-overview and the set-tracking To-Do resolve to the newest set channel in MTG Strategy,
    which the incoming set's already is by the time a rotation runs, so `!guide` when a mod creates that
    channel is what those pages follow."""
    stale = archive_candidates(guild.text_channels)
    if not stale:
        return
    archive = discord.utils.get(guild.categories, name=FORMAT_ARCHIVE_CATEGORY)
    if archive is None:
        log.warning(f"format-schedule: no '{FORMAT_ARCHIVE_CATEGORY}' category; skipping archiving")
        return
    admin_channel = _admin_channel(guild)
    for channel in stale:
        if await _archive_channel(channel, archive):
            await _notify_archived(admin_channel, channel)


def _admin_channel(guild: discord.Guild) -> discord.TextChannel | None:
    for channel in guild.text_channels:
        if "admin" in channel.name.lower():
            return channel
    return None


async def _post_send_off(channel: discord.TextChannel) -> None:
    """Post the outgoing set's final standings into its channel before it's archived — the overall board
    plus each per-format board that has players. Skipped when the channel matches no stale set."""
    seed = set_seed_for_channel(channel.name)
    if seed is None:
        return
    embeds = await asyncio.to_thread(send_off_embeds, seed.code)
    for embed in embeds:
        try:
            await channel.send(embed=embed)
        except discord.HTTPException:
            log.warning(f"format-schedule: could not post the {seed.code} send-off in #{channel.name}", exc_info=True)
            return


def send_off_embeds(set_code: str) -> list[discord.Embed]:
    """The outgoing set's final leaderboard embeds, built off the DB — shared by the rotation tick and
    `!test sendoff` so both render the same boards."""
    with SessionLocal() as session:
        magic_set = session.execute(
            select(MagicSet).where(func.upper(MagicSet.code) == set_code.upper())
        ).scalar_one_or_none()
        if magic_set is None:
            return []
        return build_set_send_off_embeds(session, magic_set)


async def _notify_archived(admin_channel: discord.TextChannel | None, channel: discord.TextChannel) -> None:
    if admin_channel is None:
        log.info("format-schedule: no admin channel found; skipping archive notice")
        return
    try:
        await admin_channel.send(f"📥 Moved {channel.mention} to **{FORMAT_ARCHIVE_CATEGORY}**")
    except discord.HTTPException:
        log.warning(f"format-schedule: could not post archive notice for #{channel.name}", exc_info=True)


async def _archive_channel(channel: discord.TextChannel, archive: discord.CategoryChannel) -> bool:
    neighbor = _alphabetical_neighbor(archive, channel)
    try:
        if neighbor is None:
            await channel.move(beginning=True, category=archive)
        else:
            await channel.move(after=neighbor, category=archive)
        log.info(f"format-schedule: archived #{channel.name} to {FORMAT_ARCHIVE_CATEGORY}")
        return True
    except discord.HTTPException:
        log.warning(f"format-schedule: could not archive #{channel.name}", exc_info=True)
        return False


def _alphabetical_neighbor(archive: discord.CategoryChannel,
                           channel: discord.TextChannel) -> discord.TextChannel | None:
    """The archived channel to slot after, keeping the category's emoji-blind alphabetical order.
    ``None`` sorts the newcomer to the top."""
    name = stripped_channel_name(channel.name)
    neighbor = None
    for existing in archive.text_channels:
        if stripped_channel_name(existing.name) < name:
            neighbor = existing
    return neighbor


def select_pin(events: list, pin: SchedulePin) -> tuple[list, list, str]:
    """The pinned schedule's groups and its title scope: a format-filtered view, or the whole active
    set when the pin carries no format filter (the set channel). Untrimmed, to match what
    /event-scribe renders for an explicit filter or set.

    The scope is the date-derived active set, the same source the leaderboard rotates on. It also names
    the pin ``_refresh_pin`` searches for, so a scope naming any other set silently matches no pin.
    """
    if pin.pin_filters:
        in_progress, upcoming = select_groups(events, list(pin.pin_filters), apply_horizon=False)
        return in_progress, upcoming, pin.scope_label
    set_name = active_set_seed().name
    in_progress, upcoming = select_groups(events, None, set_name, apply_horizon=False)
    return in_progress, upcoming, set_name


def _archives_set_pin(pin: SchedulePin, now: datetime) -> bool:
    """Whether the set channel's pin should be written in its final, archival form.

    True inside the active set's last week. The pin is written once more with absolute dates and no
    section headers, then left alone — refreshing to the end would leave it holding a board whose every
    queue had expired, and the channel is archived days later with that pin as the season's record.
    Format pins (Quick, Flashback, Sealed) are not tied to a set and never archive.
    """
    return not pin.pin_filters and set_pin_frozen(now)


async def _pin_already_archival(channel: discord.TextChannel, scope: str) -> bool:
    """Whether the archival write has already happened, read off the pin instead of tracked state: an
    archival board carries no ``<t:`` relative timestamp, a live one always does. Keeps the final write
    to exactly once without a table, and survives a restart."""
    message = await _pinned_schedule(channel, schedule_title_marker(scope))
    if message is None:
        return False
    if RELATIVE_TIMESTAMP in message_text(message):
        return False
    log.info(f"format-schedule: the {scope} pin is already archival; leaving it frozen")
    return True


def announce_groups(events: list, pin: SchedulePin) -> list:
    in_progress, upcoming = select_groups(events, list(pin.announce_filters), apply_horizon=False)
    return in_progress + upcoming


def _resolve_channel(guild: discord.Guild, pin: SchedulePin) -> discord.TextChannel | None:
    """A category-routed pin follows the active set's own channel by name, never the newest channel in
    the category: a mod creates the incoming set's channel during preview season, and newest-created
    would hand the running set's pin and announcements to a set that has not started yet."""
    if pin.category is not None:
        seed = active_set_seed()
        channel = channel_for_set(guild.text_channels, seed, pin.category)
        if channel is None:
            log.info(f"format-schedule: no {seed.code} channel in category '{pin.category}' for {pin.key}")
        return channel
    for channel in guild.text_channels:
        if pin.channel_name in channel.name:
            return channel
    log.info(f"format-schedule: no channel matching '{pin.channel_name}' for {pin.key}")
    return None


async def _refresh_pin(channel: discord.TextChannel, scope: str, in_progress: list,
                       upcoming: list, emojis: dict, *, create_if_missing: bool = False,
                       archival: bool = False) -> None:
    """Edit the pin in place, matching on the title so the right pin is edited when a channel holds
    several. Pins are human-seeded (the owner pins a filtered /event-scribe post) and a channel without
    a matching pin is left alone. ``create_if_missing`` would post and pin the schedule itself instead;
    no pin enables it today, reserved for when the bot should seed a channel's pin."""
    payload = build_schedule_payload(in_progress, upcoming, emojis, scope, archival=archival)
    message = await _pinned_schedule(channel, schedule_title_marker(scope))
    if message is None:
        if create_if_missing:
            await _create_pinned_schedule(channel, scope, payload)
        return
    try:
        await message.edit(**payload)
    except discord.HTTPException:
        log.warning(f"format-schedule: could not edit the '{scope}' pin in #{channel.name}", exc_info=True)


async def _create_pinned_schedule(channel: discord.TextChannel, scope: str, payload: dict) -> None:
    """Post and pin a fresh schedule. ``_pinned_schedule`` only finds pinned posts, so an unpinned one
    would be re-created every tick — if the pin fails, the post is removed so creation stays atomic."""
    try:
        message = await channel.send(**payload)
    except discord.HTTPException:
        log.warning(f"format-schedule: could not post the '{scope}' pin in #{channel.name}", exc_info=True)
        return
    try:
        await message.pin()
    except discord.HTTPException:
        log.warning(f"format-schedule: could not pin the '{scope}' schedule in #{channel.name}; "
                    "removing the unpinned post", exc_info=True)
        await _delete_quietly(message)


async def _delete_quietly(message: discord.Message) -> None:
    try:
        await message.delete()
    except discord.HTTPException:
        log.warning("format-schedule: could not remove the unpinned schedule post", exc_info=True)


async def _pinned_schedule(channel: discord.TextChannel, marker: str) -> discord.Message | None:
    try:
        async for message in channel.pins():
            if _bot.user is not None and message.author.id == _bot.user.id and marker in message_text(message):
                return message
    except discord.HTTPException:
        log.warning(f"format-schedule: could not read pins in #{channel.name}", exc_info=True)
    return None


async def _announce(channel: discord.TextChannel, pin: SchedulePin, fresh: list,
                    scheduled: list, emojis: dict) -> None:
    """Announce each freshly-opened group. ``scheduled`` is the full filtered schedule (in-progress +
    upcoming), so the Next Up preview can look past ``fresh`` to the rotation that follows."""
    if not fresh:
        return
    recent = await _recent_bot_messages(channel)
    for group in fresh:
        embed, marker = announcement_for(pin, group, scheduled, emojis)
        if already_announced(recent, marker, group.label):
            continue
        try:
            await channel.send(embed=embed)
            recent.append(embed.description or "")
        except discord.HTTPException:
            log.warning(f"format-schedule: could not announce '{group.label}' in #{channel.name}", exc_info=True)


def announcement_for(pin: SchedulePin, group: mtgscribe.EventGroup, groups: list, emojis: dict):
    """Build the announcement embed and its dedup marker for a freshly-opened event. The single place
    both the tick and `!test formatschedule` route through, so they can't drift. Competitive pins get
    the reminder builder; the rest get the rotation "is live!" callout with a Next Up preview."""
    if pin.announce == ANNOUNCE_COMPETITIVE:
        return build_competitive_reminder(group, emojis), group.label
    word = announcement_format(group)
    embed = build_announcement(group, emojis, format_word=word, next_group=next_rotation(groups, group))
    return embed, word or "is live"


async def _recent_bot_messages(channel: discord.TextChannel) -> list[str]:
    since = datetime.now(timezone.utc) - DEDUP_LOOKBACK
    texts: list[str] = []
    try:
        async for message in channel.history(after=since, limit=HISTORY_SCAN_LIMIT):
            if _bot.user is None or message.author.id != _bot.user.id:
                continue
            text = message_text(message)
            if text:
                texts.append(text)
    except discord.HTTPException:
        log.warning(f"format-schedule: could not scan #{channel.name} history", exc_info=True)
    return texts
