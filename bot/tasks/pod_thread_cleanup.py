"""Nightly archive of finished pod threads at 02:00 ET.

Discord threads have no auto-archive below 24h, so old draft rooms and never-fired queue threads
linger in the sidebar. Archiving is reversible, so a stray reply just reopens the thread. A short
lookback keeps each run to a handful; already-archived threads and any with activity inside the
grace window are left for a later night so a live conversation is never cut off.
"""
from __future__ import annotations

import logging
from collections.abc import Iterable
from datetime import datetime, timedelta, timezone

import discord
from discord.ext import commands
from sqlalchemy import select

from bot.database import SessionLocal
from bot.models import PodDraftEvent, PodSignal
from bot.services.pod_schedule import SCHEDULE_TZ
from bot.services.pod_signals import QUEUE_BUCKET, STATUS_OPEN


CLEANUP_HOUR_ET = 2
LOOKBACK_DAYS = 2
ACTIVITY_GRACE = timedelta(hours=2)

log = logging.getLogger(__name__)

_bot: commands.Bot | None = None


def init_thread_cleanup(bot: commands.Bot) -> None:
    global _bot
    _bot = bot
    bot.pod_scheduler.add_job(
        archive_past_threads, "cron", hour=CLEANUP_HOUR_ET, minute=0,
        timezone=SCHEDULE_TZ, id="pod-thread-cleanup", replace_existing=True,
    )
    log.info(f"scheduled nightly pod thread cleanup at {CLEANUP_HOUR_ET:02d}:00 ET")


async def archive_past_threads() -> None:
    if _bot is None:
        return
    now = datetime.now(timezone.utc)
    event_thread_ids = _past_event_thread_ids(now)
    queue_thread_ids = _stale_queue_thread_ids(now)
    archived = 0
    for thread_id in event_thread_ids:
        if await _archive_thread(thread_id, now):
            archived += 1
    for thread_id in queue_thread_ids:
        if await _archive_thread(thread_id, now):
            archived += 1
    total = len(event_thread_ids) + len(queue_thread_ids)
    log.info(f"pod thread cleanup: archived {archived} of {total} past threads")


async def delete_threads(bot: commands.Bot, thread_ids: Iterable[int]) -> int:
    """Delete the given threads outright. Backs `!test reset`, where the rows that owned them are gone
    and an archived draft room would only linger as a dead end."""
    deleted = 0
    for thread_id in thread_ids:
        try:
            channel = await bot.fetch_channel(thread_id)
        except discord.NotFound:
            continue
        except discord.HTTPException as e:
            log.warning(f"test reset: fetch_channel({thread_id}) failed: {e}")
            continue
        if not isinstance(channel, discord.Thread):
            continue
        try:
            await channel.delete(reason="!test reset cleanup")
        except discord.HTTPException as e:
            log.warning(f"test reset: delete({thread_id}) failed: {e}")
            continue
        deleted += 1
    return deleted


def _past_event_thread_ids(now: datetime) -> list[int]:
    window_start = now - timedelta(days=LOOKBACK_DAYS)
    with SessionLocal() as session:
        rows = session.execute(
            select(
                PodDraftEvent.discord_thread_id,
                PodDraftEvent.team_a_thread_id,
                PodDraftEvent.team_b_thread_id,
            ).where(PodDraftEvent.event_time < now, PodDraftEvent.event_time >= window_start)
        ).all()
    ids: list[int] = []
    seen: set[int] = set()
    for row in rows:
        for raw in row:
            if raw is None:
                continue
            thread_id = int(raw)
            if thread_id not in seen:
                seen.add(thread_id)
                ids.append(thread_id)
    return ids


def _stale_queue_thread_ids(now: datetime) -> list[int]:
    window_start = now - timedelta(days=LOOKBACK_DAYS)
    with SessionLocal() as session:
        rows = session.execute(
            select(PodSignal.discussion_thread_id).where(
                PodSignal.bucket == QUEUE_BUCKET,
                PodSignal.discussion_thread_id.is_not(None),
                PodSignal.status != STATUS_OPEN,
                PodSignal.last_activity_at >= window_start,
            )
        ).all()
    ids: list[int] = []
    seen: set[int] = set()
    for (raw,) in rows:
        thread_id = int(raw)
        if thread_id not in seen:
            seen.add(thread_id)
            ids.append(thread_id)
    return ids


async def _archive_thread(thread_id: int, now: datetime) -> bool:
    try:
        channel = await _bot.fetch_channel(thread_id)
    except discord.NotFound:
        return False
    except discord.HTTPException as e:
        log.warning(f"pod thread cleanup: fetch_channel({thread_id}) failed: {e}")
        return False
    if not isinstance(channel, discord.Thread) or channel.archived:
        return False
    if _last_activity(channel) > now - ACTIVITY_GRACE:
        return False
    try:
        await channel.edit(archived=True, reason="Nightly pod thread cleanup")
    except discord.HTTPException as e:
        log.warning(f"pod thread cleanup: archive({thread_id}) failed: {e}")
        return False
    return True


def _last_activity(thread: discord.Thread) -> datetime:
    if thread.last_message_id is not None:
        return discord.utils.snowflake_time(thread.last_message_id)
    return thread.created_at or thread.archive_timestamp
