"""`!championship` and `!p0p1` — moderator-only event posts for the invoking channel, or the DM they were
typed in. The `!message` is deleted, every run posts fresh so a daily call bumps the channel, and nothing
is pinged: role mentions render as pills but notify nobody.
"""
from __future__ import annotations

import asyncio
import contextlib
import logging
from datetime import datetime, timezone

import discord
from discord.ext import commands

from bot import audit
from bot.commands.authorization import moderator_authorized
from bot.config import settings
from bot.services import championship, p0p1_contest, p0p1_copy, pod_launch
from bot.services import championship_copy as cc
from bot.services.containers import as_view
from bot.services.ping_roles import (
    SET_CHAMPION_ROLE_NAME,
    TOP_P0P1_CHALLENGER_ROLE_NAME,
    champion_role_mention,
)
from bot.services.pod_roles import find_role
from bot.services.pod_schedule import SCHEDULE_TZ
from bot.sets import active_set_code

log = logging.getLogger(__name__)

MSG_NO_CONTEST = "⚠️ No P0P1 contest to advertise. Add one to `p0p1_contests.json` first."
MSG_UNKNOWN_CONTEST = "⚠️ No P0P1 contest registered for `{code}`."

REJECTION_LIFETIME_S = 15


async def setup(bot: commands.Bot) -> None:
    @bot.command(name="championship", aliases=["champs"])
    @commands.check(moderator_authorized)
    async def championship_cmd(ctx: commands.Context) -> None:
        """Explain what the Set Championship is, dated and linked when an edition is upcoming."""
        await _delete_invocation(ctx)
        now = datetime.now(SCHEDULE_TZ)
        set_code, event_at, signup_at, event = await _upcoming_championship(now)
        guild = _guild(bot, ctx)
        container = cc.explainer(
            set_code=set_code, event_at=event_at, signup_at=signup_at,
            champion_mention=champion_role_mention(find_role(guild, SET_CHAMPION_ROLE_NAME)),
            card_url=await _signup_card_url(event, guild),
            coordination_channel=f"<#{settings.pod_draft_channel_id}>",
        )
        await ctx.send(view=as_view(container), allowed_mentions=discord.AllowedMentions.none())
        audit.event("championship_ad", user_id=str(ctx.author.id), set_code=set_code,
                    channel_id=str(ctx.channel.id))

    @bot.command(name="p0p1", aliases=["pack0", "challenge"])
    @commands.check(moderator_authorized)
    async def p0p1_cmd(ctx: commands.Context, set_code: str | None = None) -> None:
        """Advertise the contest closing soonest, or the one a set code names."""
        await _delete_invocation(ctx)
        now = datetime.now(timezone.utc)
        if set_code is None:
            contest = p0p1_contest.contest_to_advertise(now)
        else:
            contest = p0p1_contest.contest_for(set_code)
        if contest is None:
            await _reject(ctx, MSG_NO_CONTEST if set_code is None else MSG_UNKNOWN_CONTEST.format(code=set_code))
            return
        featured = p0p1_contest.featured_contest(now)
        container = p0p1_copy.advertisement(
            contest, now, featured_code=featured.code if featured is not None else None,
            challenger_mention=p0p1_copy.challenger_mention(
                find_role(_guild(bot, ctx), TOP_P0P1_CHALLENGER_ROLE_NAME)),
        )
        await ctx.send(view=as_view(container), allowed_mentions=discord.AllowedMentions.none())
        audit.event("p0p1_ad", user_id=str(ctx.author.id), contest=contest.code,
                    phase=contest.phase(now), channel_id=str(ctx.channel.id))

    championship_cmd.error(ignore_unauthorized)
    p0p1_cmd.error(ignore_unauthorized)


async def ignore_unauthorized(ctx: commands.Context, error: commands.CommandError) -> None:
    """`!p0p1` is a guessable word, so a player trying it has their message deleted with no reply."""
    if isinstance(error, commands.CheckFailure):
        await _delete_invocation(ctx)
        return
    raise error


async def _upcoming_championship(
    now: datetime,
) -> tuple[str, datetime | None, datetime | None, tuple[str, datetime] | None]:
    """(set code for the standings link, start time, when signup is posted, the event row) with every
    field but the code dropped once the edition has been played."""
    plan = championship.plan_for(now)
    if plan is None:
        return active_set_code(now), None, None, None
    event = await asyncio.to_thread(championship.event_for_set_sync, plan.set_code)
    event_at = event[1] if event is not None else plan.event_at
    if event_at < now:
        return plan.set_code, None, None, None
    return plan.set_code, event_at, championship.signup_post_at(plan), event


def _guild(bot: commands.Bot, ctx: commands.Context) -> discord.Guild | None:
    """The invoking guild, or the configured one when the post is being previewed in a DM."""
    if ctx.guild is not None:
        return ctx.guild
    return bot.get_guild(settings.discord_guild_id) if settings.discord_guild_id else None


async def _signup_card_url(
    event: tuple[str, datetime] | None, guild: discord.Guild | None,
) -> str | None:
    """The signup card's jump link, None while the championship is unposted."""
    if event is None or guild is None:
        return None
    card = await asyncio.to_thread(pod_launch.scheduled_card_ref_sync, event[0])
    if card is None:
        return None
    _, channel_id, message_id, _ = card
    return f"https://discord.com/channels/{guild.id}/{channel_id}/{message_id}"


async def _delete_invocation(ctx: commands.Context) -> None:
    if ctx.guild is None:
        return
    with contextlib.suppress(discord.HTTPException):
        await ctx.message.delete()


async def _reject(ctx: commands.Context, message: str) -> None:
    if ctx.guild is None:
        await ctx.send(message)
        return
    await ctx.send(message, delete_after=REJECTION_LIFETIME_S)
