"""Answer the line, a worst-card-ever call or `!worstcard`, mostly with one of the worst cards ever printed"""
from __future__ import annotations

import logging
import random
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
WORST_CARD_EVER = re.compile(r"\bworst cards?\b.*\bever\b")


class UsedTaListener(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.answered_at: float | None = None
        self.undrawn_cards: list[str] = []

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if message.author.bot:
            return
        if says_the_line(message.content):
            answer, said = self.answer_the_line, "the line"
        elif calls_a_worst_card_ever(message.content):
            answer, said = self.reply_worst_card, "worst card ever"
        else:
            return
        if self.answered_at is not None and time.monotonic() - self.answered_at < COOLDOWN_S:
            return
        try:
            await answer(message)
        except discord.HTTPException as exc:
            log.warning(f"usedta answer failed: {exc}")
        self.answered_at = time.monotonic()
        await bot_log.get(self.bot).post_plain(
            f"<@{self.bot.owner_id}> **{message.author.display_name}** said {said}: {message.jump_url}")

    @commands.command(name="worstcard")
    async def worstcard(self, ctx: commands.Context) -> None:
        try:
            await ctx.send(self.draw_worst_card())
        except discord.HTTPException as exc:
            log.warning(f"worstcard post failed: {exc}")

    async def answer_the_line(self, message: discord.Message) -> None:
        if random.random() < 0.2:
            await message.channel.send(reference=MEME_FORWARD)
        else:
            await self.reply_worst_card(message)

    async def reply_worst_card(self, message: discord.Message) -> None:
        await message.reply(self.draw_worst_card(), mention_author=False)

    def draw_worst_card(self) -> str:
        if not self.undrawn_cards:
            self.undrawn_cards = random.sample(worst_card_urls(), k=len(worst_card_urls()))
        return self.undrawn_cards.pop()


def says_the_line(text: str) -> bool:
    """Spelling of the contractions and the last word varies, the word skeleton does not. Nothing matches
    without the tail's verb, so the substring check ends almost every message before an allocation."""
    lowered = text.lower()
    if "use" not in lowered:
        return False
    return LINE.search(normalized(lowered)) is not None


def calls_a_worst_card_ever(text: str) -> bool:
    lowered = text.lower()
    if "worst" not in lowered:
        return False
    return WORST_CARD_EVER.search(normalized(lowered)) is not None


def normalized(lowered: str) -> str:
    return NON_WORD.sub(" ", APOSTROPHES.sub("", lowered))


def worst_card_urls() -> tuple[str, ...]:
    return (
        "https://scryfall.com/card/mrd/59/chimney-imp",
        "https://scryfall.com/card/me4/175/wood-elemental",
        "https://scryfall.com/card/me3/211/sorrows-path",
        "https://scryfall.com/card/nem/36/pale-moon",
        "https://scryfall.com/card/ons/190/break-open",
        "https://scryfall.com/card/drk/23/deep-water",
        "https://scryfall.com/card/me4/180/armageddon-clock",
        "https://scryfall.com/card/4ed/92/power-leak",
        "https://scryfall.com/card/rav/76/zephyr-spirit",
        "https://scryfall.com/card/hml/22/bakis-curse",
        "https://scryfall.com/card/ody/143/hint-of-insanity",
        "https://scryfall.com/card/fem/27a/tidal-flats",
        "https://scryfall.com/card/hml/62/ambush",
        "https://scryfall.com/card/pcy/143/wintermoon-mesa",
        "https://scryfall.com/card/mmq/286/assembly-hall",
        "https://scryfall.com/card/leg/32/rapid-fire",
        "https://scryfall.com/card/mir/157/barreling-attack",
        "https://scryfall.com/card/mir/317/razor-pendulum",
        "https://scryfall.com/card/leg/17/great-wall",
        "https://scryfall.com/card/leg/204/shelkin-brownie",
        "https://scryfall.com/card/ice/309/arcums-sleigh",
        "https://scryfall.com/card/mmq/13/common-cause",
        "https://scryfall.com/card/tor/30/cephalid-snitch",
        "https://scryfall.com/card/hml/101/apocalypse-chime",
        "https://scryfall.com/card/vis/147/juju-bubble",
        "https://scryfall.com/card/ody/208/mudhole",
        "https://scryfall.com/card/arn/17/merchant-ship",
        "https://scryfall.com/card/9ed/286/aladdins-ring",
        "https://scryfall.com/card/me4/206/ice-cauldron",
        "https://scryfall.com/card/me4/217/obelisk-of-undoing",
        "https://scryfall.com/card/chk/263/nine-ringed-bo",
        "https://scryfall.com/card/arb/115/dragon-appeasement",
    )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(UsedTaListener(bot))
