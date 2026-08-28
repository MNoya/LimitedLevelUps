"""Public `!<cube>` commands that post a CubeCobra overview link plus named shortcuts, all masked links."""
from __future__ import annotations

from dataclasses import dataclass

import discord
from discord.ext import commands

from bot import emojis
from bot.discord_helpers import EM_SPACE, NBSP
from bot.services.pod_format import MEMA_CUBE_ID, PEASANT_CODE, cube_id_for

LEAD_EMOJI_NAME = "cube"
FALLBACK_LEAD_EMOJI = "🧊"


def bold_underline(text: str) -> str:
    return f"__**{text}**__"


@dataclass(frozen=True)
class Shortcut:
    label: str
    url: str
    emoji_names: tuple[str, ...] = ()
    fallback_emoji: str = ""


@dataclass(frozen=True)
class CubeLink:
    cube_id: str
    owner_name: str | None = None
    aliases: tuple[str, ...] = ()
    lead_emoji_name: str = LEAD_EMOJI_NAME
    shortcuts: tuple[Shortcut, ...] | None = None
    overview_heading: bool = False
    indent_shortcuts: bool = False


def _default_shortcuts(cube_id: str) -> tuple[Shortcut, ...]:
    return (
        Shortcut("Tier List", f"https://cubecobra.com/cube/list/{cube_id}?view=mainboard&s1=Tags", fallback_emoji="📊"),
        Shortcut("Primer", f"https://cubecobra.com/cube/about/{cube_id}?view=primer", fallback_emoji="📖"),
        Shortcut("Changelog", f"https://cubecobra.com/cube/about/{cube_id}?view=blog", fallback_emoji="📝"),
    )


MEMA_LIST = "https://www.cubecobra.com/cube/list/MEMA?view=mainboard&f="
MEMA_SHORTCUTS = (
    Shortcut("HOB Cards", f"{MEMA_LIST}set%3Ahob", emoji_names=("hob",)),
    Shortcut("LTR Cards", f"{MEMA_LIST}set%3Altr", emoji_names=("ltr",)),
    Shortcut("Bonus Cards", f"{MEMA_LIST}(-set%3Ahob+-set%3Altr)+or+(n%3Agift)", emoji_names=("hoc", "ltc")),
)


CUBE_COMMANDS = {
    "peasant": CubeLink(cube_id_for(PEASANT_CODE), "daneelius", aliases=("daneelius", "peasantcube")),
    "sampcube": CubeLink("samp", "samp", aliases=("samp",)),
    "mema": CubeLink(
        MEMA_CUBE_ID, aliases=("ltr", "hob", "masters"), lead_emoji_name="mema",
        shortcuts=MEMA_SHORTCUTS, overview_heading=True, indent_shortcuts=True),
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


def _owner_mention(guild: discord.Guild | None, name: str | None) -> str | None:
    if name is None:
        return None
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


def _cube_message(link: CubeLink, owner_mention: str | None) -> str:
    cube_id = link.cube_id
    lead = emojis.get(link.lead_emoji_name) or FALLBACK_LEAD_EMOJI
    overview_url = f"https://cubecobra.com/cube/overview/{cube_id}"
    if link.overview_heading:
        overview_link = f"## {lead} {overview_url}"
    else:
        overview_link = f"{lead} [cubecobra.com/cube/overview/{cube_id}](<{overview_url}>)"
        if owner_mention is not None:
            overview_link = f"{overview_link} {owner_mention}"
    shortcuts = (EM_SPACE * 2).join(
        _shortcut_text(shortcut) for shortcut in (link.shortcuts or _default_shortcuts(cube_id))
    )
    if link.indent_shortcuts:
        shortcuts = f"{NBSP}{shortcuts}"
    return f"{overview_link}\n\n{shortcuts}"


def _shortcut_text(shortcut: Shortcut) -> str:
    icons = "".join(emojis.get(name) for name in shortcut.emoji_names) or shortcut.fallback_emoji
    return f"{icons}{NBSP}[{bold_underline(shortcut.label)}](<{shortcut.url}>)"
