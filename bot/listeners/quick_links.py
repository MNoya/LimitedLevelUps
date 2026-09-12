"""Short prefix commands that post a link or a canned explainer to the current channel."""
from __future__ import annotations

import discord
from discord.ext import commands

SITE_URL = "https://limitedlevelups.com"
LEADERBOARD_URL = "https://limitedlevelups.com/leaderboard"
TIER_LIST_URL = "https://limitedlevelups.com/tier-list"
PODS_URL = "https://limitedlevelups.com/pods"
EVERGREEN_URL = "https://limitedlevelups.com/episodes/evergreen"

TEAM_DRAFT_TITLE = "Team Draft"


def team_draft_body(bot_mention: str) -> str:
    return (
        "Players are grouped into two teams and the winner is the team with the "
        "most match wins.\n\n"
        "**Setup**\n"
        f"{bot_mention} assigns the teams in alternating seats.\n\n"
        "**Matches**\n"
        "After the draft each player plays each opponent on the opposing team.\n\n"
        "**Communication**\n"
        "During the draft, teammates aren't allowed to discuss picks or strategies.\n"
        "Later, each team gets its own private thread and voice room to discuss strategy."
    )


class QuickLinksListener(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @commands.command(name="llu", aliases=["website"])
    async def llu(self, ctx: commands.Context) -> None:
        await ctx.channel.send(SITE_URL)

    @commands.command(name="leaderboard")
    async def leaderboard(self, ctx: commands.Context) -> None:
        await ctx.channel.send(LEADERBOARD_URL)

    @commands.command(name="tier-list", aliases=["tierlist"])
    async def tier_list(self, ctx: commands.Context) -> None:
        await ctx.channel.send(TIER_LIST_URL)

    @commands.command(name="pods")
    async def pods(self, ctx: commands.Context) -> None:
        await ctx.channel.send(PODS_URL)

    @commands.command(name="evergreen")
    async def evergreen(self, ctx: commands.Context) -> None:
        await ctx.channel.send(EVERGREEN_URL)

    @commands.command(name="teams", aliases=["teamdraft"])
    async def teams(self, ctx: commands.Context) -> None:
        body = team_draft_body(self.bot.user.mention)
        embed = discord.Embed(title=TEAM_DRAFT_TITLE, description=body, color=discord.Color.green())
        await ctx.channel.send(embed=embed)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(QuickLinksListener(bot))
