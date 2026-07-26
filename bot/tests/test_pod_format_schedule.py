from datetime import date

from bot.services import pod_format
from bot.services import pod_format_schedule as schedule
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
    day = date(2026, 8, 1)
    monkeypatch.setitem(schedule.FORMATS_BY_DAY, day, (schedule.LATEST, "NEO"))
    monkeypatch.setitem(schedule.FORMATS_BY_DAY, (day, "LATE"), (schedule.LATEST, "PEASANT"))

    assert schedule.formats_for(day, "EARLY") == (active_set_code(), "NEO")
    assert schedule.formats_for(day, "LATE") == (active_set_code(), "PEASANT")
    assert schedule.formats_for(day) == (active_set_code(), "NEO")


def test_a_day_off_the_schedule_offers_only_the_latest_set():
    assert schedule.formats_for(date(1999, 1, 1)) == (active_set_code(),)


def test_a_day_can_drop_the_latest_set_entirely(monkeypatch):
    day = date(2026, 8, 2)
    monkeypatch.setitem(schedule.FORMATS_BY_DAY, day, ("PEASANT",))

    assert schedule.formats_for(day) == ("PEASANT",)


def test_naming_the_active_set_beside_latest_opens_one_pod_not_two(monkeypatch):
    day = date(2026, 8, 3)
    monkeypatch.setitem(schedule.FORMATS_BY_DAY, day, (schedule.LATEST, active_set_code(), "NEO"))

    assert schedule.formats_for(day) == (active_set_code(), "NEO")
