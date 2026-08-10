"""Swiss-tournament pairer + standings for pod drafts. Pure functions only; the manager handles side effects.

Inputs: roster of Player records + chronological list of MatchOutcome records.
Outputs: pairings as `[(player_a_id, player_b_id), ...]` and Standings sorted by wins → OMW% → GW% → OGW% → name.
Round 1 pairs across the table (seat i vs i+half). Rounds 2+ pair by seat *distance* within each record
group — a seeded proximity bracket where the top seed faces the player half the group away (furthest), never
the neighbour, keeping top seeds apart until the final. Pairing down to the next group when a group is odd,
always rematch-free.
Tiebreakers follow MTR §1.6: per-opponent terms in OMW%/OGW% are floored at 1/3.
"""
from __future__ import annotations

import random
from dataclasses import dataclass


_MIN_PCT = 1.0 / 3.0  # MTR floor for OMW% / OGW% per-opponent terms
@dataclass(frozen=True)
class Player:
    id: str    # stable per-tournament identifier (we use draftmancer_name)
    name: str  # display name
    seat: int | None = None  # draft-table seat index (0-based); drives round-1 pairing


@dataclass(frozen=True)
class MatchOutcome:
    round_num: int
    player_a_id: str
    player_b_id: str
    winner_id: str
    score: str  # "2-0" or "2-1"

    @property
    def loser_id(self) -> str:
        return self.player_b_id if self.winner_id == self.player_a_id else self.player_a_id

    def games_for(self, player_id: str) -> tuple[int, int]:
        """Returns (games_won, games_lost) for player_id; score is always 'winner_games-loser_games'."""
        parts = self.score.split("-", 1)
        winner_games, loser_games = int(parts[0]), int(parts[1])
        if player_id == self.winner_id:
            return winner_games, loser_games
        return loser_games, winner_games


@dataclass(frozen=True)
class Standing:
    rank: int
    player_id: str
    player_name: str
    wins: int
    losses: int
    omw_pct: float
    gw_pct: float
    ogw_pct: float


def pair_round(
    players: list[Player],
    prior_matches: list[MatchOutcome],
    round_num: int,
    *,
    rng: random.Random | None = None,
    final_round: bool = False,
) -> list[tuple[str, str]]:
    """Return pairings for round_num as a list of (player_a_id, player_b_id).

    Round 1 pairs by seat distance — seat N faces seat N+half, so each player meets whoever sat
    furthest from them at the table. When seats are unknown it falls back to a random shuffle.
    Later rounds pair within each record group, pairing down across groups only when forced and never
    re-pairing two players who have already met. Proximity (top seed vs the player half the group away,
    furthest from the neighbour) breaks ties between equal pairings — except in the final round, where
    standings decide everything and a neighbour rematch from the seating no longer matters.
    Raises ValueError if no rematch-free pairing exists.
    """
    if len(players) < 2:
        return []
    if round_num == 1:
        if all(p.seat is not None for p in players):
            ordered = sorted(players, key=lambda p: p.seat)
            half = len(ordered) // 2
            return [(ordered[i].id, ordered[i + half].id) for i in range(half)]
        roster = list(players)
        (rng or random).shuffle(roster)
        return [(roster[i].id, roster[i + 1].id) for i in range(0, len(roster), 2)]

    wins: dict[str, int] = {p.id: 0 for p in players}
    for m in prior_matches:
        if m.winner_id in wins:
            wins[m.winner_id] += 1
    ordered = sorted(players, key=lambda p: (-wins[p.id], _seat_key(p)))
    played: set[frozenset[str]] = {frozenset((m.player_a_id, m.player_b_id)) for m in prior_matches}

    result = _pair_proximity(ordered, wins, played, final_round)
    if result is None:
        raise ValueError(f"no valid pairing for round {round_num}")
    return result


def _pair_proximity(
    queue: list[Player], wins: dict[str, int], played: set[frozenset[str]], final_round: bool,
) -> list[tuple[str, str]] | None:
    """Pair within each record group, pairing down to the next group only as a last resort and never
    re-pairing two players who have already met. queue stays sorted by record then seat across the
    recursion."""
    best = _best_pairing(queue, wins, played, final_round)
    return best[1] if best is not None else None


