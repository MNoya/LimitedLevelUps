"""Record-based 'pod bracket' pairer — the fast-advance alternative to pod_swiss.

pod_swiss pairs a whole round at once, only after every match in the prior round is reported. The
bracket advances per match: the moment two players reach the same record they're paired into the
next round — winners play winners, losers play losers, and the 2-0 Trophy Match starts as soon as
both 2-0 players exist, without waiting for the rest of the round.

A rematch is never produced. A pod that isn't a power of two carries odd record groups, so someone
has to play across groups, and pairing every group the instant it can fill would leave the last
source match's two players facing each other. Two rules prevent that: a group that a past opponent
could still fall into is held, and the unpaired pool is never taken below `unpaired_floor`. Playing
across groups is decided once the source round is settled and the whole remainder solves at once.

Standings and tiebreakers still come from pod_swiss.compute_standings; this module only decides
pairings. Pure functions — the orchestration layer handles every side effect.
"""
from __future__ import annotations

from bot.services.pod_swiss import BYE_NAME, MatchOutcome, Player


BRACKET_POD_SIZES = (8, 10)
PADDED_ROUNDS = (2, 3)


def supports(roster_size: int) -> bool:
    """Table sizes the bracket pairs; any other size falls back to Swiss."""
    return roster_size in BRACKET_POD_SIZES


def unpaired_floor(expected_prior: int) -> int:
    """Smallest unpaired pool that is still guaranteed to hold a rematch-free pairing.

    Every player entering the round has met `expected_prior` opponents, so in a pool of
    2*expected_prior+2 each one can still be paired with at least half of it, which is enough for a
    pairing of the whole pool to exist. Below that the pool can shrink onto two players who already
    met — at 10 that is exactly the last source match's winner and loser.
    """
    return 2 * expected_prior + 2


def incremental_pairings(
    players: list[Player],
    completed: list[MatchOutcome],
    existing_next: list[tuple[str, str]],
    target_round: int,
    *,
    source_round_complete: bool,
) -> list[tuple[str, str]]:
    """Return the *new* pairings to add to target_round given the completed earlier-round matches.

    While players are still finishing the source round only same-record pairs are made, and only from
    groups that are neither held (see `held_records`) nor would take the unpaired pool below
    `unpaired_floor`. Once nobody is left to arrive the whole remainder is paired at once, playing
    players across record groups as little as it takes and never into a rematch. A rematch is paired
    only when the source round is settled and no rematch-free pairing of the remainder exists at all,
    so a pod can't stall. `completed` must be in chronological (report) order.
    """
    expected_prior = target_round - 1
    records = player_records(players, completed)
    already = {pid for pair in existing_next for pid in pair}
    ordered = [pid for pid in _report_order(players, completed) if pid not in already]

    ready = [pid for pid in ordered if sum(records[pid]) == expected_prior]
    unready = [pid for pid in ordered if sum(records[pid]) < expected_prior]
    played = {frozenset((m.player_a_id, m.player_b_id)) for m in completed}

    if source_round_complete or not unready:
        return _pair_remainder(ready, records, played, force=source_round_complete)

    held = held_records(players, completed, target_round)
    return _same_record_pairs(ready, len(ready) + len(unready), records, played, held, expected_prior)


def player_records(players: list[Player], completed: list[MatchOutcome]) -> dict[str, tuple[int, int]]:
    """(wins, losses) per player id. Outcomes naming a player outside the roster are ignored.

    A forfeited bye counts a loss against the player who dropped, unlike the record that ends up on
    their profile: pairing is the one place the loss has to land, since it is what sinks them through
    the record groups so each later bye falls to a lower-standing opponent.
    """
    ids = {p.id for p in players}
    wins = {pid: 0 for pid in ids}
    losses = {pid: 0 for pid in ids}
    for m in completed:
        if m.is_bye:
            if m.winner_id in ids:
                wins[m.winner_id] += 1
            if m.loser_id in ids:
                losses[m.loser_id] += 1
            continue
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


