"""Forward a community meme when someone writes the line it answers, once a day.

Matching normalizes apostrophes, casing and punctuation away and then holds the whole word skeleton, so a
partial echo does not fire. A forward carries only ids, so the source message is never read.
"""
from __future__ import annotations

import logging
import re
import time

import discord
from discord.ext import commands

from bot.services import bot_log

log = logging.getLogger(__name__)

MEME_FORWARD = discord.MessageReference(
    guild_id=775371722065051658, channel_id=1149794318886895687, message_id=1394849924147056661,
    type=discord.MessageReferenceType.forward,
)

COOLDOWN_S = 24 * 3600

APOSTROPHES = re.compile(r"['‘’ʼ`´]")
NON_WORD = re.compile(r"[^a-z0-9]+")
LINE = re.compile(
    r"\b(?:(?:do|does|did)(?: ?nt|n ?t| not)|(?:are|is|was)(?: ?nt|n ?t| not)|aint|never)\s+(?:\w+\s+){0,2}"
    r"(?:make|makin|making|made|print|printin|printing|printed)\s+"
    r"(?!(?:me|you|us|him|her|it|them|em)\s+\w+\s+like\b)(?:\w+\s+){0,3}"
    r"like\s+they\s+used?\s+(?:to|ta|too|2)\b"
)


class UsedTaListener(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.forwarded_at: float | None = None

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if message.author.bot or not says_the_line(message.content):
            return
        if self.forwarded_at is not None and time.monotonic() - self.forwarded_at < COOLDOWN_S:
            return
        try:
            await message.channel.send(reference=MEME_FORWARD)
        except discord.HTTPException as exc:
            log.warning(f"usedta meme unreachable: {exc}")
        self.forwarded_at = time.monotonic()
        await bot_log.get(self.bot).post_plain(
            f"<@{self.bot.owner_id}> **{message.author.display_name}** said the line: {message.jump_url}")


def says_the_line(text: str) -> bool:
    """Spelling of the contractions and the last word varies, the word skeleton does not. Nothing matches
    without the tail's verb, so the substring check ends almost every message before an allocation."""
    lowered = text.lower()
    if "use" not in lowered:
        return False
    return LINE.search(NON_WORD.sub(" ", APOSTROPHES.sub("", lowered))) is not None


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(UsedTaListener(bot))
