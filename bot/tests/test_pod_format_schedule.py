from datetime import date

import pytest

from bot.services import pod_format
from bot.services import pod_format_schedule as schedule
from bot.services.pod_signals import LANE_EARLY, LANE_LATE
from bot.sets import active_set_code


def test_every_scheduled_format_resolves_to_a_known_set_or_cube():
    unresolved = {}
    for key in schedule.FORMATS_BY_DAY:
        day, lane = key if isinstance(key, tuple) else (key, None)
        for code in schedule.formats_for(day, lane):
            if pod_format.resolve_format_code(code) != code:
                unresolved[key] = code

    assert unresolved == {}


def test_a_slot_override_beats_the_whole_day_entry(monkeypatch):
    day = date(2027, 1, 4)
    monkeypatch.setitem(schedule.FORMATS_BY_DAY, day, (schedule.LATEST, "NEO"))
    monkeypatch.setitem(schedule.FORMATS_BY_DAY, (day, LANE_LATE), (schedule.LATEST, "PEASANT"))

    assert schedule.formats_for(day, LANE_EARLY) == (active_set_code(), "NEO")
    assert schedule.formats_for(day, LANE_LATE) == (active_set_code(), "PEASANT")
    assert schedule.formats_for(day) == (active_set_code(), "NEO")


def test_a_day_off_the_schedule_offers_only_the_latest_set():
    assert schedule.formats_for(date(1999, 1, 1)) == (active_set_code(),)


def test_a_day_can_drop_the_latest_set_entirely(monkeypatch):
    day = date(2027, 1, 5)
    monkeypatch.setitem(schedule.FORMATS_BY_DAY, day, ("PEASANT",))

    assert schedule.formats_for(day) == ("PEASANT",)


def test_naming_the_active_set_beside_latest_opens_one_pod_not_two(monkeypatch):
    day = date(2027, 1, 6)
    monkeypatch.setitem(schedule.FORMATS_BY_DAY, day, (schedule.LATEST, active_set_code(), "NEO"))

    assert schedule.formats_for(day) == (active_set_code(), "NEO")


@pytest.mark.parametrize("day, expected", [
    (date(2026, 3, 2), "ECL"),
    (date(2026, 3, 3), "TMT"),
    (date(2026, 4, 21), "SOS"),
])
def test_a_day_carries_the_set_live_on_that_day(day, expected):
    assert schedule.latest_on(day) == expected


def test_a_day_past_a_rotation_offers_the_set_it_will_draft(monkeypatch):
    day = date(2026, 3, 3)
    monkeypatch.setitem(schedule.FORMATS_BY_DAY, day, (schedule.LATEST, "NEO"))

    assert schedule.formats_on(day) == ("TMT", "NEO")


def test_a_day_shows_only_what_it_adds_to_the_daily_set(monkeypatch):
    day = date(2026, 3, 4)
    monkeypatch.setitem(schedule.FORMATS_BY_DAY, day, (schedule.LATEST, "NEO"))

    assert schedule.extras_on(day) == ("NEO",)


def test_a_day_offering_the_set_alone_adds_nothing(monkeypatch):
    day = date(2026, 3, 5)
    monkeypatch.setitem(schedule.FORMATS_BY_DAY, day, (schedule.LATEST,))

    assert schedule.extras_on(day) == ()


def test_a_closed_slot_offers_nothing_while_the_day_still_offers_the_set(monkeypatch):
    day = date(2027, 1, 7)
    monkeypatch.setitem(schedule.FORMATS_BY_DAY, day, (schedule.LATEST,))
    monkeypatch.setitem(schedule.FORMATS_BY_DAY, (day, LANE_EARLY), schedule.CLOSED)

    assert schedule.formats_for(day, LANE_EARLY) == ()
    assert schedule.formats_for(day, LANE_LATE) == (active_set_code(),)


def test_the_rotation_day_is_found_inside_the_rendered_span():
    assert schedule.rotation_in(schedule.calendar_days(date(2026, 3, 5), 1)) == date(2026, 3, 3)


def test_a_span_inside_one_set_has_no_rotation():
    assert schedule.rotation_in(schedule.calendar_days(date(2026, 3, 12), 1)) is None


def test_the_calendar_starts_on_the_monday_of_the_week_it_covers():
    days = schedule.calendar_days(date(2026, 3, 5), 2)

    assert days[0] == date(2026, 3, 2)
    assert days[-1] == date(2026, 3, 15)
    assert len(days) == 14
