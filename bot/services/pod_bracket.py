"""Record-based 'pod bracket' pairer — the fast-advance alternative to pod_swiss.

pod_swiss pairs a whole round at once, only after every match in the prior round is reported. The
bracket advances per match: the moment two players reach the same record they're paired into the
next round. For 8 players this is the classic draft bracket — winners play winners, losers play
losers, and the 2-0 Trophy Match starts as soon as both 2-0 players exist, without waiting for the
rest of the round.

Standings and tiebreakers still come from pod_swiss.compute_standings; this module only decides
pairings. Pure functions — the orchestration layer handles every side effect.
"""
from __future__ import annotations

from bot.services.pod_swiss import MatchOutcome, Player


BRACKET_POD_SIZE = 8


def supports(roster_size: int) -> bool:
    """The bracket is designed and tested for 8 players; other sizes should fall back to Swiss."""
    return roster_size == BRACKET_POD_SIZE


def incremental_pairings(
    players: list[Player],
    completed: list[MatchOutcome],
    existing_next: list[tuple[str, str]],
    target_round: int,
    *,
    source_round_complete: bool,
) -> list[tuple[str, str]]:
    """Return the *new* pairings to add to target_round given the completed earlier-round matches.

    A player is ready for target_round once they've finished exactly target_round-1 matches and
    aren't already paired into target_round. Ready players are grouped by record. A record group is
    held while (a) a still-playing player could still land in it and (b) two players who already met
    could both land in it — pairing early there risks stranding those two into a forced rematch once
    everyone else is spoken for. Groups with no such risk (every round-2 group, the 2-0 Trophy Match)
    pair the instant they can. A held group pairs once it's safe, via a rematch-free matching that only
    falls back to a rematch when source_round_complete and no rematch-free matching exists — so the
    bracket resolves without ever manufacturing an avoidable rematch. `completed` must be in
    chronological (report) order.
    """
    expected_prior = target_round - 1
    ids = {p.id for p in players}
    records = player_records(players, completed)
    wins = {pid: records[pid][0] for pid in ids}
    losses = {pid: records[pid][1] for pid in ids}
    last_index: dict[str, int] = {}
    for idx, m in enumerate(completed):
        if m.player_a_id not in ids or m.player_b_id not in ids:
            continue
        last_index[m.player_a_id] = idx
        last_index[m.player_b_id] = idx

    already = {pid for pair in existing_next for pid in pair}
    ready = [
        p.id for p in players
        if wins[p.id] + losses[p.id] == expected_prior and p.id not in already
    ]
    ready.sort(key=lambda pid: last_index.get(pid, -1))

    groups: dict[tuple[int, int], list[str]] = {}
    for pid in ready:
        groups.setdefault((wins[pid], losses[pid]), []).append(pid)

    played = {frozenset((m.player_a_id, m.player_b_id)) for m in completed}
    held = held_records(players, completed, target_round)

    new_pairings: list[tuple[str, str]] = []
    for record in sorted(groups, key=lambda r: (-r[0], r[1])):
        if record in held:
            continue
        new_pairings.extend(_pair_group(groups[record], played, force=source_round_complete))
    return new_pairings


def player_records(players: list[Player], completed: list[MatchOutcome]) -> dict[str, tuple[int, int]]:
    """(wins, losses) per player id. Outcomes naming a player outside the roster are ignored."""
    ids = {p.id for p in players}
    wins = {pid: 0 for pid in ids}
    losses = {pid: 0 for pid in ids}
    for m in completed:
        if m.player_a_id not in ids or m.player_b_id not in ids:
            continue
        wins[m.winner_id] += 1
        losses[m.loser_id] += 1
    return {pid: (wins[pid], losses[pid]) for pid in ids}


def contains_rematch(pairings: list[tuple[str, str]], completed: list[MatchOutcome]) -> bool:
    """Whether any of these pairings repeats a match the players already played."""
    played = {frozenset((m.player_a_id, m.player_b_id)) for m in completed}
    for a, b in pairings:
        if frozenset((a, b)) in played:
            return True
    return False


def held_records(
    players: list[Player], completed: list[MatchOutcome], target_round: int,
) -> set[tuple[int, int]]:
    """Record groups the bracket must hold rather than pair now: a still-playing player could still
    land in the group AND two players who already met could both land in it, so pairing now risks
    stranding them into a forced rematch. Shared by `incremental_pairings` (which skips a held group)
    and `padding_slots` (which shows it without naming a provisional opponent) so the preview and the
    lock can never disagree — the divergence that let a preview name a pairing the lock then moved."""
    expected_prior = target_round - 1
    ids = {p.id for p in players}
    records = player_records(players, completed)
    wins = {pid: records[pid][0] for pid in ids}
    losses = {pid: records[pid][1] for pid in ids}
    played = {frozenset((m.player_a_id, m.player_b_id)) for m in completed}
    still_playing = [pid for pid in ids if wins[pid] + losses[pid] < expected_prior]

    def can_reach(pid: str, record: tuple[int, int]) -> bool:
        need_w, need_l = record[0] - wins[pid], record[1] - losses[pid]
        return need_w >= 0 and need_l >= 0 and need_w + need_l == expected_prior - (wins[pid] + losses[pid])

    ready_records = {
        (wins[pid], losses[pid]) for pid in ids if wins[pid] + losses[pid] == expected_prior
    }
    held: set[tuple[int, int]] = set()
    for record in ready_records:
        may_grow = any(can_reach(pid, record) for pid in still_playing)
        rematch = any(
            can_reach(x, record) and can_reach(y, record)
            for x, y in (tuple(pair) for pair in played)
        )
        if may_grow and rematch:
            held.add(record)
    return held


