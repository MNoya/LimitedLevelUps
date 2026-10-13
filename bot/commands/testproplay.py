from __future__ import annotations

import random
from datetime import datetime

import discord
from discord.ext import commands
from discord.utils import format_dt

from bot.commands.test_group import HALL_OF_FAME, test_group
from bot.config import OWNER_DISCORD_ID
from bot.services import bot_log
from bot.services.fantasy_event import event_for
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
from bot.services.ping_roles import FANTASY_CHAMPION_ROLE_NAME
from bot.services.pod_roles import role_label
from bot.services.watch_party import PREMIER_SCHEDULES

PREVIEW_EVENT = "WC32"
PREVIEW_CREST = (
    "https://images.ctfassets.net/ryplwhabvmmk/1CcEwjasOi5N6xxlAVYkkR/4db466968ff258f6d5f338912c48d65c/"
    "Magic-World-Championship-32-Logo-1000x700.png"
)


async def setup(bot: commands.Bot) -> None:
    @test_group.command(name="proplay")
    @commands.is_owner()
    async def test_pro_play(ctx: commands.Context) -> None:
        event = event_for(PREVIEW_EVENT)
        schedule = PREMIER_SCHEDULES[event.schedule_name]
        day_one_starts = datetime.combine(schedule.days[0].day, schedule.days[0].start, schedule.tz)
        winners = podium_sync(PREVIEW_EVENT) or sample_winners()
        champion_role = role_label(ctx.guild, FANTASY_CHAMPION_ROLE_NAME)
        posts = [
            ("1. Seven days before Round 1, with the upcoming watch party post", picks_open_embed(event)),
            ("2. 24 hours and 1 hour before picks close", close_reminder_embed(event)),
            (f"3. When coverage starts each day, {format_dt(day_one_starts, 'f')}", day_live_embed(event, "Day 1")),
            (f"4. When Round {event.cut_round} is revealed", day_one_complete_embed(event)),
            (f"5. When Round {event.swiss_rounds} is revealed", bracket_open_embed(event)),
            ("7. When the Final is revealed", ceremony_embed(event, winners, champion_role)),
        ]
        for caption, embed in posts:
            embed.set_thumbnail(url=PREVIEW_CREST)
            await ctx.send(f"__**{caption}**__", embed=embed, allowed_mentions=discord.AllowedMentions.none())
        await ctx.send("__**6. When Melee completes Round 1, Round 8 or a Top 8 stage: posts in #bot-spam**__")
        round_done = round_complete_embed(event, "Round 1", "1")
        round_done.set_thumbnail(url=PREVIEW_CREST)
        await bot_log.get(ctx.bot).post_plain(
            f"<@{OWNER_DISCORD_ID}>",
            embed=round_done,
            allowed_mentions=discord.AllowedMentions(users=True),
        )


def sample_winners() -> list[FantasyWinner]:
    names = random.sample(HALL_OF_FAME, 3)
    return [
        FantasyWinner(rank=rank, name=name, discord_id=None, points=points, bracket_points=0)
        for rank, (name, points) in enumerate(zip(names, (177, 171, 159)), start=1)
    ]
