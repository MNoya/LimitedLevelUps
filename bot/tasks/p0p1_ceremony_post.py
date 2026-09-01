"""Crowns the P0P1 podium when a contest reaches its scoring date: swaps the Top P0P1 Challenger role to
the new top three and posts the reveal into the contest set's own channel.

Hourly rather than pinned to the instant, so a deploy across the scoring time still lands it. Idempotent on
the announcement already sitting in the channel, so the repeated tick neither reposts nor re-swaps roles.
The role swap and the pings run on the production guild alone; a hand-fired test elsewhere renders the post
without touching real roles.
"""
from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timedelta, timezone

import discord
from discord.ext import commands
from sqlalchemy.exc import SQLAlchemyError

from bot import audit
from bot.config import PRODUCTION_GUILD_ID, settings
from bot.discord_helpers import message_text
from bot.services import p0p1_ceremony, p0p1_contest, p0p1_copy
from bot.services.format_schedule import channel_for_set
from bot.services.ping_roles import TOP_P0P1_CHALLENGER_ROLE_NAME
from bot.sets import ALL_SETS

log = logging.getLogger(__name__)

REVEAL_WINDOW = timedelta(days=14)

_bot: commands.Bot | None = None


def init_p0p1_ceremony(bot: commands.Bot) -> None:
    global _bot
    _bot = bot
    bot.pod_scheduler.add_job(
        fire_ceremony, "cron", minute=5, timezone=timezone.utc,
        id="p0p1-podium-ceremony", replace_existing=True,
    )
    log.info("p0p1-ceremony: hourly tick armed for each contest scoring date")


async def fire_ceremony() -> None:
    if _bot is None:
        return
    now = datetime.now(timezone.utc)
    contest = contest_due(now)
    if contest is None:
        return
    guild = _bot.get_guild(settings.discord_guild_id) if settings.discord_guild_id else None
    if guild is None:
        log.warning("p0p1-ceremony: no configured guild, skipping")
        return
    try:
        await post_ceremony(guild, contest, now)
    except (SQLAlchemyError, discord.HTTPException):
        log.warning(f"p0p1-ceremony: {contest.code} tick failed, retrying next hour", exc_info=True)


def contest_due(now: datetime) -> p0p1_contest.Contest | None:
    """The most recent contest whose scoring date has passed inside the reveal window. Older ones already
    carry their announcement, and the idempotency check stops a fresh one inside the window from reposting."""
    for contest in p0p1_contest.all_contests():
        if contest.scoring_date <= now < contest.scoring_date + REVEAL_WINDOW:
            return contest
    return None


async def post_ceremony(
    guild: discord.Guild, contest: p0p1_contest.Contest, now: datetime, *, force: bool = False,
) -> bool:
    """Returns whether the reveal posted. ``force`` skips the already-posted check for a hand-fired run."""
    channel = _set_channel(guild, contest.code)
    if channel is None:
        log.warning(f"p0p1-ceremony: no channel found for {contest.code}, skipping")
        return False
    if not force and await _already_announced(channel, contest):
        return False

    winners = await asyncio.to_thread(p0p1_ceremony.podium_sync, contest.code)
    if not winners:
        log.warning(f"p0p1-ceremony: no podium for {contest.code}, skipping")
        return False

    on_production = guild.id == PRODUCTION_GUILD_ID
    await _ensure_member_cache(guild)
    role = discord.utils.get(guild.roles, name=TOP_P0P1_CHALLENGER_ROLE_NAME)

    members: list[discord.Member] = []
    podium: list[str] = []
    for winner in winners:
        member = guild.get_member(int(winner.discord_id)) if winner.discord_id and winner.discord_id.isdigit() else None
        if member is not None:
            members.append(member)
            podium.append(member.mention)
        else:
            podium.append(f"**{winner.name}**")

    if on_production and role is not None:
        await _swap_challengers(role, members)
    elif role is None:
        log.warning(f"p0p1-ceremony: {TOP_P0P1_CHALLENGER_ROLE_NAME!r} missing in {guild.name}, announcing only")

    featured = p0p1_contest.featured_contest(now)
    view = p0p1_copy.ceremony_view(
        contest, featured_code=featured.code if featured is not None else None,
        podium=podium, challenger_mention=p0p1_copy.challenger_mention(role),
    )
    mentions = discord.AllowedMentions(users=members if on_production else [], roles=False, everyone=False)
    started = time.monotonic()
    await channel.send(view=view, allowed_mentions=mentions)
    audit.event("p0p1_ceremony", contest=contest.code, channel_id=str(channel.id),
                winners=[winner.name for winner in winners], granted=len(members) if on_production else 0)
    await _post_debug(contest, channel, winners, len(members), on_production, time.monotonic() - started)
    return True


async def _swap_challengers(role: discord.Role, members: list[discord.Member]) -> None:
    for holder in list(role.members):
        if holder in members:
            continue
        try:
            await holder.remove_roles(role, reason="p0p1 podium rotation")
        except discord.HTTPException:
            log.warning(f"p0p1-ceremony: could not strip {role.name!r} from {holder}", exc_info=True)
    for member in members:
        try:
            await member.add_roles(role, reason="p0p1 podium winner")
        except discord.HTTPException:
            log.warning(f"p0p1-ceremony: could not grant {role.name!r} to {member}", exc_info=True)


async def _post_debug(
    contest: p0p1_contest.Contest, channel: discord.TextChannel, winners: list[p0p1_ceremony.Winner],
    granted: int, on_production: bool, elapsed: float,
) -> None:
    bot_log = getattr(_bot, "bot_log", None)
    if bot_log is None:
        return
    podium = ", ".join(f"{winner.rank}. {winner.name}" for winner in winners)
    parts = [
        f"P0P1 `{contest.code}` podium posted in {channel.mention}",
        f"winners {podium}",
        f"granted the role to **{granted}** of {len(winners)}",
        f"took {elapsed:.0f}s",
    ]
    if not on_production:
        parts.append("**not the production guild, no roles changed and nobody pinged**")
    await bot_log.post("\n".join(f"- {part}" for part in parts), tag="P0P1",
                       fingerprint=f"p0p1-ceremony-{contest.code}-{elapsed:.3f}")


def _set_channel(guild: discord.Guild, set_code: str) -> discord.TextChannel | None:
    for seed in ALL_SETS:
        if seed.code == set_code.upper():
            return channel_for_set(guild.text_channels, seed, category=None)
    return None


async def _already_announced(channel: discord.TextChannel, contest: p0p1_contest.Contest) -> bool:
    """Whether this contest's reveal already sits in the channel, matched on the header and the contest name
    so a prior contest's reveal does not suppress this one."""
    since = contest.scoring_date - timedelta(hours=1)
    marker = "results are in"
    try:
        async for message in channel.history(after=since, limit=200):
            if _bot is not None and _bot.user is not None and message.author.id != _bot.user.id:
                continue
            body = message_text(message)
            if marker in body and contest.name in body:
                return True
    except discord.HTTPException:
        log.warning(f"p0p1-ceremony: could not read #{channel.name} history, skipping to avoid a repeat",
                    exc_info=True)
        return True
    return False


async def _ensure_member_cache(guild: discord.Guild) -> None:
    if guild.chunked:
        return
    try:
        await guild.chunk()
    except (discord.ClientException, asyncio.TimeoutError):
        log.warning(f"p0p1-ceremony: could not chunk {guild.name}, winners may read as absent", exc_info=True)
