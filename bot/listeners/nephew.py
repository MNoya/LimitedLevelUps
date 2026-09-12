"""Forward a community meme to the current channel on `!nephew`.

A forward carries only ids, so the source message is never read.
"""
from __future__ import annotations

import logging

import discord
from discord.ext import commands

log = logging.getLogger(__name__)

MEME_FORWARD = discord.MessageReference(
    guild_id=775371722065051658, channel_id=775801228898730034, message_id=1548332853681459290,
    type=discord.MessageReferenceType.forward,
)


class NephewListener(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @commands.command(name="nephew", aliases=["niece", "newphews"])
    async def nephew(self, ctx: commands.Context) -> None:
        try:
            await ctx.channel.send(reference=MEME_FORWARD)
        except discord.HTTPException as exc:
            log.warning(f"nephew meme unreachable: {exc}")


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(NephewListener(bot))
