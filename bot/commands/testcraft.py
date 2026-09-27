from __future__ import annotations

from discord.ext import commands

from bot.commands.craft import craft_message, craft_set_code
from bot.commands.test_group import test_group


async def setup(bot: commands.Bot) -> None:
    @test_group.command(name="craft")
    @commands.is_owner()
    async def test_craft(ctx: commands.Context, set_code: str = "") -> None:
        await ctx.send(craft_message((set_code or craft_set_code()).upper()))
