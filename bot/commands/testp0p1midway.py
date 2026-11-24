"""Owner-only `!test p0p1midway`: render the P0P1 midway post through the real builder, pinging nobody"""
from __future__ import annotations

from datetime import datetime, timezone

import discord
from discord.ext import commands

from bot.commands.test_group import test_group
from bot.services import p0p1_contest, p0p1_copy

MSG_NO_CONTEST = "No P0P1 contest in `p0p1_contests.json`"


async def setup(bot: commands.Bot) -> None:
    @test_group.command(name="p0p1midway")
    @commands.is_owner()
    async def test_p0p1_midway(ctx: commands.Context) -> None:
        """Owner-only. Render the midway post for the current contest in this channel."""
        now = datetime.now(timezone.utc)
        contest = p0p1_contest.contest_to_advertise(now)
        if contest is None:
            await ctx.send(MSG_NO_CONTEST)
            return
        featured = p0p1_contest.featured_contest(now)
        view = p0p1_copy.midway_view(contest, featured_code=featured.code if featured is not None else None)
        await ctx.send(view=view, allowed_mentions=discord.AllowedMentions.none())
