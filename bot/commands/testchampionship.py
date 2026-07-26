"""Owner-only `!test championship` — stage the whole Set Championship flow in Discord.

Posts a real card and event thread in the pod-draft coordination channel (with the @Pod Drafters
mention), then sends every follow-on message inside that thread in order, each titled with when the
live flow would post it: the frozen standings, the three invite waves with the Confirm / Maybe / Can't
row, the Yes-tally seeding table, and finally the Daily Pod Launcher in the channel. Shares the
production builders (`championship_copy`, `pod_draft` seeding, `pod_rsvp`); it owns only the synthetic
roster it feeds in and the staging titles. Meant for a test server, since it creates a real card.
"""
from __future__ import annotations

import asyncio

import discord
from discord import ui
from discord.ext import commands
from sqlalchemy import select

from datetime import datetime, timedelta

from bot.commands.pod_draft import (
    CHAMPIONSHIP_CUT,
    SEEDING_CUT_ALTERNATES,
    build_leaderboard_standings_embed,
    build_seeding_image_message_from_names,
    seeding_phase_projected,
)
from bot.commands.pod_rsvp import build_championship_wave_view, post_scheduled_card
from bot.commands.test_group import test_group
from bot.config import settings
from bot.database import SessionLocal
from bot.models import MagicSet
from bot.services import championship
from bot.services import championship_copy as cc
from bot.services import pod_swiss
from bot.services.ping_roles import SET_CHAMPION_ROLE_NAME
from bot.services.player_stats import SeededAttendee, rank_players_for_set
from bot.services.pod_launch import LauncherSlot, event_thread_id_sync, scheduled_card_ref_sync
from bot.services.pod_roles import find_role
from bot.services.pod_schedule import POD_DRAFTERS_ROLE_NAME, SCHEDULE_TZ
from bot.services.pod_signals import (
    RSVP_MAYBE,
    RSVP_NO,
    RSVP_YES,
    STATUS_FIRED,
    STATUS_OPEN,
    named_bucket_key,
)
from bot.tasks.pod_daily_poll import PodPollView, build_poll_embed
from bot.services.pod_swiss import MatchOutcome
from bot.services.pod_tournament import (
    TOTAL_ROUNDS,
    build_champion_embed,
    build_deck_ping,
    build_live_submit_deck_button,
    mark_trophy_match,
    pod_page_url,
)
from bot.sets import active_set_code

MSG_NO_SUCCESSOR = "No successor set is registered, so there is no championship date to derive yet."
MSG_NO_COORDINATION_CHANNEL = "The pod-draft coordination channel is not set up, so nothing was staged."
MSG_CARD_FAILED = "Could not post the championship card."
MSG_THREAD_FAILED = "Could not resolve the championship thread."

_FALLBACK_PLAYERS: list[tuple[str, float]] = [
    (name, 130.0 - index * 3.5)
    for index, name in enumerate((
        "Jace Beleren", "Liliana Vess", "Chandra Nalaar", "Nissa Revane", "Gideon Jura",
        "Teferi Akosa", "Kaya Ghost", "Vraska Golgari", "Ajani Goldmane", "Sorin Markov",
        "Ral Zarek", "Kiora Atua", "Domri Rade", "Ashiok Nightmare", "Tamiyo Moon",
        "Narset Reversal", "Dovin Baan", "Saheeli Rai", "Angrath Flame", "Karn Silver",
    ))
]


