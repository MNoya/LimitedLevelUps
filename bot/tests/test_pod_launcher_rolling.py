from datetime import datetime, time, timedelta

import pytest

from bot.commands.test_group import HALL_OF_FAME
from bot.config import settings
from bot.models import PodSignal, PodSignalMember
from bot.services import pod_launch
from bot.services.pod_launch import LauncherSlot, create_poll_signals
from bot.services.pod_signals import (
    KIND_POLL,
    LANE_EARLY,
    LANE_LATE,
    SCHEDULE_TZ,
    STATUS_EXPIRED,
    STATUS_FIRED,
    STATUS_OPEN,
    bucket_for_lane,
    lane_of,
    slot_can_fire,
    slot_event_time,
)
from bot.tasks.pod_daily_poll import (
    _confirm_slot_states,
    _lane_order,
    _lane_slots,
    _representative_slot,
)


DAYS_TO_FRIDAY = ((4 - datetime.now(SCHEDULE_TZ).date().weekday()) % 7) or 7
FRIDAY = datetime.now(SCHEDULE_TZ).date() + timedelta(days=DAYS_TO_FRIDAY)
SATURDAY = FRIDAY + timedelta(days=1)
FRIDAY_AFTERNOON = datetime.combine(FRIDAY, time(16, 0), tzinfo=SCHEDULE_TZ)


# --- lanes ---

def test_weekday_and_weekend_buckets_of_one_time_share_a_lane():
    friday_late = bucket_for_lane(FRIDAY, LANE_LATE)
    saturday_late = bucket_for_lane(SATURDAY, LANE_LATE)

    assert friday_late.key != saturday_late.key
    assert lane_of(friday_late.key) == lane_of(saturday_late.key) == LANE_LATE
    assert friday_late.role_name != saturday_late.role_name


@pytest.mark.parametrize(
    "slot_day, expected",
    [(FRIDAY, True), (SATURDAY, False)],
)
def test_a_slot_fires_only_once_its_own_day_is_live(slot_day, expected):
    assert slot_can_fire(slot_event_time(slot_day, "LATE"), FRIDAY_AFTERNOON) is expected


# --- rolled columns ---

def _played(bucket_key, day, winner="Finkel"):
    return LauncherSlot(
        bucket_key, committed=True, status=STATUS_FIRED, count=8, slot_time=slot_event_time(day, bucket_key),
        names=list(HALL_OF_FAME[:8]), thread_id="1", signal_id=None, thread_name="MSH Jul 24 Late Pod",
        finished=True, winner=winner, winner_slug="finkel",
    )


def _committed_card(bucket_key, day, *, card_message_id):
    return LauncherSlot(
        bucket_key, committed=True, status=STATUS_FIRED, count=4, slot_time=slot_event_time(day, bucket_key),
        names=list(HALL_OF_FAME[:4]), thread_id="1", signal_id=None, card_message_id=card_message_id,
        card_channel_id="2", thread_name="MSH Jul 24 Late Pod",
    )


def _gathering(bucket_key, day, status=STATUS_OPEN, count=2):
    return LauncherSlot(
        bucket_key, committed=False, status=status, count=count,
        slot_time=slot_event_time(day, bucket_key), names=list(HALL_OF_FAME[:count]),
        thread_id=None, signal_id=f"sig-{bucket_key}-{day}",
    )


def test_a_rolled_column_stays_one_column_across_the_weekend_boundary():
    slots = [_played("LATE", FRIDAY), _gathering("EVENING", SATURDAY)]

    lanes = _lane_order(slots)

    assert lanes == [LANE_LATE]
    assert [slot.bucket_key for slot in _lane_slots(slots, LANE_LATE)] == ["LATE", "EVENING"]


def test_the_column_button_targets_the_gathering_slot_not_the_played_pod():
    slots = [_played("LATE", FRIDAY), _gathering("EVENING", SATURDAY)]

    representative = _representative_slot(slots, LANE_LATE)

    assert representative.bucket_key == "EVENING"
    assert representative.committed is False


