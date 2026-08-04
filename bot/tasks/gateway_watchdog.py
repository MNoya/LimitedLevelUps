"""Report a Discord gateway that stops delivering events.

discord.py notices a dead socket only when it stops answering: `poll_event` gives up after 60s of
total silence, and the keep-alive thread forces a reconnect once heartbeat ACKs stop. Neither covers
a socket that answers heartbeats while no dispatch events arrive, which is what an upstream
interaction failure looks like from in here. The process stays up, crons keep firing, the logs stay
clean, and every button a player clicks times out unanswered, so the outage reads as a bot bug.

This only reports. Reconnecting or restarting on its own would be acting on a guess: the same silence
comes from a Discord API outage, where a restart loop costs pod managers and draft sockets and fixes
nothing. Naming the symptom within a few minutes is the whole value, and a watchdog with no authority
to act cannot make an outage worse.
"""
from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Callable

import discord
from discord.ext import commands, tasks

from bot.config import settings


CHECK_INTERVAL_S = 60
QUIET_SECONDS = 300
ALERT_COOLDOWN_S = 900

MSG_GATEWAY_SILENT = (
    "🚨 Discord Gateway stopped delivering events {minutes} minutes ago - check "
    "https://discordstatus.com for updates"
)

log = logging.getLogger(__name__)

_watchdog: GatewayWatchdog | None = None


def init_gateway_watchdog(bot: commands.Bot) -> None:
    global _watchdog
    _watchdog = GatewayWatchdog(bot)
    bot.add_listener(_watchdog.mark_event, "on_socket_event_type")
    _watchdog.start()
    log.info(f"gateway watchdog armed: probes after {QUIET_SECONDS}s without a dispatch event")


class GatewayWatchdog:
    """Tracks how long the gateway has gone without a dispatch event and says so when it stalls."""

    def __init__(self, bot: commands.Bot, *, clock: Callable[[], float] = time.monotonic):
        self.bot = bot
        self.last_event_at = clock()
        self.last_alert_at: float | None = None
        self._clock = clock

    def start(self) -> None:
        self._tick.start()

    async def mark_event(self, event_type: str) -> None:
        self.last_event_at = self._clock()

    async def check(self) -> None:
        """A quiet server probes on a routine basis, so only a failing probe logs above debug."""
        quiet_for = self._clock() - self.last_event_at
        if quiet_for < QUIET_SECONDS:
            return

        guild = self.bot.get_guild(settings.discord_guild_id) if settings.discord_guild_id else None
        if guild is None or self.bot.user is None:
            log.error("gateway watchdog has no cached guild to probe; skipping this check")
            return

        log.debug(f"no gateway event for {quiet_for:.0f}s; probing the socket")
        if await self.probe(guild):
            log.debug(f"gateway answered the probe after {quiet_for:.0f}s of silence")
            self.last_event_at = self._clock()
            return
        await self.alert(quiet_for)

    async def probe(self, guild: discord.Guild) -> bool:
        """Ask the gateway for one member chunk. The reply arrives as a dispatch event, so an answer
        proves the path that carries interactions is alive and silence proves it is not."""
        try:
            await guild.query_members(user_ids=[self.bot.user.id], limit=1, cache=False)
        except (asyncio.TimeoutError, discord.DiscordException, OSError, RuntimeError):
            log.error("gateway probe got no member chunk back", exc_info=True)
            return False
        return True

    async def alert(self, quiet_for: float) -> None:
        """Rate limited so a long outage leaves one trail every quarter hour, not one a minute."""
        if self.last_alert_at is not None and self._clock() - self.last_alert_at < ALERT_COOLDOWN_S:
            return
        self.last_alert_at = self._clock()
        log.error(f"gateway delivered no events for {quiet_for:.0f}s and the probe went unanswered")
        bot_log = getattr(self.bot, "bot_log", None)
        if bot_log is None:
            return
        await bot_log.post(
            MSG_GATEWAY_SILENT.format(minutes=int(quiet_for // 60)),
            fingerprint="gateway-silence",
            tag="GATEWAY",
        )

    @tasks.loop(seconds=CHECK_INTERVAL_S)
    async def _tick(self) -> None:
        try:
            await self.check()
        except Exception:
            log.exception("gateway watchdog check failed")

    @_tick.before_loop
    async def _before_tick(self) -> None:
        await self.bot.wait_until_ready()
        self.last_event_at = self._clock()
