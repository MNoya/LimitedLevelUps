from datetime import date

from bot.services import pod_format
from bot.services import pod_format_schedule as schedule


def test_every_scheduled_format_resolves_to_a_known_set_or_cube():
    unresolved = {
        key: code for key, code in schedule.OTHER_FORMAT_BY_DAY.items()
        if pod_format.resolve_format_code(code) != code
    }

    assert unresolved == {}


def test_a_slot_override_beats_the_whole_day_entry(monkeypatch):
    day = date(2026, 8, 1)
    monkeypatch.setitem(schedule.OTHER_FORMAT_BY_DAY, day, "NEO")
    monkeypatch.setitem(schedule.OTHER_FORMAT_BY_DAY, (day, "LATE"), "PEASANT")

    assert schedule.other_format_for(day, "EARLY") == "NEO"
    assert schedule.other_format_for(day, "LATE") == "PEASANT"
    assert schedule.other_format_for(day) == "NEO"


def test_a_day_off_the_schedule_offers_only_the_latest_set():
    scheduled_day = next(iter(schedule.OTHER_FORMAT_BY_DAY))

    assert schedule.other_format_for(scheduled_day) is not None
    assert schedule.other_format_for(date(1999, 1, 1)) is None
