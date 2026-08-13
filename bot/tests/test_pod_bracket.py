import pytest

from bot.services import pod_bracket
from bot.services.pod_tournament import format_result_change
from bot.services.pod_swiss import BYE_NAME, BYE_SCORE
from bot.tests.pod_helpers import match, pairset, players


def _seat(player_id: str) -> int:
    return int(player_id[1:])


def _ten_player_round1() -> list:
    return [
        match(1, "p0", "p1", "p0"), match(1, "p2", "p3", "p2"), match(1, "p4", "p5", "p4"),
        match(1, "p6", "p7", "p6"), match(1, "p8", "p9", "p8"),
    ]


def _play_bracket(roster, pick_winner) -> tuple[list, dict[int, list[tuple[str, str]]]]:
    """Play three rounds the way the bot does: report one match at a time and pair the next round
    after each result, so the pairer only ever sees a partly-finished source round."""
    half = len(roster) // 2
    pairings = {1: [(roster[i].id, roster[i + half].id) for i in range(half)], 2: [], 3: []}
    completed: list = []
    for round_num in (1, 2, 3):
        for index, (a, b) in enumerate(pairings[round_num]):
            completed.append(match(round_num, a, b, pick_winner(a, b)))
            if round_num < 3:
                pairings[round_num + 1] += pod_bracket.incremental_pairings(
                    roster, completed, pairings[round_num + 1], round_num + 1,
                    source_round_complete=index == half - 1,
                )
    return completed, pairings


_WINNER_PICKS = {
    "lower seat wins": lambda a, b: min((a, b), key=_seat),
    "higher seat wins": lambda a, b: max((a, b), key=_seat),
    "alternating": lambda a, b: (min if (_seat(a) + _seat(b)) % 2 else max)((a, b), key=_seat),
}


# --- supports -------------------------------------------------------------

def test_supports_the_two_table_sizes():
    assert pod_bracket.supports(8) is True
    assert pod_bracket.supports(10) is True
    assert pod_bracket.supports(6) is False
    assert pod_bracket.supports(4) is False


# --- incremental_pairings -------------------------------------------------

def test_round2_pairs_winners_and_losers_from_first_two_results():
    roster = players(8)
    completed = [match(1, "p0", "p1", "p0"), match(1, "p2", "p3", "p2")]
    new = pod_bracket.incremental_pairings(roster, completed, [], 2, source_round_complete=False)
    assert pairset(new) == {frozenset({"p0", "p2"}), frozenset({"p1", "p3"})}


def test_round2_no_pairing_from_a_single_result():
    roster = players(8)
    completed = [match(1, "p0", "p1", "p0")]
    new = pod_bracket.incremental_pairings(roster, completed, [], 2, source_round_complete=False)
    assert new == []  # one winner + one loser, neither has a same-record partner yet


def test_round2_excludes_already_paired_players():
    roster = players(8)
    completed = [
        match(1, "p0", "p1", "p0"), match(1, "p2", "p3", "p2"),
        match(1, "p4", "p5", "p4"), match(1, "p6", "p7", "p6"),
    ]
    existing = [("p0", "p2"), ("p1", "p3")]  # already created
    new = pod_bracket.incremental_pairings(roster, completed, existing, 2, source_round_complete=False)
    assert pairset(new) == {frozenset({"p4", "p6"}), frozenset({"p5", "p7"})}


def test_round2_full_slate_when_all_reported():
    roster = players(8)
    completed = [
        match(1, "p0", "p1", "p0"), match(1, "p2", "p3", "p2"),
        match(1, "p4", "p5", "p4"), match(1, "p6", "p7", "p6"),
    ]
    new = pod_bracket.incremental_pairings(roster, completed, [], 2, source_round_complete=True)
    assert len(new) == 4
    winners, losers = {"p0", "p2", "p4", "p6"}, {"p1", "p3", "p5", "p7"}
    assert all(set(p) <= winners or set(p) <= losers for p in new)


def test_round3_trophy_opens_before_loser_bracket_finishes():
    roster = players(8)
    completed = [
        match(1, "p0", "p4", "p0"), match(1, "p1", "p5", "p1"),
        match(1, "p2", "p6", "p2"), match(1, "p3", "p7", "p3"),
        match(2, "p0", "p1", "p0"), match(2, "p2", "p3", "p2"),  # winner bracket only
    ]
    new = pod_bracket.incremental_pairings(roster, completed, [], 3, source_round_complete=False)
    # p0 and p2 are both 2-0 → the trophy match forms while p4-p7 haven't played R2 yet
    assert frozenset({"p0", "p2"}) in pairset(new)


