"""Owner-only `!test p0p1reminder` — fire the real T-1 vote reminder, pinging only the caller.

The full path, not a render, so the role swap is exercisable off production, which has no hand-invoked
equivalent: a role grant is one Discord call per member, making a real sweep about two minutes.

Success is reported to bot-spam by the run itself, so only a failure answers here.
"""
from __future__ import annotations

from datetime import datetime, timezone

from discord.ext import commands

from bot.commands.test_group import test_group
from bot.services import p0p1_contest
from bot.tasks.p0p1_reminder_post import contest_due, post_reminder

MSG_NO_CONTEST = "No P0P1 contest in `p0p1_contests.json`"
MSG_NO_CHANNEL = "No channel found for `{code}`. Create the set channel here first"


async def setup(bot: commands.Bot) -> None:
    @test_group.command(name="p0p1reminder")
    @commands.is_owner()
    async def test_p0p1_reminder(ctx: commands.Context) -> None:
        """Owner-only. Fire the reminder for real, pinging only the caller."""
        now = datetime.now(timezone.utc)
        contest = contest_due(now) or p0p1_contest.contest_to_advertise(now)
        if contest is None:
            await ctx.send(MSG_NO_CONTEST)
            return
        outcome = await post_reminder(ctx.guild, contest, now, force=True, restrict_to=ctx.author)
        if outcome is None:
            await ctx.send(MSG_NO_CHANNEL.format(code=contest.code))
