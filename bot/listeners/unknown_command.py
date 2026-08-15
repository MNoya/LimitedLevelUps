"""Answer someone who types `!command`, since every player-facing command is a slash command.

The library's fallback handler logs the failure and drops the context, which reaches the bot-spam channel
as a nameless error. Owning the event puts the reply where the person who typed it can read it, and keeps
every other prefix failure on the path that raises the alarm.
"""
from __future__ import annotations

import difflib
import logging
import re

import discord
from discord.ext import commands

log = logging.getLogger(__name__)

MSG_UNKNOWN_COMMAND_GUESS = "`!{typed}` is not a command, try `{suggestion}`"
MSG_UNKNOWN_COMMAND = "`!{typed}` is not a command, run `/help` to see the list"

DELETE_AFTER_S = 20.0
COMMAND_WORD = re.compile(r"^[a-z][a-z0-9-]{1,31}$")
MATCH_CUTOFF = 0.6


class UnknownCommandListener(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @commands.Cog.listener()
    async def on_command_error(self, ctx: commands.Context, error: commands.CommandError) -> None:
        if ctx.command is not None and ctx.command.has_error_handler():
            return
        if ctx.cog is not None and ctx.cog.has_error_handler():
            return
        if not isinstance(error, commands.CommandNotFound):
            log.error(f"prefix command {ctx.invoked_with} failed for {ctx.author}", exc_info=error)
            return

        typed = (ctx.invoked_with or "").lower()
        if not COMMAND_WORD.match(typed):
            return
        suggestion = closest_command(typed, slash_command_names(self.bot, ctx.guild))
        log.info(f"unknown command !{typed} from {ctx.author} in #{ctx.channel}: {ctx.message.jump_url}")

        template = MSG_UNKNOWN_COMMAND if suggestion is None else MSG_UNKNOWN_COMMAND_GUESS
        try:
            await ctx.reply(template.format(typed=typed, suggestion=suggestion), mention_author=False,
                            delete_after=DELETE_AFTER_S)
        except discord.HTTPException as exc:
            log.warning(f"could not answer !{typed}: {exc}")


def slash_command_names(bot: commands.Bot, guild: discord.Guild | None) -> set[str]:
    """Qualified names of every registered slash command, global and guild-scoped, without the leading /"""
    scopes: list[discord.abc.Snowflake | None] = [None]
    if guild is not None:
        scopes.append(discord.Object(id=guild.id))
    names: set[str] = set()
    for scope in scopes:
        for command in bot.tree.walk_commands(guild=scope):
            names.add(command.qualified_name)
    return names


def closest_command(typed: str, names: set[str]) -> str | None:
    """The `/command` worth suggesting, matching a subcommand on its own word so `!ready` finds `/pod ready`"""
    ordered = sorted(names)
    for name in ordered:
        if typed == name:
            return f"/{name}"
    for name in ordered:
        if typed == name.split(" ")[-1]:
            return f"/{name}"
    matches = difflib.get_close_matches(typed, ordered, n=1, cutoff=MATCH_CUTOFF)
    if matches:
        return f"/{matches[0]}"
    return None


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(UnknownCommandListener(bot))