def test_round3_trophy_opens_after_the_floor_slack_went_to_a_lower_group():
    roster = players(8)
    report_order = [
        match(1, "p0", "p4", "p0"), match(1, "p1", "p5", "p1"),
        match(2, "p0", "p1", "p0"), match(2, "p4", "p5", "p4"),
        match(1, "p2", "p6", "p2"), match(1, "p3", "p7", "p3"),
        match(2, "p2", "p3", "p2"),
    ]

    completed: list = []
    round3: list = []
    for result in report_order:
        completed.append(result)
        round3 += pod_bracket.incremental_pairings(
            roster, completed, round3, 3, source_round_complete=False,
        )

    assert frozenset({"p1", "p4"}) in pairset(round3)
    assert frozenset({"p0", "p2"}) in pairset(round3)


def test_a_rematch_only_group_plays_across_records_instead():
    roster = players(4)
    completed = [
        match(1, "p0", "p1", "p0"), match(1, "p2", "p3", "p2"),
        match(2, "p2", "p0", "p2"), match(2, "p1", "p3", "p1"),
    ]
    # entering R3: 2-0 p2 (alone), 1-1 {p0, p1} who already met in R1, 0-2 p3 (alone)
    new = pod_bracket.incremental_pairings(roster, completed, [], 3, source_round_complete=True)

    assert len(new) == 2
    assert frozenset({"p0", "p1"}) not in pairset(new)
    assert pod_bracket.contains_rematch(new, completed) is False


def test_round3_holds_one_one_group_until_no_avoidable_rematch():
    # p0 and p1 met in R1; both go W-L / L-W and land at 1-1. The other two 1-1 players (p5, p6)
    # finish R2 first, so a greedy pairer would lock p5-p6 and strand p0-p1 into their R1 rematch.
    # The group must wait, then pair rematch-free.
    roster = players(8)
    r1 = [  # winners p0 p2 p4 p6, losers p1 p3 p5 p7
        match(1, "p0", "p1", "p0"), match(1, "p2", "p3", "p2"),
        match(1, "p4", "p5", "p4"), match(1, "p6", "p7", "p6"),
    ]
    r2_in_report_order = [  # winners' bracket p0/p2 & p4/p6, losers' bracket p1/p3 & p5/p7
        match(2, "p5", "p7", "p5"),  # p5 → 1-1, ready first
        match(2, "p4", "p6", "p4"),  # p6 → 1-1
        match(2, "p2", "p0", "p2"),  # p0 → 1-1 (its R1 win now offset by an R2 loss)
        match(2, "p1", "p3", "p1"),  # p1 → 1-1, ready last (completes R2)
    ]

    completed = list(r1)
    accumulated: list = []
    for i, result in enumerate(r2_in_report_order):
        completed.append(result)
        source_complete = i == len(r2_in_report_order) - 1
        new = pod_bracket.incremental_pairings(
            roster, completed, accumulated, 3, source_round_complete=source_complete,
        )
        accumulated += new

    one_one = {"p0", "p1", "p5", "p6"}
    one_one_pairs = [p for p in accumulated if set(p) <= one_one]

    assert frozenset({"p0", "p1"}) not in pairset(accumulated)  # never the R1 rematch
    assert len(one_one_pairs) == 2
    assert {pid for pair in one_one_pairs for pid in pair} == one_one


@pytest.mark.parametrize("pick_winner", _WINNER_PICKS.values(), ids=list(_WINNER_PICKS))
@pytest.mark.parametrize("size", (8, 10))
def test_bracket_fills_every_round_and_never_repeats_a_match(size, pick_winner):
    roster = players(size)

    _, pairings = _play_bracket(roster, pick_winner)

    everyone = {p.id for p in roster}
    for round_num in (2, 3):
        assert len(pairings[round_num]) == size // 2
        assert {pid for pair in pairings[round_num] for pid in pair} == everyone
    played = [frozenset(pair) for round_num in (1, 2, 3) for pair in pairings[round_num]]
    assert len(played) == len(set(played))


def test_round2_at_ten_starts_three_matches_before_round1_finishes():
    # The last R1 match leaves a 1-0 and a 0-1 who just played, so the fifth and fourth R2 matches
    # can only be made once it reports. The first three do not have to wait for it.
    roster = players(10)
    completed: list = []
    accumulated: list = []
    for result in _ten_player_round1()[:4]:
        completed.append(result)
        accumulated += pod_bracket.incremental_pairings(
            roster, completed, accumulated, 2, source_round_complete=False,
        )

    assert len(accumulated) == 3


