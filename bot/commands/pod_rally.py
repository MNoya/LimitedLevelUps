"""`!pod` — put the pod in front of whoever is reading, in whatever form the channel needs.

Inside a pod thread, a mock's included, it moves the lobby card back to the bottom, for a lobby that chat has
buried. Anywhere else it posts one line for the pod most worth filling: how many seats are missing, how many
players are already sitting in Draftmancer, and where to join. A set or cube code anywhere in the message
asks for that format instead. Open to everyone and nothing is pinged. The message is left up, since anything
a player writes after `!pod` is their own words and the answer posts under it either way.
"""
from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import Sequence
from dataclasses import dataclass

import discord
from discord.ext import commands

from bot import audit, emojis
from bot.config import settings
from bot.services import pod_launch, pod_rally
from bot.services.pod_schedule import build_underfill_fired_message
from bot.services.pod_active import active_manager_for_channel
from bot.services.pod_draft_manager import set_rally_fired_hook
from bot.services.pod_join_button import build_join_view
from bot.services.pod_reminder_copy import RALLY_NO_POD, RALLY_NO_POD_NO_LAUNCHER

log = logging.getLogger(__name__)

MSG_POD_ALREADY_FULL = "That pod already has a full table"

NOTICE_LIFETIME_S = 15


@dataclass
class PostedRally:
    event_id: str | None
    name: str
    message: discord.Message


_LAST_RALLY: dict[int, PostedRally] = {}


async def setup(bot: commands.Bot) -> None:
    set_rally_fired_hook(finish_rally_on_start)

    @bot.command(name="pod")
    async def pod_cmd(ctx: commands.Context, *, note: str = "") -> None:
        """Bump the lobby card in a pod thread, or rally for the live pod anywhere else. A set or cube code
        anywhere in the message rallies for that format, and a caller who named one wants the rally even
        inside a pod thread."""
        set_codes = pod_rally.set_keywords(note)
        channel_id = ctx.channel.id if ctx.channel else None
        manager = active_manager_for_channel(channel_id)
        if not set_codes and manager is not None and await _answer_from_pod_channel(ctx, manager):
            return
        await _rally(ctx, set_codes)


async def _answer_from_pod_channel(ctx: commands.Context, manager) -> bool:
    """Whether the pod bound to this channel answered on its own. A pod with no card up has nothing to move,
    so it says nothing and lets the rally answer instead: a lobby that is drafting, finished, or left over
    from a test still leaves someone asking a real question about the pods that are live now.

    A choice the pod is being asked about follows the lobby card down, so a table reading the bottom of the
    thread finds the lobby and the question about it together.

    A mock's thread card bumps like any other. Its channel card is what `!mock` moves, and moving both off
    one command would put a card in front of two audiences the caller can only see one of."""
    if not await manager.bump_lobby_card():
        return False
    await manager.bump_offer_card()
    audit.event("pod_card_bump", user_id=str(ctx.author.id), event_id=manager.event_id)
    log.info(f"pod: {ctx.author} bumped the lobby card for event {manager.event_id}")
    return True


async def _rally(ctx: commands.Context, set_codes: Sequence[str] = ()) -> None:
    guild = _guild(ctx)
    guild_id = str(guild.id) if guild is not None else ""
    target = await pod_rally.resolve_target(guild_id, set_codes)
    if target is not None and pod_rally.lobby_is_full(target):
        await ctx.send(MSG_POD_ALREADY_FULL, delete_after=NOTICE_LIFETIME_S)
        return
    await _retire_previous_rally(ctx.channel)
    if target is None:
        await ctx.send(await _no_pod_message(guild_id), suppress_embeds=True)
        return
    posted = await ctx.send(
        pod_rally.build_rally_line(target), view=_join_view(target), suppress_embeds=True,
        allowed_mentions=discord.AllowedMentions.none(),
    )
    _LAST_RALLY[ctx.channel.id] = PostedRally(target.event_id, target.name, posted)
    audit.event("pod_rally", user_id=str(ctx.author.id), channel_id=str(ctx.channel.id), kind=target.kind)
    log.info(f"pod: {ctx.author} rallied {target.kind} pod '{target.name}' in channel {ctx.channel.id}")


def _join_view(target: pod_rally.RallyTarget) -> discord.ui.View | None:
    """The personalized join button, which only an open lobby has a session for."""
    if target.kind == pod_rally.KIND_LOBBY and target.session_id:
        return build_join_view(target.session_id)
    return None


async def finish_rally_on_start(bot, event_id: str, player_count: int, thread_url: str) -> None:
    """Rewrite every standing rally for this pod into the fired record once its draft starts. A rally is a
    static post in whichever channel someone called it from, so left alone it would keep asking for players
    for a pod that is already drafting. Editing it in place keeps the caller's own `!pod` message answered
    instead of deleting the reply and leaving the question hanging with no context above it."""
    for channel_id, rally in list(_LAST_RALLY.items()):
        if rally.event_id != event_id:
            continue
        del _LAST_RALLY[channel_id]
        record = build_underfill_fired_message(rally.name, player_count, thread_url)
        try:
            await rally.message.edit(content=record, view=None, suppress=True,
                                     allowed_mentions=discord.AllowedMentions.none())
        except discord.HTTPException:
            log.warning(f"could not rewrite the rally for event {event_id} at draft start", exc_info=True)


async def _retire_previous_rally(channel) -> None:
    """Drop this channel's earlier rally before the next one posts, so the channel never holds two of them
    reading different numbers. A rally is worth nothing above the conversation, so it is reposted at the
    bottom instead of edited in place. Tracked in memory: a restart at worst leaves one stale rally up."""
    previous = _LAST_RALLY.pop(channel.id, None)
    if previous is None:
        return
    with contextlib.suppress(discord.HTTPException):
        await previous.message.delete()


async def _no_pod_message(guild_id: str) -> str:
    board = await asyncio.to_thread(pod_launch.live_launcher_board_sync)
    hello = emojis.prefix("chordoHello")
    if board is None or not guild_id:
        return RALLY_NO_POD_NO_LAUNCHER.format(hello=hello)
    _, channel_id, message_id, _ = board
    return RALLY_NO_POD.format(
        hello=hello, manat=emojis.get("manat"),
        launcher_url=pod_rally.message_url(guild_id, channel_id, message_id),
    )


def _guild(ctx: commands.Context) -> discord.Guild | None:
    """The invoking guild, or the configured one when the command is being run from a DM."""
    if ctx.guild is not None:
        return ctx.guild
    return ctx.bot.get_guild(settings.discord_guild_id) if settings.discord_guild_id else None
