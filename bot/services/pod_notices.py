"""Settings-change notices: each new notice replaces the bot's previous one of the same kind."""
from __future__ import annotations

import logging
from collections.abc import Sequence

import discord

log = logging.getLogger("bot.pod_notices")


async def send_settings_notice(channel, bot_user, content: str, *, marker: str | Sequence[str]) -> None:
    """Post the notice, then drop the bot's older messages carrying any of its markers. One notice can
    report several settings at once, and then it retires the older notice of every setting it names."""
    markers = [marker] if isinstance(marker, str) else list(marker)
    try:
        posted = await channel.send(content)
    except discord.HTTPException:
        log.warning("could not post settings-change notice", exc_info=True)
        return
    if bot_user is None or not isinstance(channel, (discord.Thread, discord.TextChannel)):
        return

    def stale(message: discord.Message) -> bool:
        if message.id == posted.id or message.author.id != bot_user.id:
            return False
        return any(mark in message.content for mark in markers)

    try:
        await channel.purge(limit=None, check=stale, reason="Stale settings notice")
    except discord.HTTPException as exc:
        log.warning(f"could not purge stale settings notices ({markers}): {exc}")