def test_round2_at_ten_plays_the_leftovers_across_records():
    roster = players(10)
    completed = _ten_player_round1()

    new = pod_bracket.incremental_pairings(roster, completed, [], 2, source_round_complete=True)

    records = pod_bracket.player_records(roster, completed)
    across = [pair for pair in new if records[pair[0]] != records[pair[1]]]
    assert len(new) == 5
    assert len(across) == 1  # ten players cannot split evenly, so exactly one match crosses records
    assert pod_bracket.contains_rematch(new, completed) is False


# --- padding_slots --------------------------------------------------------

def test_padding_all_unknown_before_any_result():
    roster = players(8)
    slots = pod_bracket.padding_slots(roster, [], [], [], 2)
    assert slots == [((1, 0), (1, 0), None, None), ((1, 0), (1, 0), None, None),
                     ((0, 1), (0, 1), None, None), ((0, 1), (0, 1), None, None)]


def test_padding_names_a_waiting_player():
    roster = players(8)
    completed = [match(1, "p0", "p1", "p0"), match(1, "p2", "p3", "p2"), match(1, "p4", "p5", "p4")]
    # two real R2 matches already exist (a winner pair + a loser pair)
    slots = pod_bracket.padding_slots(
        roster, completed, real_pairs=[((1, 0), (1, 0)), ((0, 1), (0, 1))],
        paired_names=["p0", "p2", "p1", "p3"], round_num=2,
    )
    assert slots == [((1, 0), (1, 0), "p4", None), ((0, 1), (0, 1), "p5", None)]


def test_padding_unknown_when_no_one_waiting():
    roster = players(8)
    completed = [match(1, "p0", "p1", "p0"), match(1, "p2", "p3", "p2")]
    slots = pod_bracket.padding_slots(
        roster, completed, real_pairs=[((1, 0), (1, 0)), ((0, 1), (0, 1))],
        paired_names=["p0", "p2", "p1", "p3"], round_num=2,
    )
    assert slots == [((1, 0), (1, 0), None, None), ((0, 1), (0, 1), None, None)]


def test_padding_pairs_two_waiting_players_in_one_slot():
    roster = players(8)
    completed = [
        match(1, "p0", "p4", "p0"), match(1, "p1", "p5", "p1"),
        match(1, "p2", "p6", "p2"), match(1, "p3", "p7", "p3"),
        match(2, "p0", "p1", "p0"), match(2, "p2", "p3", "p2"),
    ]
    # R3 has the 1-1 match created; the two 2-0 players (p0, p2) still wait for the trophy slot
    slots = pod_bracket.padding_slots(
        roster, completed, real_pairs=[((1, 1), (1, 1))],
        paired_names=["p1", "p3"], round_num=3,
    )
    assert slots[0] == ((2, 0), (2, 0), "p0", "p2")  # trophy slot names both finalists


def test_padding_stays_anonymous_for_a_held_rematch_prone_group():
    # p5 and p6 reach 1-1 first, but p0 & p1 (who met in R1) can still land at 1-1, so the group is
    # held. The preview must not name p5-p6 as a match — that is the bait that let players start a
    # pairing the lock later moved. Both 1-1 slots stay anonymous until the group locks.
    roster = players(8)
    completed = [
        match(1, "p0", "p1", "p0"), match(1, "p2", "p3", "p2"),
        match(1, "p4", "p5", "p4"), match(1, "p6", "p7", "p6"),
        match(2, "p5", "p7", "p5"),  # p5 → 1-1
        match(2, "p4", "p6", "p4"),  # p6 → 1-1
    ]
    slots = pod_bracket.padding_slots(roster, completed, real_pairs=[], paired_names=[], round_num=3)

    one_one = [s for s in slots if s[0] == (1, 1)]
    assert one_one == [((1, 1), (1, 1), None, None), ((1, 1), (1, 1), None, None)]
    assert ((1, 1), (1, 1), "p5", "p6") not in slots


def test_padding_empty_for_unsupported_round():
    roster = players(8)
    assert pod_bracket.padding_slots(roster, [], [], [], 1) == []
    assert pod_bracket.padding_slots(roster, [], [], [], 4) == []


def test_padding_projects_the_ten_player_round2_pair_up_slot():
    roster = players(10)
    slots = pod_bracket.padding_slots(roster, [], [], [], 2)

    assert len(slots) == 5
    assert [(a, b) for a, b, _, _ in slots] == [
        ((1, 0), (1, 0)), ((1, 0), (1, 0)), ((1, 0), (0, 1)), ((0, 1), (0, 1)), ((0, 1), (0, 1)),
    ]


