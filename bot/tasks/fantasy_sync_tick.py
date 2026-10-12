"""Keeps the fantasy tables current: Melee results every ten minutes on event days, the field hourly before"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from discord.ext import commands
from requests import RequestException
from sqlalchemy.exc import SQLAlchemyError

from bot.database import SessionLocal
from bot.services.fantasy_event import FantasyEvent, all_events
from bot.services.fantasy_reveal import advance_auto_reveal
from bot.services.fantasy_sync import SyncSummary, sync_event
from bot.services.melee import MeleeClient
from bot.services.watch_party import PREMIER_SCHEDULES
from bot.tasks.pro_play_posts import alert_unseeded_bracket, announce_reveal

log = logging.getLogger(__name__)


def init_fantasy_sync(bot: commands.Bot) -> None:
    bot.pod_scheduler.add_job(
        fire_fantasy_sync, "cron", minute="*/10", timezone=timezone.utc,
        id="fantasy-sync", replace_existing=True,
    )
    log.info("fantasy-sync: ten-minute tick armed for fantasy event days")


async def fire_fantasy_sync() -> None:
    now = datetime.now(timezone.utc)
    for event in all_events():
        if not sync_due(event, now):
            continue
        try:
            summary, reveal = await asyncio.to_thread(_sync, event)
        except (SQLAlchemyError, RequestException):
            log.warning(f"fantasy-sync: {event.code} tick failed, retrying next tick", exc_info=True)
            continue
        if summary.unseeded_quarterfinals:
            await alert_unseeded_bracket(event)
        if reveal is not None:
            await announce_reveal(event, *reveal)


def sync_due(event: FantasyEvent, now: datetime) -> bool:
    window = live_window(event)
    if window is None:
        return False
    starts, ends = window
    if starts <= now <= ends:
        return True
    field_window_opens = starts - timedelta(days=14)
    return field_window_opens <= now < starts and now.minute < 10


def live_window(event: FantasyEvent) -> tuple[datetime, datetime] | None:
    if event.replay_only or event.schedule_name is None:
        return None
    schedule = PREMIER_SCHEDULES.get(event.schedule_name)
    if schedule is None:
        return None
    first, last = schedule.days[0], schedule.days[-1]
    starts = datetime.combine(first.day, first.start, schedule.tz) - timedelta(minutes=30)
    ends = datetime.combine(last.day, last.end, schedule.tz) + timedelta(hours=2)
    return starts, ends


def _sync(event: FantasyEvent) -> tuple[SyncSummary, tuple[int, int] | None]:
    with SessionLocal() as session:
        summary = sync_event(session, event, MeleeClient())
        reveal = advance_auto_reveal(session, event, datetime.now(timezone.utc))
        session.commit()
    if reveal is not None:
        log.info(f"fantasy-sync: {event.code} auto-revealed through round {reveal[1]}")
    return summary, reveal
