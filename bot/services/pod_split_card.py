"""The card a pod's second table is organized on: who sits where, Confirm and Leave, and each table's thread"""
from __future__ import annotations

import asyncio
import contextlib
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

import discord
from discord import ui

from bot.commands.messages import MSG_CONFIRM_BUTTON, MSG_CONFIRM_LOCK_IN
from bot.services.pod_confirm import Attendance, TablePlan, decline_players_sync
from bot.services.pod_drafts import load_event_set_code_sync
from bot.services.pod_link_dm import thread_link
from bot.services.pod_reminder_copy import STAGED_TABLES_ROW
from bot.services.pod_roster_fields import add_table_plan_fields
from bot.services.pod_signals import RSVP_EMOJI, RSVP_NO
from bot.services.pod_staging import confirm_seat_sync, pod_numeral
from bot.services.pod_table_seating import current_seating, seating_drawing
from bot.services.pod_tournament import is_pod_organizer

SPLIT_PREFIX = "podsplit"
CONFIRM = "confirm"
LEAVE = "leave"
MOVE = "move"

MSG_SPLIT_TITLE = "🪑 Organizing a second table"
MSG_SPLIT_STARTED_BY = "-# Started by {name}"
MSG_SPLIT_TABLE_LINK = "Table {index}"
MSG_SPLIT_UNKNOWN_STARTER = "an Organizer"
MSG_SPLIT_LEAVE = "Leave"
MSG_SPLIT_MOVE = "Finalize Tables"
MSG_SPLIT_MOVE_REFUSED = "Only Organizers and the player who opened Table 2 can finalize the tables"
MSG_SPLIT_FINALIZED = "🚀 Tables finalized by {name}"
MSG_SPLIT_NOBODY_MOVED = "Everyone in Table 1's lobby already sits at Table 1"
MSG_SPLIT_MOVED = "Removed from Table 1's lobby: {names}"

MoveHook = Callable[[str], Awaitable["MoveResult"]]
_MOVE_HOOK: MoveHook | None = None


def register_move_hook(hook: MoveHook) -> None:
    global _MOVE_HOOK
    _MOVE_HOOK = hook


def split_embed(attendance: Attendance, plan: TablePlan, set_code: str, started_by: str) -> discord.Embed:
    description = f"{MSG_SPLIT_STARTED_BY.format(name=started_by)}\n{MSG_CONFIRM_LOCK_IN}"
    embed = discord.Embed(title=MSG_SPLIT_TITLE, description=description, color=discord.Color.green())
    add_table_plan_fields(embed, attendance, plan, set_code=set_code)
    return embed


async def render_split_embed(event_id: str, guild: discord.Guild | None, starter_id: int) -> discord.Embed:
    set_code, current = await asyncio.gather(
        asyncio.to_thread(load_event_set_code_sync, event_id), current_seating(event_id),
    )
    attendance, plan = seating_drawing(current)
    starter = guild.get_member(starter_id) if guild is not None else None
    started_by = starter.display_name if starter is not None else MSG_SPLIT_UNKNOWN_STARTER
    return split_embed(attendance, plan, set_code or "", started_by)


def split_view(event_id: str, starter_id: int, table_urls: list[str]) -> ui.View:
    view = ui.View(timeout=None)
    for action in (CONFIRM, LEAVE, MOVE):
        view.add_item(SplitCardButton(action, event_id, starter_id))
    for index, url in enumerate(table_urls, start=1):
        view.add_item(ui.Button(label=MSG_SPLIT_TABLE_LINK.format(index=index), url=url, row=1))
    return view


_BUTTON_LOOKS = {
    CONFIRM: (MSG_CONFIRM_BUTTON, "✅", discord.ButtonStyle.success),
    LEAVE: (MSG_SPLIT_LEAVE, RSVP_EMOJI[RSVP_NO], discord.ButtonStyle.secondary),
    MOVE: (MSG_SPLIT_MOVE, "🚀", discord.ButtonStyle.primary),
}


class SplitCardButton(
    ui.DynamicItem[ui.Button],
    template=rf"{SPLIT_PREFIX}:(?P<action>{CONFIRM}|{LEAVE}|{MOVE}):(?P<event_id>[^:]+):(?P<starter_id>[0-9]+)",
):
    def __init__(self, action: str, event_id: str, starter_id: int) -> None:
        label, emoji, style = _BUTTON_LOOKS[action]
        super().__init__(ui.Button(
            label=label, emoji=emoji, style=style, custom_id=f"{SPLIT_PREFIX}:{action}:{event_id}:{starter_id}", row=0,
        ))
        self.action = action
        self.event_id = event_id
        self.starter_id = starter_id

    @classmethod
    async def from_custom_id(cls, interaction: discord.Interaction, item: ui.Button, match: re.Match):
        return cls(match["action"], match["event_id"], int(match["starter_id"]))

    async def callback(self, interaction: discord.Interaction) -> None:
        if self.action == MOVE:
            await self._move(interaction)
            return
        await interaction.response.defer()
        user = interaction.user
        await asyncio.to_thread(answer_split_sync, self.event_id, str(user.id), user.display_name, self.action)
        await self._rerender(interaction)

    async def _move(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True, thinking=True)
        allowed = interaction.user.id == self.starter_id or await is_pod_organizer(interaction.client, interaction.user)
        if not allowed:
            await interaction.followup.send(MSG_SPLIT_MOVE_REFUSED, ephemeral=True)
            return
        result = await _MOVE_HOOK(self.event_id) if _MOVE_HOOK is not None else MoveResult()
        await interaction.followup.send(move_reply(result), ephemeral=True)
        if result.error is None:
            with contextlib.suppress(discord.HTTPException):
                await interaction.channel.send(
                    embed=finalized_embed(interaction.user.display_name, result.tables),
                    allowed_mentions=discord.AllowedMentions.none(),
                )
        await self._rerender(interaction)

    async def _rerender(self, interaction: discord.Interaction) -> None:
        embed = await render_split_embed(self.event_id, interaction.guild, self.starter_id)
        with contextlib.suppress(discord.HTTPException):
            await interaction.message.edit(embed=embed)


@dataclass(frozen=True)
class FinalTable:
    index: int
    thread_name: str
    url: str
    players: list[str]


@dataclass(frozen=True)
class MoveResult:
    removed: list[str] = field(default_factory=list)
    tables: list[FinalTable] = field(default_factory=list)
    error: str | None = None


def finalized_embed(name: str, tables: list[FinalTable]) -> discord.Embed:
    """Who finalized, then each table as a link to its thread with its players under it"""
    lines = [MSG_SPLIT_FINALIZED.format(name=name)]
    for table in tables:
        link = f"{pod_numeral(table.index)} {thread_link(table.thread_name, table.url)}"
        lines.append(STAGED_TABLES_ROW.format(link=link))
        lines.append(", ".join(table.players))
    return discord.Embed(description="\n".join(lines), color=discord.Color.green())


def move_reply(result: MoveResult) -> str:
    if result.error:
        return f"⚠️ {result.error}"
    if not result.removed:
        return MSG_SPLIT_NOBODY_MOVED
    return MSG_SPLIT_MOVED.format(names=", ".join(f"**{name}**" for name in result.removed))


def answer_split_sync(event_id: str, discord_id: str, display_name: str, answer: str) -> None:
    """Confirm takes a seat at any point of a split, signing the player up first when they never did"""
    if answer == LEAVE:
        decline_players_sync(event_id, [discord_id])
        return
    confirm_seat_sync(event_id, discord_id, display_name)