async def setup(bot: commands.Bot) -> None:
    @test_group.command(name="championship")
    @commands.is_owner()
    async def test_championship(ctx: commands.Context) -> None:
        """Owner-only. Stage the full Set Championship flow in the pod-draft coordination channel."""
        plan = championship.plan_for()
        if plan is None:
            await ctx.send(MSG_NO_SUCCESSOR)
            return
        channel = ctx.bot.get_channel(settings.pod_draft_channel_id)
        if not isinstance(channel, discord.TextChannel):
            await ctx.send(MSG_NO_COORDINATION_CHANNEL)
            return
        players = await asyncio.to_thread(_preview_players_sync, championship.INVITE_DEPTH) or _FALLBACK_PLAYERS
        names = [name for name, _ in players]
        event_at = plan.event_at
        champion_role = find_role(channel.guild, SET_CHAMPION_ROLE_NAME)

        card_body = cc.card_content(
            set_name=plan.set_name, set_code=plan.set_code, next_set_name=plan.next_set_name,
            next_set_code=plan.next_set_code, next_release_at=plan.next_release_at,
            champion_mention=cc.card_champion_mention(champion_role),
        )
        event_id = await post_scheduled_card(
            ctx.bot, channel, set_code=plan.set_code, event_time=event_at,
            name=f"👑 {plan.set_code} Set Championship", notify_role_name=POD_DRAFTERS_ROLE_NAME,
            pairing_mode="swiss", seating_mode="leaderboard", card_body=card_body,
        )
        if event_id is None:
            await ctx.send(MSG_CARD_FAILED)
            return
        thread = await _resolve_preview_thread(ctx.bot, event_id)
        if thread is None:
            await ctx.send(MSG_THREAD_FAILED)
            return

        attendees = await asyncio.to_thread(championship.standings_seed_attendees_sync, plan.set_code)
        if not attendees:
            attendees = [
                SeededAttendee(slug=None, display_name=name, rank=rank, score=score, trophies=max(0, 22 - rank))
                for rank, (name, score) in enumerate(players, 1)
            ]
        await _stage(thread, "Posted right after the card")
        await thread.send(embed=build_leaderboard_standings_embed(attendees, timestamp=datetime.now(SCHEDULE_TZ)))

        post_url = _card_post_url(thread.guild.id, await asyncio.to_thread(scheduled_card_ref_sync, event_id))
        preview_rsvps = _preview_rsvp_states(names)
        wave_when = ("10 minutes after the card", "2 hours after the card", "4 hours after the card")
        for wave_index, (low, high) in enumerate(championship.INVITE_WAVE_TIERS):
            tier = names[low:high]
            if not tier:
                continue
            await _stage(thread, f"Posted {wave_when[wave_index]}")
            tokens = [
                cc.wave_recipient_line(preview_rsvps.get(name), mention=f"**@{name}**", display_name=name)
                for name in tier
            ]
            await thread.send(
                content=cc.wave_invite_ping(
                    wave_index, plan.set_code, tokens, event_at, post_url,
                    cc.champion_mention_for_wave(wave_index, champion_role),
                ),
                view=build_championship_wave_view(event_id),
                allowed_mentions=discord.AllowedMentions.none(),
            )

        await _stage(thread, "Posted 1 hour after the last wave")
        seeding_file, seeding_embed = await asyncio.to_thread(
            build_seeding_image_message_from_names, names, None,
            seat_cap=CHAMPIONSHIP_CUT, header=seeding_phase_projected(), cut_label=SEEDING_CUT_ALTERNATES,
        )
        await _thread_send(thread, seeding_file, seeding_embed)

        await _stage(channel, "Posted on the Daily Pod Launcher, championship day")
        slots = _preview_launcher_slots(plan.set_code, event_at, names, str(thread.id))
        await channel.send(
            embed=build_poll_embed(slots, channel.guild), view=PodPollView(slots, channel.guild),
            allowed_mentions=discord.AllowedMentions.none(),
        )

    @test_group.command(name="tiebreakers")
    @commands.is_owner()
    async def test_tiebreakers(ctx: commands.Context) -> None:
        """Owner-only. Preview the Final Standings tiebreaker table that surfaces when a placement is
        decided on tiebreakers (a trophy-match loser bumped below 2nd)."""
        standings, match_states = _tiebreaker_preview_scenario()
        embed = build_champion_embed(
            standings, event_name="Tiebreaker Preview Pod",
            pending_count=0, champion_locked=True, match_states=match_states,
        )
        await ctx.send(embed=embed)

    @test_group.command(name="deckping")
    @commands.is_owner()
    async def test_deckping(ctx: commands.Context) -> None:
        """Owner-only. Preview the R3 deck-chase ping: one action line each, trailed by pings."""
        me = ctx.author.id
        view = ui.View(timeout=None)
        view.add_item(build_live_submit_deck_button())
        await ctx.send(
            build_deck_ping(([me, me], [me, me]), ([me], [me, me]), pod_page_url("Sample Pod 7")),
            allowed_mentions=discord.AllowedMentions(users=True),
            view=view,
        )


def _preview_launcher_slots(
    set_code: str, event_at: datetime, names: list[str], thread_id: str,
) -> list[LauncherSlot]:
    """Championship-day launcher slots for the preview: the Early lane overridden to the committed
    championship pointer, the Late lane a normal open weekend slot."""
    top_yes = names[: championship.SEAT_COUNT]
    afternoon = LauncherSlot(
        bucket_key="AFTERNOON", committed=True, status=STATUS_FIRED, count=len(top_yes),
        slot_time=event_at, names=top_yes, thread_id=thread_id, signal_id=None,
        set_code=set_code, championship=True,
    )
    evening = LauncherSlot(
        bucket_key=named_bucket_key("EVENING", set_code), committed=False, status=STATUS_OPEN, count=0,
        slot_time=event_at + timedelta(hours=6), names=[], thread_id=None, signal_id="preview",
        set_code=set_code,
    )
    return [afternoon, evening]


