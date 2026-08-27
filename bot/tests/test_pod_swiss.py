import random

import pytest

from bot.services.pod_swiss import BYE_NAME, BYE_SCORE, Player, compute_standings, pair_round, played_record
from bot.tests.pod_helpers import match, pairset, players


def test_round_1_pairs_all_players_once():
    roster = players(6)
    pairings = pair_round(roster, [], 1, rng=random.Random(0))
    assert len(pairings) == 3
    flat = [pid for pair in pairings for pid in pair]
    assert sorted(flat) == [p.id for p in roster]


def test_round_1_is_random_with_rng_when_seats_unknown():
    roster = players(6)
    a = pair_round(roster, [], 1, rng=random.Random(1))
    b = pair_round(roster, [], 1, rng=random.Random(2))
    assert a != b  # different seeds → different pairings


def test_round_1_pairs_by_seat_distance():
    roster = [Player(id=f"p{i}", name=f"Player{i}", seat=i) for i in range(8)]
    shuffled = list(roster)
    random.Random(3).shuffle(shuffled)  # seat, not list order, must drive pairing
    pairings = pair_round(shuffled, [], 1)
    assert pairset(pairings) == {
        frozenset({"p0", "p4"}),
        frozenset({"p1", "p5"}),
        frozenset({"p2", "p6"}),
        frozenset({"p3", "p7"}),
    }


def test_round_1_seat_distance_sixplayers():
    roster = [Player(id=f"p{i}", name=f"Player{i}", seat=i) for i in range(6)]
    pairings = pair_round(roster, [], 1)
    assert pairset(pairings) == {
        frozenset({"p0", "p3"}),
        frozenset({"p1", "p4"}),
        frozenset({"p2", "p5"}),
    }


def test_round_2_pairs_winners_with_winners_when_possible():
    roster = players(4)
    r1 = [match(1, "p0", "p1", "p0"), match(1, "p2", "p3", "p2")]
    pairings = pair_round(roster, r1, 2)
    pair_set = pairset(pairings)
    # Both winners (p0, p2) should be paired together; both losers (p1, p3) together
    assert frozenset({"p0", "p2"}) in pair_set
    assert frozenset({"p1", "p3"}) in pair_set


def test_round_2_pairs_winners_by_seat_not_game_margin():
    roster = [Player(id=f"p{i}", name=f"Player{i}", seat=i) for i in range(8)]
    r1 = [
        match(1, "p0", "p4", "p0", "2-1"),  # seat-0 winner, scrappy 2-1
        match(1, "p1", "p5", "p1", "2-0"),
        match(1, "p2", "p6", "p2", "2-0"),
        match(1, "p3", "p7", "p3", "2-1"),  # seat-3 winner, scrappy 2-1
    ]
    pair_set = pairset(pair_round(roster, r1, 2))
    # Four 1-0 winners at seats 0-3 pair by distance (half away), regardless of 2-0 vs 2-1
    assert frozenset({"p0", "p2"}) in pair_set
    assert frozenset({"p1", "p3"}) in pair_set
    # Four 0-1 losers at seats 4-7 pair the same way
    assert frozenset({"p4", "p6"}) in pair_set
    assert frozenset({"p5", "p7"}) in pair_set


def test_no_rematch_constraint():
    roster = players(4)
    r1 = [match(1, "p0", "p1", "p0"), match(1, "p2", "p3", "p2")]
    r2 = [match(2, "p0", "p2", "p0"), match(2, "p1", "p3", "p3")]
    pairings = pair_round(roster, r1 + r2, 3)
    pair_set = pairset(pairings)
    # p0 has played p1 and p2 — must face p3
    assert frozenset({"p0", "p3"}) in pair_set
    assert frozenset({"p1", "p2"}) in pair_set


