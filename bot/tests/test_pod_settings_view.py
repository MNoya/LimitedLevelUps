"""Pure-function tests for the pod-draft Settings panel."""
from __future__ import annotations

import pytest

from bot.services.pod_settings_view import (
    MAX_PLAYERS_OPTIONS,
    PACKS_MAX,
    PACKS_MIN,
    parse_setting_field,
)


@pytest.mark.parametrize("raw,current,expected_value,expects_error", [
    ("4", 3, 4, False),
    ("  4  ", 3, 4, False),
    ("", 3, None, False),
    ("   ", None, None, False),
    ("3", 3, None, False),
    ("99", 3, None, True),
    ("0", 3, None, True),
    ("four", 3, None, True),
    ("4.5", 3, None, True),
    ("-2", 3, None, True),
    ("99", 99, None, False),
])
def test_a_setting_field_reads_as_a_change_a_no_op_or_a_refusal(raw, current, expected_value, expects_error):
    value, error = parse_setting_field(
        raw, current, minimum=PACKS_MIN, maximum=PACKS_MAX, label="Packs Per Player")

    assert value == expected_value
    assert (error is not None) == expects_error


def test_a_six_player_table_can_be_picked():
    assert 6 in MAX_PLAYERS_OPTIONS