def test_padding_leaves_records_open_while_a_pair_up_decides_the_shape():
    # 10 players: the R2 pair-up sends R3 to three 2-0 players if the 1-0 wins and two if the 0-1 does,
    # so R3 has no shape to preview until it reports.
    roster = players(10)
    completed = _ten_player_round1() + [
        match(2, "p0", "p2", "p0"),  # 1-0 bracket
        match(2, "p4", "p6", "p4"),  # 1-0 bracket
    ]
    # p8 (1-0) vs p1 (0-1) is the pair-up and is still unreported
    slots = pod_bracket.padding_slots(roster, completed, real_pairs=[], paired_names=[], round_num=3)

    assert len(slots) == 5
    assert all(slot == (None, None, None, None) for slot in slots)


# --- regenerate after a correction ----------------------------------------

def test_correction_keeps_the_pairings_it_does_not_invalidate():
    roster = players(8)
    reported = [
        match(1, "p0", "p1", "p0"), match(1, "p2", "p3", "p2"),
        match(1, "p4", "p5", "p4"), match(1, "p6", "p7", "p6"),
    ]
    before = pod_bracket.incremental_pairings(roster, reported, [], 2, source_round_complete=True)
    corrected = [m for m in reported if m.player_a_id != "p2"] + [match(1, "p2", "p3", "p3", "2-1")]

    records = pod_bracket.player_records(roster, corrected)
    survivors = [(a, b) for a, b in before if records[a] == records[b]]
    refilled = pod_bracket.incremental_pairings(roster, corrected, survivors, 2, source_round_complete=True)

    assert len(survivors) == 2
    assert pairset(survivors) < pairset(before)
    assert {"p2", "p3"} <= {name for pair in refilled for name in pair}
    assert pairset(survivors + refilled) - pairset(before) == pairset(refilled)


def test_player_records_counts_wins_and_losses():
    roster = players(4)
    completed = [match(1, "p0", "p1", "p0"), match(2, "p0", "p2", "p2")]

    records = pod_bracket.player_records(roster, completed)

    assert records["p0"] == (1, 1)
    assert records["p1"] == (0, 1)
    assert records["p2"] == (1, 0)
    assert records["p3"] == (0, 0)


def test_contains_rematch_flags_a_repeat_of_a_played_match():
    completed = [match(1, "p0", "p1", "p0")]

    assert pod_bracket.contains_rematch([("p1", "p0")], completed) is True
    assert pod_bracket.contains_rematch([("p0", "p2")], completed) is False


# --- shared wording -------------------------------------------------------

def test_format_result_change_reported_leads_with_winner_and_score():
    phrase = format_result_change("Arcyl", "Bramblewick", "Bramblewick", "2-1")

    assert phrase.startswith("Bramblewick")
    assert "2-1" in phrase
    assert "Arcyl" in phrase


def test_format_result_change_cleared_names_both_without_score():
    phrase = format_result_change("Arcyl", "Bramblewick", None, None)

    assert "Arcyl" in phrase
    assert "Bramblewick" in phrase
    assert not any(ch.isdigit() for ch in phrase)


def test_format_result_change_drops_arena_ids_from_both_players():
    phrase = format_result_change("Arcyl#48087", "Bramblewick#13488", "Arcyl#48087", "2-0")

    assert "#48087" not in phrase and "#13488" not in phrase
    assert all(part in phrase for part in ("Arcyl", "Bramblewick", "2-0"))


def test_a_forfeited_bye_sinks_the_dropped_player_into_the_losers_group():
    roster = players(8)
    completed = [
        match(1, "p0", "p1", "p0", BYE_SCORE),  # p1 dropped
        match(1, "p2", "p3", "p2"), match(1, "p4", "p5", "p4"), match(1, "p6", "p7", "p6"),
    ]

    new = pod_bracket.incremental_pairings(roster, completed, [], 2, source_round_complete=True)

    assert pod_bracket.player_records(roster, completed)["p1"] == (0, 1)
    dropped_pair = next(set(p) for p in new if "p1" in p)
    assert dropped_pair <= {"p1", "p3", "p5", "p7"}


def test_an_odd_pool_floats_a_bye_to_the_worst_record():
    roster = players(7)
    completed = [
        match(1, "p0", "p1", "p0"), match(1, "p2", "p3", "p2"), match(1, "p4", "p5", "p4"),
        match(1, "p6", BYE_NAME, "p6", BYE_SCORE),
    ]

    new = pod_bracket.incremental_pairings(roster, completed, [], 2, source_round_complete=True)

    byes = [p for p in new if BYE_NAME in p]
    assert len(byes) == 1
    assert byes[0][0] in {"p1", "p3", "p5"}  # a 0-1, never one of the winners
    assert len(new) == 4
