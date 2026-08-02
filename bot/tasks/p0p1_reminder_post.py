"""Fires the P0P1 vote reminder into the contest set's own channel one day before voting closes.

Hourly rather than pinned to the exact instant, so a deploy across the fire time still lands the ping.
Channel history keeps it to one post: a reminder is recognised by its own role mention.
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
from bot.config import settings
from bot.discord_helpers import message_text
from bot.services import p0p1_contest, p0p1_copy, p0p1_reminder
from bot.services.format_schedule import channel_for_set
from bot.sets import ALL_SETS

log = logging.getLogger(__name__)

REMINDER_LEAD = timedelta(days=1)

_bot: commands.Bot | None = None


def init_p0p1_reminder(bot: commands.Bot) -> None:
    global _bot
    _bot = bot
    bot.pod_scheduler.add_job(
        fire_reminder, "cron", minute=0, timezone=timezone.utc,
        id="p0p1-vote-reminder", replace_existing=True,
    )
    log.info(f"p0p1-reminder: hourly tick armed, {REMINDER_LEAD.days}d before each voting deadline")


async def fire_reminder() -> None:
    if _bot is None:
        return
    now = datetime.now(timezone.utc)
    contest = contest_due(now)
    if contest is None:
        return
    guild = _bot.get_guild(settings.discord_guild_id) if settings.discord_guild_id else None
    if guild is None:
        log.warning("p0p1-reminder: no configured guild, skipping")
        return
    try:
        await post_reminder(guild, contest, now)
    except (SQLAlchemyError, discord.HTTPException):
        log.warning(f"p0p1-reminder: {contest.code} tick failed, retrying next hour", exc_info=True)


def contest_due(now: datetime) -> p0p1_contest.Contest | None:
    """The contest inside its final day of voting, or None. A contest whose window is shorter than the lead
    qualifies from the moment it opens, so a short contest still gets its nudge."""
    for contest in p0p1_contest.all_contests():
        if contest.previews_open <= now < contest.voting_deadline and now >= contest.voting_deadline - REMINDER_LEAD:
            return contest
    return None


async def post_reminder(
    guild: discord.Guild, contest: p0p1_contest.Contest, now: datetime, *, force: bool = False,
    restrict_to: discord.Member | None = None,
) -> p0p1_reminder.ReminderOutcome | None:
    """``force`` skips the already-posted check, for a hand-fired run. ``restrict_to`` is the caller, the
    only person a run outside the production guild pings."""
    channel = _set_channel(guild, contest.code)
    if channel is None:
        log.warning(f"p0p1-reminder: no channel found for {contest.code}, skipping")
        return None
    role = await p0p1_reminder.reminder_role(guild)
    if role is None:
        return None
    if not force and await _already_reminded(channel, role, contest, now):
        return None

    featured = p0p1_contest.featured_contest(now)
    voter_count = await asyncio.to_thread(p0p1_reminder.voter_count_sync, contest.code)

    async def send(role_mention: str) -> None:
        view = p0p1_copy.reminder_view(
            contest, featured_code=featured.code if featured is not None else None,
            role_mention=role_mention, voter_count=voter_count,
        )
        await channel.send(view=view, allowed_mentions=discord.AllowedMentions(roles=[role]))

    started = time.monotonic()
    outcome = await p0p1_reminder.ping_non_voters(guild, role, contest.code, send, restrict_to=restrict_to)
    audit.event("p0p1_reminder", contest=contest.code, channel_id=str(channel.id),
                targeted=outcome.targeted, pinged=outcome.pinged, absent=outcome.absent)
    await _post_debug(contest, channel, outcome, time.monotonic() - started)
    return outcome


async def _post_debug(
    contest: p0p1_contest.Contest, channel: discord.TextChannel,
    outcome: p0p1_reminder.ReminderOutcome, elapsed: float,
) -> None:
    """The ping is unattended and leaves no trace once the role is emptied, so this is its only record. The
    fingerprint carries the run duration to defeat the bot-log cooldown, which would read as a missed run."""
    bot_log = getattr(_bot, "bot_log", None)
    if bot_log is None:
        return
    parts = [
        f"P0P1 `{contest.code}` reminder posted in {channel.mention}",
        f"pinged **{outcome.pinged}** of {outcome.targeted}",
        f"{outcome.absent} not in the server",
        f"audience from `{outcome.source}`",
        f"took {elapsed:.0f}s",
    ]
    if outcome.restricted:
        parts.append("**held to the caller, not the production guild**")
    if outcome.source == p0p1_reminder.SOURCE_PLAYERS:
        parts.append("**no `auth` schema, audience is not the real non-voter list**")
    await bot_log.post("\n".join(f"- {part}" for part in parts), tag="P0P1",
                       fingerprint=f"p0p1-reminder-{contest.code}-{elapsed:.3f}")


def _set_channel(guild: discord.Guild, set_code: str) -> discord.TextChannel | None:
    """The set's discussion channel, matched anywhere in the server: a contest runs during preview season,
    when the incoming set's channel may not have been filed under the live-set category yet."""
    for seed in ALL_SETS:
        if seed.code == set_code.upper():
            return channel_for_set(guild.text_channels, seed, category=None)
    return None


async def _already_reminded(
    channel: discord.TextChannel, role: discord.Role, contest: p0p1_contest.Contest, now: datetime,
) -> bool:
    """Whether this contest's reminder is already in the channel. Matched on the role mention, which no
    other post carries, plus the contest name so a prior contest's reminder does not suppress this one."""
    since = contest.voting_deadline - REMINDER_LEAD - timedelta(hours=1)
    try:
        async for message in channel.history(after=since, limit=200):
            if _bot is not None and _bot.user is not None and message.author.id != _bot.user.id:
                continue
            body = message_text(message)
            if role.mention in body and contest.name in body:
                return True
    except discord.HTTPException:
        log.warning(f"p0p1-reminder: could not read #{channel.name} history, skipping to avoid a repeat",
                    exc_info=True)
        return True
    return False
