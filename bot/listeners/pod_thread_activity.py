"""Counts what gets said in pod threads, so the roster card knows whether chat has buried it.

Nothing here reads Discord. The count is kept as messages arrive and reset whenever the card is posted,
which is what lets `!confirm` decide between editing the card where it is and moving it to the bottom
without a history lookup on every call.
"""
from __future__ import annotations

import discord
from discord.ext import commands

from bot.tasks.pod_draft_reminder import note_thread_message


class PodThreadActivityListener(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if isinstance(message.channel, discord.Thread):
            note_thread_message(message.channel.id)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(PodThreadActivityListener(bot))
