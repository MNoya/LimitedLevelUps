"""Nightly archive of finished pod threads at 02:00 ET.

Discord threads have no auto-archive below 24h, so old draft rooms and never-fired queue threads
linger in the sidebar. Archiving is reversible, so a stray reply just reopens the thread. A short
lookback keeps each run to a handful; already-archived threads and any with activity inside the
grace window are left for a later night so a live conversation is never cut off.
"""
from __future__ import annotations

import asyncio
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


async def delete_bot_threads_in(channel: discord.TextChannel, bot_user_id: int) -> int:
    """Delete every thread in this channel the bot owns, archived ones included, and say how many went.

    `!test reset` clears threads it can name from the rows it is deleting, which misses any thread those
    rows stopped pointing at. A pod that splits is the case: its first table moves onto a thread of its
    own and the thread everybody gathered in belongs to nothing afterwards, so run after run they stack
    up in the sidebar. Ownership is the filter, so a thread somebody else opened in the channel is left
    alone."""
    threads = list(channel.threads)
    async for archived in channel.archived_threads(limit=None):
        threads.append(archived)
    owned = [thread for thread in threads if thread.owner_id == bot_user_id]
    return await _delete_all(owned)


async def delete_threads(bot: commands.Bot, thread_ids: Iterable[int]) -> int:
    """Delete the given threads outright. Backs `!test reset`, where the rows that owned them are gone
    and an archived draft room would only linger as a dead end."""
    threads = []
    for thread_id in thread_ids:
        try:
            channel = await bot.fetch_channel(thread_id)
        except discord.NotFound:
            continue
        except discord.HTTPException as e:
            log.warning(f"test reset: fetch_channel({thread_id}) failed: {e}")
            continue
        if isinstance(channel, discord.Thread):
            threads.append(channel)
    return await _delete_all(threads)


async def _delete_all(threads: list[discord.Thread]) -> int:
    """Delete every thread at once and count the ones that went.

    One at a time, a `!test reset` clearing a night of pods spent most of a minute waiting on round trips
    that have nothing to do with each other."""
    async def delete(thread: discord.Thread) -> bool:
        try:
            await thread.delete(reason="!test reset cleanup")
        except discord.HTTPException as e:
            log.warning(f"test reset: delete({thread.id}) failed: {e}")
            return False
        return True

    results = await asyncio.gather(*(delete(thread) for thread in threads))
    return sum(results)


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
