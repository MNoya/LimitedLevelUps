from datetime import date, datetime, time, timedelta

import pytest

from bot.services.pod_schedule_card import arrival_line
from bot.models import PodDraftEvent, PodScheduleSlot
from bot.services import pod_format_schedule as schedule
from bot.services.pod_format import PEASANT_CODE
from bot.services.pod_signals import SLOT_EARLY, SLOT_LATE
from bot.sets import RELEASE_TZ, active_set_code


def _add_slots(session, slots):
    for (day, slot_key), formats in slots.items():
        session.add(PodScheduleSlot(day=day, slot=slot_key, formats=list(formats), source="manual"))
    session.flush()


def _add_pod(session, day, set_code, *, kind="tournament"):
    session.add(PodDraftEvent(
        event_date=day, event_time=datetime.combine(day, time(20, 0)), set_code=set_code, kind=kind,
        name=f"{set_code} pod", draftmancer_session="s", discord_thread_id="t", socket_status="open",
    ))
    session.flush()


def test_an_overlay_row_beats_the_derived_default(session):
    day = date(2027, 1, 4)
    _add_slots(session, {(day, SLOT_EARLY): (schedule.LATEST, "NEO"), (day, SLOT_LATE): (schedule.LATEST, "PEASANT")})

    with schedule.schedule_overlay(session, day, day):
        assert schedule.formats_for(day, SLOT_EARLY) == (active_set_code(), "NEO")
        assert schedule.formats_for(day, SLOT_LATE) == (active_set_code(), "PEASANT")
        assert schedule.formats_for(day) == (active_set_code(), "NEO", "PEASANT")


def test_a_day_off_the_schedule_offers_only_the_latest_set():
    assert schedule.formats_for(date(1999, 1, 1)) == (active_set_code(),)


def test_a_slot_can_drop_the_latest_set_entirely(session):
    day = date(2027, 1, 5)
    _add_slots(session, {(day, SLOT_EARLY): ("PEASANT",)})

    with schedule.schedule_overlay(session, day, day):
        assert schedule.formats_for(day, SLOT_EARLY) == ("PEASANT",)


def test_naming_the_active_set_beside_latest_opens_one_pod_not_two(session):
    day = date(2027, 1, 6)
    _add_slots(session, {(day, SLOT_EARLY): (schedule.LATEST, active_set_code(), "NEO")})

    with schedule.schedule_overlay(session, day, day):
        assert schedule.formats_for(day, SLOT_EARLY) == (active_set_code(), "NEO")


@pytest.mark.parametrize("day, expected", [
    (date(2026, 3, 2), "ECL"),
    (date(2026, 3, 3), "TMT"),
    (date(2026, 4, 21), "SOS"),
])
def test_a_day_carries_the_set_live_on_that_day(day, expected):
    assert schedule.latest_on(day) == expected


def test_the_championship_closes_its_own_early_slot():
    champs = date(2026, 9, 19)

    assert schedule.formats_on(champs, SLOT_EARLY) == ()
    assert schedule.formats_on(champs, SLOT_LATE) == ("HOB",)


@pytest.mark.parametrize("day, opens, planned", [
    (date(2026, 9, 18), ("HOB",), ("HOB",)),
    (date(2026, 9, 19), ("HOB",), ("HOB",)),
    (date(2026, 9, 20), (PEASANT_CODE,), (PEASANT_CODE,)),
    (date(2026, 9, 21), (), (schedule.FLASHBACK,)),
    (date(2026, 9, 26), (PEASANT_CODE,), (PEASANT_CODE,)),
    (date(2026, 9, 28), (), (schedule.FLASHBACK,)),
    (date(2026, 9, 29), ("FRA",), ("FRA",)),
])
def test_the_days_after_a_championship_drop_the_latest_set(day, opens, planned):
    assert schedule.formats_on(day) == opens
    assert schedule.planned_on(day) == planned