def _best_pairing(
    queue: list[Player], wins: dict[str, int], played: set[frozenset[str]], final_round: bool,
) -> tuple[int, list[tuple[str, str]]] | None:
    """Return (float_cost, pairing) for the rematch-free pairing that floats the fewest players across
    record groups, tie-broken by seat proximity. float_cost sums each pair's win-count gap, so a
    within-group pair costs 0; minimizing it keeps a record group intact rather than pairing two of its
    members down just because a proximal choice stranded a rivalry. None when no rematch-free pairing
    exists. queue is sorted by record then seat, so each call re-derives the leading record group. In
    the final round proximity is dropped — the group is paired in standings order, neighbours and all."""
    if not queue:
        return (0, [])
    if len(queue) % 2 != 0:
        return None
    a = queue[0]
    group_size = 1
    while group_size < len(queue) and wins[queue[group_size].id] == wins[a.id]:
        group_size += 1
    if final_round:
        same_record = list(range(1, group_size))
    else:
        half = group_size // 2
        same_record = sorted(range(1, group_size), key=lambda i: (abs(i - half), -i))
    pair_down = list(range(group_size, len(queue)))
    best: tuple[int, list[tuple[str, str]]] | None = None
    for i in same_record + pair_down:
        b = queue[i]
        if frozenset((a.id, b.id)) in played:
            continue
        sub = _best_pairing(queue[1:i] + queue[i + 1:], wins, played, final_round)
        if sub is None:
            continue
        cost = (wins[a.id] - wins[b.id]) + sub[0]
        if best is None or cost < best[0]:
            best = (cost, [(a.id, b.id)] + sub[1])
            if cost == 0:
                break
    return best


def compute_standings(
    players: list[Player],
    matches: list[MatchOutcome],
) -> list[Standing]:
    """Returns standings sorted by wins → OMW% → GW% → OGW% → name."""
    by_id = {p.id: p for p in players}
    wins = {p.id: 0 for p in players}
    losses = {p.id: 0 for p in players}
    games_won = {p.id: 0 for p in players}
    games_lost = {p.id: 0 for p in players}
    opponents: dict[str, list[str]] = {p.id: [] for p in players}

    for m in matches:
        a, b = m.player_a_id, m.player_b_id
        if a not in by_id or b not in by_id:
            continue
        if m.winner_id == a:
            wins[a] += 1
            losses[b] += 1
        elif m.winner_id == b:
            wins[b] += 1
            losses[a] += 1
        else:
            continue
        a_won, a_lost = m.games_for(a)
        b_won, b_lost = m.games_for(b)
        games_won[a] += a_won
        games_lost[a] += a_lost
        games_won[b] += b_won
        games_lost[b] += b_lost
        opponents[a].append(b)
        opponents[b].append(a)

    mw_pct: dict[str, float] = {}
    for pid in by_id:
        total = wins[pid] + losses[pid]
        mw_pct[pid] = max(_MIN_PCT, wins[pid] / total) if total > 0 else 0.0
    gw_pct: dict[str, float] = {}
    for pid in by_id:
        total_games = games_won[pid] + games_lost[pid]
        gw_pct[pid] = max(_MIN_PCT, games_won[pid] / total_games) if total_games > 0 else 0.0
    omw: dict[str, float] = {}
    ogw: dict[str, float] = {}
    for pid in by_id:
        opps = opponents[pid]
        omw[pid] = sum(mw_pct[o] for o in opps) / len(opps) if opps else 0.0
        ogw[pid] = sum(gw_pct[o] for o in opps) / len(opps) if opps else 0.0

    def rank_key(p: Player) -> tuple:
        return (-wins[p.id], -omw[p.id], -gw_pct[p.id], -ogw[p.id], p.name.lower())

    ranked = sorted(players, key=rank_key)
    return [
        Standing(
            rank=i + 1,
            player_id=p.id,
            player_name=p.name,
            wins=wins[p.id],
            losses=losses[p.id],
            omw_pct=omw[p.id],
            gw_pct=gw_pct[p.id],
            ogw_pct=ogw[p.id],
        )
        for i, p in enumerate(ranked)
    ]


_UNSEEDED = 1_000_000  # players without a known draft seat sort after every seated player


def _seat_key(p: Player) -> int:
    return p.seat if p.seat is not None else _UNSEEDED