def _preview_rsvp_states(names: list[str]) -> dict[str, str]:
    """A few synthetic RSVPs so the staged waves show the already-answered treatment: the top names
    stand in as Yes, Maybe, and Can't, the rest still get a fresh ping."""
    states: dict[str, str] = {}
    for name, state in zip(names, (RSVP_YES, RSVP_MAYBE, RSVP_NO)):
        states[name] = state
    return states


async def _stage(destination, when: str) -> None:
    """A staging title marking when the next message would post in the live flow."""
    await destination.send(f"### ⏱ {when}", allowed_mentions=discord.AllowedMentions.none())


async def _thread_send(thread: discord.Thread, file, embed) -> None:
    await thread.send(embed=embed, file=file) if file else await thread.send(embed=embed)


async def _resolve_preview_thread(bot: commands.Bot, event_id: str) -> discord.Thread | None:
    thread_id = await asyncio.to_thread(event_thread_id_sync, event_id)
    if thread_id is None:
        return None
    thread = bot.get_channel(int(thread_id))
    if thread is None:
        try:
            thread = await bot.fetch_channel(int(thread_id))
        except discord.HTTPException:
            return None
    return thread if isinstance(thread, discord.Thread) else None


def _card_post_url(guild_id: int, card: tuple | None) -> str:
    if card is None:
        return ""
    _, channel_id, message_id, _ = card
    return f"https://discord.com/channels/{guild_id}/{channel_id}/{message_id}"


def _tiebreaker_preview_scenario():
    """An 8-player Swiss pod where the trophy-match loser (Cyrus) finishes 3rd on OGW% behind a 2-1
    peer, so the tiebreaker table renders. Fictional names over the match graph that produces the tie."""
    seats = {"Aria": 0, "Bex": 1, "Cyrus": 2, "Dot": 3, "Enzo": 4, "Fern": 5, "Gus": 6, "Hana": 7}
    players = [pod_swiss.Player(id=name, name=name, seat=seat) for name, seat in seats.items()]
    raw = [
        (1, "Aria", "Enzo", "Aria", "2-0"),
        (1, "Bex", "Fern", "Bex", "2-0"),
        (1, "Cyrus", "Gus", "Cyrus", "2-1"),
        (1, "Dot", "Hana", "Hana", "2-1"),
        (2, "Aria", "Bex", "Aria", "2-1"),
        (2, "Enzo", "Fern", "Fern", "2-1"),
        (2, "Hana", "Cyrus", "Cyrus", "2-0"),
        (2, "Dot", "Gus", "Dot", "2-0"),
        (3, "Aria", "Cyrus", "Aria", "2-1"),
        (3, "Bex", "Hana", "Bex", "2-1"),
        (3, "Fern", "Dot", "Dot", "2-1"),
        (3, "Enzo", "Gus", "Enzo", "2-1"),
    ]
    matches = [MatchOutcome(r, a, b, w, s) for r, a, b, w, s in raw]
    standings = pod_swiss.compute_standings(players, matches)
    match_states = [
        {"a_name": "Aria", "b_name": "Cyrus", "winner_name": "Aria", "a_record": "2-0", "b_record": "2-0"},
        {"a_name": "Bex", "b_name": "Hana", "winner_name": "Bex", "a_record": "1-1", "b_record": "1-1"},
        {"a_name": "Fern", "b_name": "Dot", "winner_name": "Dot", "a_record": "1-1", "b_record": "1-1"},
        {"a_name": "Enzo", "b_name": "Gus", "winner_name": "Enzo", "a_record": "0-2", "b_record": "0-2"},
    ]
    mark_trophy_match(match_states, TOTAL_ROUNDS)
    return standings, match_states


def _preview_players_sync(limit: int) -> list[tuple[str, float]]:
    with SessionLocal() as session:
        set_id = session.execute(
            select(MagicSet.id).where(MagicSet.code == active_set_code())
        ).scalar_one_or_none()
        if set_id is None:
            return []
        return [(p.display_name, p.score) for p in rank_players_for_set(session, set_id)[:limit]]