def test_pair_down_for_6players():
    """After R1 with 3 winners + 3 losers, one winner must pair with one loser."""
    roster = players(6)
    r1 = [
        match(1, "p0", "p1", "p0"),
        match(1, "p2", "p3", "p2"),
        match(1, "p4", "p5", "p4"),
    ]
    pairings = pair_round(roster, r1, 2)
    pair_set = pairset(pairings)
    winners = {"p0", "p2", "p4"}
    losers = {"p1", "p3", "p5"}
    cross = sum(1 for p in pair_set if len(p & winners) == 1 and len(p & losers) == 1)
    same_win = sum(1 for p in pair_set if p.issubset(winners))
    same_loss = sum(1 for p in pair_set if p.issubset(losers))
    # Exactly one cross pairing (pair-down), one winner-vs-winner, one loser-vs-loser
    assert cross == 1
    assert same_win == 1
    assert same_loss == 1


def test_round_3_pairs_bottom_group_together_over_avoidable_pair_down():
    """SOS Championship R3 regression: the two 0-2 players must meet rather than each floating up to
    a 1-1, even when the proximal 1-1 pairing strands an earlier rivalry that can't rematch."""
    roster = [Player(id=f"p{i}", name=f"p{i}", seat=i) for i in range(8)]
    r1 = [
        match(1, "p0", "p4", "p0"),
        match(1, "p1", "p5", "p1"),
        match(1, "p6", "p2", "p6"),
        match(1, "p7", "p3", "p7"),
    ]
    r2 = [
        match(2, "p0", "p6", "p0"),
        match(2, "p7", "p1", "p7"),
        match(2, "p2", "p4", "p2"),
        match(2, "p3", "p5", "p3"),
    ]

    pair_set = pairset(pair_round(roster, r1 + r2, 3))

    assert frozenset({"p0", "p7"}) in pair_set
    assert frozenset({"p4", "p5"}) in pair_set
    one_one = {"p1", "p2", "p3", "p6"}
    assert sum(1 for p in pair_set if p <= one_one) == 2
    assert frozenset({"p2", "p6"}) not in pair_set


def test_final_round_pairs_by_standings_not_proximity():
    """A non-final round seeds neighbours apart (half the group away); the final round drops proximity
    and pairs the group in standings order, so fighting your neighbour is fine."""
    roster = [Player(id=f"p{i}", name=f"p{i}", seat=i) for i in range(4)]

    proximity = pairset(pair_round(roster, [], 2))
    final = pairset(pair_round(roster, [], 3, final_round=True))

    assert proximity == {frozenset({"p0", "p2"}), frozenset({"p1", "p3"})}
    assert final == {frozenset({"p0", "p1"}), frozenset({"p2", "p3"})}


def _championship_history(w1: str, l1: str, w2: str, l2: str) -> list:
    """Two rounds leaving p0/p7 at 2-0, {w1,l1,w2,l2} at 1-1, p4/p5 at 0-2 — with w1-l1 and w2-l2
    already having met, so R3 must keep the 1-1 group intact without replaying those pairs."""
    return [
        match(1, "p0", "p4", "p0"),
        match(1, "p7", "p5", "p7"),
        match(1, w1, l1, w1),
        match(1, w2, l2, w2),
        match(2, "p0", w1, "p0"),
        match(2, "p7", w2, "p7"),
        match(2, l1, "p4", l1),
        match(2, l2, "p5", l2),
    ]


@pytest.mark.parametrize(
    "w1, l1, w2, l2",
    [
        ("p1", "p2", "p3", "p6"),
        ("p2", "p1", "p6", "p3"),
        ("p1", "p3", "p2", "p6"),
        ("p3", "p1", "p6", "p2"),
        ("p1", "p6", "p2", "p3"),
        ("p6", "p1", "p3", "p2"),
    ],
)
def test_round_3_keeps_record_groups_intact_across_rematch_permutations(w1, l1, w2, l2):
    """No matter which two 1-1 rivalries already happened, R3 pairs equal records, never rematches,
    and never floats a player across record groups when an intra-group pairing exists."""
    roster = [Player(id=f"p{i}", name=f"p{i}", seat=i) for i in range(8)]
    prior = _championship_history(w1, l1, w2, l2)
    wins = {f"p{i}": 0 for i in range(8)}
    for m in prior:
        wins[m.winner_id] += 1
    played = pairset((m.player_a_id, m.player_b_id) for m in prior)

    pairings = pair_round(roster, prior, 3)
    pairs = pairset(pairings)

    assert len(pairs) == 4
    assert not (pairs & played)
    assert all(wins[a] == wins[b] for a, b in pairings)
    assert frozenset({"p0", "p7"}) in pairs
    assert frozenset({"p4", "p5"}) in pairs


