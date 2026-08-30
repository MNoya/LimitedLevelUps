from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace

from bot.models import PodScheduleSlot, PodSignal
from bot.services import pod_format_vote as vote
from bot.services.championship_dates import championship_date_for
from bot.services.pod_format_allocator import (
    STAPLE_FORMAT,
    assign_flashbacks,
    day_picks,
    featured_format,
    run_allocation,
)
from bot.services.pod_format import MEMA_CODE
from bot.services.pod_format_schedule import FLASHBACK, latest_on, set_slot
from bot.services.pod_signals import KIND_POLL, SLOT_EARLY, SLOT_LATE

MON = date(2026, 8, 31)
TUE = date(2026, 9, 1)
WED = date(2026, 9, 2)


def _user(uid):
    return SimpleNamespace(id=uid, name=f"u{uid}", display_name=f"U{uid}", avatar=None)


def _seed_floor_votes(session, code):
    for uid in range(1, 7):
        vote.toggle_vote(session, _user(uid), vote.season_code(), code)


def _flashback_days(count, start=MON):
    return [start + timedelta(days=offset) for offset in range(count)]


def test_flashback_sets_never_repeat_back_to_back():
    seq = assign_flashbacks(_flashback_days(6), {"NEO": 3, "FIN": 3})

    assert None not in seq
    assert all(seq[i] != seq[i + 1] for i in range(len(seq) - 1))


def test_flashback_days_split_proportional_to_weighted_score():
    seq = assign_flashbacks(_flashback_days(6), {"NEO": 20, "FIN": 10})

    assert seq.count("NEO") == 4
    assert seq.count("FIN") == 2


def test_a_popular_set_spreads_across_weekdays():
    days = [date(2026, 8, 31) + timedelta(days=offset) for offset in (0, 2, 4, 6, 7, 9, 11, 13)]

    seq = assign_flashbacks(days, {"FIN": 3, "NEO": 1})

    fin_weekdays = {days[i].weekday() for i, code in enumerate(seq) if code == "FIN"}
    assert len(fin_weekdays) > 1


def test_a_day_with_nothing_eligible_stays_empty():
    assert assign_flashbacks(_flashback_days(3), {}) == [None, None, None]


def test_day_picks_pair_by_weekday():
    assert day_picks(MON, "NEO", "HOB", MEMA_CODE) == (MEMA_CODE, "NEO")
    assert day_picks(WED, None, "HOB", MEMA_CODE) == (MEMA_CODE, FLASHBACK)
    assert day_picks(TUE, None, "HOB", MEMA_CODE) == ("HOB", STAPLE_FORMAT)


def test_day_picks_drop_the_featured_slot_when_the_season_has_none():
    assert day_picks(MON, "NEO", "FRA", None) == ("NEO",)
    assert day_picks(TUE, None, "FRA", None) == ("FRA", STAPLE_FORMAT)


def test_a_season_after_the_featured_one_has_no_featured_pick():
    assert featured_format("HOB") == MEMA_CODE
    assert featured_format("FRA") is None


REVEALED = datetime.now(timezone.utc) + timedelta(days=2)


def test_run_allocation_fills_both_slots_and_never_touches_a_manual_row(session):
    _seed_floor_votes(session, "NEO")
    set_slot(session, WED, SLOT_EARLY, ("PEASANT",), source="manual")
    session.commit()

    assignments = run_allocation(session, MON, rewrite=True, now=REVEALED)
    session.commit()

    assert assignments[(MON, SLOT_EARLY)] == (MEMA_CODE, "NEO")
    assert assignments[(MON, SLOT_LATE)] == (MEMA_CODE, "NEO")
    assert assignments[(TUE, SLOT_EARLY)] == (latest_on(TUE), STAPLE_FORMAT)

    manual = session.query(PodScheduleSlot).filter_by(day=WED, slot=SLOT_EARLY).one()
    assert manual.source == "manual"
    assert (WED, SLOT_EARLY) not in assignments
    assert (WED, SLOT_LATE) in assignments


def test_run_allocation_holds_flashbacks_until_a_day_after_the_first_vote(session):
    _seed_floor_votes(session, "NEO")
    session.commit()

    assignments = run_allocation(session, MON, rewrite=True, now=datetime.now(timezone.utc))

    assert assignments[(MON, SLOT_EARLY)] == (MEMA_CODE, FLASHBACK)


def test_run_allocation_ignores_a_set_below_the_vote_floor(session):
    vote.toggle_vote(session, _user(1), vote.season_code(), "NEO")
    session.commit()

    assignments = run_allocation(session, MON, rewrite=True, now=REVEALED)

    assert assignments[(MON, SLOT_EARLY)] == (MEMA_CODE, FLASHBACK)


def test_run_allocation_leaves_a_day_already_on_the_launcher_alone(session):
    _seed_floor_votes(session, "NEO")
    session.add(PodSignal(
        kind=KIND_POLL, bucket="LATE|NEO", guild_id="g", channel_id="c", message_id="m", signal_date=WED,
    ))
    session.commit()

    assignments = run_allocation(session, MON, rewrite=True)

    assert (WED, SLOT_EARLY) not in assignments
    assert (WED, SLOT_LATE) not in assignments
    assert (MON, SLOT_EARLY) in assignments


def test_run_allocation_leaves_the_championship_day_alone(session):
    _seed_floor_votes(session, "NEO")
    session.commit()
    champ = championship_date_for(date(2026, 9, 15))

    assignments = run_allocation(session, MON, rewrite=True)

    assert (champ, SLOT_EARLY) not in assignments
    assert (champ, SLOT_LATE) not in assignments
