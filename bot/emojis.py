from __future__ import annotations

import logging

import discord
from discord.ext import commands

from bot.sets import CUBE_CODE, cube_glyph_emoji_name, cube_variant_for_board, is_cube_board_code


log = logging.getLogger("bot.emojis")

_EMOJIS: dict[str, discord.Emoji] = {}


def get(name: str) -> str:
    e = _EMOJIS.get(name)
    return str(e) if e else ""


def get_emoji(name: str) -> discord.Emoji | None:
    return _EMOJIS.get(name)


def set_symbol(code: str) -> discord.Emoji | None:
    """The keyrune set-symbol app emoji for a set code, looked up case-insensitively. A whole-cube
    board takes its cube's registry glyph, and any cube board whose glyph is not uploaded falls back
    to the shared cube symbol."""
    found = _EMOJIS.get(code.lower()) or _EMOJIS.get(code.upper())
    if found is not None or not is_cube_board_code(code):
        return found
    variant = cube_variant_for_board(code)
    glyph = _EMOJIS.get(cube_glyph_emoji_name(variant)) if variant is not None else None
    return glyph or _EMOJIS.get(CUBE_CODE.lower())


def prefix(name: str) -> str:
    """Custom emoji followed by a space for inlining before text, or '' if not loaded."""
    e = _EMOJIS.get(name)
    return f"{e} " if e else ""


def resolve(token: str) -> str | None:
    """An application-emoji name resolves to its glyph, a unicode glyph passes through, and an
    application name that isn't loaded yet resolves to None."""
    e = _EMOJIS.get(token)
    if e:
        return str(e)
    return None if token.isalnum() else token


def mana_number(n: int) -> str:
    """`5` → `:mana5:` glyph if loaded, else `'5'` fallback. Mana font ships 0–20."""
    e = _EMOJIS.get(f"mana{n}")
    return str(e) if e else str(n)


async def load(bot: commands.Bot) -> None:
    try:
        fetched = await bot.fetch_application_emojis()
    except discord.HTTPException:
        log.warning("could not fetch application emojis", exc_info=True)
        return
    _EMOJIS.clear()
    for e in fetched:
        _EMOJIS[e.name] = e
    log.info(f"loaded {len(_EMOJIS)} application emojis: {', '.join(sorted(_EMOJIS)) or '(none)'}")