def test_a_day_past_a_rotation_offers_the_set_it_will_draft(session):
    day = date(2026, 3, 3)
    _add_slots(session, {(day, SLOT_EARLY): (schedule.LATEST, "NEO")})

    with schedule.schedule_overlay(session, day, day):
        assert schedule.formats_on(day, SLOT_EARLY) == ("TMT", "NEO")


def test_a_day_shows_only_what_it_adds_to_the_daily_set(session):
    day = date(2026, 3, 4)
    _add_slots(session, {(day, SLOT_EARLY): (schedule.LATEST, "NEO"), (day, SLOT_LATE): (schedule.LATEST, "NEO")})

    with schedule.schedule_overlay(session, day, day):
        assert schedule.extras_on(day) == ("NEO",)


def test_a_day_offering_the_set_alone_adds_nothing():
    assert schedule.extras_on(date(2026, 3, 5)) == ()


def test_a_real_pod_shows_as_an_extra_beside_the_daily_set(session):
    day = date(2026, 9, 10)
    _add_pod(session, day, PEASANT_CODE)

    with schedule.schedule_overlay(session, day, day):
        assert schedule.extras_on(day) == (PEASANT_CODE,)


def test_a_real_pod_supersedes_the_flashback_placeholder(session):
    day = date(2026, 9, 21)
    _add_pod(session, day, "NEO")

    with schedule.schedule_overlay(session, day, day):
        assert schedule.planned_on(day) == ("NEO",)


def test_set_slot_replaces_the_row_and_can_close_the_slot(session):
    day = date(2027, 2, 1)
    schedule.set_slot(session, day, SLOT_EARLY, (schedule.LATEST, "PEASANT"))
    schedule.set_slot(session, day, SLOT_EARLY, ())

    with schedule.schedule_overlay(session, day, day):
        assert schedule.formats_for(day, SLOT_EARLY) == ()


def test_a_closed_slot_offers_nothing_while_the_day_still_offers_the_set(session):
    day = date(2027, 1, 7)
    _add_slots(session, {(day, SLOT_EARLY): schedule.CLOSED})

    with schedule.schedule_overlay(session, day, day):
        assert schedule.formats_for(day, SLOT_EARLY) == ()
        assert schedule.formats_for(day, SLOT_LATE) == (active_set_code(),)


def test_the_rotation_day_is_found_inside_the_rendered_span():
    assert schedule.rotation_in(schedule.calendar_days(date(2026, 3, 5), 1)) == date(2026, 3, 3)


def test_the_arrival_line_drops_once_the_rotation_has_happened():
    days = schedule.calendar_days(date(2026, 3, 5), 1)
    noon = datetime.combine(date(2026, 3, 3), time(12, 0), tzinfo=RELEASE_TZ)

    before = arrival_line(None, days, noon - timedelta(hours=1))
    after = arrival_line(None, days, noon + timedelta(hours=1))

    assert before != ""
    assert after == ""


def test_a_span_marks_every_rotation_it_holds():
    span = schedule.calendar_days(date(2026, 8, 10), 8)

    assert [day for day in span if schedule.is_rotation_day(day)] == [date(2026, 8, 11), date(2026, 9, 29)]


def test_a_rotation_already_made_is_not_the_one_still_ahead():
    span = schedule.calendar_days(date(2026, 8, 10), 8)
    after_the_first = datetime(2026, 8, 12, 12, 0, tzinfo=RELEASE_TZ)

    assert schedule.rotation_in(span) == date(2026, 8, 11)
    assert schedule.rotation_in(span, after_the_first) == date(2026, 9, 29)


def test_a_span_inside_one_set_has_no_rotation():
    assert schedule.rotation_in(schedule.calendar_days(date(2026, 3, 12), 1)) is None


def test_the_calendar_starts_on_the_monday_of_the_week_it_covers():
    days = schedule.calendar_days(date(2026, 3, 5), 2)

    assert days[0] == date(2026, 3, 2)
    assert days[-1] == date(2026, 3, 15)
    assert len(days) == 14
