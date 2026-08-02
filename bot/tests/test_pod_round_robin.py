import pytest

from bot.commands.test_group import HALL_OF_FAME
from bot.services import pod_round_robin, pod_round_robin_vote
from bot.services.pod_swiss import Player


def _players(seats=(0, 1, 2, 3)):
    return [Player(id=name, name=name, seat=seat) for name, seat in zip(HALL_OF_FAME, seats)]


@pytest.mark.parametrize("size, supported", [(2, False), (4, True), (6, False), (8, False)])
def test_supports_only_a_four_player_table(size, supported):
    assert pod_round_robin.supports(size) is supported


def test_every_player_meets_every_other_exactly_once():
    players = _players()

    pairs = [pair for r in (1, 2, 3) for pair in pod_round_robin.pair_round(players, r)]

    assert len(pairs) == 6
    assert len({frozenset(pair) for pair in pairs}) == 6


@pytest.mark.parametrize("round_num", [1, 2, 3])
def test_each_round_seats_every_player_once(round_num):
    players = _players()

    pairings = pod_round_robin.pair_round(players, round_num)

    seated = [name for pair in pairings for name in pair]
    assert sorted(seated) == sorted(p.id for p in players)


def test_round_one_pairs_across_the_table():
    players = _players()

    pairings = pod_round_robin.pair_round(players, 1)

    assert pairings == [(players[0].id, players[2].id), (players[1].id, players[3].id)]


def test_pairing_follows_seats_not_roster_order():
    shuffled = [Player(id=name, name=name, seat=seat) for name, seat in zip(HALL_OF_FAME, (3, 0, 2, 1))]

    pairings = pod_round_robin.pair_round(shuffled, 1)

    assert pairings == [(shuffled[1].id, shuffled[2].id), (shuffled[3].id, shuffled[0].id)]


def test_unseated_roster_keeps_its_own_order():
    unseated = [Player(id=name, name=name) for name in HALL_OF_FAME[:4]]

    pairings = pod_round_robin.pair_round(unseated, 1)

    assert pairings == [(unseated[0].id, unseated[2].id), (unseated[1].id, unseated[3].id)]


@pytest.mark.parametrize("size, round_num", [(6, 1), (4, 0), (4, 4)])
def test_pair_round_rejects_what_it_cannot_schedule(size, round_num):
    players = [Player(id=name, name=name, seat=i) for i, name in enumerate(HALL_OF_FAME[:size])]

    with pytest.raises(ValueError):
        pod_round_robin.pair_round(players, round_num)


@pytest.mark.parametrize("pod_size", [4, 6])
def test_every_player_has_to_agree(pod_size):
    assert pod_round_robin_vote.votes_needed(pod_size) == pod_size


def test_voters_read_back_off_the_card_per_side():
    embed = pod_round_robin_vote.build_offer_embed(["<@1>", "<@2>"], ["<@3>"], 4)

    assert pod_round_robin_vote.round_robin_voters_from_embed(embed) == ["<@1>", "<@2>"]
    assert pod_round_robin_vote.wait_voters_from_embed(embed) == ["<@3>"]


def test_a_voter_is_listed_once_per_side():
    embed = pod_round_robin_vote.build_offer_embed(["<@1>", "<@1>"], [], 4)

    assert pod_round_robin_vote.round_robin_voters_from_embed(embed) == ["<@1>"]