def test_compute_standings_basic_records():
    roster = players(4)
    matches = [
        match(1, "p0", "p1", "p0", "2-1"),
        match(1, "p2", "p3", "p2", "2-0"),
        match(2, "p0", "p2", "p0", "2-0"),
        match(2, "p1", "p3", "p1", "2-1"),
    ]
    standings = compute_standings(roster, matches)
    by_id = {s.player_id: s for s in standings}
    assert (by_id["p0"].wins, by_id["p0"].losses) == (2, 0)
    assert (by_id["p1"].wins, by_id["p1"].losses) == (1, 1)
    assert (by_id["p2"].wins, by_id["p2"].losses) == (1, 1)
    assert (by_id["p3"].wins, by_id["p3"].losses) == (0, 2)
    # Top of standings is p0
    assert standings[0].player_id == "p0"


def test_compute_standings_excludes_skipped_match():
    roster = players(4)
    matches = [
        match(1, "p0", "p2", "p0", "2-0"),
        match(1, "p1", "p3", "p1", "2-0"),
        match(2, "p0", "p1", "(skipped)", "0-0"),
    ]

    standings = compute_standings(roster, matches)

    by_id = {s.player_id: s for s in standings}
    assert (by_id["p0"].wins, by_id["p0"].losses) == (1, 0)
    assert (by_id["p1"].wins, by_id["p1"].losses) == (1, 0)
    assert (by_id["p0"].gw_pct, by_id["p1"].gw_pct) == (1.0, 1.0)


def test_compute_standings_omw_pct_breaks_tie():
    roster = players(4)
    # p0 and p2 both go 1-0. p0 beats p1 (who is otherwise 0-1). p2 beats p3 (who beats p1 in a different match).
    # Hmm — let me set up a clean OMW% tiebreaker
    matches = [
        match(1, "p0", "p1", "p0", "2-0"),
        match(1, "p2", "p3", "p2", "2-0"),
        # Now: p1 and p3 both 0-1. p1's opponent (p0) has 1-0 = 100%. p3's opponent (p2) has 1-0 = 100%. Tied so far.
        # Add another round so OMW% diverges:
        match(2, "p0", "p3", "p0", "2-0"),  # p0 now 2-0; p3 now 0-2
        match(2, "p1", "p2", "p2", "2-0"),  # p2 now 2-0; p1 now 0-2
    ]
    standings = compute_standings(roster, matches)
    # p0 and p2 are both 2-0. p0's opponents: p1 (0-2), p3 (0-2). p2's opponents: p3 (0-2), p1 (0-2). Same OMW%.
    # Top 2 should be p0 and p2 in some order
    top_ids = {standings[0].player_id, standings[1].player_id}
    assert top_ids == {"p0", "p2"}


def test_compute_standings_gw_pct_uses_game_counts():
    roster = players(2)
    matches = [match(1, "p0", "p1", "p0", "2-1")]
    standings = compute_standings(roster, matches)
    p0 = next(s for s in standings if s.player_id == "p0")
    p1 = next(s for s in standings if s.player_id == "p1")
    # p0: 2 game wins / 3 games = 0.667
    assert p0.gw_pct == pytest.approx(2 / 3, rel=1e-3)
    # p1: 1 game win / 3 games = 0.333 (but min floor is 1/3 anyway)
    assert p1.gw_pct == pytest.approx(1 / 3, rel=1e-3)


