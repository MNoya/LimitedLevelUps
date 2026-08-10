"""Route failures to the bot-spam channel, so a broken path is noticed before a player reports it.

Railway keeps the full log. This is the alarm, and it is built to stay quiet: at most one message per
flush window, each failure reported once per cooldown carrying the count it accumulated while silent. A
storm of the same failure is one line saying how many, never one message per occurrence.

A WARNING alerts only when it carries a traceback, since the handled-and-logged path is the bot working
as designed. Discord codes for a message or thread that went away are dropped outright: the daily poll
cleaning up yesterday's archived threads is not news.
"""
from __future__ import annotations

import asyncio
import logging
import time

import discord
from discord.ext import commands

from bot.discord_helpers import run_detached
from bot.services import bot_log


FLUSH_INTERVAL_S = 30.0
REPEAT_COOLDOWN_S = 1800.0
FINGERPRINTS_PER_MESSAGE = 5
DETAIL_MAX_CHARS = 240

SILENT_LOGGERS = ("bot.services.bot_log", "bot.services.error_alerts")
BENIGN_DISCORD_CODES = {
    10003: "unknown channel",
    10008: "unknown message",
    50083: "thread archived",
}

log = logging.getLogger(__name__)


class ErrorAlertHandler(logging.Handler):
    """Counts failures by call site and hands the due ones to the flush loop.

    `emit` runs on whichever thread logged, including `asyncio.to_thread` workers, so it only touches
    memory. Every send happens on the loop, in `flush_alerts`."""

    def __init__(self) -> None:
        super().__init__(level=logging.WARNING)
        self._pending: dict[str, tuple[str, int]] = {}
        self._reported_at: dict[str, float] = {}

    def emit(self, record: logging.LogRecord) -> None:
        if not _alertable(record):
            return
        fingerprint = f"{record.module}.{record.funcName}:{record.lineno}"
        detail, count = self._pending.get(fingerprint, (_detail(record), 0))
        self._pending[fingerprint] = (detail, count + 1)

    def drain(self) -> list[str]:
        """The lines due now. A fingerprint inside its cooldown keeps counting silently and reports the
        whole run at once when the cooldown lapses, so a failure firing every second still costs one
        message every half hour."""
        now = time.monotonic()
        lines: list[str] = []
        for fingerprint, (detail, count) in list(self._pending.items()):
            if len(lines) >= FINGERPRINTS_PER_MESSAGE:
                break
            last = self._reported_at.get(fingerprint)
            if last is not None and now - last < REPEAT_COOLDOWN_S:
                continue
            del self._pending[fingerprint]
            self._reported_at[fingerprint] = now
            lines.append(f"`{fingerprint}` ×{count}\n{detail}")
        self._forget_stale(now)
        return lines

    def _forget_stale(self, now: float) -> None:
        if len(self._reported_at) <= 256:
            return
        cutoff = now - REPEAT_COOLDOWN_S
        self._reported_at = {fp: at for fp, at in self._reported_at.items() if at > cutoff}


def install(bot: commands.Bot) -> ErrorAlertHandler:
    handler = ErrorAlertHandler()
    logging.getLogger().addHandler(handler)
    run_detached(flush_alerts(bot, handler), "the error alert flush loop")
    return handler


async def flush_alerts(bot: commands.Bot, handler: ErrorAlertHandler) -> None:
    while True:
        await asyncio.sleep(FLUSH_INTERVAL_S)
        lines = handler.drain()
        if not lines:
            continue
        try:
            await bot_log.get(bot).post_plain("\n".join(lines))
        except Exception:  # noqa: BLE001 - the alarm must outlive a failure to sound it
            log.warning("could not post the error alert", exc_info=True)


def _alertable(record: logging.LogRecord) -> bool:
    if record.name.startswith(SILENT_LOGGERS):
        return False
    if _benign(record):
        return False
    return record.levelno >= logging.ERROR or record.exc_info is not None


def _benign(record: logging.LogRecord) -> bool:
    error = record.exc_info[1] if record.exc_info else None
    return isinstance(error, discord.HTTPException) and error.code in BENIGN_DISCORD_CODES


def _detail(record: logging.LogRecord) -> str:
    """The exception line when there is one, else the message that was logged. The traceback stays in
    Railway: a channel message is where to look, not what to read."""
    error = record.exc_info[1] if record.exc_info else None
    text = f"{type(error).__name__}: {error}" if error is not None else record.getMessage()
    return text[:DETAIL_MAX_CHARS]
