"""Owner-only `!test peasanttrophy`: the #peasant-cube champion post for a spread of trophy histories, render-only"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import discord
from discord.ext import commands

from bot.commands.test_group import HALL_OF_FAME, test_group
from bot.services.peasant_trophy_post import (
    PeasantChampion,
    PeasantFinish,
    build_peasant_trophy_text,
    trophy_stats,
)
from bot.services.pod_format import PEASANT_CODE
from bot.services.pod_slot import pod_display_name
from bot.sets import active_set_code, seed_for_code

_TROPHY = "3-0"
_MISS = "1-2"

_SCENARIOS = (
    (("UG", _TROPHY, True),),
    (("UG", _TROPHY, True), ("BR", _TROPHY, True)),
    (("WB", _TROPHY, False), ("UR", _TROPHY, False), ("URg", _TROPHY, True)),
    (("WB", _TROPHY, False), ("UG", _TROPHY, True), ("UG", _MISS, True), ("WB", _TROPHY, True)),
    (("UG", _TROPHY, False), ("UG", _TROPHY, True), ("UG", _TROPHY, True), ("UGb", _TROPHY, True)),
    (("WR", _TROPHY, False), ("WR", _TROPHY, False), ("BG", _MISS, True), ("WB", _TROPHY, True),
     ("UB", _TROPHY, True)),
)


async def setup(bot: commands.Bot) -> None:
    @test_group.command(name="peasanttrophy")
    @commands.is_owner()
    async def test_peasanttrophy(ctx: commands.Context) -> None:
        """Owner-only. Post the #peasant-cube champion post for six trophy histories, each linking this message"""
        season = seed_for_code(active_set_code())
        before_season = season.start_date - timedelta(days=30)
        in_season = season.start_date + timedelta(days=1)
        pod_name = pod_display_name(PEASANT_CODE, datetime.now(timezone.utc))
        for name, scenario in zip(HALL_OF_FAME, _SCENARIOS):
            finishes = [
                PeasantFinish(in_season if this_season else before_season, record, colors)
                for colors, record, this_season in scenario
            ]
            champion = PeasantChampion(name, finishes[-1].deck_colors, trophy_stats(finishes, season))
            text = build_peasant_trophy_text(champion, pod_name, ctx.message.jump_url)
            await ctx.send(text, allowed_mentions=discord.AllowedMentions.none())
