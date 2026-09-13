"""Owner-only `!p0p1poll` — poll every past P0P1 voter to settle the 12th contest category.

Grants the transient P0P1 role to all-time voters for the send and strips it after, the same swap the vote
reminder uses. Posts a 24-hour native Discord poll into site-feedback and reports the reach back to the
channel it was invoked from.
"""
from __future__ import annotations

import asyncio
import time
from datetime import datetime, timedelta, timezone

import discord
from discord.ext import commands
from discord.utils import format_dt, utcnow

from bot import audit, emojis
from bot.config import PRODUCTION_GUILD_ID, settings
from bot.services import p0p1_reminder

POLL_DURATION = timedelta(hours=24)
CONTEST_SET_CODE = "FRA"
CONTEST_OPENS = datetime(2026, 9, 18, 16, 0, tzinfo=timezone.utc)
CONTEST_CLOSES = datetime(2026, 9, 23, 16, 0, tzinfo=timezone.utc)

MSG_NO_GUILD = "No guild to post into"
MSG_NO_ROLE = "Could not resolve the P0P1 role"

POLL_MESSAGE = (
    "{role} hey we are increasing the categories from 8 to 12, also adding hybrids under each: "
    "5 common, 5 uncommon and 1 multicolor signpost are locked in.\n\n"
    "Please vote to help define the 12th option!\n\n"
    "{fra}The next challenge will start {contest_opens} and end with Early Access {contest_closes}\n"
    "-# This poll closes in {closes}"
)
POLL_QUESTION = "Last voting category?"
POLL_ANSWERS = (
    "Best Card (rares + mythics)",
    "Best Rare (exclude mythics)",
    "Best Colorless (lands and artifacts, below rare)",
)


async def setup(bot: commands.Bot) -> None:
    @bot.command(name="p0p1poll")
    @commands.is_owner()
    async def p0p1_poll(ctx: commands.Context) -> None:
        """Owner-only. Grant the P0P1 role to every past voter and post the 24h challenger poll to site-feedback."""
        guild = ctx.guild or (bot.get_guild(settings.discord_guild_id) if settings.discord_guild_id else None)
        if guild is None:
            await ctx.send(MSG_NO_GUILD)
            return
        channel = guild.get_channel(settings.feedback_channel_id) or ctx.channel
        role = await p0p1_reminder.poll_role(guild)
        if role is None:
            await ctx.send(MSG_NO_ROLE)
            return

        voters = await asyncio.to_thread(p0p1_reminder.all_voter_discord_ids_sync)
        restrict_to = None if guild.id == PRODUCTION_GUILD_ID else ctx.author
        discord_ids = p0p1_reminder.audience(guild, voters.discord_ids, restrict_to)

        async def send(role_mention: str) -> None:
            poll = discord.Poll(question=POLL_QUESTION, duration=POLL_DURATION)
            for answer in POLL_ANSWERS:
                poll.add_answer(text=answer)
            symbol = emojis.set_symbol(CONTEST_SET_CODE)
            content = POLL_MESSAGE.format(
                role=role_mention,
                fra=f"{symbol} " if symbol is not None else "",
                contest_opens=format_dt(CONTEST_OPENS, style="D"),
                contest_closes=f"{format_dt(CONTEST_CLOSES, style="F")}",
                closes=format_dt(utcnow() + POLL_DURATION, style="R"),
            )
            await channel.send(content, poll=poll, allowed_mentions=discord.AllowedMentions(roles=[role]))

        started = time.monotonic()
        pinged, members = await p0p1_reminder.ping_audience(guild, role, discord_ids, send)
        elapsed = time.monotonic() - started
        audit.event("p0p1_poll", user_id=str(ctx.author.id), channel_id=str(channel.id),
                    targeted=len(discord_ids), pinged=pinged, source=voters.source)
        await ctx.send(
            f"P0P1 poll posted in {channel.mention}, pinged **{pinged}** of {len(discord_ids)} past voters, "
            f"{len(discord_ids) - len(members)} not in the server, audience from `{voters.source}`, "
            f"took {elapsed:.0f}s"
        )
