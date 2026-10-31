from __future__ import annotations

import contextlib

import discord
from discord.ext import commands

from bot import audit
from bot.commands.authorization import moderator_authorized
from bot.sets import newest_playable_set_code
from bot.tasks.prerelease_trophy_post import send_trophy_card


async def setup(bot: commands.Bot) -> None:
    @bot.command(name="trophy")
    @commands.check(moderator_authorized)
    async def trophy_card_cmd(ctx: commands.Context, *, label: str = "Trophy") -> None:
        shown_label = " ".join(word[:1].upper() + word[1:] for word in label.split())
        set_code = newest_playable_set_code()
        await send_trophy_card(ctx.channel, set_code, ctx.bot.user, shown_label)
        audit.event("trophy_card_post", label=shown_label, set=set_code, channel_id=str(ctx.channel.id),
                    user_id=str(ctx.author.id))
        with contextlib.suppress(discord.HTTPException):
            await ctx.message.delete()
