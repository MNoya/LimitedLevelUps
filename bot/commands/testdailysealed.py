"""Owner-only `!test dailysealed`: the morning Daily Sealed post, render-only"""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

import discord
from discord.ext import commands

from bot.commands.test_group import test_group
from bot.database import SessionLocal
from bot.services.daily_sealed import serving_day
from bot.services.daily_sealed_post import (
    DAILY_SEALED_ROLE_NAME,
    PoolSummary,
    pool_summary,
)
from bot.services.pod_roles import role_mention
from bot.sets import active_set_code
from bot.tasks.daily_sealed_post import daily_sealed_view


async def setup(bot: commands.Bot) -> None:
    @test_group.command(name="dailysealed")
    @commands.is_owner()
    async def test_dailysealed(ctx: commands.Context) -> None:
        """Owner-only. Post today's Daily Sealed card from stored pools, or from sample pools when none exist"""
        today = serving_day(datetime.now(timezone.utc))
        stored_today, stored_yesterday = await asyncio.to_thread(_load_summaries, today)
        sample_today, sample_yesterday = _sample_summaries(today)
        mention = role_mention(ctx.guild, DAILY_SEALED_ROLE_NAME)
        for current, previous in ((stored_today or sample_today, stored_yesterday or sample_yesterday),
                                  (sample_today, _empty(sample_yesterday))):
            view = daily_sealed_view(current, previous, mention)
            await ctx.send(view=view, allowed_mentions=discord.AllowedMentions.none())


def _load_summaries(today) -> tuple[PoolSummary | None, PoolSummary | None]:
    with SessionLocal() as session:
        return pool_summary(session, today), pool_summary(session, today - timedelta(days=1))


def _sample_summaries(today) -> tuple[PoolSummary, PoolSummary]:
    set_code = active_set_code()
    yesterday = PoolSummary(
        day=today - timedelta(days=1), set_code=set_code, number=23, build_count=14,
        pair_counts=[("UB", 5), ("WU", 3), ("BR", 2)], colors="UBr", event_format="ArenaDirect_Sealed",
        wins=5, losses=3,
    )
    current = PoolSummary(
        day=today, set_code=set_code, number=24, build_count=0, pair_counts=[], colors="WG", event_format="Sealed",
        wins=2, losses=3,
    )
    return current, yesterday


def _empty(summary: PoolSummary) -> PoolSummary:
    return PoolSummary(
        day=summary.day, set_code=summary.set_code, number=summary.number, build_count=0, pair_counts=[],
        colors=summary.colors, event_format=summary.event_format, wins=summary.wins, losses=summary.losses,
    )
