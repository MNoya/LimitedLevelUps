from __future__ import annotations

from datetime import date, datetime, timezone

import discord
from discord.ext import commands
from discord.utils import format_dt

from bot.commands.test_group import test_group
from bot.services import mtgscribe
from bot.services.watch_party import CHANNEL_TZ, channel_name, upcoming_windows
from bot.tasks.watch_party_post import (
    UPCOMING_LEAD,
    announcement_candidates,
    build_announcement,
    build_window_embed,
    channel_topic,
    scheduled_event_candidates,
)


async def setup(bot: commands.Bot) -> None:
    @test_group.command(name="watchparty")
    @commands.is_owner()
    async def test_watch_party(ctx: commands.Context, on_day: str = "") -> None:
        today = date.fromisoformat(on_day) if on_day else datetime.now(timezone.utc).astimezone(CHANNEL_TZ).date()
        windows = upcoming_windows(mtgscribe.load_events(arena_only=False), today)
        current = windows[0] if windows else None
        await ctx.send(f"__**Watch party on {today:%b %-d %Y}**__\n`#{channel_name(current)}`\n"
                       f"```\n{channel_topic(windows, today)}\n```")
        if current is None:
            return
        emojis = {emoji.name: emoji for emoji in await ctx.bot.fetch_application_emojis()}
        await ctx.send(f"__**Posts {UPCOMING_LEAD.days} days before it starts or when the previous event ends**__",
                       embed=build_window_embed(current, emojis, live=False))
        await ctx.send(f"__**Posts at {format_dt(current.headliner.starts_at(), 'f')}**__",
                       embed=build_window_embed(current, emojis, live=True))
        for covered in scheduled_event_candidates(current):
            await ctx.send(f"__**Scheduled Event**__ **{covered.name}**\n{covered.details}\n"
                           f"{format_dt(covered.starts_at(), 'f')} to {format_dt(covered.ends_at(), 'f')}")
        for covered in announcement_candidates(current):
            await ctx.send(f"__**Posts at {format_dt(covered.starts_at(), 'f')}**__")
            await ctx.send(build_announcement(covered), allowed_mentions=discord.AllowedMentions.none())
