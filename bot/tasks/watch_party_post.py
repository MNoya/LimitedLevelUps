from __future__ import annotations

import logging
from datetime import date, datetime, timezone

import discord
from discord.ext import commands
from discord.utils import format_dt

from bot.commands.event_scribe import (
    COVERAGE_SCOPE,
    build_coverage_payload,
    coverage_emoji,
    date_range,
    schedule_title_marker,
)
from bot.commands.messages import MSG_EVENT_LIVE
from bot.config import settings
from bot.discord_helpers import message_text
from bot.services import mtgscribe
from bot.tasks.format_schedule_post import create_pinned_schedule, pinned_schedule
from bot.services.watch_party import (
    CHANNEL_TZ,
    HEADLINER_ORDER,
    CoverageWindow,
    CoveredEvent,
    channel_name,
    upcoming_windows,
)

HISTORY_SCAN_LIMIT = 50

MSG_TOPIC_LEAD = "Discuss the latest pro-level events"
MSG_TOPIC_NOW = "Now: {names} - {dates}"
MSG_TOPIC_NEXT = "Next up: {names} - {dates}"
MSG_TOPIC_STREAMS = "Watch on {urls}"
MSG_WINDOW_UPCOMING = "upcoming"
MSG_WINDOW_FOLLOW = "Follow on https://magic.gg/"
MSG_WINDOW_DATES = "{dates} ({relative})"
MSG_WINDOW_ENDS = "Ends {day} ({relative})"
MSG_ALSO_THIS_WEEKEND = "**Also this weekend:**"
MSG_ANNOUNCEMENT = (
    "**Join the {kind} Watch Party!**\n"
    "Come discuss the event, draft commentary, question the pros’ picks, and everything about {about}\n\n"
    "{subject_line}"
)
MSG_ANNOUNCEMENT_SUBJECT = "Subject: {name} - {subject}"

log = logging.getLogger(__name__)

_bot: commands.Bot | None = None


def init_watch_party(bot: commands.Bot) -> None:
    global _bot
    _bot = bot
    if not settings.watch_party_enabled:
        log.info("WATCH_PARTY_ENABLED=false; watch party tick disabled")
        return
    bot.pod_scheduler.add_job(fire_watch_party, "cron", minute="*/15", id="watch-party", replace_existing=True)
    log.info("watch-party armed every 15 minutes")


async def fire_watch_party() -> None:
    channel = _bot.get_channel(settings.watch_party_channel_id) if _bot is not None else None
    if not isinstance(channel, discord.TextChannel):
        log.debug(f"watch-party: channel {settings.watch_party_channel_id} unavailable; skipping tick")
        return
    now = datetime.now(timezone.utc)
    events = mtgscribe.load_events(arena_only=False)
    windows = upcoming_windows(events, now.astimezone(CHANNEL_TZ).date())
    await _sync_channel(channel, windows, now.astimezone(CHANNEL_TZ).date())
    await _refresh_coverage_pin(channel, events)
    if not windows:
        return
    await _post_window_embed(channel, windows[0], now)
    await _create_scheduled_events(channel, windows[0], now)
    await _announce_started_events(channel, windows[0], now)


def channel_topic(windows: list[CoverageWindow], today: date) -> str:
    lines = [MSG_TOPIC_LEAD]
    if not windows:
        return "\n".join(lines)
    current = windows[0]
    if current.first_day <= today:
        lines.append(MSG_TOPIC_NOW.format(names=_names(current), dates=_window_dates(current)))
        following = windows[1] if len(windows) > 1 else None
    else:
        following = current
    if following is not None:
        lines.append(MSG_TOPIC_NEXT.format(names=_names(following), dates=_window_dates(following)))
    urls = _stream_urls(current)
    if urls:
        lines.append(MSG_TOPIC_STREAMS.format(urls=_join(urls)))
    return "\n".join(lines)


def scheduled_event_candidates(window: CoverageWindow) -> list[CoveredEvent]:
    return [covered for covered in window.events if covered.kind.scheduled_event]


def announcement_candidates(window: CoverageWindow) -> list[CoveredEvent]:
    return [covered for covered in window.events if covered.kind.announced]


def window_embed_state(window: CoverageWindow, now: datetime) -> bool | None:
    headliner = window.headliner
    if window.first_day > now.astimezone(CHANNEL_TZ).date():
        return False
    if headliner.starts_at() <= now < headliner.ends_at():
        return True
    return None


def build_window_embed(window: CoverageWindow, emojis: dict, *, live: bool) -> discord.Embed:
    headliner = window.headliner
    emoji = coverage_emoji(headliner, emojis)
    lead = f"{emoji} " if emoji else ""
    lines = [f"### {lead}{window_marker(window, live=live)}"]
    if headliner.details:
        lines.append(f"**{headliner.details}**")
    if live:
        lines.append(MSG_WINDOW_ENDS.format(
            day=f"{headliner.last_day:%B %-d}", relative=format_dt(headliner.ends_at(), "R"),
        ))
    else:
        lines.append(MSG_WINDOW_DATES.format(
            dates=_event_dates(headliner), relative=format_dt(headliner.starts_at(), "R"),
        ))
    others = [covered for covered in _ranked(window) if covered is not headliner]
    if others:
        lines.append(f"\n{MSG_ALSO_THIS_WEEKEND}")
        lines.extend(_also_line(covered) for covered in others)
    urls = _stream_urls(window)
    if not live:
        lines.append(f"\n{MSG_WINDOW_FOLLOW}")
    elif urls:
        lines.append(f"\n{MSG_TOPIC_STREAMS.format(urls=_join(urls))}")
    return discord.Embed(description="\n".join(lines), color=discord.Color.green())