ROUND_RECORD_BUCKETS: dict[int, tuple[tuple[tuple[int, int], int], ...]] = {
    2: (((1, 0), 2), ((0, 1), 2)),
    3: (((2, 0), 1), ((1, 1), 2), ((0, 2), 1)),
}


def padding_slots(
    players: list[Player],
    completed: list[MatchOutcome],
    real_records: list[tuple[int, int]],
    paired_names: list[str],
    round_num: int,
) -> list[tuple[tuple[int, int], str | None, str | None]]:
    """Waiting-match slots that fill a bracket round to its full fixed slate, so a round always
    renders the same number of dropdowns. For the 8-player bracket each round's same-record buckets
    are fixed (R2: two 1-0, two 0-1; R3: one 2-0, two 1-1, one 0-2).

    `real_records` is the start-of-round (wins, losses) of each real match already created;
    `paired_names` are the players already in one. A player who has finished the prior round but
    isn't paired yet is named into a slot (earliest-ready first) so a partly-known match reads
    'Alice vs 1-0'; slots with no known side stay anonymous. A record group the bracket is still
    holding (see `held_records`) stays fully anonymous even when players are waiting in it — naming a
    provisional opponent there is what let players start a match the lock later moved. Returns one
    (record, name_a, name_b) per missing match, best record first; name_* is None when unknown."""
    buckets = ROUND_RECORD_BUCKETS.get(round_num)
    if not buckets:
        return []
    ids = {p.id for p in players}
    wins = {pid: 0 for pid in ids}
    losses = {pid: 0 for pid in ids}
    last_index: dict[str, int] = {}
    for idx, m in enumerate(completed):
        if m.player_a_id not in ids or m.player_b_id not in ids:
            continue
        wins[m.winner_id] += 1
        losses[m.loser_id] += 1
        last_index[m.player_a_id] = idx
        last_index[m.player_b_id] = idx

    have: dict[tuple[int, int], int] = {}
    for rec in real_records:
        have[rec] = have.get(rec, 0) + 1
    paired = set(paired_names)
    expected_prior = round_num - 1
    waiting = sorted(
        (pid for pid in ids if wins[pid] + losses[pid] == expected_prior and pid not in paired),
        key=lambda pid: last_index.get(pid, -1),
    )
    queues: dict[tuple[int, int], list[str]] = {}
    for pid in waiting:
        queues.setdefault((wins[pid], losses[pid]), []).append(pid)

    held = held_records(players, completed, round_num)
    out: list[tuple[tuple[int, int], str | None, str | None]] = []
    for rec, expected in buckets:
        queue = queues.get(rec, [])
        for _ in range(max(expected - have.get(rec, 0), 0)):
            if rec in held:
                out.append((rec, None, None))
                continue
            a = queue.pop(0) if queue else None
            b = queue.pop(0) if queue else None
            out.append((rec, a, b))
    return out


def _pair_group(
    pool: list[str], played: set[frozenset[str]], *, force: bool,
) -> list[tuple[str, str]]:
    """Pair an earliest-first ordered same-record pool with a rematch-free matching. Backtracks so
    that whenever any rematch-free matching of the pool exists it is found — greedy first-fit could
    strand a later pair into a rematch that a different early choice would have avoided. An odd player
    out waits for the next arrival. Only when `force` and no rematch-free matching exists does it fall
    back to pairing the leftovers anyway, so the bracket can't stall on a genuinely unavoidable
    rematch."""
    matching = _rematch_free_matching(pool, played)
    if matching is not None:
        return matching
    if not force:
        return []
    return [(pool[i], pool[i + 1]) for i in range(0, len(pool) - 1, 2)]


def _rematch_free_matching(
    pool: list[str], played: set[frozenset[str]],
) -> list[tuple[str, str]] | None:
    """A perfect matching of pool reusing no prior pairing, or None if none exists (including an odd
    pool). Pairs the earliest-ready player first so pairing order stays stable."""
    if not pool:
        return []
    if len(pool) % 2 != 0:
        return None
    a = pool[0]
    for i in range(1, len(pool)):
        b = pool[i]
        if frozenset((a, b)) in played:
            continue
        rest = _rematch_free_matching(pool[1:i] + pool[i + 1:], played)
        if rest is not None:
            return [(a, b)] + rest
    return None
