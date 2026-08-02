"""Round-robin pairer for four-player pods. Pure functions only; the manager handles side effects.

Four players over the pod's three rounds is a complete round robin: everyone faces all three opponents,
so the pod is decided at the table instead of on tiebreakers. Six would need five rounds, which is a
different event, so every other roster size falls back to Swiss.

The schedule is fixed and results-independent. Round 1 pairs across the table, the same convention
pod_swiss uses for its first round, then rounds 2 and 3 complete the circle. No rematch is possible by
construction. Standings, records and pod points still come from the Swiss code — this module only
decides who plays whom.
"""
from __future__ import annotations

from bot.services.pod_swiss import Player


ROUND_ROBIN_POD_SIZE = 4

_SCHEDULE = (
    ((0, 2), (1, 3)),
    ((0, 1), (2, 3)),
    ((0, 3), (1, 2)),
)


def supports(roster_size: int) -> bool:
    """Only four players make a full round robin inside three rounds; other sizes fall back to Swiss."""
    return roster_size == ROUND_ROBIN_POD_SIZE


def pair_round(players: list[Player], round_num: int) -> list[tuple[str, str]]:
    """Return pairings for round_num as a list of (player_a_id, player_b_id).

    Players are ordered by draft seat, falling back to the given order for anyone unseated, so every
    round reads one stable order. Raises ValueError on a roster this pairer does not support or a round
    outside the schedule.
    """
    if not supports(len(players)):
        raise ValueError(f"round robin needs {ROUND_ROBIN_POD_SIZE} players, got {len(players)}")
    if not 1 <= round_num <= len(_SCHEDULE):
        raise ValueError(f"round robin has {len(_SCHEDULE)} rounds, got round {round_num}")
    ordered = _seat_order(players)
    return [(ordered[a].id, ordered[b].id) for a, b in _SCHEDULE[round_num - 1]]


def _seat_order(players: list[Player]) -> list[Player]:
    """Players by draft seat, keeping roster order among any that have no seat."""
    indexed = list(enumerate(players))
    indexed.sort(key=lambda pair: (pair[1].seat is None, pair[1].seat if pair[1].seat is not None else 0, pair[0]))
    return [player for _, player in indexed]
