"""Discord channel sink for pod-draft "something went wrong" signals.

Smoke alarm, not audit log — Railway has the full picture. Posts a terse line per
surprise event, with a 60s per-fingerprint cooldown to collapse storms.
Resolves by configured id, else by channel name; silent no-op when neither is found.
"""
from __future__ import annotations

import hashlib
import logging
import time

import discord
from discord.ext import commands

from bot.config import settings
from bot.discord_helpers import channel_matching_name


log = logging.getLogger(__name__)


_PER_FP_COOLDOWN_S = 60.0
_MESSAGE_MAX_CHARS = 1900


class BotLog:
    def __init__(self, bot: commands.Bot, channel_id: int | None) -> None:
        self.bot = bot
        self.channel_id = channel_id
        self._last_posted: dict[str, float] = {}

    async def post(self, summary: str, *, fingerprint: str | None = None, tag: str = "INFO") -> None:
        now = time.monotonic()
        fp = fingerprint or hashlib.sha1(f"{tag}|{summary}".encode("utf-8")).hexdigest()
        last = self._last_posted.get(fp)
        if last is not None and now - last < _PER_FP_COOLDOWN_S:
            log.info(f"bot_log suppressed (cooldown) tag={tag} fp={fp}")
            return
        body = f"**[{tag}]** {summary}"
        if len(body) > _MESSAGE_MAX_CHARS:
            body = body[:_MESSAGE_MAX_CHARS]
        channel = await self._resolve_channel()
        if channel is None:
            return
        try:
            await channel.send(body)
        except discord.HTTPException:
            log.warning("bot_log channel send failed", exc_info=True)
            return
        self._last_posted[fp] = now
        if len(self._last_posted) > 256:
            cutoff = now - _PER_FP_COOLDOWN_S * 4
            self._last_posted = {k: v for k, v in self._last_posted.items() if v > cutoff}

    async def post_plain(self, content: str | None = None, *, embed: "discord.Embed | None" = None) -> None:
        """Send raw content/embed to the bot-spam channel"""
        if content is None and embed is None:
            return
        if content is not None and len(content) > _MESSAGE_MAX_CHARS:
            content = content[:_MESSAGE_MAX_CHARS]
        channel = await self._resolve_channel()
        if channel is None:
            return
        try:
            await channel.send(content=content, embed=embed)
        except discord.HTTPException:
            log.warning("bot_log channel send failed", exc_info=True)

    async def _resolve_channel(self):
        """Falls back to a channel named `bot-spam` when no id is configured, so a test server logs without
        anyone setting a per-environment id."""
        if self.channel_id is None:
            return self._channel_by_name()
        try:
            return self.bot.get_channel(self.channel_id) or await self.bot.fetch_channel(self.channel_id)
        except discord.HTTPException:
            log.warning(f"bot_log channel {self.channel_id} unreachable", exc_info=True)
            return self._channel_by_name()

    def _channel_by_name(self):
        """`get` hands the silent fallback whatever object it was called with, which need not be a Bot."""
        for guild in getattr(self.bot, "guilds", ()):
            channel = channel_matching_name(guild, settings.discord_botlog_channel_name)
            if channel is not None:
                return channel
        return None


_NOOP_LOG: "BotLog | None" = None


def get(bot: commands.Bot) -> BotLog:
    """Return the BotLog attached to ``bot``; silent fallback for tests or pre-setup_hook callers."""
    existing = getattr(bot, "bot_log", None)
    if isinstance(existing, BotLog):
        return existing
    global _NOOP_LOG
    if _NOOP_LOG is None:
        _NOOP_LOG = BotLog(bot, None)
    return _NOOP_LOG
