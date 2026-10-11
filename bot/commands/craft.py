from __future__ import annotations

import logging
from datetime import datetime, timezone

import discord
from discord.ext import commands

from bot import audit, emojis
from bot.config import settings
from bot.discord_helpers import pin_quietly
from bot.services.format_schedule import active_set_seed, channel_for_set
from bot.services.p0p1_contest import all_contests
from bot.sets import release_instant, set_name_for

logger = logging.getLogger(__name__)

MSG_CRAFT_LINK = "{symbol}{url}"
MSG_CRAFT_RELEASE = "## {symbol}{name} is live!\n\n➡️ {url}"


async def setup(bot: commands.Bot) -> None:
    bot.add_command(craft)


@commands.command(name="craft")
async def craft(ctx: commands.Context) -> None:
    code = craft_set_code()
    audit.event("craft_invoked", user_id=str(ctx.author.id), set_code=code)
    await ctx.send(craft_message(code))


def craft_set_code(when: datetime | None = None) -> str:
    now = when or datetime.now(timezone.utc)
    active = active_set_seed(now)
    active_release = release_instant(active.start_date)
    for contest in all_contests():
        if contest.previews_open <= now and contest.release > active_release:
            return contest.code
    return active.code


def craft_message(set_code: str) -> str:
    return MSG_CRAFT_LINK.format(symbol=symbol_prefix(set_code), url=craft_url(set_code))


def craft_release_message(set_code: str) -> str:
    name = set_name_for(set_code)
    return MSG_CRAFT_RELEASE.format(symbol=symbol_prefix(set_code), name=name, url=craft_url(set_code))


def symbol_prefix(set_code: str) -> str:
    symbol = emojis.set_symbol(set_code)
    return f"{symbol} " if symbol is not None else ""


def craft_url(set_code: str) -> str:
    return f"{settings.public_site_url}/tools/craft/{set_code}"


async def pin_craft_link(guild: discord.Guild) -> None:
    seed = active_set_seed()
    channel = channel_for_set(guild.text_channels, seed)
    if channel is None:
        return
    try:
        message = await channel.send(craft_release_message(seed.code))
        await pin_quietly(message, reason=f"{seed.code} bulk craft lists")
    except discord.HTTPException:
        logger.warning(f"craft: could not pin the {seed.code} craft link in #{channel.name}", exc_info=True)
