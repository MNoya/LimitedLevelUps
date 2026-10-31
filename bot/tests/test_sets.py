from datetime import date, datetime, timezone

import pytest

from bot.sets import SetSeed, newest_playable_set_code, prerelease_date_for, set_code_for_event


def test_prerelease_date_falls_back_to_the_friday_before_the_arena_release():
    recorded = SetSeed("HOB", "The Hobbit", date(2026, 8, 11), date(2026, 9, 28), prerelease_date=date(2026, 8, 7))
    derived = SetSeed("XXX", "Unrecorded", date(2026, 8, 11), date(2026, 9, 28))

    assert prerelease_date_for(recorded) == date(2026, 8, 7)
    assert prerelease_date_for(derived) == date(2026, 8, 7)


@pytest.mark.parametrize("when, expected", [
    (datetime(2026, 8, 5, 3, 0, tzinfo=timezone.utc), "MSH"),
    (datetime(2026, 8, 5, 5, 0, tzinfo=timezone.utc), "HOB"),
    (datetime(2026, 8, 20, 12, 0, tzinfo=timezone.utc), "HOB"),
    (datetime(2025, 10, 25, 12, 0, tzinfo=timezone.utc), "SPM"),
])
def test_trophy_default_moves_to_the_new_set_at_midnight_et_on_the_wednesday_of_its_prerelease_week(when, expected):
    code = newest_playable_set_code(when)

    assert code == expected


def test_chaos_expansion_routes_only_events_from_the_2026_event_on():
    cases = [
        ("Chaos", date(2026, 9, 2), "CHAOS"),
        ("Chaos", date(2026, 9, 1), "CHAOS"),
        ("Chaos", date(2025, 6, 15), None),
        ("Chaos", date(2023, 1, 21), None),
        ("Chaos", None, None),
        ("Cube - Powered", date(2020, 1, 1), "CUBE"),
        ("Cube - Powered", None, "CUBE"),
        ("SomethingUnrouted", date(2026, 9, 2), None),
    ]

    for expansion, event_date, expected in cases:
        assert set_code_for_event(expansion, event_date) == expected
