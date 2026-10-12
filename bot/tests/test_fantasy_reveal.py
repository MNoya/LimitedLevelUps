from datetime import datetime, timezone

import pytest

from bot.services.fantasy_event import event_for
from bot.services.fantasy_reveal import (
    DAY_ONE_COMPLETE,
    EVENT_COMPLETE,
    SWISS_COMPLETE,
    auto_reveal_through,
    manual_release_rounds,
    revealed_milestones,
    round_number_for_reveal,
)


def at(hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 11, 13, hour, minute, tzinfo=timezone.utc)


def test_each_day_opener_and_top8_round_waits_for_a_moderator():
    event = event_for("WC32")

    rounds = manual_release_rounds(event)

    assert rounds == {1, 8, 15, 16, 17}


@pytest.mark.parametrize("current, completed, now, expected", [
    (0, {1: at(10, 0)}, at(18, 0), 0),
    (1, {2: at(10, 15)}, at(11, 44), 1),
    (1, {2: at(10, 15)}, at(11, 45), 2),
    (1, {2: at(10, 0), 3: at(11, 0)}, at(12, 30), 3),
    (1, {2: at(10, 0), 3: at(11, 30)}, at(12, 30), 2),
    (1, {3: at(10, 0)}, at(18, 0), 1),
    (7, {8: at(10, 0)}, at(18, 0), 7),
    (14, {15: at(10, 0)}, at(18, 0), 14),
])
def test_rounds_reveal_after_the_coverage_delay_except_manual_rounds(current, completed, now, expected):
    revealed = auto_reveal_through(current, completed, now, manual_release_rounds(event_for("WC32")))

    assert revealed == expected


@pytest.mark.parametrize("argument, expected", [
    ("3", 3),
    ("15", None),
    ("quarterfinals", 15),
    ("quarters", 15),
    ("semis", 16),
    ("Semifinals", 16),
    ("final", 17),
    ("finals", 17),
    ("top", None),
])
def test_reveal_argument_maps_to_round_numbers(argument, expected):
    number = round_number_for_reveal(argument, 14)

    assert number == expected


@pytest.mark.parametrize("previous, revealed, expected", [
    (6, 7, [DAY_ONE_COMPLETE]),
    (7, 8, []),
    (0, 3, []),
    (13, 14, [SWISS_COMPLETE]),
    (16, 17, [EVENT_COMPLETE]),
    (5, 17, [DAY_ONE_COMPLETE, SWISS_COMPLETE, EVENT_COMPLETE]),
])
def test_reveal_posts_fire_when_the_marker_passes_day_one_the_swiss_or_the_final(previous, revealed, expected):
    milestones = revealed_milestones(event_for("WC32"), previous, revealed)

    assert milestones == expected
