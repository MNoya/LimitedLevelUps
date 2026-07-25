import pytest

from bot.services import pod_format_interest as fi
from bot.sets import active_set_code


FLEX = [fi.LATEST, fi.FLASHBACK]
LATEST_ONLY = [fi.LATEST]
FLASHBACK_ONLY = [fi.FLASHBACK]
NO_PREFERENCE: list[str] = []


def test_normalize_orders_dedupes_and_drops_unknown():
    assert fi.normalize(["flashback", "latest", "flashback", "bogus"]) == [fi.LATEST, fi.FLASHBACK]
    assert fi.normalize([]) == []
    assert fi.normalize(None) == []


def test_flexible_is_both_draftable_set_interests():
    assert fi.is_flexible([fi.LATEST, fi.FLASHBACK]) is True
    assert fi.is_flexible([fi.LATEST]) is False
    assert fi.is_flexible([fi.FLASHBACK, fi.CUBE]) is False


def test_interest_summary_labels():
    assert fi.interest_summary([]) == "No preference"
    assert fi.interest_summary([fi.LATEST]) == "Latest Set"
    assert fi.interest_summary([fi.LATEST, fi.FLASHBACK]) == fi.FLEXIBLE_LABEL
    assert fi.interest_summary([fi.LATEST, fi.FLASHBACK, fi.CUBE]) == fi.FLEXIBLE_LABEL
    assert fi.interest_summary([fi.FLASHBACK, fi.CUBE]) == "Flashback and Cube"


def test_composition_classifies_each_member_once():
    members = [
        [fi.LATEST],
        [fi.LATEST],
        [fi.FLASHBACK],
        [fi.FLASHBACK],
        [fi.FLASHBACK],
        [fi.LATEST, fi.FLASHBACK],
        [fi.CUBE],
        [],
    ]

    comp = fi.composition(members)

    assert (comp.latest_only, comp.flashback_only, comp.flexible) == (2, 3, 1)
    assert (comp.cube, comp.unstated, comp.total) == (1, 1, 8)


def test_composition_capacity_folds_flexible_into_both():
    comp = fi.composition([[fi.LATEST], [fi.FLASHBACK], [fi.LATEST, fi.FLASHBACK], [fi.LATEST, fi.FLASHBACK]])

    assert comp.latest_capacity == 3
    assert comp.flashback_capacity == 3
    assert comp.has_signal is True


def test_should_offer_format_poll_needs_dedicated_flashback_and_capacity():
    strong = fi.composition([[fi.FLASHBACK], [fi.FLASHBACK], [fi.LATEST, fi.FLASHBACK]])
    only_flexible = fi.composition([[fi.LATEST, fi.FLASHBACK]] * 5)
    all_latest = fi.composition([[fi.LATEST]] * 8)

    assert fi.should_offer_format_poll(strong) is True
    assert fi.should_offer_format_poll(only_flexible) is False
    assert fi.should_offer_format_poll(all_latest) is False


def test_slot_fires_latest_holds_on_a_split_that_no_single_format_fills():
    split = fi.composition([[fi.LATEST]] * 3 + [[fi.FLASHBACK]] * 3)
    latest_ready = fi.composition([[fi.LATEST]] * 4 + [[fi.LATEST, fi.FLASHBACK]] * 2)
    unstated_counts_latest = fi.composition([[fi.LATEST]] * 3 + [[]] * 3)
    flashback_only = fi.composition([[fi.FLASHBACK]] * 6)

    assert fi.slot_fires_latest(split, 6) is False
    assert fi.slot_fires_latest(latest_ready, 6) is True
    assert fi.slot_fires_latest(unstated_counts_latest, 6) is True
    assert fi.slot_fires_latest(flashback_only, 6) is False


def test_format_at_fire_stays_on_latest_set():
    members = [[fi.FLASHBACK]] * 8

    assert fi.format_at_fire(members) == active_set_code()


@pytest.mark.parametrize("roster, expected_latest, expected_flashback", [
    (
        [("Ava", FLASHBACK_ONLY), ("Bram", FLASHBACK_ONLY), ("Cy", FLASHBACK_ONLY),
         ("Dee", FLASHBACK_ONLY), ("Elm", FLASHBACK_ONLY), ("Fen", FLASHBACK_ONLY),
         ("Gus", NO_PREFERENCE), ("Hal", FLEX)],
        ["Gus"],
        ["Ava", "Bram", "Cy", "Dee", "Elm", "Fen", "Hal"],
    ),
    (
        [("Ava", LATEST_ONLY), ("Bram", LATEST_ONLY), ("Cy", LATEST_ONLY), ("Dee", LATEST_ONLY),
         ("Elm", LATEST_ONLY), ("Fen", LATEST_ONLY), ("Gus", FLASHBACK_ONLY), ("Hal", FLASHBACK_ONLY),
         ("Ivy", FLEX)],
        ["Ava", "Bram", "Cy", "Dee", "Elm", "Fen"],
        ["Gus", "Hal", "Ivy"],
    ),
    (
        [("Ava", LATEST_ONLY), ("Bram", LATEST_ONLY), ("Cy", LATEST_ONLY), ("Dee", LATEST_ONLY),
         ("Elm", LATEST_ONLY), ("Fen", LATEST_ONLY), ("Ivy", FLEX)],
        ["Ava", "Bram", "Cy", "Dee", "Elm", "Fen", "Ivy"],
        [],
    ),
    (
        [("Ava", LATEST_ONLY), ("Bram", LATEST_ONLY), ("Cy", FLASHBACK_ONLY), ("Dee", FLEX)],
        ["Ava", "Bram", "Dee"],
        ["Cy"],
    ),
    (
        [("Ava", NO_PREFERENCE), ("Bram", LATEST_ONLY)],
        ["Bram", "Ava"],
        [],
    ),
])
def test_format_teams_never_diverts_a_flexible_body_onto_a_table_of_riders(
    roster, expected_latest, expected_flashback,
):
    latest_team, flashback_team = fi.format_teams(roster)

    assert latest_team == expected_latest
    assert flashback_team == expected_flashback