def projected_slate(
    players: list[Player], completed: list[MatchOutcome], target_round: int,
) -> list[tuple[tuple[int, int], tuple[int, int]]] | None:
    """The (record_a, record_b) of every match the round will hold, best record first, or None when
    the shape still depends on a result.

    Each record group a still-playing player sits in splits evenly into one rank up and one rank down,
    which settles the whole shape as long as every such group is even. An odd one does not: at 10 the
    round-2 player who plays across groups sends the round-3 shape one way by winning and another by
    losing, so round 3 has no slate to preview until that match reports.
    """
    counts = _projected_counts(players, completed, target_round)
    if counts is None:
        return None
    slate: list[tuple[tuple[int, int], tuple[int, int]]] = []
    carried: tuple[int, int] | None = None
    for record in sorted(counts, key=lambda r: (-r[0], r[1])):
        remaining = counts[record]
        if carried is not None:
            slate.append((carried, record))
            remaining -= 1
            carried = None
        while remaining >= 2:
            slate.append((record, record))
            remaining -= 2
        if remaining:
            carried = record
    return None if carried is not None else slate


def padding_slots(
    players: list[Player],
    completed: list[MatchOutcome],
    real_pairs: list[tuple[tuple[int, int], tuple[int, int]]],
    paired_names: list[str],
    round_num: int,
) -> list[tuple[tuple[int, int] | None, tuple[int, int] | None, str | None, str | None]]:
    """Waiting-match slots that fill a bracket round to its full slate, so a round always renders one
    dropdown per match it will hold.

    `real_pairs` is the start-of-round (record_a, record_b) of each real match already created;
    `paired_names` are the players already in one. A player who has finished the prior round but isn't
    paired yet is named into a slot (earliest-ready first) only where their record leaves one slot to
    land in, so the preview can never name a pairing the lock then moves. Returns one
    (record_a, record_b, name_a, name_b) per missing match, best record first; a record is None when
    `projected_slate` can't yet say, a name is None when no player is known for that side.
    """
    if round_num not in PADDED_ROUNDS:
        return []
    missing = len(players) // 2 - len(real_pairs)
    if missing <= 0:
        return []
    slate = projected_slate(players, completed, round_num)
    remaining = _unfilled_slots(slate, real_pairs) if slate is not None else None
    if remaining is None or len(remaining) != missing:
        return [(None, None, None, None)] * missing

    queues = _waiting_by_record(players, completed, paired_names, round_num)
    slots_per_record: dict[tuple[int, int], int] = {}
    for record_a, record_b in remaining:
        for record in {record_a, record_b}:
            slots_per_record[record] = slots_per_record.get(record, 0) + 1

    out: list[tuple[tuple[int, int] | None, tuple[int, int] | None, str | None, str | None]] = []
    for record_a, record_b in remaining:
        name_a = _take_waiting(queues, slots_per_record, record_a)
        name_b = _take_waiting(queues, slots_per_record, record_b)
        out.append((record_a, record_b, name_a, name_b))
    return out


def _report_order(players: list[Player], completed: list[MatchOutcome]) -> list[str]:
    """Player ids ordered by when their latest result landed, so the bracket pairs whoever has been
    waiting longest first."""
    ids = {p.id for p in players}
    last_index: dict[str, int] = {}
    for idx, m in enumerate(completed):
        if m.player_a_id not in ids or m.player_b_id not in ids:
            continue
        last_index[m.player_a_id] = idx
        last_index[m.player_b_id] = idx
    return sorted((p.id for p in players), key=lambda pid: last_index.get(pid, -1))


def _same_record_pairs(
    ready: list[str],
    pool_size: int,
    records: dict[str, tuple[int, int]],
    played: set[frozenset[str]],
    held: set[tuple[int, int]],
    expected_prior: int,
) -> list[tuple[str, str]]:
    """Pairs that are safe to make while players are still finishing the source round. Never pairs
    across record groups — until a group is settled there's no telling whether anyone needs to."""
    floor = unpaired_floor(expected_prior)
    groups: dict[tuple[int, int], list[str]] = {}
    for pid in ready:
        groups.setdefault(records[pid], []).append(pid)

    pairs: list[tuple[str, str]] = []
    for record in sorted(groups, key=lambda r: (-r[0], r[1])):
        if record in held:
            continue
        queue = groups[record]
        while len(queue) >= 2 and pool_size - 2 >= floor:
            pair = _earliest_rematch_free_pair(queue, played)
            if pair is None:
                break
            pairs.append(pair)
            queue.remove(pair[0])
            queue.remove(pair[1])
            pool_size -= 2
    return pairs


def _earliest_rematch_free_pair(
    queue: list[str], played: set[frozenset[str]],
) -> tuple[str, str] | None:
    for i, a in enumerate(queue):
        for b in queue[i + 1:]:
            if frozenset((a, b)) not in played:
                return (a, b)
    return None


