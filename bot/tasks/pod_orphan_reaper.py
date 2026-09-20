"""Interval sweep that closes a mock lobby no manager holds.

A hard crash or a Draftmancer session that never reconnects can leave an open mock card with a working
Join button and a live event row that nothing will close. The manager's own idle watch and reconnect
handle the common cases; this only catches what falls outside them, long after the lobby could still be
gathering.
"""
from __future__ import annotations

import logging

from discord.ext import commands

from bot.config import settings
from bot.services.pod_draft_manager import reap_orphan_mock_lobbies

log = logging.getLogger(__name__)


def init_orphan_reaper(bot: commands.Bot) -> None:
    interval = settings.pod_orphan_reaper_minutes * 60
    bot.pod_scheduler.add_job(
        _run_orphan_reaper, "interval", seconds=interval, args=[bot],
        id="pod-orphan-reaper", replace_existing=True,
    )
    log.info(f"scheduled the mock orphan reaper every {settings.pod_orphan_reaper_minutes}m")


async def _run_orphan_reaper(bot: commands.Bot) -> None:
    try:
        await reap_orphan_mock_lobbies(bot)
    except Exception:
        log.warning("[ORPHAN-REAPER] sweep failed", exc_info=True)
