"""Who sits at which table while a pod runs two Draftmancer rooms, read fresh from the rooms and the roster"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Protocol

from bot.services.pod_active import ACTIVE_POD_MANAGERS
from bot.services.pod_confirm import Attendance, Table, TablePlan, attendance_for_event_sync, seating_plan
from bot.services.pod_draft_manager import set_event_max_players, trim_event_table
from bot.services.pod_staging import Signup, confirmed_first_roster_sync
from bot.services.pod_table_trim import Seat


class Room(Protocol):
    """One table's room, which is a Draftmancer lobby live and a stand-in list in the `!test split` sandbox"""

    def is_open(self) -> bool: ...

    async def seats(self) -> list[Seat]: ...

    async def trim(self, n: int, leaving: list[Seat]) -> str | None: ...

    async def cap(self, n: int) -> str | None: ...


class DraftmancerRoom:
    def __init__(self, event_id: str) -> None:
        self.event_id = event_id

    def is_open(self) -> bool:
        manager = ACTIVE_POD_MANAGERS.get(self.event_id)
        return manager is not None and not manager.drafting and not manager.draft_complete

    async def seats(self) -> list[Seat]:
        manager = ACTIVE_POD_MANAGERS.get(self.event_id)
        return await manager.room_seats() if manager is not None else []

    async def trim(self, n: int, leaving: list[Seat]) -> str | None:
        return await trim_event_table(self.event_id, n, leaving)

    async def cap(self, n: int) -> str | None:
        return await set_event_max_players(self.event_id, n)


TABLE_ROOMS: dict[str, list[Room]] = {}


@dataclass(frozen=True)
class TableSeating:
    tables: list[list[str]]
    waiting: list[str]


@dataclass(frozen=True)
class CurrentSeating:
    seating: TableSeating
    plan: TablePlan
    roster: list[Signup]
    attendance: Attendance
    room_seats: list[list[Seat]]


async def current_seating(event_id: str) -> CurrentSeating:
    """The seating of a pod's tables right now, from its roster and the rooms its tables have open"""
    attendance, roster = await asyncio.gather(
        asyncio.to_thread(attendance_for_event_sync, event_id),
        asyncio.to_thread(confirmed_first_roster_sync, event_id),
    )
    plan = seating_plan(attendance)
    rooms = TABLE_ROOMS.get(event_id) or [DraftmancerRoom(event_id)]
    room_seats = list(await asyncio.gather(*(room.seats() for room in rooms)))
    present = [[seat.discord_id for seat in seats if seat.discord_id] for seats in room_seats]
    present += [[] for _ in range(len(plan.tables) - len(present))]
    return CurrentSeating(seat_tables(roster, present, plan), plan, roster, attendance, room_seats)


def seat_tables(roster: list[Signup], rooms: list[list[str]], plan: TablePlan) -> TableSeating:
    """A player in a room keeps it, table 1's room past the plan's first table moves on, and the rest fill open seats"""
    sizes = [table.seated for table in plan.tables[:len(rooms)]]
    sizes += [0] * (len(rooms) - len(sizes))
    confirmed = [signup.discord_id for signup in roster if signup.confirmed]
    tables: list[list[str]] = [[] for _ in rooms]
    placed: set[str] = set()
    overflow: list[str] = []
    for index, room in enumerate(rooms):
        present = [discord_id for discord_id in confirmed if discord_id in room and discord_id not in placed]
        placed.update(present)
        if index == 0:
            tables[0] = present[:sizes[0]]
            overflow = present[sizes[0]:]
        else:
            tables[index] = present
    absent = [discord_id for discord_id in confirmed if discord_id not in placed]
    waiting: list[str] = []
    for discord_id in overflow:
        _take_open_seat(tables, sizes, waiting, discord_id, first_table=1)
    for discord_id in absent:
        _take_open_seat(tables, sizes, waiting, discord_id, first_table=0)
    return TableSeating(tables, waiting)


def seating_drawing(current: CurrentSeating) -> tuple[Attendance, TablePlan]:
    """The attendance and plan that draw this seating on the card, with players no table holds waiting after it"""
    names = {signup.discord_id: signup.display_name for signup in current.roster}
    seating = current.seating
    plan_tables = list(current.plan.tables)
    tables = []
    for index, seated in enumerate(seating.tables):
        capacity = plan_tables[index].capacity if index < len(plan_tables) else 0
        if seated or capacity:
            tables.append(Table(seated=len(seated), capacity=max(capacity, len(seated))))
    seated_names = [names[discord_id] for seated in seating.tables for discord_id in seated]
    waiting_names = [names[discord_id] for discord_id in seating.waiting]
    attendance = current.attendance
    drawn = Attendance(
        confirmed=tuple(seated_names + waiting_names), yes=attendance.yes, maybe=attendance.maybe,
        declined=attendance.declined, new_drafters=attendance.new_drafters, pinned=attendance.pinned,
    )
    return drawn, TablePlan(tuple(tables), waiting=len(waiting_names))


def _take_open_seat(
    tables: list[list[str]], sizes: list[int], waiting: list[str], discord_id: str, first_table: int,
) -> None:
    for index in range(first_table, len(tables)):
        if len(tables[index]) < sizes[index]:
            tables[index].append(discord_id)
            return
    waiting.append(discord_id)