def _pair_remainder(
    pool: list[str],
    records: dict[str, tuple[int, int]],
    played: set[frozenset[str]],
    *,
    force: bool,
) -> list[tuple[str, str]]:
    """Pair everyone still waiting, now that nobody else can arrive. An odd pool sends its worst record
    to a bye. Falls back to a pairing that does repeat a match only when `force` and no rematch-free
    one exists, so a pod can't stall on it."""
    ordered = sorted(pool, key=lambda pid: (-records[pid][0], records[pid][1]))
    if len(ordered) % 2 == 1:
        floated = ordered.pop()
        return _pair_remainder(ordered, records, played, force=force) + [(floated, BYE_NAME)]
    best = _best_matching(ordered, records, played)
    if best is not None:
        return best[1]
    if not force:
        return []
    return [(ordered[i], ordered[i + 1]) for i in range(0, len(ordered) - 1, 2)]


def _best_matching(
    queue: list[str], records: dict[str, tuple[int, int]], played: set[frozenset[str]],
) -> tuple[int, list[tuple[str, str]]] | None:
    """(cost, pairing) for the rematch-free pairing of the whole queue that puts the fewest players
    against a different record, or None when no rematch-free pairing exists. Cost sums each pair's win
    gap, so an all-same-record pairing costs 0. Backtracks, since a greedy first choice can strand a
    later pair into a rematch a different one would have avoided. queue is sorted best record first."""
    if not queue:
        return (0, [])
    if len(queue) % 2 != 0:
        return None
    a = queue[0]
    best: tuple[int, list[tuple[str, str]]] | None = None
    for i in range(1, len(queue)):
        b = queue[i]
        if frozenset((a, b)) in played:
            continue
        rest = _best_matching(queue[1:i] + queue[i + 1:], records, played)
        if rest is None:
            continue
        cost = abs(records[a][0] - records[b][0]) + rest[0]
        if best is None or cost < best[0]:
            best = (cost, [(a, b)] + rest[1])
            if cost == 0:
                break
    return best


def _projected_counts(
    players: list[Player], completed: list[MatchOutcome], target_round: int,
) -> dict[tuple[int, int], int] | None:
    expected_prior = target_round - 1
    records = player_records(players, completed)
    counts: dict[tuple[int, int], int] = {}
    still_playing: dict[tuple[int, int], int] = {}
    for player in players:
        record = records[player.id]
        played_count = sum(record)
        if played_count == expected_prior:
            counts[record] = counts.get(record, 0) + 1
        elif played_count == expected_prior - 1:
            still_playing[record] = still_playing.get(record, 0) + 1
        else:
            return None

    for record, size in still_playing.items():
        if size % 2:
            return None
        wins, losses = record
        counts[(wins + 1, losses)] = counts.get((wins + 1, losses), 0) + size // 2
        counts[(wins, losses + 1)] = counts.get((wins, losses + 1), 0) + size // 2
    return counts


def _unfilled_slots(
    slate: list[tuple[tuple[int, int], tuple[int, int]]],
    real_pairs: list[tuple[tuple[int, int], tuple[int, int]]],
) -> list[tuple[tuple[int, int], tuple[int, int]]] | None:
    """The slate minus the matches already created, or None when a created match isn't in the slate —
    a projection that disagrees with the board is one the preview must not draw from."""
    remaining = list(slate)
    for pair in real_pairs:
        for idx, slot in enumerate(remaining):
            if set(slot) == set(pair):
                remaining.pop(idx)
                break
        else:
            return None
    return remaining


def _waiting_by_record(
    players: list[Player], completed: list[MatchOutcome], paired_names: list[str], round_num: int,
) -> dict[tuple[int, int], list[str]]:
    """Players who finished the prior round but have no match yet, earliest-ready first, by record."""
    records = player_records(players, completed)
    paired = set(paired_names)
    queues: dict[tuple[int, int], list[str]] = {}
    for pid in _report_order(players, completed):
        if pid in paired or sum(records[pid]) != round_num - 1:
            continue
        queues.setdefault(records[pid], []).append(pid)
    return queues


def _take_waiting(
    queues: dict[tuple[int, int], list[str]],
    slots_per_record: dict[tuple[int, int], int],
    record: tuple[int, int],
) -> str | None:
    """The next player waiting at this record, but only when the record has a single slot left to land
    in. With more than one, which slot they end up in is still open and naming them would be a guess."""
    if slots_per_record.get(record, 0) != 1:
        return None
    queue = queues.get(record) or []
    return queue.pop(0) if queue else None
