"""What a table organizer would decide, as a function of the numbers a pod can be read off.

In the ten minutes before a pod somebody has to say what the table is going to play: read how many said
yes, count who is really in the Draftmancer lobby, notice the two who never showed, and put the choice in
front of the room. The bot has every one of those numbers, so this is the rule that turns them into the one
thing worth saying right now.

Nothing here posts anything or changes a pod. It answers what to offer, and `bot.tasks.pod_organizer` runs
it every minute and carries out the answer.

Two ways the pod learns that nobody else is coming, and they carry different timing. A roster that can only
ever make four is asked as soon as the lobby has anybody in it, since waiting cannot improve it. A roster
that could still make six or more waits for its start time to pass and for the room to sit still.
"""
from __future__ import annotations

from dataclasses import dataclass

from bot.services.pod_team_vote import TEAM_VOTE_POD_SIZE


PICK_2_TABLE = 4
MIN_LOBBY_TO_ASK = 2
SETTLED_MINUTES = 2
CALL_MISSING_LEAD_MIN = 5

NOTHING = "nothing"
CALL_MISSING = "call_missing"
OFFER_PICK_2_SIGNUPS = "offer_pick_2_signups"
OFFER_PICK_2_LOBBY = "offer_pick_2_lobby"
OFFER_TEAM_DRAFT = "offer_team_draft"


@dataclass(frozen=True)
class TableSnapshot:
    """One minute's reading of a pod.

    `ceiling` is everyone who could still walk in, so it counts maybes, and a lobby holding more than its
    roster counts the room. `settled_minutes` is how long the lobby count has held still."""

    in_draftmancer: int
    ceiling: int
    minutes_to_start: float
    settled_minutes: float
    pick_2_set: bool
    pick_2_offered: bool
    team_offered: bool
    missing_called: bool


def decide(snapshot: TableSnapshot) -> str:
    """The one thing worth saying to this table right now, or NOTHING.

    Five players get NOTHING on purpose: five is odd, so there is no shape to offer and no check worth
    starting. Eight and seven get NOTHING too, since the lobby-full prompt already asks the only question
    a full room has left."""
    if not snapshot.missing_called and 0 < snapshot.minutes_to_start <= CALL_MISSING_LEAD_MIN:
        return CALL_MISSING
    if _asks_pick_2(snapshot) and snapshot.ceiling == PICK_2_TABLE:
        if snapshot.in_draftmancer >= MIN_LOBBY_TO_ASK:
            return OFFER_PICK_2_SIGNUPS
    if snapshot.minutes_to_start > 0 or snapshot.settled_minutes < SETTLED_MINUTES:
        return NOTHING
    if snapshot.in_draftmancer == TEAM_VOTE_POD_SIZE and not snapshot.team_offered:
        return OFFER_TEAM_DRAFT
    if _asks_pick_2(snapshot) and snapshot.in_draftmancer == PICK_2_TABLE:
        return OFFER_PICK_2_LOBBY
    return NOTHING


def name_list(names: list[str]) -> str:
    if len(names) < 3:
        return " and ".join(names)
    return ", ".join(names[:-1]) + f" and {names[-1]}"


def _asks_pick_2(snapshot: TableSnapshot) -> bool:
    return snapshot.pick_2_set and not snapshot.pick_2_offered
