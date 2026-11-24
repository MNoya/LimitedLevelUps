"""`/pod-table` on a live lobby: open Table 2 and keep the card showing who sits where in step with both rooms"""
from __future__ import annotations

import asyncio
import contextlib
import logging
from dataclasses import dataclass, field

import discord
from discord.ext import commands

from bot import audit
from bot.commands.pod_rsvp import add_members_to_thread
from bot.discord_helpers import RenderQueue
from bot.services import pod_launch
from bot.services.pod_active import ACTIVE_POD_MANAGERS, set_room_arrivals_hook
from bot.services.pod_drafts import load_event_id_by_thread_sync
from bot.services.pod_split_card import FinalTable, MoveResult, register_move_hook, render_split_embed, split_view
from bot.services.pod_staging import Signup, confirm_seat_sync
from bot.services.pod_table_seating import TABLE_ROOMS, DraftmancerRoom, current_seating
from bot.services.pod_table_trim import Seat, seats_to_remove

log = logging.getLogger(__name__)

MSG_NOT_OPEN = "Table 1's lobby is closed or already drafting"
MSG_NOTHING_TO_MOVE = "Everyone fits at Table 1"

CARD_RENDERS = RenderQueue(delay_s=2.0)


@dataclass
class SecondTable:
    source_event_id: str
    starter_id: int
    threads: list[discord.Thread]
    table_event_ids: list[str]
    card: discord.Message | None
    confirmed: set[str] = field(default_factory=set)
    rooms_seen: dict[str, frozenset[str]] = field(default_factory=dict)


SECOND_TABLES: dict[str, SecondTable] = {}


async def opens_second_table(source_event_id: str) -> bool:
    """Whether `/pod-table` should split this pod: a signup pod whose lobby is live and whose draft has not started"""
    manager = ACTIVE_POD_MANAGERS.get(source_event_id)
    live = (manager is not None and manager.sio.connected and not manager.drafting and not manager.draft_complete)
    if not live or source_event_id in SECOND_TABLES:
        return False
    return await asyncio.to_thread(pod_launch.scheduled_card_ref_sync, source_event_id) is not None


async def open_second_table(
    source_event_id: str, source_thread: discord.Thread, table_two: discord.Thread, starter: discord.abc.User,
) -> None:
    """Count table 1's room as confirmed and post the card in its thread once Table 2 exists"""
    seats = await ACTIVE_POD_MANAGERS[source_event_id].room_seats()
    table_two_event_id = await asyncio.to_thread(load_event_id_by_thread_sync, str(table_two.id)) or ""
    second = SecondTable(source_event_id, starter.id, [source_thread, table_two], [source_event_id, table_two_event_id],
                         card=None)
    await _confirm_players(second, source_thread.guild, [(seat.discord_id, seat.arena_name) for seat in seats])
    TABLE_ROOMS[source_event_id] = [DraftmancerRoom(source_event_id), DraftmancerRoom(table_two_event_id)]
    second.card = await source_thread.send(
        embed=await render_split_embed(source_event_id, source_thread.guild, starter.id),
        view=split_view(source_event_id, starter.id, [source_thread.jump_url, table_two.jump_url]),
    )
    track_second_table(second)
    audit.event("pod_second_table", source_event_id=source_event_id, table_event_id=table_two_event_id,
                user_id=str(starter.id))
    log.info(f"second-table: opened {table_two.name} off {source_event_id} seated={len(seats)}")


def track_second_table(second: SecondTable) -> None:
    SECOND_TABLES[second.source_event_id] = second