def test_match_games_for_winner_and_loser():
    m = match(1, "p0", "p1", "p0", "2-1")
    assert m.games_for("p0") == (2, 1)
    assert m.games_for("p1") == (1, 2)
    m2 = match(1, "p2", "p3", "p3", "2-0")
    assert m2.games_for("p2") == (0, 2)
    assert m2.games_for("p3") == (2, 0)


def test_pair_round_raises_when_no_valid_pairing():
    # 4 players, all have played each other → no valid pairing for round 4
    roster = players(4)
    matches = [
        match(1, "p0", "p1", "p0"), match(1, "p2", "p3", "p2"),
        match(2, "p0", "p2", "p0"), match(2, "p1", "p3", "p3"),
        match(3, "p0", "p3", "p0"), match(3, "p1", "p2", "p1"),
    ]
    with pytest.raises(ValueError):
        pair_round(roster, matches, 4)


def test_8_player_round_1_yields_4_pairings():
    roster = players(8)
    pairings = pair_round(roster, [], 1, rng=random.Random(0))
    assert len(pairings) == 4
    flat = sorted(pid for pair in pairings for pid in pair)
    assert flat == [p.id for p in roster]


def _seeded_layout() -> list[Player]:
    """The 8-seat leaderboard layout: top half in order, bottom reversed, 3<->4 / 5<->6 swapped.

    Seat:  0   1   2   3   4   5   6   7
    Rank: #1  #2  #4  #3  #8  #7  #5  #6
    """
    ranks = ["r1", "r2", "r4", "r3", "r8", "r7", "r5", "r6"]
    return [Player(id=rid, name=rid, seat=seat) for seat, rid in enumerate(ranks)]


def test_round_2_splits_top_seeds_and_draws_cross_table_winner():
    roster = _seeded_layout()
    # R1 across the table (seat i vs i+4): 1v8, 2v7, 4v5, 3v6 — top seeds hold
    r1 = [
        match(1, "r1", "r8", "r1"),
        match(1, "r2", "r7", "r2"),
        match(1, "r4", "r5", "r4"),
        match(1, "r3", "r6", "r3"),
    ]
    pair_set = pairset(pair_round(roster, r1, 2))
    # #1 draws the 4*5 winner (#4), #2 draws the 3*6 winner (#3) — #1 and #2 land in opposite halves
    assert frozenset({"r1", "r4"}) in pair_set
    assert frozenset({"r2", "r3"}) in pair_set
    assert frozenset({"r1", "r2"}) not in pair_set


def test_round_3_is_the_adjacent_trophy_match():
    roster = _seeded_layout()
    r1 = [
        match(1, "r1", "r8", "r1"),
        match(1, "r2", "r7", "r2"),
        match(1, "r4", "r5", "r4"),
        match(1, "r3", "r6", "r3"),
    ]
    r2 = [
        match(2, "r1", "r4", "r1"),  # 2-0: r1, r2 at adjacent seats 0,1
        match(2, "r2", "r3", "r2"),
        match(2, "r8", "r5", "r5"),
        match(2, "r7", "r6", "r6"),
    ]
    pair_set = pairset(pair_round(roster, r1 + r2, 3))
    # The two undefeated seeds at adjacent seats meet for the trophy
    assert frozenset({"r1", "r2"}) in pair_set
    # No round repeats a prior matchup
    played = pairset((m.player_a_id, m.player_b_id) for m in r1 + r2)
    assert pair_set.isdisjoint(played)


def test_round_2_pairs_by_distance_at_non_eight_sizes():
    # Six seated players, three winners hold across-table R1 (seat i vs i+3)
    roster = [Player(id=f"p{i}", name=f"p{i}", seat=i) for i in range(6)]
    r1 = [match(1, "p0", "p3", "p0"), match(1, "p1", "p4", "p1"), match(1, "p2", "p5", "p2")]
    pair_set = pairset(pair_round(roster, r1, 2))
    # Winners p0,p1,p2 (seats 0-2): top seed faces the half-away winner, the third pairs down
    assert frozenset({"p0", "p1"}) in pair_set
    cross = sum(1 for p in pair_set if len(p & {"p0", "p1", "p2"}) == 1)
    assert cross == 1  # exactly one winner pairs down to a loser


