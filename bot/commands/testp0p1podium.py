"""Owner-only `!test p0p1podium` — render the P0P1 podium reveal through the real builder.

Render only, no role swap and no real ping: the true podium reads from the ``auth`` schema, which no
developer database has, so this shows the copy with fictional winners. The caller stands in for a member
who gets a mention pill; the rest render as bold names, the way someone who left the server does.
"""
from __future__ import annotations

from datetime import datetime, timezone

import discord
from discord.ext import commands

from bot.commands.test_group import HALL_OF_FAME, test_group
from bot.services import p0p1_contest, p0p1_copy
from bot.services.pod_roles import find_role
from bot.services.ping_roles import TOP_P0P1_CHALLENGER_ROLE_NAME

MSG_NO_CONTEST = "No P0P1 contest in `p0p1_contests.json`"


async def setup(bot: commands.Bot) -> None:
    @test_group.command(name="p0p1podium")
    @commands.is_owner()
    async def test_p0p1_podium(ctx: commands.Context) -> None:
        """Owner-only. Render the podium reveal with fictional winners, no roles changed."""
        now = datetime.now(timezone.utc)
        contest = p0p1_contest.contest_to_advertise(now)
        if contest is None:
            await ctx.send(MSG_NO_CONTEST)
            return
        featured = p0p1_contest.featured_contest(now)
        podium = [ctx.author.mention, f"**{HALL_OF_FAME[0]}**", f"**{HALL_OF_FAME[1]}**"]
        view = p0p1_copy.ceremony_view(
            contest, featured_code=featured.code if featured is not None else None,
            podium=podium, challenger_mention=p0p1_copy.challenger_mention(
                find_role(ctx.guild, TOP_P0P1_CHALLENGER_ROLE_NAME)),
        )
        await ctx.send(view=view, allowed_mentions=discord.AllowedMentions.none())