def test_the_column_button_falls_back_to_the_played_pod_while_it_is_the_only_slot():
    slots = [_played("LATE", FRIDAY)]

    assert _representative_slot(slots, LANE_LATE).committed is True


def test_the_preference_picker_offers_one_confirm_per_column():
    slots = [
        _played("EARLY", FRIDAY), _gathering("EARLY", SATURDAY),
        _played("LATE", FRIDAY), _gathering("EVENING", SATURDAY),
    ]

    states = _confirm_slot_states(slots)

    assert [bucket_key for bucket_key, _open, _card in states] == ["EARLY", "EVENING"]
    assert [card for _bucket_key, _open, card in states] == [None, None]


def test_the_preference_picker_confirms_onto_the_card_of_a_committed_column():
    slots = [_committed_card("LATE", FRIDAY, card_message_id="777")]

    states = _confirm_slot_states(slots)

    assert states == [("LATE", True, "777")]


def test_a_dead_slot_is_dropped_once_the_column_rolled_past_it():
    lane_slots = [
        _gathering("EARLY", FRIDAY, status=STATUS_EXPIRED, count=1),
        _gathering("AFTERNOON", SATURDAY),
    ]

    kept = pod_launch._without_rolled_past_slots(lane_slots)

    assert [slot.bucket_key for slot in kept] == ["AFTERNOON"]


def test_a_dead_slot_stays_while_the_column_has_not_rolled():
    lane_slots = [_gathering("EARLY", FRIDAY, status=STATUS_EXPIRED, count=1)]

    assert pod_launch._without_rolled_past_slots(lane_slots) == lane_slots


def test_a_played_pod_is_never_dropped_by_a_roll():
    lane_slots = [_played("LATE", FRIDAY), _gathering("EVENING", SATURDAY)]

    kept = pod_launch._without_rolled_past_slots(lane_slots)

    assert [slot.bucket_key for slot in kept] == ["LATE", "EVENING"]


# --- adopt or create ---

def test_the_morning_post_adopts_a_rolled_slot_and_keeps_its_signups(session):
    rolled = _seed_signal(session, bucket_for_lane(FRIDAY, LANE_EARLY).key, FRIDAY, message_id="yesterday")
    session.add(PodSignalMember(signal_id=rolled.id, discord_user_id="1", display_name=HALL_OF_FAME[0]))
    session.flush()

    bound = create_poll_signals(
        session, guild_id="g", channel_id="c", message_id="today", signal_date=FRIDAY,
    )

    session.refresh(rolled)
    assert rolled.message_id == "today"
    assert [signal_id for signal_id, _slot_time in bound] == [
        rolled.id, _signal_for(session, bucket_for_lane(FRIDAY, LANE_LATE).key, FRIDAY).id,
    ]
    assert len(rolled.members) == 1


def test_the_morning_post_leaves_a_fired_slot_alone_and_opens_a_fresh_one(session):
    fired = _seed_signal(
        session, bucket_for_lane(FRIDAY, LANE_EARLY).key, FRIDAY, message_id="yesterday",
        status=STATUS_FIRED,
    )

    bound = create_poll_signals(
        session, guild_id="g", channel_id="c", message_id="today", signal_date=FRIDAY,
    )

    session.refresh(fired)
    assert fired.message_id == "yesterday"
    assert fired.id not in [signal_id for signal_id, _slot_time in bound]


def test_rolling_a_lane_opens_the_next_day_and_is_idempotent(session, monkeypatch):
    monkeypatch.setattr("bot.services.pod_launch.SessionLocal", _session_factory(session))

    first = pod_launch.roll_slot_forward_sync(
        lane=LANE_LATE, from_day=FRIDAY, guild_id="g", channel_id="c", message_id="today",
    )
    second = pod_launch.roll_slot_forward_sync(
        lane=LANE_LATE, from_day=FRIDAY, guild_id="g", channel_id="c", message_id="today",
    )

    assert first == second
    signal_id, bucket_key, slot_time = first
    assert bucket_key == bucket_for_lane(SATURDAY, LANE_LATE).key
    assert slot_time == slot_event_time(SATURDAY, bucket_key)
    assert _open_signal_count(session, bucket_key, SATURDAY) == 1