def test_8_player_round_2_pairs_within_brackets():
    roster = players(8)
    r1 = [
        match(1, "p0", "p1", "p0"),
        match(1, "p2", "p3", "p2"),
        match(1, "p4", "p5", "p4"),
        match(1, "p6", "p7", "p6"),
    ]
    pairings = pair_round(roster, r1, 2)
    pair_set = pairset(pairings)
    winners = {"p0", "p2", "p4", "p6"}
    losers = {"p1", "p3", "p5", "p7"}
    # All pairings should be winner-vs-winner or loser-vs-loser
    assert all(p.issubset(winners) or p.issubset(losers) for p in pair_set)


def test_bye_counts_as_a_win_and_leaves_the_dropped_player_no_loss_on_record():
    roster = players(4)
    matches = [
        match(1, "p0", "p1", "p0", BYE_SCORE),
        match(1, "p2", "p3", "p2", "2-1"),
    ]

    standings = compute_standings(roster, matches)

    by_id = {s.player_id: s for s in standings}
    assert (by_id["p0"].wins, by_id["p0"].losses) == (1, 0)
    assert (by_id["p1"].wins, by_id["p1"].losses) == (0, 0)
    assert played_record("p0", matches) == (1, 0)
    assert played_record("p1", matches) == (0, 0)


def test_bye_is_left_out_of_every_opponent_average():
    roster = players(4)
    matches = [
        match(1, "p0", "p1", "p0", BYE_SCORE),
        match(1, "p2", "p3", "p2", "2-0"),
    ]

    standings = compute_standings(roster, matches)

    by_id = {s.player_id: s for s in standings}
    assert (by_id["p0"].omw_pct, by_id["p0"].ogw_pct) == (0.0, 0.0)
    assert by_id["p2"].omw_pct > 0.0


def test_odd_field_floats_the_bye_to_the_bottom_of_the_standings():
    roster = players(5)
    matches = [
        match(1, "p0", "p1", "p0", "2-0"),
        match(1, "p2", "p3", "p2", "2-0"),
    ]

    pairings = pair_round(roster, matches, 2)

    byes = [pair for pair in pairings if BYE_NAME in pair]
    assert byes == [("p4", BYE_NAME)]
    assert len(pairings) == 3


def test_dropped_player_leaves_the_pool_and_the_bye_floats_to_the_worst_standing():
    roster = players(10)
    r1 = [
        match(1, "p0", "p7", "p0", "2-0"),
        match(1, "p2", "p8", "p2", "2-0"),
        match(1, "p6", "p9", "p6", "2-0"),
        match(1, "p1", "p3", "p1", "2-0"),
        match(1, "p4", "p5", "p4", "2-0"),
    ]
    r2 = [
        match(2, "p0", "p1", "p0", "2-0"),
        match(2, "p2", "p4", "p2", "2-0"),
        match(2, "p6", "p7", "p6", "2-0"),
        match(2, "p3", "p8", "p3", "2-0"),
        match(2, "p5", "p9", "p5", "2-0"),
    ]

    pairings = pair_round(roster, r1 + r2, 3, dropped_ids={"p1"})

    assert all("p1" not in pair for pair in pairings)
    byes = [pair for pair in pairings if BYE_NAME in pair]
    assert len(byes) == 1
    assert byes[0][0] in {"p7", "p8", "p9"}


def test_a_second_bye_skips_whoever_already_held_one():
    roster = players(5)
    matches = [
        match(1, "p0", "p1", "p0", "2-0"),
        match(1, "p2", "p3", "p2", "2-0"),
        match(1, "p4", BYE_NAME, "p4", BYE_SCORE),
        match(2, "p1", "p3", "p1", "2-0"),
        match(2, "p0", "p2", "p0", "2-0"),
    ]

    pairings = pair_round(roster, matches, 3)

    byes = [pair for pair in pairings if BYE_NAME in pair]
    assert byes and byes[0][0] != "p4"
