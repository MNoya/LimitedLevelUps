"""Public `!<cube>` commands that post a CubeCobra overview link plus named shortcuts, all masked links."""
from __future__ import annotations

from dataclasses import dataclass

import discord
from discord.ext import commands

from bot import emojis
from bot.discord_helpers import EM_SPACE, NBSP
from bot.services.pod_format import PEASANT_CODE, cube_id_for

LEAD_EMOJI_NAME = "cube"
FALLBACK_LEAD_EMOJI = "🧊"


def bold_underline(text: str) -> str:
    return f"__**{text}**__"


@dataclass(frozen=True)
class CubeLink:
    cube_id: str
    owner_name: str
    aliases: tuple[str, ...] = ()


CUBE_COMMANDS = {
    "peasant": CubeLink(cube_id_for(PEASANT_CODE), "daneelius", aliases=("daneelius", "peasantcube")),
    "sampcube": CubeLink("samp", "samp", aliases=("samp",)),
}


async def setup(bot: commands.Bot) -> None:
    for name, link in CUBE_COMMANDS.items():
        _register_cube_command(bot, name, link)


def _register_cube_command(bot: commands.Bot, name: str, link: CubeLink) -> None:
    @bot.command(name=name, aliases=list(link.aliases))
    async def cube(ctx: commands.Context) -> None:
        owner = _owner_mention(ctx.guild, link.owner_name)
        await ctx.send(
            _cube_message(link, owner),
            allowed_mentions=discord.AllowedMentions(users=True, roles=False, everyone=False),
        )


def _owner_mention(guild: discord.Guild | None, name: str) -> str:
    member = _find_member_by_name(guild, name)
    return member.mention if member else f"**@{name}**"


def _find_member_by_name(guild: discord.Guild | None, name: str) -> discord.Member | None:
    if guild is None:
        return None
    lowered = name.lower()
    for member in guild.members:
        handles = (member.name, member.display_name, member.global_name)
        if any(handle and handle.lower() == lowered for handle in handles):
            return member
    return None


def _cube_message(link: CubeLink, owner_mention: str) -> str:
    cube_id = link.cube_id
    lead = emojis.get(LEAD_EMOJI_NAME) or FALLBACK_LEAD_EMOJI
    overview_path = f"cubecobra.com/cube/overview/{cube_id}"
    overview_link = f"{lead} [{overview_path}](<https://{overview_path}>) {owner_mention}"
    shortcuts = (EM_SPACE * 2).join(
        (
            f"📊{NBSP}[{bold_underline('Tier List')}](<https://cubecobra.com/cube/list/{cube_id}?view=mainboard&s1=Tags>)",
            f"📖{NBSP}[{bold_underline('Primer')}](<https://cubecobra.com/cube/about/{cube_id}?view=primer>)",
            f"📝{NBSP}[{bold_underline('Changelog')}](<https://cubecobra.com/cube/about/{cube_id}?view=blog>)",
        )
    )
    return f"{overview_link}\n\n{shortcuts}"
