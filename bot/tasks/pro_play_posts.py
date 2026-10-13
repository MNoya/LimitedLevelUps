"""Pro Play posts: clock posts and Melee round alerts on a ten-minute tick, reveal posts as the marker moves"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Callable

import discord
from discord.ext import commands
from sqlalchemy import select

from bot.config import OWNER_DISCORD_ID, PRODUCTION_GUILD_ID, settings
from bot.database import SessionLocal
from bot.models import FantasyRound
from bot.services import bot_log
from bot.services.fantasy_event import FantasyEvent, all_events
from bot.services.fantasy_podium import FantasyWinner, podium_sync
from bot.services.fantasy_posts import (
    bracket_open_embed,
    ceremony_embed,
    close_reminder_embed,
    day_live_embed,
    day_one_complete_embed,
    picks_open_embed,
    round_complete_embed,
)
from bot.services.fantasy_reveal import (
    DAY_ONE_COMPLETE,
    EVENT_COMPLETE,
    SWISS_COMPLETE,
    TOP8_ROUND_NAMES,
    manual_release_rounds,
    revealed_milestones,
)
from bot.services.ping_roles import FANTASY_CHAMPION_ROLE_NAME
from bot.services.pod_roles import find_role, role_label, rotate_role
from bot.services.role_ping import ensure_member_cache
from bot.services.watch_party import PREMIER_SCHEDULES

TICK = timedelta(minutes=10)
PICKS_OPEN_LEAD = timedelta(days=7)
CLOSE_REMINDER_LEADS = (timedelta(hours=24), timedelta(hours=1))
DAY_LABELS = ("Day 1", "Day 2", "Top 8")
TOP8_LABELS = ("Quarterfinals", "Semifinals", "Final")

MSG_UNSEEDED_BRACKET = (
    "**{event}** Quarterfinals don't pair seeds 5 to 8 against seeds 1 to 4, so Bracket positions follow Melee tables"
)

log = logging.getLogger(__name__)

_bot: commands.Bot | None = None


def init_pro_play_posts(bot: commands.Bot) -> None:
    global _bot
    _bot = bot


async def fire_pro_play_posts() -> None:
    tick = tick_start(datetime.now(timezone.utc))
    for event in all_events():
        if event.replay_only:
            continue
        for moment, build in timed_posts(event):
            if is_due(moment, tick):
                await _post_to_watch_party(event, build())
        completed = await asyncio.to_thread(_completed_rounds, event.code)
        for round_number in manual_release_rounds(event):
            completed_at = completed.get(round_number)
            if completed_at is not None and is_due(completed_at, tick):
                await _alert_round_complete(event, round_number)


async def announce_reveal(event: FantasyEvent, previous: int, revealed: int) -> None:
    for milestone in revealed_milestones(event, previous, revealed):
        if milestone == DAY_ONE_COMPLETE:
            await _post_to_watch_party(event, day_one_complete_embed(event))
        elif milestone == SWISS_COMPLETE:
            await _post_to_watch_party(event, bracket_open_embed(event))
        elif milestone == EVENT_COMPLETE:
            await _crown_podium(event)


def timed_posts(event: FantasyEvent) -> list[tuple[datetime, Callable[[], discord.Embed]]]:
    posts: list[tuple[datetime, Callable[[], discord.Embed]]] = [
        (event.picks_lock_at - PICKS_OPEN_LEAD, lambda: picks_open_embed(event)),
    ]
    for lead in CLOSE_REMINDER_LEADS:
        posts.append((event.picks_lock_at - lead, lambda: close_reminder_embed(event)))
    schedule = PREMIER_SCHEDULES.get(event.schedule_name or "")
    if schedule is not None:
        for label, day in zip(DAY_LABELS, schedule.days):
            starts_at = datetime.combine(day.day, day.start, schedule.tz)
            posts.append((starts_at, lambda label=label: day_live_embed(event, label)))
    return posts


def round_label(event: FantasyEvent, round_number: int) -> tuple[str, str]:
    if round_number <= event.swiss_rounds:
        return f"Round {round_number}", str(round_number)
    stage = round_number - event.swiss_rounds - 1
    return TOP8_LABELS[stage], TOP8_ROUND_NAMES[stage][-1]


def tick_start(now: datetime) -> datetime:
    return now.replace(minute=now.minute - now.minute % 10, second=0, microsecond=0)


def is_due(moment: datetime, tick: datetime) -> bool:
    return tick - TICK < moment <= tick


def _completed_rounds(event_code: str) -> dict[int, datetime]:
    with SessionLocal() as session:
        return dict(session.execute(
            select(FantasyRound.round_number, FantasyRound.completed_at).where(FantasyRound.event_code == event_code)
        ).all())


async def _post_to_watch_party(event: FantasyEvent, embed: discord.Embed, *, pin: bool = False) -> None:
    if not event.live:
        return
    channel = _watch_party_channel()
    if channel is None:
        log.warning(f"pro-play-posts: watch party channel unavailable, {event.code} post skipped")
        return
    try:
        message = await channel.send(embed=embed, allowed_mentions=discord.AllowedMentions.none())
        if pin:
            await message.pin(reason="Pro Play results")
    except discord.HTTPException:
        log.warning(f"pro-play-posts: could not post for {event.code}", exc_info=True)
        return
    log.info(f"pro-play-posts: posted for {event.code}: {embed.description.splitlines()[0]}")


def _watch_party_channel() -> discord.TextChannel | None:
    if not settings.watch_party_enabled or _bot is None:
        return None
    channel = _bot.get_channel(settings.watch_party_channel_id)
    return channel if isinstance(channel, discord.TextChannel) else None


async def _crown_podium(event: FantasyEvent) -> None:
    winners = await asyncio.to_thread(podium_sync, event.code)
    channel = _watch_party_channel()
    if not winners or channel is None or not event.live:
        return
    guild = channel.guild
    role = find_role(guild, FANTASY_CHAMPION_ROLE_NAME)
    if guild.id == PRODUCTION_GUILD_ID and role is not None:
        await ensure_member_cache(guild)
        members = _podium_members(guild, winners)
        granted = await rotate_role(role, members, reason=f"{event.code} fantasy podium")
        log.info(f"pro-play-posts: {FANTASY_CHAMPION_ROLE_NAME} moved to {granted} of {len(winners)} for {event.code}")
    elif role is None:
        log.warning(f"pro-play-posts: {FANTASY_CHAMPION_ROLE_NAME!r} missing in {guild.name}, announcing only")
    champion_role = role_label(guild, FANTASY_CHAMPION_ROLE_NAME)
    await _post_to_watch_party(event, ceremony_embed(event, winners, champion_role), pin=True)


def _podium_members(guild: discord.Guild, winners: list[FantasyWinner]) -> list[discord.Member]:
    members = []
    for winner in winners:
        if winner.discord_id is None or not winner.discord_id.isdigit():
            continue
        member = guild.get_member(int(winner.discord_id))
        if member is not None:
            members.append(member)
    return members


async def alert_unseeded_bracket(event: FantasyEvent) -> None:
    if _bot is None:
        return
    await bot_log.get(_bot).post_plain(
        f"<@{OWNER_DISCORD_ID}> {MSG_UNSEEDED_BRACKET.format(event=event.short_name)}",
        allowed_mentions=discord.AllowedMentions(users=True),
    )


async def _alert_round_complete(event: FantasyEvent, round_number: int) -> None:
    if _bot is None:
        return
    label, argument = round_label(event, round_number)
    await bot_log.get(_bot).post_plain(
        f"<@{OWNER_DISCORD_ID}>",
        embed=round_complete_embed(event, label, argument),
        allowed_mentions=discord.AllowedMentions(users=True),
    )
    log.info(f"pro-play-posts: {event.code} {label} complete on Melee, moderators alerted")
