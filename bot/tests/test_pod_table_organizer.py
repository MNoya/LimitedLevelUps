from datetime import datetime, timedelta, timezone

import pytest

from bot.services.pod_format import PICK_2_SETS
from bot.services.pod_signals import fire_threshold_for
from bot.services.pod_table_organizer import (
    CALL_MISSING,
    NOTHING,
    OFFER_PICK_2_LOBBY,
    OFFER_PICK_2_SIGNUPS,
    OFFER_TEAM_DRAFT,
    TableSnapshot,
    decide,
)


NOW = datetime(2026, 8, 18, 18, 0, tzinfo=timezone.utc)
DEFAULT_THRESHOLD = 6


def _snapshot(**overrides) -> TableSnapshot:
    fields = dict(
        in_draftmancer=0, ceiling=8, minutes_to_start=-5, settled_minutes=5,
        pick_2_set=True, pick_2_offered=False, team_offered=False, missing_called=True,
    )
    fields.update(overrides)
    return TableSnapshot(**fields)


@pytest.mark.parametrize("minutes_out, code, expected", [
    (30, PICK_2_SETS[0], 4),
    (90, PICK_2_SETS[0], DEFAULT_THRESHOLD),
    (-5, PICK_2_SETS[0], DEFAULT_THRESHOLD),
    (30, "SOS", DEFAULT_THRESHOLD),
])
def test_a_pick_2_slot_opens_at_four_inside_the_last_hour(minutes_out, code, expected):
    slot_time = NOW + timedelta(minutes=minutes_out)

    assert fire_threshold_for(slot_time, code, NOW, DEFAULT_THRESHOLD) == expected


def test_a_slot_with_no_time_keeps_the_normal_threshold():
    assert fire_threshold_for(None, PICK_2_SETS[0], NOW, DEFAULT_THRESHOLD) == DEFAULT_THRESHOLD


@pytest.mark.parametrize("overrides, expected", [
    (dict(ceiling=4, in_draftmancer=2, minutes_to_start=9), OFFER_PICK_2_SIGNUPS),
    (dict(ceiling=4, in_draftmancer=1, minutes_to_start=9), NOTHING),
    (dict(ceiling=8, in_draftmancer=4, minutes_to_start=2), NOTHING),
    (dict(in_draftmancer=4, settled_minutes=2), OFFER_PICK_2_LOBBY),
    (dict(in_draftmancer=4, settled_minutes=1), NOTHING),
    (dict(in_draftmancer=6, settled_minutes=2), OFFER_TEAM_DRAFT),
    (dict(in_draftmancer=5), NOTHING),
    (dict(in_draftmancer=8), NOTHING),
    (dict(in_draftmancer=3), NOTHING),
    (dict(in_draftmancer=4, pick_2_set=False), NOTHING),
    (dict(in_draftmancer=4, pick_2_offered=True), NOTHING),
    (dict(in_draftmancer=6, team_offered=True), NOTHING),
])
def test_the_organizer_offers_the_shape_the_room_can_play(overrides, expected):
    snapshot = _snapshot(**overrides)

    assert decide(snapshot) == expected


@pytest.mark.parametrize("minutes_to_start, missing_called, expected", [
    (5, False, CALL_MISSING),
    (6, False, NOTHING),
    (4, True, NOTHING),
    (-1, False, NOTHING),
])
def test_the_missing_players_are_named_once_five_minutes_out(minutes_to_start, missing_called, expected):
    snapshot = _snapshot(
        in_draftmancer=4, minutes_to_start=minutes_to_start, missing_called=missing_called,
        pick_2_set=False,
    )

    assert decide(snapshot) == expected
