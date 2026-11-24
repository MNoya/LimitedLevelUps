"""Which seats leave when an organizer shrinks a live lobby below the players already in it"""
from __future__ import annotations

from dataclasses import dataclass

from bot.services.pod_staging import Signup


@dataclass(frozen=True)
class Seat:
    user_id: str
    arena_name: str
    discord_id: str | None


def seats_to_remove(seats: list[Seat], roster: list[Signup], keep: int) -> list[Seat]:
    """The seats past the first `keep` in keep order, the most removable first"""
    leaving = keep_order(seats, roster)[keep:]
    leaving.reverse()
    return leaving


def keep_order(seats: list[Seat], roster: list[Signup]) -> list[Seat]:
    """Keep order: the signup roster in seat order, then walk-ins, then unlinked seats, the last two by join order"""
    rank = {signup.discord_id: position for position, signup in enumerate(roster)}
    signed_up = [seat for seat in seats if seat.discord_id in rank]
    signed_up.sort(key=lambda seat: rank[seat.discord_id])
    walk_ins = [seat for seat in seats if seat.discord_id is not None and seat.discord_id not in rank]
    unlinked = [seat for seat in seats if seat.discord_id is None]
    return signed_up + walk_ins + unlinked