def window_marker(window: CoverageWindow, *, live: bool) -> str:
    status = MSG_EVENT_LIVE if live else MSG_WINDOW_UPCOMING
    return f"**{window.headliner.name}** {status}"


def build_announcement(covered: CoveredEvent) -> str:
    about = f"the **{covered.ordinal}**" if covered.ordinal else f"**{covered.name}**"
    return MSG_ANNOUNCEMENT.format(kind=covered.kind.name, about=about, subject_line=announcement_marker(covered))


def announcement_marker(covered: CoveredEvent) -> str:
    return MSG_ANNOUNCEMENT_SUBJECT.format(name=covered.name, subject=covered.first_subject())


async def _sync_channel(channel: discord.TextChannel, windows: list[CoverageWindow], today: date) -> None:
    name = channel_name(windows[0] if windows else None)
    topic = channel_topic(windows, today)
    if channel.name == name and (channel.topic or "") == topic:
        return
    try:
        await channel.edit(name=name, topic=topic, reason="watch party follows the coverage calendar")
        log.info(f"watch-party: channel now {name}")
    except discord.HTTPException:
        log.warning(f"watch-party: could not rename the channel to {name}", exc_info=True)


async def _refresh_coverage_pin(channel: discord.TextChannel, events: list) -> None:
    emojis = {emoji.name: emoji for emoji in await _bot.fetch_application_emojis()}
    payload = build_coverage_payload(events, emojis)
    message = await pinned_schedule(channel, schedule_title_marker(COVERAGE_SCOPE))
    if message is None:
        await create_pinned_schedule(channel, COVERAGE_SCOPE, payload)
        log.info("watch-party: posted and pinned the Coverage schedule")
        return
    current = message.embeds[0].description if message.embeds else None
    if current == payload["embed"].description:
        return
    try:
        await message.edit(**payload)
    except discord.HTTPException:
        log.warning("watch-party: could not edit the Coverage pin", exc_info=True)


async def _post_window_embed(channel: discord.TextChannel, window: CoverageWindow, now: datetime) -> None:
    live = window_embed_state(window, now)
    if live is None or await _already_posted(channel, window_marker(window, live=live)):
        return
    emojis = {emoji.name: emoji for emoji in await _bot.fetch_application_emojis()}
    await channel.send(embed=build_window_embed(window, emojis, live=live))
    log.info(f"watch-party: posted {window_marker(window, live=live)}")


async def _create_scheduled_events(channel: discord.TextChannel, window: CoverageWindow, now: datetime) -> None:
    existing = {event.name for event in channel.guild.scheduled_events}
    for covered in scheduled_event_candidates(window):
        if covered.name in existing or covered.starts_at() <= now:
            continue
        try:
            await channel.guild.create_scheduled_event(
                name=covered.name,
                description=covered.details,
                start_time=covered.starts_at(),
                end_time=covered.ends_at(),
                entity_type=discord.EntityType.external,
                privacy_level=discord.PrivacyLevel.guild_only,
                location=channel.jump_url,
            )
            log.info(f"watch-party: created the {covered.name} scheduled event")
        except discord.HTTPException:
            log.warning(f"watch-party: could not create the {covered.name} scheduled event", exc_info=True)


async def _announce_started_events(channel: discord.TextChannel, window: CoverageWindow, now: datetime) -> None:
    for covered in announcement_candidates(window):
        if not covered.starts_at() <= now < covered.first_day_ends_at():
            continue
        if await _already_posted(channel, announcement_marker(covered)):
            continue
        await channel.send(build_announcement(covered), allowed_mentions=discord.AllowedMentions.none())
        log.info(f"watch-party: announced {covered.name}")


async def _already_posted(channel: discord.TextChannel, marker: str) -> bool:
    async for message in channel.history(limit=HISTORY_SCAN_LIMIT):
        if message.author.id == channel.guild.me.id and marker in message_text(message):
            return True
    return False


def _names(window: CoverageWindow) -> str:
    return _join([covered.name for covered in _ranked(window)])


def _ranked(window: CoverageWindow) -> list[CoveredEvent]:
    return sorted(window.events, key=lambda covered: (HEADLINER_ORDER.index(covered.kind), covered.first_day))


def _also_line(covered: CoveredEvent) -> str:
    parts = [covered.name, covered.details, _event_dates(covered)]
    return ", ".join(part for part in parts if part)


def _event_dates(covered: CoveredEvent) -> str:
    return date_range(covered.event.start_local, covered.event.end_local)


def _window_dates(window: CoverageWindow) -> str:
    start = datetime.combine(window.first_day, datetime.min.time())
    end = datetime.combine(window.last_day, datetime.min.time())
    return date_range(start, end)


def _stream_urls(window: CoverageWindow) -> list[str]:
    urls: list[str] = []
    for covered in _ranked(window):
        if covered.stream_url and covered.stream_url not in urls:
            urls.append(covered.stream_url)
    return urls


def _join(items: list[str]) -> str:
    if len(items) <= 1:
        return "".join(items)
    return f"{', '.join(items[:-1])} and {items[-1]}"

