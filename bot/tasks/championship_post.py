"""Set Championship auto-scheduler and creator.

A daily ET tick posts the season-closing championship its lead days ahead: the announcement plus the
RSVP card (swiss, leaderboard-seated) in the coordination channel, the standings frozen onto the event
so seeds lock in, and the frozen standings list in the thread. Over the following hours it runs the
invite waves — awareness pings of successive rank tiers with a Confirm / Maybe / Can't row — then posts
the Yes-tally seeding table once the last wave is out. Idempotent per set — it never posts a second card
once one exists.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta

import discord
from discord.ext import commands

from bot.commands.pod_draft import build_leaderboard_standings_embed, refresh_seeding_table
from bot.commands.pod_rsvp import build_championship_wave_view, post_scheduled_card
from bot.config import settings
from bot.services import championship
from bot.services import championship_copy as cc
from bot.services import pod_launch
from bot.services.ping_roles import SET_CHAMPION_ROLE_NAME
from bot.services.pod_roles import find_role
from bot.services.pod_schedule import POD_DRAFTERS_ROLE_NAME, SCHEDULE_TZ

log = logging.getLogger(__name__)

_bot: commands.Bot | None = None

WAVE_OFFSETS_MIN: tuple[int, ...] = (10, 120, 240)
SEEDING_TALLY_OFFSET_MIN = WAVE_OFFSETS_MIN[-1] + 60


def init_championship_schedule(bot: commands.Bot) -> None:
    global _bot
    _bot = bot
    bot.pod_scheduler.add_job(
        fire_championship_tick, "cron", hour=championship.CREATION_HOUR_ET, minute=0,
        timezone=SCHEDULE_TZ, id="championship-create", replace_existing=True,
    )
    log.info(f"scheduled set championship tick at {championship.CREATION_HOUR_ET:02d}:00 ET")


async def fire_championship_tick() -> None:
    if _bot is None:
        return
    plan = championship.plan_due_for_creation(datetime.now(SCHEDULE_TZ))
    if plan is None:
        return
    existing = await asyncio.to_thread(championship.event_for_set_sync, plan.set_code)
    if existing is not None:
        log.info(f"championship for {plan.set_code} already exists; skipping")
        return
    await create_championship(_bot, plan)


async def create_championship(bot: commands.Bot, plan: championship.ChampionshipPlan) -> str | None:
    channel = bot.get_channel(settings.pod_draft_channel_id)
    if not isinstance(channel, discord.TextChannel):
        log.warning("championship: coordination channel unresolved or not a text channel")
        return None
    role = find_role(channel.guild, SET_CHAMPION_ROLE_NAME)
    champion_mention = cc.champion_role_mention(role)
    content = cc.card_content(
        set_name=plan.set_name, set_code=plan.set_code, next_set_name=plan.next_set_name,
        next_set_code=plan.next_set_code, next_release_at=plan.next_release_at,
        champion_mention=champion_mention,
    )
    native_body = cc.native_event_body(
        set_name=plan.set_name, set_code=plan.set_code, champion_mention=champion_mention,
    )
    event_id = await post_scheduled_card(
        bot, channel, set_code=plan.set_code, event_time=plan.event_at,
        name=f"👑 {plan.set_code} Set Championship", notify_role_name=POD_DRAFTERS_ROLE_NAME,
        pairing_mode="swiss", seating_mode="leaderboard", card_body=content, native_body=native_body,
    )
    if event_id is None:
        log.warning(f"championship for {plan.set_code} failed to post its card")
        return None
    frozen = await asyncio.to_thread(championship.freeze_seeds_sync, event_id, plan.set_code)
    log.info(f"created {plan.set_code} Set Championship (event {event_id}, froze {frozen} seeds)")
    championship.mark_invites_pending(event_id)
    thread = await _resolve_thread(bot, event_id)
    if thread is not None:
        await _post_thread_seeding(thread, event_id, plan.set_code, plan.event_at)
    _arm_waves(bot, event_id, datetime.now(SCHEDULE_TZ))
    return event_id


async def _resolve_thread(bot: commands.Bot, event_id: str) -> "discord.Thread | None":
    thread_id = await asyncio.to_thread(pod_launch.event_thread_id_sync, event_id)
    if thread_id is None:
        return None
    thread = bot.get_channel(int(thread_id))
    if thread is None:
        try:
            thread = await bot.fetch_channel(int(thread_id))
        except discord.HTTPException:
            return None
    return thread if isinstance(thread, discord.Thread) else None


async def _post_thread_seeding(
    thread: discord.Thread, event_id: str, set_code: str, event_at: datetime,
) -> None:
    """Post the locked standings snapshot as the full leaderboard table. The seat-cut seeding table is
    auto-managed by the leaderboard seeding refresh for championship pods, so it is not posted here."""
    attendees = await asyncio.to_thread(championship.standings_seed_attendees_sync, set_code)
    embed = build_leaderboard_standings_embed(attendees, timestamp=datetime.now(SCHEDULE_TZ))
    try:
        await thread.send(embed=embed)
    except discord.HTTPException:
        log.warning(f"championship: could not post standings in thread {thread.id}", exc_info=True)


def _arm_waves(bot: commands.Bot, event_id: str, created_at: datetime) -> None:
    """Schedule the invite waves after the card is posted so the frozen standings sink in first: top 10
    at 10 minutes, 11-20 at two hours, 21-32 at four hours. Each is an awareness ping of its tier, not a
    gate. The Yes-tally seeding table follows an hour after the last wave, once signups have gathered."""
    for wave_index, offset_min in enumerate(WAVE_OFFSETS_MIN):
        bot.pod_scheduler.add_job(
            fire_wave_job, "date", run_date=created_at + timedelta(minutes=offset_min),
            args=[event_id, wave_index],
            id=f"championship-wave-{event_id}-{wave_index}", replace_existing=True,
        )
    bot.pod_scheduler.add_job(
        fire_seeding_tally_job, "date", run_date=created_at + timedelta(minutes=SEEDING_TALLY_OFFSET_MIN),
        args=[event_id], id=f"championship-tally-{event_id}", replace_existing=True,
    )


async def fire_wave_job(event_id: str, wave_index: int) -> None:
    if _bot is None:
        return
    meta = await asyncio.to_thread(championship.event_meta_sync, event_id)
    if meta is None:
        return
    set_code, event_at = meta
    await fire_wave(_bot, event_id, set_code, event_at, wave_index=wave_index)


async def fire_seeding_tally_job(event_id: str) -> None:
    """Post the Yes-tally seeding table once the last wave has gone out, then leave it to refresh in
    place as more players confirm."""
    if _bot is None:
        return
    championship.mark_invites_complete(event_id)
    await refresh_seeding_table(_bot, event_id)


async def fire_wave(
    bot: commands.Bot, event_id: str, set_code: str, event_at: datetime, *, wave_index: int,
) -> None:
    """Ping one rank tier in the thread with the invite and the Confirm / Maybe / Can't row, so the tier
    sees the event and can answer in one click. Anyone already answered is shown by their status emoji
    and name instead of a fresh ping, so a later wave never re-pings them. Awareness only — every wave
    fires and anyone may RSVP. The seeding table is left for after signups gather, not printed here."""
    seeds = await asyncio.to_thread(championship.frozen_seeds_sync, event_id)
    tier = championship.wave_recipients(seeds, wave_index)
    if not tier:
        return
    thread = await _resolve_thread(bot, event_id)
    if thread is None:
        return
    card = await asyncio.to_thread(pod_launch.scheduled_card_ref_sync, event_id)
    if card is None:
        return
    _, channel_id, message_id, _ = card
    post_url = f"https://discord.com/channels/{thread.guild.id}/{channel_id}/{message_id}"
    rsvp_states = await asyncio.to_thread(pod_launch.rsvp_state_by_user_sync, event_id)
    tokens = [
        cc.wave_recipient_line(
            rsvp_states.get(seed.discord_id), mention=f"<@{seed.discord_id}>", display_name=seed.display_name,
        )
        for seed in tier
    ]
    role = find_role(thread.guild, SET_CHAMPION_ROLE_NAME)
    champion_mention = cc.champion_mention_for_wave(wave_index, role)
    content = cc.wave_invite_ping(wave_index, set_code, tokens, event_at, post_url, champion_mention)
    try:
        await thread.send(
            content=content, view=build_championship_wave_view(event_id),
            allowed_mentions=discord.AllowedMentions(users=True),
        )
    except discord.HTTPException:
        log.warning(f"championship: could not post wave {wave_index} in thread {thread.id}", exc_info=True)

