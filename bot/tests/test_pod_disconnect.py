"""Pure-function tests for the mid-draft disconnect cards."""
from __future__ import annotations

import pytest

from bot.services import pod_disconnect


@pytest.mark.parametrize("players_left,expected", [(7, 4), (8, 5), (6, 4), (5, 3), (1, 1), (0, 1)])
def test_a_disconnect_is_decided_by_a_majority_of_who_is_left(players_left, expected):
    assert pod_disconnect.votes_needed(players_left) == expected


def test_the_offer_card_carries_its_own_tally_and_target():
    card = pod_disconnect.build_offer_embed(
        ["Reid"], dropped_at=1770000000, needed=4,
        bot_votes=["<@1>", "<@2>"], restart_votes=["<@3>"])

    assert pod_disconnect.needed_from_embed(card) == 4
    assert pod_disconnect.bot_voters_from_embed(card) == ["<@1>", "<@2>"]
    assert pod_disconnect.restart_voters_from_embed(card) == ["<@3>"]


def test_the_deciding_click_leaves_the_card_saying_who_decided_it():
    """A settled vote keeps its card: only the buttons go, and the outcome is said in a new message."""
    card = pod_disconnect.build_offer_embed(
        ["Reid"], dropped_at=1770000000, needed=2, bot_votes=["<@1>"])

    settled = pod_disconnect.rerender_offer(card, ["<@1>", "<@2>"], [])

    assert settled.description == card.description
    assert settled.footer.text == card.footer.text
    assert pod_disconnect.bot_voters_from_embed(settled) == ["<@1>", "<@2>"]


@pytest.mark.parametrize("card", [
    pod_disconnect.build_waiting_embed(["Reid"], opens_at=1770000000),
    pod_disconnect.build_offer_embed(["Reid"], dropped_at=1770000000, needed=2),
    pod_disconnect.build_back_embed(["Reid"]),
])
def test_every_card_heads_itself_in_the_description(card):
    """An embed title renders no markdown and no timestamp, so no card may use one."""
    assert card.title is None
    assert card.description.startswith("### ")