def test_a_rolled_slot_and_todays_slot_share_the_message_and_the_snapshot_stacks_them(session, monkeypatch):
    monkeypatch.setattr("bot.services.pod_launch.SessionLocal", _session_factory(session))
    create_poll_signals(session, guild_id="g", channel_id="c", message_id="today", signal_date=FRIDAY)
    session.commit()
    pod_launch.roll_slot_forward_sync(
        lane=LANE_LATE, from_day=FRIDAY, guild_id="g", channel_id="c", message_id="today",
    )

    slots = pod_launch.launcher_snapshot_sync("today", FRIDAY)

    late_column = [slot for slot in slots if lane_of(slot.bucket_key) == LANE_LATE]
    assert [slot.slot_time for slot in late_column] == [
        slot_event_time(FRIDAY, "LATE"), slot_event_time(SATURDAY, "EVENING"),
    ]
    assert _lane_order(slots) == [LANE_EARLY, LANE_LATE]


def test_the_board_day_ignores_the_days_its_columns_rolled_to(session, monkeypatch):
    monkeypatch.setattr("bot.services.pod_launch.SessionLocal", _session_factory(session))
    create_poll_signals(session, guild_id="g", channel_id="c", message_id="today", signal_date=FRIDAY)
    session.commit()
    pod_launch.roll_slot_forward_sync(
        lane=LANE_LATE, from_day=FRIDAY, guild_id="g", channel_id="c", message_id="today",
    )

    assert pod_launch.launcher_date_for_message_sync("today") == FRIDAY
    assert pod_launch.poll_exists_for_date_sync(FRIDAY) is True
    assert pod_launch.poll_exists_for_date_sync(SATURDAY) is False


def test_held_signups_are_offered_for_graduation_once_their_day_is_live(session, monkeypatch):
    monkeypatch.setattr("bot.services.pod_launch.SessionLocal", _session_factory(session))
    early = _seed_signal(session, "EARLY", FRIDAY, message_id="today")
    late = _seed_signal(session, "LATE", FRIDAY, message_id="today")
    _fill(session, early, settings.pod_signal_fire_threshold)
    _fill(session, late, settings.pod_signal_fire_threshold - 1)
    session.commit()

    candidates = pod_launch.slot_fire_candidates_sync("today", FRIDAY)

    assert [state.signal_id for state in candidates] == [early.id]


def _seed_signal(session, bucket_key, signal_date, *, message_id, status=STATUS_OPEN):
    signal = PodSignal(
        kind=KIND_POLL, bucket=bucket_key, guild_id="g", channel_id="c", message_id=message_id,
        signal_date=signal_date, slot_time=slot_event_time(signal_date, bucket_key), status=status,
    )
    session.add(signal)
    session.flush()
    return signal


def _fill(session, signal, count):
    for index in range(count):
        session.add(PodSignalMember(
            signal_id=signal.id, discord_user_id=str(index), display_name=HALL_OF_FAME[index],
        ))
    session.flush()


def _signal_for(session, bucket_key, signal_date):
    return session.query(PodSignal).filter_by(bucket=bucket_key, signal_date=signal_date).one()


def _open_signal_count(session, bucket_key, signal_date):
    return session.query(PodSignal).filter_by(
        bucket=bucket_key, signal_date=signal_date, status=STATUS_OPEN,
    ).count()


def _session_factory(session):
    class _Ctx:
        def __enter__(self):
            return session

        def __exit__(self, *exc):
            return False

    return lambda: _Ctx()
