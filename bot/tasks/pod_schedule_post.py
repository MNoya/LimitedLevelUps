"""Re-sweep the community allocation from the current votes and keep the pod format schedule card fresh in pod
chat on a daily cadence.

The allocation math is cheap, so each tick re-runs the sweep before repainting: the persisted overlay tracks
the vote within hours and the card, launcher and calendar keep reading one source. The first tick after the
flashback season's first launcher posts and pins a fresh card in place of the old one. Organizer manual overrides
and the championship day are left alone. The render, post and edit-in-place live in `pod_schedule_card`.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, time

from discord.ext import commands

from bot.config import settings
from bot.database import SessionLocal
from bot.discord_helpers import resolve_pod_chat_channel
from bot.services.pod_calendar import persist_calendar
from bot.services.pod_format_allocator import run_allocation
from bot.services.pod_schedule_card import refresh_schedule_post
from bot.services.championship_dates import plan_for, season_start
from bot.services.pod_schedule import SCHEDULE_TZ
from bot.services.pod_signals import POST_HOUR_ET
from bot.services.pod_schedule_controls import PodScheduleView

log = logging.getLogger(__name__)

POST_TIMES = (time(10, 30), time(15, 0), time(20, 30))

_bot: commands.Bot | None = None


def init_pod_schedule_post(bot: commands.Bot) -> None:
    global _bot
    _bot = bot
    if not settings.pod_schedule_enabled:
        log.info("POD_SCHEDULE_ENABLED=false; pod-schedule post tick disabled")
        return
    for slot in POST_TIMES:
        bot.pod_scheduler.add_job(
            fire_schedule_post,
            "cron",
            hour=slot.hour,
            minute=slot.minute,
            timezone=SCHEDULE_TZ,
            id=f"pod-schedule-post-{slot.hour:02d}{slot.minute:02d}",
            replace_existing=True,
        )
    windows = ", ".join(f"{slot.hour:02d}:{slot.minute:02d}" for slot in POST_TIMES)
    log.info(f"pod-schedule post armed: {windows} {SCHEDULE_TZ.key}")


async def fire_schedule_post() -> None:
    if _bot is None:
        log.error("pod-schedule post: bot reference is not initialised")
        return
    channel = resolve_pod_chat_channel(_bot)
    if channel is None:
        log.warning("pod-schedule post: no pod chat channel; skipping tick")
        return
    now = datetime.now(SCHEDULE_TZ)
    count = await asyncio.to_thread(_sweep, now.date())
    log.info(f"pod-schedule post: swept {count} slots from {now.date()}")
    await refresh_schedule_post(channel, view=PodScheduleView(), repost_before=_season_launcher_at(now))


def _season_launcher_at(now: datetime) -> datetime | None:
    """When the flashback season's first launcher went up, once it has, so the card pinned before it is replaced
    with a fresh one showing the season's formats"""
    plan = plan_for(now)
    start = season_start(plan.set_code) if plan is not None else None
    if start is None:
        return None
    launcher_at = datetime.combine(start, time(POST_HOUR_ET), tzinfo=SCHEDULE_TZ)
    return launcher_at if now >= launcher_at else None


def _sweep(today) -> int:
    with SessionLocal() as session:
        assignments = run_allocation(session, today, rewrite=True)
        persist_calendar(session, today)
        session.commit()
        return len(assignments)