async def move_players(event_id: str) -> MoveResult:
    """Make the rooms match the card: table 1 keeps its seats, everyone else leaves its room, every room is capped"""
    rooms = TABLE_ROOMS.get(event_id)
    if not rooms or not rooms[0].is_open():
        return MoveResult(error=MSG_NOT_OPEN)
    current = await current_seating(event_id)
    if len(current.plan.tables) < 2:
        return MoveResult(error=MSG_NOTHING_TO_MOVE)
    table_one = current.plan.tables[0]
    leaving = table_one_leavers(current.room_seats[0], current.roster, current.seating.tables[0], table_one.seated)
    error = await rooms[0].trim(table_one.capacity, leaving)
    if error:
        return MoveResult(error=error)
    second = SECOND_TABLES.get(event_id)
    for index in range(1, min(len(rooms), len(current.plan.tables))):
        await rooms[index].cap(current.plan.tables[index].capacity)
        if second is not None:
            seated = current.seating.tables[index]
            await add_members_to_thread(second.threads[index], [(discord_id, "") for discord_id in seated])
    log.info(f"second-table: moved {event_id} removed={[seat.arena_name for seat in leaving]}")
    names = {signup.discord_id: signup.display_name for signup in current.roster}
    return MoveResult(
        removed=[names.get(seat.discord_id, seat.arena_name) for seat in leaving],
        tables=_final_tables(second, current.seating.tables, names) if second is not None else [],
    )


def table_one_leavers(seats: list[Seat], roster: list[Signup], keeping: list[str], size: int) -> list[Seat]:
    """Everyone in table 1's room the card seats elsewhere, then whoever is still past its size in removal order"""
    kept = set(keeping)
    moving = [seat for seat in seats if seat.discord_id is not None and seat.discord_id not in kept]
    staying = [seat for seat in seats if seat not in moving]
    return moving + seats_to_remove(staying, roster, keep=size)


def live_split(event_id: str) -> SecondTable | None:
    """The pod's second-table split while table 1's lobby is still open, forgetting one whose draft has moved on"""
    second = SECOND_TABLES.get(event_id)
    rooms = TABLE_ROOMS.get(event_id)
    if second is None:
        return None
    if not rooms or not rooms[0].is_open():
        SECOND_TABLES.pop(event_id, None)
        TABLE_ROOMS.pop(event_id, None)
        return None
    return second


def refresh_split_card(second: SecondTable) -> None:
    CARD_RENDERS.request(second.source_event_id, lambda: _refresh_card(second))


async def on_room_arrivals(table_event_id: str, discord_ids: list[str]) -> None:
    """Count a linked player who sits down in either room as confirmed, and redraw the card when a room changed"""
    for second in list(SECOND_TABLES.values()):
        if table_event_id not in second.table_event_ids or live_split(second.source_event_id) is None:
            continue
        room = frozenset(discord_ids)
        if second.rooms_seen.get(table_event_id) == room:
            return
        second.rooms_seen[table_event_id] = room
        await _confirm_players(second, second.card.guild, [(discord_id, None) for discord_id in discord_ids])
        refresh_split_card(second)
        return


def _final_tables(second: SecondTable, seating: list[list[str]], names: dict[str, str]) -> list[FinalTable]:
    tables = []
    for index, (thread, seated) in enumerate(zip(second.threads, seating), start=1):
        players = [names[discord_id] for discord_id in seated if discord_id in names]
        tables.append(FinalTable(index, thread.name, thread.jump_url, players))
    return tables


async def _confirm_players(
    second: SecondTable, guild: discord.Guild | None, players: list[tuple[str | None, str | None]],
) -> None:
    """Sign up and confirm linked players in a room once each, named as the server shows them"""
    fresh = []
    for discord_id, fallback_name in players:
        if discord_id is None or discord_id in second.confirmed:
            continue
        member = guild.get_member(int(discord_id)) if guild is not None else None
        name = member.display_name if member is not None else fallback_name
        if name is None:
            continue
        second.confirmed.add(discord_id)
        fresh.append((discord_id, name))
    if fresh:
        await asyncio.to_thread(_confirm_seats_sync, second.source_event_id, fresh)


def _confirm_seats_sync(event_id: str, players: list[tuple[str, str]]) -> None:
    for discord_id, name in players:
        confirm_seat_sync(event_id, discord_id, name)


async def _refresh_card(second: SecondTable) -> None:
    embed = await render_split_embed(second.source_event_id, second.card.guild, second.starter_id)
    with contextlib.suppress(discord.HTTPException):
        await second.card.edit(embed=embed)


async def setup(bot: commands.Bot) -> None:
    register_move_hook(move_players)
    set_room_arrivals_hook(on_room_arrivals)
