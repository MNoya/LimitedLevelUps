from __future__ import annotations

from datetime import date
from typing import Literal, get_args

import discord
from discord.ext import commands

from bot.commands import token_messages as tmsg
from bot.commands.messages import MSG_JOINED_LEADERBOARD, MSG_TOKEN_INVALIDATED
from bot.commands.signup import MSG_TIMEOUT as MSG_JOIN_TIMEOUT
from bot.commands.signup import MSG_WELCOME_BACK, send_signup_instructions
from bot.commands.test_group import fake_arena_id, random_hall_of_famers, test_group
from bot.listeners.auto_link_listener import MSG_ALREADY_LINKED, updated_message
from bot.services.active_set import active_set_code
from bot.services.dm_flows import send_token_instructions
from bot.services.pod_link_dm import build_link_dm, thread_link
from bot.services.pod_tournament import (
    BYE_NAME,
    BYE_SCORE,
    SKIPPED_SENTINEL,
    RoundResultsView,
    build_live_deck_color_select_view,
    build_pairing_dm_embed,
    build_submit_deck_dm_embed,
)
from bot.services.token_link_flow import INSTRUCTIONS as LINK_17LANDS_INSTRUCTIONS
from bot.services.token_link_flow import MSG_TIMEOUT as MSG_LINK_TIMEOUT

DmGroup = Literal["pods", "account"]
DM_GROUPS = get_args(DmGroup)


async def setup(bot: commands.Bot) -> None:
    @test_group.command(name="dms")
    @commands.is_owner()
    async def test_dms(ctx: commands.Context, group: DmGroup | None = None, to: discord.User | None = None) -> None:
        target = to or ctx.author
        try:
            await send_test_dms(target.send, ctx.message.jump_url, group or "")
        except discord.Forbidden:
            if to is None:
                await ctx.send("⚠️ Couldn't DM you, open DMs from server members and try again")
            else:
                await ctx.send(f"⚠️ Couldn't DM {to.mention}, they have DMs from server members closed")
            return
        await ctx.message.add_reaction("📬")


async def send_test_dms(send, link_url: str, group: str = "") -> None:
    """Every DM players get, in the order a pod night sends them, for reviewing copy and push notifications"""
    if group in ("", "pods"):
        await _send_pod_dms(send, link_url)
    if group in ("", "account"):
        await _send_account_dms(send)


async def _send_pod_dms(send, link_url: str) -> None:
    code = active_set_code()
    pod_slot = f"{code} {date.today():%b} {date.today().day} Late Pod"
    pod_name = f"{pod_slot} 1"
    viewer, opponent, new_opponent = random_hall_of_famers(3)
    viewer_arena = fake_arena_id(viewer)
    first_pairing = (opponent, fake_arena_id(opponent))
    new_pairing = (new_opponent, fake_arena_id(new_opponent))
    session_id = f"{code}-TestOpen"
    thread_ref = thread_link(pod_name, link_url, decorated=True)
    lobby_variants = [
        {"thread_ref": thread_ref, "arena_name": viewer_arena, "rsvp": "yes"},
        {"thread_ref": thread_ref, "arena_name": None, "rsvp": "maybe"},
        {"thread_ref": thread_ref, "arena_name": viewer_arena, "rsvp": "yes", "playing": 14, "pods": 2,
         "pod_ref": thread_link(pod_name, link_url), "other_pods": [thread_link(f"{pod_slot} 2", link_url)]},
        {"thread_ref": thread_link(f"👑 {code} Set Championship", link_url, decorated=True),
         "arena_name": viewer_arena, "rsvp": "yes"},
    ]
    for variant in lobby_variants:
        body, view = build_link_dm(session_id=session_id, **variant)
        await send(body, view=view)

    first_match = _match_state(viewer, opponent)
    first_embed = _pairing_embed(pod_name, link_url, first_pairing, first_match)
    await send(embed=first_embed, view=RoundResultsView([first_match]))
    await send(embed=_pairing_embed(pod_name, link_url, new_pairing, None, updated=True))
    match = _match_state(viewer, new_opponent)
    reported_states = [
        {**match, "winner_name": viewer, "score": "2-1"},
        {**match, "winner_name": new_opponent, "score": "2-0"},
        {**match, "winner_name": SKIPPED_SENTINEL, "score": "0-0"},
        {**match, "b_name": BYE_NAME, "b_display": BYE_NAME, "winner_name": viewer, "score": BYE_SCORE},
        {**match, "winner_name": new_opponent, "score": BYE_SCORE},
    ]
    for state in reported_states:
        await send(embed=_pairing_embed(pod_name, link_url, new_pairing, state), view=RoundResultsView([state]))

    await send(embed=build_submit_deck_dm_embed(None), view=build_live_deck_color_select_view(None))
    await send(embed=build_submit_deck_dm_embed("WU"), view=build_live_deck_color_select_view("WU"))


def _match_state(viewer: str, opponent: str) -> dict:
    return {
        "match_id": "dmaudit-1", "a_name": viewer, "b_name": opponent,
        "a_display": viewer, "b_display": opponent, "winner_name": None, "score": None,
    }


def _pairing_embed(
    pod_name: str, pairings_url: str, pairing: tuple[str, str], match_state: dict | None, updated: bool = False,
) -> discord.Embed:
    opponent, opponent_arena = pairing
    return build_pairing_dm_embed(
        round_num=2, opponent_name=opponent, opponent_arena=opponent_arena,
        pairings_url=pairings_url, event_name=pod_name, updated=updated,
        match_state=match_state, viewer_is_a=True if match_state else None,
    )


async def _send_account_dms(send) -> None:
    await send_signup_instructions(send)
    await send_token_instructions(send, LINK_17LANDS_INSTRUCTIONS)
    for message in (
        tmsg.CHECKING,
        tmsg.FETCHING_EVENTS,
        tmsg.INVALID_FORMAT,
        tmsg.REJECTED,
        tmsg.TOKEN_IN_USE,
        MSG_JOIN_TIMEOUT,
        MSG_LINK_TIMEOUT,
        MSG_JOINED_LEADERBOARD,
        MSG_WELCOME_BACK,
        MSG_ALREADY_LINKED,
        updated_message(True),
        updated_message(False),
        MSG_TOKEN_INVALIDATED,
    ):
        await send(message)
