"""Short prefix commands that post a link or a canned explainer to the current channel."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import discord
from discord.ext import commands

from bot.services.championship_dates import ChampionshipPlan, plan_for, season_start, vote_opens_at, voting_open
from bot.services.pod_format_allocator import VOTE_FLOOR
from bot.services.pod_format_interest import FLASHBACK_ROLE_NAME, flashback_emoji
from bot.services.pod_format_vote import VoteFormatsButton
from bot.services.pod_roles import role_label
from bot.services.pod_schedule import ORGANIZER_ROLE_NAME, SCHEDULE_TZ
from bot.services.pod_schedule_controls import ViewScheduleButton
from bot.services.pod_signals import SLOT_EARLY, bucket_for_slot

SITE_URL = "https://limitedlevelups.com"
LEADERBOARD_URL = "https://limitedlevelups.com/leaderboard"
TIER_LIST_URL = "https://limitedlevelups.com/tier-list"
PODS_URL = "https://limitedlevelups.com/pods"
EVERGREEN_URL = "https://limitedlevelups.com/episodes/evergreen"
POD_ETIQUETTE_URL = "https://limitedlevelups.com/pods/guide#etiquette"

TEAM_DRAFT_TITLE = "Team Draft"
POD_ETIQUETTE_TITLE = "Pod Draft Etiquette"


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


def pod_etiquette_body(organizer: str) -> str:
    return (
        "▫️ Join the Draftmancer table when notified\n"
        "▫️ Play all 3 rounds, win or lose\n"
        f"▫️ Having a problem? Ask an {organizer}\n"
        "▫️ Report your result as soon as your match ends"
    )


def flashback_season_body(guild: discord.Guild | None, now: datetime) -> str:
    plan = plan_for(now)
    first_pod = _first_flashback_pod(plan)
    flashback = role_label(guild, FLASHBACK_ROLE_NAME)
    return (
        f"{_flashback_season_heading(plan, first_pod, now)}\n"
        f"{_flashback_season_dates(plan, first_pod, flashback, now)}"
        f"▫️ Sets with **{VOTE_FLOOR}+ votes** get days by vote share"
    )


def flashback_season_view(now: datetime) -> discord.ui.View:
    view = discord.ui.View(timeout=None)
    if voting_open(now):
        view.add_item(VoteFormatsButton())
    view.add_item(ViewScheduleButton())
    return view


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

    @commands.command(name="etiquette")
    async def etiquette(self, ctx: commands.Context) -> None:
        body = pod_etiquette_body(role_label(ctx.guild, ORGANIZER_ROLE_NAME))
        embed = discord.Embed(
            title=POD_ETIQUETTE_TITLE, url=POD_ETIQUETTE_URL, description=body, color=discord.Color.green()
        )
        await ctx.channel.send(embed=embed)

    @commands.command(name="flashback")
    async def flashback(self, ctx: commands.Context) -> None:
        now = datetime.now(timezone.utc)
        embed = discord.Embed(description=flashback_season_body(ctx.guild, now), color=discord.Color.green())
        await ctx.channel.send(embed=embed, view=flashback_season_view(now))


def _first_flashback_pod(plan: ChampionshipPlan | None) -> datetime | None:
    start = season_start(plan.set_code) if plan is not None else None
    early_pod = bucket_for_slot(start, SLOT_EARLY) if start is not None else None
    if early_pod is None:
        return None
    return datetime.combine(start, early_pod.start, tzinfo=SCHEDULE_TZ)


def _flashback_season_heading(plan: ChampionshipPlan | None, first_pod: datetime | None, now: datetime) -> str:
    opens_at = vote_opens_at(plan) if plan is not None else None
    emoji = flashback_emoji()
    if opens_at is None:
        return f"### {emoji} Flashback Season vote starts soon"
    if now < opens_at:
        return f"### {emoji} Flashback Season vote starts <t:{int(opens_at.timestamp())}:R>"
    if first_pod is not None and now < first_pod:
        return f"### {emoji} Flashback Season vote is on!"
    return f"### {emoji} Flashback Season is on!"


def _flashback_season_dates(
    plan: ChampionshipPlan | None, first_pod: datetime | None, flashback: str, now: datetime,
) -> str:
    if first_pod is None:
        return ""
    if now < first_pod:
        return f"▫️ {flashback} Pods start <t:{int(first_pod.timestamp())}:f>\n"
    last_day = plan.next_release_at - timedelta(days=1)
    return f"▫️ {flashback} Pods run until <t:{int(last_day.timestamp())}:D>\n"


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(QuickLinksListener(bot))
