import pytest

from bot.services.pod_pairing_select import DEFAULT_PAIRING_MODE, pairing_label, pairing_options
from bot.services.pod_tournament import closed_decklist_after_pairing


def test_default_pairing_mode_is_fast_bracket():
    assert DEFAULT_PAIRING_MODE == "bracket"
    assert pairing_label(None) == "Fast Bracket"


def test_pairing_options_default_to_bracket_when_unset():
    defaulted = [option.value for option in pairing_options(None) if option.default]

    assert defaulted == ["bracket"]


def test_pairing_options_honor_an_explicit_mode():
    defaulted = [option.value for option in pairing_options("swiss") if option.default]

    assert defaulted == ["swiss"]


@pytest.mark.parametrize("previous_mode, mode, closed, expected", [
    ("swiss", "team", False, True),
    ("team", "swiss", True, False),
    ("team", "bracket", True, False),
    ("swiss", "bracket", True, True),
    ("bracket", "swiss", False, False),
])
def test_closed_decklist_follows_team_pairing(previous_mode, mode, closed, expected):
    result = closed_decklist_after_pairing(previous_mode, mode, closed)

    assert result is expected
