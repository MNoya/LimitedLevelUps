from dataclasses import replace
from datetime import datetime, time, timedelta

import pytest
from sqlalchemy import select

from bot.commands.test_group import HALL_OF_FAME
from bot.config import settings
from bot.models import PodDraftEvent, PodSignal, PodSignalMember
from bot.services import pod_format_schedule as schedule
from bot.services import pod_launch
from bot.services.pod_launch import LauncherSlot, create_poll_signals
from bot.services.pod_signals import (
    KIND_POLL,
    KIND_SCHEDULED,
    LANE_EARLY,
    LANE_LATE,
    SCHEDULE_TZ,
    SCHEDULED_BUCKET,
    STATUS_EXPIRED,
    STATUS_FIRED,
    STATUS_OPEN,
    bucket_for_lane,
    lane_of,
    named_bucket_key,
    next_lane_start,
    slot_can_fire,
    slot_event_time,
    time_key_of,
)
from bot.tasks.pod_daily_poll import (
    _lane_order,
    _lane_slots,
    _gathering_groups,
    _group_block,
    _played_on_day,
    _shared_roster_names,
    _slot_by_key,
    _slot_item,
)


DAYS_TO_FRIDAY = ((4 - datetime.now(SCHEDULE_TZ).date().weekday()) % 7) or 7
FRIDAY = datetime.now(SCHEDULE_TZ).date() + timedelta(days=DAYS_TO_FRIDAY)
SATURDAY = FRIDAY + timedelta(days=1)
FRIDAY_AFTERNOON = datetime.combine(FRIDAY, time(16, 0), tzinfo=SCHEDULE_TZ)
THRESHOLD = settings.pod_signal_fire_threshold
EARLIER = datetime(2026, 7, 26, 9, 0, tzinfo=SCHEDULE_TZ)
LATER = EARLIER + timedelta(hours=5)


# --- lanes ---

@pytest.mark.parametrize("lane, called_at, expected_start", [
    (LANE_EARLY, datetime(2026, 7, 26, 0, 35, tzinfo=SCHEDULE_TZ), datetime(2026, 7, 26, 14, 0)),
    (LANE_EARLY, datetime(2026, 7, 26, 15, 0, tzinfo=SCHEDULE_TZ), datetime(2026, 7, 27, 14, 0)),
    (LANE_LATE, datetime(2026, 7, 26, 15, 0, tzinfo=SCHEDULE_TZ), datetime(2026, 7, 26, 20, 0)),
    (LANE_LATE, datetime(2026, 7, 26, 21, 0, tzinfo=SCHEDULE_TZ), datetime(2026, 7, 27, 20, 0)),
    (LANE_EARLY, datetime(2026, 11, 1, 20, 0, tzinfo=SCHEDULE_TZ), datetime(2026, 11, 2, 14, 0)),
    (LANE_LATE, datetime(2026, 7, 25, 15, 0, tzinfo=SCHEDULE_TZ), datetime(2026, 7, 25, 21, 0)),
    (LANE_LATE, datetime(2026, 7, 24, 21, 30, tzinfo=SCHEDULE_TZ), datetime(2026, 7, 25, 21, 0)),
])
def test_a_slot_rolls_to_tomorrow_once_todays_start_has_passed(lane, called_at, expected_start):
    start = next_lane_start(lane, called_at)

    assert start == expected_start.replace(tzinfo=SCHEDULE_TZ)


def test_buckets_of_one_time_share_a_lane_across_the_week():
    friday_late = bucket_for_lane(FRIDAY, LANE_LATE)
    saturday_late = bucket_for_lane(SATURDAY, LANE_LATE)

    assert friday_late.key != saturday_late.key
    assert lane_of(friday_late.key) == lane_of(saturday_late.key) == LANE_LATE
    assert friday_late.role_name == saturday_late.role_name


@pytest.mark.parametrize(
    "slot_day, expected",
    [(FRIDAY, True), (SATURDAY, False)],
)
def test_a_slot_fires_only_once_its_own_day_is_live(slot_day, expected):
    assert slot_can_fire(slot_event_time(slot_day, "LATE"), FRIDAY_AFTERNOON) is expected


# --- rolled columns ---

LATEST = schedule.latest_on(FRIDAY)
ROLLED_LATEST = schedule.latest_on(SATURDAY)


def _played(bucket_key, day, winner="Finkel"):
    return LauncherSlot(
        named_bucket_key(bucket_key, LATEST), committed=True, status=STATUS_FIRED, count=8,
        slot_time=slot_event_time(day, bucket_key), set_code=LATEST,
        names=list(HALL_OF_FAME[:8]), thread_id="1", signal_id=None, thread_name="MSH Jul 24 Late Pod",
        finished=True, locked=True, winner=winner, winner_slug="finkel",
        created_at=slot_event_time(day, bucket_key) - timedelta(hours=3),
    )


def _drafting(bucket_key, day):
    """A pod whose draft started but is not finalized, the only state a closed slot beside it still has a
    late seat to ask for."""
    return replace(_played(bucket_key, day), finished=False, winner=None, winner_slug=None)


def _committed_card(bucket_key, day, *, card_message_id):
    return LauncherSlot(
        named_bucket_key(bucket_key, LATEST), committed=True, status=STATUS_FIRED, count=4,
        slot_time=slot_event_time(day, bucket_key), set_code=LATEST,
        names=list(HALL_OF_FAME[:4]), thread_id="1", signal_id=None, card_message_id=card_message_id,
        card_channel_id="2", thread_name="MSH Jul 24 Late Pod",
    )


def _gathering(bucket_key, day, status=STATUS_OPEN, count=2, set_code=LATEST):
    return LauncherSlot(
        named_bucket_key(bucket_key, set_code), committed=False, status=status, count=count,
        slot_time=slot_event_time(day, bucket_key), names=list(HALL_OF_FAME[:count]),
        thread_id=None, signal_id=f"sig-{bucket_key}-{set_code}-{day}", set_code=set_code,
    )


def test_a_rolled_column_stays_one_column_across_the_weekend_boundary():
    slots = [_played("LATE", FRIDAY), _gathering("EVENING", SATURDAY)]

    lanes = _lane_order(slots)

    assert lanes == [LANE_LATE]
    assert [slot.set_code for slot in _lane_slots(slots, LANE_LATE)] == [LATEST, LATEST]


def test_a_press_targets_the_pod_its_own_key_names():
    slots = [
        _gathering("LATE", FRIDAY, set_code=LATEST),
        _gathering("LATE", FRIDAY, set_code="PEASANT", count=3),
    ]

    pressed = _slot_by_key(slots, named_bucket_key("LATE", "PEASANT"))

    assert pressed.set_code == "PEASANT"
    assert pressed.count == 3


def test_a_press_on_a_rolled_column_targets_the_joinable_day_not_the_played_pod():
    slots = [_played("LATE", FRIDAY), _gathering("LATE", SATURDAY)]

    pressed = _slot_by_key(slots, named_bucket_key("LATE", LATEST))

    assert pressed.committed is False
    assert pressed.slot_time == slot_event_time(SATURDAY, "LATE")


def test_a_press_falls_back_to_the_played_pod_while_it_is_the_only_one():
    slots = [_played("LATE", FRIDAY)]

    assert _slot_by_key(slots, named_bucket_key("LATE", LATEST)).committed is True


def test_a_dead_slot_is_dropped_once_the_column_rolled_past_it():
    lane_slots = [
        _gathering("EARLY", FRIDAY, status=STATUS_EXPIRED, count=1),
        _gathering("AFTERNOON", SATURDAY),
    ]

    kept = pod_launch._without_rolled_past_slots(lane_slots)

    assert [slot.slot_time for slot in kept] == [slot_event_time(SATURDAY, "AFTERNOON")]


def test_a_dead_slot_stays_while_the_column_has_not_rolled():
    lane_slots = [_gathering("EARLY", FRIDAY, status=STATUS_EXPIRED, count=1)]

    assert pod_launch._without_rolled_past_slots(lane_slots) == lane_slots


def test_a_played_pod_is_never_dropped_by_a_roll():
    lane_slots = [_played("LATE", FRIDAY), _gathering("EVENING", SATURDAY)]

    kept = pod_launch._without_rolled_past_slots(lane_slots)

    assert [slot.slot_time for slot in kept] == [
        slot_event_time(FRIDAY, "LATE"), slot_event_time(SATURDAY, "EVENING"),
    ]


@pytest.mark.parametrize("slot, expected", [
    (_played("LATE", FRIDAY), True),
    (_played("EVENING", SATURDAY), False),
    (_gathering("EARLY", FRIDAY), False),
])
def test_a_retired_board_keeps_only_the_pods_its_own_day_played(slot, expected):
    assert _played_on_day(slot, FRIDAY) is expected


@pytest.mark.parametrize("slots, gathering_codes", [
    ([_played("LATE", FRIDAY), _gathering("LATE", FRIDAY, set_code="PEASANT")], [["PEASANT"]]),
    ([_played("LATE", FRIDAY), _gathering("EVENING", SATURDAY)], [[LATEST]]),
    ([_gathering("LATE", FRIDAY), _gathering("LATE", FRIDAY, set_code="PEASANT")], [[LATEST, "PEASANT"]]),
    ([_played("LATE", FRIDAY)], []),
])
def test_a_column_offers_only_the_pods_still_taking_signups(slots, gathering_codes):
    groups = _gathering_groups(slots)

    assert [[slot.set_code for slot in group] for group in groups] == gathering_codes


@pytest.mark.parametrize("beside, links_to_pod", [
    ([_drafting("LATE", FRIDAY)], True),
    ([_played("LATE", FRIDAY)], False),
    ([_committed_card("LATE", FRIDAY, card_message_id="1")], False),
    ([_gathering("LATE", FRIDAY)], False),
    ([_drafting("LATE", FRIDAY), _gathering("EVENING", SATURDAY)], False),
    ([], False),
])
def test_a_closed_slot_gives_its_button_to_the_pod_drafting_at_its_time(beside, links_to_pod):
    closed = _gathering("LATE", FRIDAY, status=STATUS_EXPIRED, set_code="PEASANT")

    item = _slot_item(closed, None, beside + [closed])

    assert (item is not None and item.url is not None) is links_to_pod
    assert item is None or not item.disabled


def test_two_closed_formats_at_one_time_point_at_their_pod_once():
    pod = _drafting("LATE", FRIDAY)
    first = _gathering("LATE", FRIDAY, status=STATUS_EXPIRED, set_code="PEASANT")
    second = _gathering("LATE", FRIDAY, status=STATUS_EXPIRED, set_code="CUBE")
    lane_slots = [pod, first, second]

    links = [_slot_item(slot, None, lane_slots) for slot in (first, second)]

    assert [link is not None for link in links] == [True, False]


@pytest.mark.parametrize("status, counts_down", [(STATUS_OPEN, True), (STATUS_EXPIRED, False)])
def test_only_a_time_still_joinable_counts_down(status, counts_down):
    group = [_gathering("LATE", FRIDAY, status=status)]

    block = _group_block(group, None)

    assert (":R>" in block) is counts_down
    assert ":F>" in block


# --- adopt or create ---

def test_the_morning_post_opens_one_pod_per_format_the_day_offers(session, latest_and_peasant):
    bound = create_poll_signals(
        session, guild_id="g", channel_id="c", message_id="today", signal_date=FRIDAY,
    )

    early, late = bucket_for_lane(FRIDAY, LANE_EARLY).key, bucket_for_lane(FRIDAY, LANE_LATE).key
    assert _buckets_of(session, bound) == [
        named_bucket_key(early, LATEST), named_bucket_key(early, "PEASANT"),
        named_bucket_key(late, LATEST), named_bucket_key(late, "PEASANT"),
    ]
    assert len({signal_id for signal_id, _slot_time in bound}) == 4


def test_the_morning_post_adopts_a_rolled_pod_and_keeps_its_signups(session, latest_only):
    early = bucket_for_lane(FRIDAY, LANE_EARLY).key
    rolled = _seed_signal(session, early, FRIDAY, message_id="yesterday")
    session.add(PodSignalMember(signal_id=rolled.id, discord_user_id="1", display_name=HALL_OF_FAME[0]))
    session.flush()

    bound = create_poll_signals(
        session, guild_id="g", channel_id="c", message_id="today", signal_date=FRIDAY,
    )

    session.refresh(rolled)
    assert rolled.message_id == "today"
    assert [signal_id for signal_id, _slot_time in bound][0] == rolled.id
    assert len(rolled.members) == 1


def test_the_morning_post_adopts_a_slot_keyed_before_named_formats_shipped(session, latest_only):
    early = bucket_for_lane(FRIDAY, LANE_EARLY).key
    legacy = _seed_signal(session, early, FRIDAY, message_id="yesterday", bucket_key=early)
    session.add(PodSignalMember(signal_id=legacy.id, discord_user_id="1", display_name=HALL_OF_FAME[0]))
    session.flush()

    create_poll_signals(session, guild_id="g", channel_id="c", message_id="today", signal_date=FRIDAY)

    session.refresh(legacy)
    assert legacy.bucket == named_bucket_key(early, LATEST)
    assert legacy.set_code == LATEST
    assert len(legacy.members) == 1


def test_the_morning_post_leaves_a_fired_pod_alone_and_opens_a_fresh_one(session, latest_only):
    early = bucket_for_lane(FRIDAY, LANE_EARLY).key
    fired = _seed_signal(session, early, FRIDAY, message_id="yesterday", status=STATUS_FIRED)

    bound = create_poll_signals(
        session, guild_id="g", channel_id="c", message_id="today", signal_date=FRIDAY,
    )

    session.refresh(fired)
    assert fired.message_id == "yesterday"
    assert fired.id not in [signal_id for signal_id, _slot_time in bound]


def test_a_slot_that_already_closed_unfired_is_not_reopened_on_a_second_board(session, latest_only):
    early = bucket_for_lane(FRIDAY, LANE_EARLY).key
    closed = _seed_signal(session, early, FRIDAY, message_id="morning", status=STATUS_EXPIRED)

    bound = create_poll_signals(
        session, guild_id="g", channel_id="c", message_id="evening", signal_date=FRIDAY,
    )

    rows = session.execute(
        select(PodSignal).where(PodSignal.bucket == named_bucket_key(early, LATEST))
    ).scalars().all()
    assert [row.id for row in rows] == [closed.id]
    assert closed.id not in [signal_id for signal_id, _slot_time in bound]


def test_a_pod_that_exists_is_skipped_and_the_other_format_still_opens(session, latest_and_peasant):
    early = bucket_for_lane(FRIDAY, LANE_EARLY).key
    _seed_pod(session, slot_event_time(FRIDAY, early), set_code=LATEST)

    bound = create_poll_signals(
        session, guild_id="g", channel_id="c", message_id="today", signal_date=FRIDAY,
    )

    assert named_bucket_key(early, "PEASANT") in _buckets_of(session, bound)
    assert named_bucket_key(early, LATEST) not in _buckets_of(session, bound)


def test_a_drafting_pod_leaves_the_other_format_at_its_slot_gathering(session, monkeypatch, latest_and_peasant):
    monkeypatch.setattr("bot.services.pod_launch.SessionLocal", _session_factory(session))
    early = bucket_for_lane(FRIDAY, LANE_EARLY).key
    create_poll_signals(session, guild_id="g", channel_id="c", message_id="today", signal_date=FRIDAY)
    _seed_pod(session, slot_event_time(FRIDAY, early), set_code=LATEST, socket_status="draft_done")
    session.commit()

    slots = pod_launch.launcher_snapshot_sync("today", FRIDAY)

    early_column = [slot for slot in slots if lane_of(slot.bucket_key) == LANE_EARLY]
    assert [(slot.set_code, slot.locked) for slot in early_column] == [(LATEST, True), ("PEASANT", False)]


def test_a_pod_waiting_in_its_lobby_is_not_locked_yet(session, monkeypatch, latest_only):
    monkeypatch.setattr("bot.services.pod_launch.SessionLocal", _session_factory(session))
    early = bucket_for_lane(FRIDAY, LANE_EARLY).key
    _seed_pod(session, slot_event_time(FRIDAY, early), set_code=LATEST, socket_status="connected")
    session.commit()

    slots = pod_launch.launcher_snapshot_sync("today", FRIDAY)

    lobby_open = [slot for slot in slots if slot.set_code == LATEST and slot.committed][0]
    assert lobby_open.locked is False


def test_both_tables_of_a_split_pod_reach_the_column(session, monkeypatch, latest_only):
    monkeypatch.setattr("bot.services.pod_launch.SessionLocal", _session_factory(session))
    slot_time = slot_event_time(FRIDAY, bucket_for_lane(FRIDAY, LANE_EARLY).key)
    _seed_pod(session, slot_time, set_code=LATEST, name=f"{LATEST} pod 1", created_at=EARLIER)
    _seed_pod(session, slot_time, set_code=LATEST, name=f"{LATEST} pod 2", created_at=LATER)
    session.commit()

    slots = pod_launch.launcher_snapshot_sync("today", FRIDAY)

    assert [slot.thread_name for slot in slots if slot.committed] == [f"{LATEST} pod 1", f"{LATEST} pod 2"]


def test_a_later_signup_at_one_slot_leaves_the_earlier_pod_off_the_column(session, monkeypatch, latest_only):
    monkeypatch.setattr("bot.services.pod_launch.SessionLocal", _session_factory(session))
    slot_time = slot_event_time(FRIDAY, bucket_for_lane(FRIDAY, LANE_EARLY).key)
    _seed_pod(session, slot_time, set_code=LATEST, name=f"{LATEST} pod", created_at=EARLIER)
    _seed_pod(session, slot_time, set_code=LATEST, name=f"{LATEST} pod #2", created_at=LATER)
    session.commit()

    slots = pod_launch.launcher_snapshot_sync("today", FRIDAY)

    assert [slot.thread_name for slot in slots if slot.committed] == [f"{LATEST} pod #2"]


def test_a_lane_looks_at_tomorrow_for_a_pod_its_closed_slot_can_never_open(session, monkeypatch):
    """The Set Championship sits on a slot the format schedule closes, so no signal ever reaches its day and
    the lane it holds would never look there. The launcher is what players read the night before, so a pod
    that already exists at tomorrow's slot is found without one. The lane with nothing tomorrow stays put."""
    monkeypatch.setattr("bot.services.pod_launch.SessionLocal", _session_factory(session))
    monkeypatch.setattr(
        "bot.services.pod_format_schedule.FORMATS_BY_DAY", {(SATURDAY, LANE_EARLY): schedule.CLOSED},
    )
    afternoon = bucket_for_lane(SATURDAY, LANE_EARLY).key
    _seed_pod(
        session, slot_event_time(SATURDAY, afternoon), set_code=LATEST, name="👑 MSH Set Championship",
    )
    session.commit()

    slots = pod_launch.launcher_snapshot_sync("today", FRIDAY)

    early = [slot for slot in slots if lane_of(slot.bucket_key) == LANE_EARLY]
    late = [slot for slot in slots if lane_of(slot.bucket_key) == LANE_LATE]
    assert [(slot.championship, slot.slot_time) for slot in early if slot.committed] == [
        (True, slot_event_time(SATURDAY, afternoon)),
    ]
    assert [slot.slot_time for slot in late] == [slot_event_time(FRIDAY, bucket_for_lane(FRIDAY, LANE_LATE).key)]


def test_a_closed_slot_opens_no_pod_while_the_other_slot_still_does(session, monkeypatch):
    monkeypatch.setattr(
        "bot.services.pod_format_schedule.FORMATS_BY_DAY",
        {FRIDAY: (schedule.LATEST,), (FRIDAY, LANE_EARLY): schedule.CLOSED},
    )

    bound = create_poll_signals(
        session, guild_id="g", channel_id="c", message_id="today", signal_date=FRIDAY,
    )

    late = bucket_for_lane(FRIDAY, LANE_LATE).key
    assert _buckets_of(session, bound) == [named_bucket_key(late, LATEST)]


def test_rolling_into_a_closed_slot_opens_nothing(session, monkeypatch):
    monkeypatch.setattr("bot.services.pod_launch.SessionLocal", _session_factory(session))
    monkeypatch.setattr(
        "bot.services.pod_format_schedule.FORMATS_BY_DAY", {(SATURDAY, LANE_LATE): schedule.CLOSED},
    )

    rolled = pod_launch.roll_slot_forward_sync(
        lane=LANE_LATE, from_day=FRIDAY, guild_id="g", channel_id="c", message_id="today",
    )

    assert rolled == []


def test_rolling_a_lane_opens_the_next_day_and_is_idempotent(session, monkeypatch, latest_only):
    monkeypatch.setattr("bot.services.pod_launch.SessionLocal", _session_factory(session))

    first = pod_launch.roll_slot_forward_sync(
        lane=LANE_LATE, from_day=FRIDAY, guild_id="g", channel_id="c", message_id="today",
    )
    second = pod_launch.roll_slot_forward_sync(
        lane=LANE_LATE, from_day=FRIDAY, guild_id="g", channel_id="c", message_id="today",
    )

    assert first == second
    signal_id, bucket_key, slot_time = first[0]
    time_key = bucket_for_lane(SATURDAY, LANE_LATE).key
    assert bucket_key == named_bucket_key(time_key, ROLLED_LATEST)
    assert slot_time == slot_event_time(SATURDAY, time_key)
    assert _open_signal_count(session, bucket_key, SATURDAY) == 1


def test_rolling_a_lane_opens_every_format_the_next_day_offers(session, monkeypatch, latest_and_peasant):
    monkeypatch.setattr("bot.services.pod_launch.SessionLocal", _session_factory(session))

    rolled = pod_launch.roll_slot_forward_sync(
        lane=LANE_LATE, from_day=FRIDAY, guild_id="g", channel_id="c", message_id="today",
    )

    time_key = bucket_for_lane(SATURDAY, LANE_LATE).key
    assert [bucket_key for _signal_id, bucket_key, _slot_time in rolled] == [
        named_bucket_key(time_key, ROLLED_LATEST), named_bucket_key(time_key, "PEASANT"),
    ]


def test_a_rolled_slot_and_todays_slot_share_the_message_and_the_snapshot_stacks_them(
    session, monkeypatch, latest_only,
):
    monkeypatch.setattr("bot.services.pod_launch.SessionLocal", _session_factory(session))
    create_poll_signals(session, guild_id="g", channel_id="c", message_id="today", signal_date=FRIDAY)
    session.commit()
    pod_launch.roll_slot_forward_sync(
        lane=LANE_LATE, from_day=FRIDAY, guild_id="g", channel_id="c", message_id="today",
    )

    slots = pod_launch.launcher_snapshot_sync("today", FRIDAY)

    late_column = [slot for slot in slots if lane_of(slot.bucket_key) == LANE_LATE]
    assert [slot.slot_time for slot in late_column] == [
        slot_event_time(FRIDAY, "LATE"), slot_event_time(SATURDAY, bucket_for_lane(SATURDAY, LANE_LATE).key),
    ]
    assert _lane_order(slots) == [LANE_EARLY, LANE_LATE]


def test_the_board_day_ignores_the_days_its_columns_rolled_to(session, monkeypatch, latest_only):
    monkeypatch.setattr("bot.services.pod_launch.SessionLocal", _session_factory(session))
    create_poll_signals(session, guild_id="g", channel_id="c", message_id="today", signal_date=FRIDAY)
    session.commit()
    pod_launch.roll_slot_forward_sync(
        lane=LANE_LATE, from_day=FRIDAY, guild_id="g", channel_id="c", message_id="today",
    )

    assert pod_launch.launcher_date_for_message_sync("today") == FRIDAY
    assert pod_launch.poll_exists_for_date_sync(FRIDAY) is True
    assert pod_launch.poll_exists_for_date_sync(SATURDAY) is False


# --- render order ---

def test_a_slot_renders_the_latest_set_first_however_its_rows_come_back(session, monkeypatch, latest_and_peasant):
    monkeypatch.setattr("bot.services.pod_launch.SessionLocal", _session_factory(session))
    early = bucket_for_lane(FRIDAY, LANE_EARLY).key
    peasant = _seed_signal(session, early, FRIDAY, message_id="today", set_code="PEASANT")
    latest = _seed_signal(session, early, FRIDAY, message_id="today")
    _fill(session, peasant, 2, prefix="peasant")
    session.commit()

    slots = pod_launch.launcher_snapshot_sync("today", FRIDAY)

    early_column = [slot for slot in slots if lane_of(slot.bucket_key) == LANE_EARLY]
    assert [slot.set_code for slot in early_column] == [LATEST, "PEASANT"]
    assert [slot.signal_id for slot in early_column] == [latest.id, peasant.id]


def test_the_shared_marker_reads_every_pod_of_a_slot_whatever_state_it_is_in():
    fired = _marker_slot(LATEST, [HALL_OF_FAME[0], HALL_OF_FAME[1]], committed=True)
    gathering = _marker_slot("PEASANT", [HALL_OF_FAME[1], HALL_OF_FAME[2]])
    organized = _marker_slot("NEO", [HALL_OF_FAME[2], HALL_OF_FAME[3]], committed=True)

    shared = _shared_roster_names([fired, gathering, organized])

    assert shared == {HALL_OF_FAME[1], HALL_OF_FAME[2]}


# --- firing ---

def test_a_pod_graduates_on_its_own_signup_count(session, monkeypatch, latest_and_peasant):
    monkeypatch.setattr("bot.services.pod_launch.SessionLocal", _session_factory(session))
    full = _seed_signal(session, "EARLY", FRIDAY, message_id="today", set_code="PEASANT")
    short = _seed_signal(session, "LATE", FRIDAY, message_id="today")
    _fill(session, full, THRESHOLD)
    _fill(session, short, THRESHOLD - 1)
    session.commit()

    candidates = pod_launch.slot_fire_candidates_sync("today", FRIDAY)

    assert [state.signal_id for state in candidates] == [full.id]


def test_the_fullest_pod_graduates_first_and_a_tie_goes_to_the_latest_set(
    session, monkeypatch, latest_and_peasant,
):
    monkeypatch.setattr("bot.services.pod_launch.SessionLocal", _session_factory(session))
    early_peasant = _seed_signal(session, "EARLY", FRIDAY, message_id="today", set_code="PEASANT")
    early_latest = _seed_signal(session, "EARLY", FRIDAY, message_id="today")
    late_peasant = _seed_signal(session, "LATE", FRIDAY, message_id="today", set_code="PEASANT")
    _fill(session, early_peasant, THRESHOLD, prefix="ep")
    _fill(session, early_latest, THRESHOLD, prefix="el")
    _fill(session, late_peasant, THRESHOLD + 2, prefix="lp")
    session.commit()

    candidates = pod_launch.slot_fire_candidates_sync("today", FRIDAY)

    assert [state.signal_id for state in candidates] == [
        late_peasant.id, early_latest.id, early_peasant.id,
    ]


def test_a_claim_is_refused_once_a_pod_beside_it_took_the_shared_signups(session, monkeypatch, latest_only):
    monkeypatch.setattr("bot.services.pod_launch.SessionLocal", _session_factory(session))
    signal = _seed_signal(session, "EARLY", FRIDAY, message_id="today")
    _fill(session, signal, THRESHOLD - 1)
    session.commit()

    assert pod_launch.claim_slot_fire_sync(signal.id) is False


def test_a_pod_that_fires_leaves_the_roster_of_the_format_beside_it_alone(
    session, monkeypatch, latest_and_peasant,
):
    monkeypatch.setattr("bot.services.pod_launch.SessionLocal", _session_factory(session))
    firing = _seed_signal(session, "EARLY", FRIDAY, message_id="today")
    beside = _seed_signal(session, "EARLY", FRIDAY, message_id="today", set_code="PEASANT")
    _fill(session, firing, THRESHOLD - 1, prefix="own")
    _fill(session, beside, THRESHOLD - 1, prefix="theirs")
    _fill(session, firing, 2, prefix="both")
    _fill(session, beside, 2, prefix="both")
    session.commit()

    pod_launch.claim_slot_fire_sync(firing.id)

    assert len(pod_launch.poll_yes_members_sync(firing.id)) == THRESHOLD + 1
    assert len(beside.members) == THRESHOLD + 1


# --- reposting ---

def test_reposting_a_board_carries_the_column_that_already_rolled_to_tomorrow(
    session, monkeypatch, latest_only,
):
    monkeypatch.setattr("bot.services.pod_launch.SessionLocal", _session_factory(session))
    early = bucket_for_lane(FRIDAY, LANE_EARLY).key
    late = bucket_for_lane(FRIDAY, LANE_LATE).key
    _seed_signal(session, early, SATURDAY, message_id="today")
    tonight = _seed_signal(session, late, FRIDAY, message_id="today")
    _join(session, tonight, "player", "Finkel")
    session.commit()

    moved = pod_launch.rebind_launcher_rows_sync("today", "resurfaced")

    resurfaced = pod_launch.launcher_snapshot_sync("resurfaced", FRIDAY)
    superseded = pod_launch.launcher_snapshot_sync("today", FRIDAY)
    assert moved == 2
    assert [entry.signal_id for entry in superseded] == [None, None]
    assert [(entry.bucket_key, entry.count) for entry in resurfaced if entry.signal_id] == [
        (named_bucket_key(early, LATEST), 0), (named_bucket_key(late, LATEST), 1),
    ]


def test_reposting_a_board_leaves_behind_a_row_the_new_one_already_carries(
    session, monkeypatch, latest_only,
):
    monkeypatch.setattr("bot.services.pod_launch.SessionLocal", _session_factory(session))
    early = bucket_for_lane(FRIDAY, LANE_EARLY).key
    late = bucket_for_lane(FRIDAY, LANE_LATE).key
    duplicate = _seed_signal(session, early, FRIDAY, message_id="today", status=STATUS_EXPIRED)
    _seed_signal(session, early, FRIDAY, message_id="resurfaced", status=STATUS_EXPIRED)
    tomorrow = _seed_signal(session, late, SATURDAY, message_id="today")
    session.commit()

    moved = pod_launch.rebind_launcher_rows_sync("today", "resurfaced")

    session.refresh(duplicate)
    session.refresh(tomorrow)
    assert moved == 1
    assert duplicate.message_id == "today"
    assert tomorrow.message_id == "resurfaced"


def test_a_day_left_holding_two_boards_retires_both(session, monkeypatch, latest_only):
    monkeypatch.setattr("bot.services.pod_launch.SessionLocal", _session_factory(session))
    early = bucket_for_lane(FRIDAY, LANE_EARLY).key
    _seed_signal(session, early, FRIDAY, message_id="morning", status=STATUS_EXPIRED)
    _seed_signal(session, early, FRIDAY, message_id="evening", status=STATUS_EXPIRED, set_code="PEASANT")
    session.commit()

    boards = pod_launch.past_launcher_boards_sync(SATURDAY, FRIDAY - timedelta(days=3))

    assert {message_id for _channel_id, message_id, _day in boards} == {"morning", "evening"}


# --- leaving ---

def test_leaving_the_board_drops_the_player_from_every_pod_still_gathering(session, monkeypatch, latest_only):
    monkeypatch.setattr("bot.services.pod_launch.SessionLocal", _session_factory(session))
    early = bucket_for_lane(FRIDAY, LANE_EARLY).key
    late = bucket_for_lane(FRIDAY, LANE_LATE).key
    early_latest = _seed_signal(session, early, FRIDAY, message_id="today")
    early_peasant = _seed_signal(session, early, FRIDAY, message_id="today", set_code="PEASANT")
    late_slot = _seed_signal(session, late, FRIDAY, message_id="today")
    for slot in (early_latest, early_peasant, late_slot):
        _join(session, slot, "leaver", "Finkel")
        _join(session, slot, "stayer", "LSV")
    session.commit()

    left = pod_launch.leave_board_slots_sync("today", "leaver")

    assert [slot.signal_id for slot in left] == [early_latest.id, early_peasant.id, late_slot.id]
    assert _member_ids(session, early_latest) == ["stayer"]
    assert _member_ids(session, late_slot) == ["stayer"]


def test_leaving_one_board_leaves_another_boards_signups_alone(session, monkeypatch, latest_only):
    monkeypatch.setattr("bot.services.pod_launch.SessionLocal", _session_factory(session))
    late = bucket_for_lane(FRIDAY, LANE_LATE).key
    fired = _seed_signal(session, late, FRIDAY, message_id="today", status=STATUS_FIRED)
    tomorrow = _seed_signal(session, late, SATURDAY, message_id="other")
    _join(session, fired, "leaver", "Finkel")
    _join(session, tomorrow, "leaver", "Finkel")
    session.commit()

    left = pod_launch.leave_board_slots_sync("today", "leaver")

    assert left == []
    assert _member_ids(session, fired) == ["leaver"]
    assert _member_ids(session, tomorrow) == ["leaver"]


# --- cancel ---

def test_a_fired_slot_with_no_pod_left_renders_closed(session, monkeypatch, latest_only):
    monkeypatch.setattr("bot.services.pod_launch.SessionLocal", _session_factory(session))
    late = bucket_for_lane(FRIDAY, LANE_LATE).key
    slot = _seed_signal(session, late, FRIDAY, message_id="today", status=STATUS_FIRED)
    _fill(session, slot, THRESHOLD)
    session.commit()

    late_column = [
        entry for entry in pod_launch.launcher_snapshot_sync("today", FRIDAY)
        if lane_of(entry.bucket_key) == LANE_LATE
    ]

    assert [(entry.committed, entry.status) for entry in late_column] == [(False, STATUS_EXPIRED)]


def test_a_fired_slot_still_covered_by_its_pod_renders_as_the_pod(session, monkeypatch, latest_only):
    monkeypatch.setattr("bot.services.pod_launch.SessionLocal", _session_factory(session))
    late = bucket_for_lane(FRIDAY, LANE_LATE).key
    slot = _seed_signal(session, late, FRIDAY, message_id="today", status=STATUS_FIRED)
    _fill(session, slot, THRESHOLD)
    _seed_pod(session, slot_event_time(FRIDAY, late), set_code=LATEST)
    session.commit()

    late_column = [
        entry for entry in pod_launch.launcher_snapshot_sync("today", FRIDAY)
        if lane_of(entry.bucket_key) == LANE_LATE
    ]

    assert [entry.committed for entry in late_column] == [True]


@pytest.mark.parametrize("pod_set_code, expected_match", [(LATEST, True), ("PEASANT", False)])
def test_a_canceled_pod_finds_the_slot_it_fired_out_of(
    session, monkeypatch, latest_only, pod_set_code, expected_match,
):
    monkeypatch.setattr("bot.services.pod_launch.SessionLocal", _session_factory(session))
    late = bucket_for_lane(FRIDAY, LANE_LATE).key
    slot = _seed_signal(session, late, FRIDAY, message_id="today", status=STATUS_FIRED)
    event = _seed_pod(session, slot_event_time(FRIDAY, late), set_code=pod_set_code)
    session.commit()

    found = pod_launch.fired_slot_for_pod_sync(event.id)

    assert found == (slot.id if expected_match else None)


# --- play again ---

@pytest.mark.parametrize("played_lane, expected_lane", [(LANE_EARLY, LANE_EARLY), (LANE_LATE, LANE_LATE)])
def test_play_again_offers_the_slot_a_day_after_the_pod_played(
    session, monkeypatch, latest_only, played_lane, expected_lane,
):
    monkeypatch.setattr("bot.services.pod_launch.SessionLocal", _session_factory(session))
    _seed_signal(session, bucket_for_lane(SATURDAY, LANE_EARLY).key, SATURDAY, message_id="tomorrow")
    _seed_signal(session, bucket_for_lane(SATURDAY, LANE_LATE).key, SATURDAY, message_id="tomorrow")
    played_at = slot_event_time(FRIDAY, bucket_for_lane(FRIDAY, played_lane).key)
    event = _seed_pod(session, played_at, set_code=LATEST)
    session.commit()

    keys = pod_launch.play_again_slots_sync(event.id, played_at)

    expected = bucket_for_lane(SATURDAY, expected_lane).key
    assert [time_key_of(key) for key in keys] == [expected]


def test_play_again_offers_an_off_grid_pod_the_nearest_slot_a_day_later(
    session, monkeypatch, latest_only,
):
    monkeypatch.setattr("bot.services.pod_launch.SessionLocal", _session_factory(session))
    _seed_signal(session, bucket_for_lane(SATURDAY, LANE_EARLY).key, SATURDAY, message_id="tomorrow")
    _seed_signal(session, bucket_for_lane(SATURDAY, LANE_LATE).key, SATURDAY, message_id="tomorrow")
    late_start = slot_event_time(FRIDAY, bucket_for_lane(FRIDAY, LANE_LATE).key)
    played_at = late_start - timedelta(minutes=40)
    event = _seed_pod(session, played_at, set_code=LATEST)
    session.commit()

    keys = pod_launch.play_again_slots_sync(event.id, played_at)

    assert [time_key_of(key) for key in keys] == [bucket_for_lane(SATURDAY, LANE_LATE).key]


def test_play_again_skips_a_mock_draft(session, monkeypatch, latest_only):
    monkeypatch.setattr("bot.services.pod_launch.SessionLocal", _session_factory(session))
    _seed_signal(session, bucket_for_lane(SATURDAY, LANE_EARLY).key, SATURDAY, message_id="tomorrow")
    played_at = slot_event_time(FRIDAY, bucket_for_lane(FRIDAY, LANE_EARLY).key)
    event = _seed_pod(session, played_at, set_code=LATEST)
    event.kind = "mock"
    session.commit()

    assert pod_launch.play_again_slots_sync(event.id, played_at) is None


@pytest.fixture
def latest_only(monkeypatch):
    monkeypatch.setattr("bot.services.pod_format_schedule.FORMATS_BY_DAY", {})


@pytest.fixture
def latest_and_peasant(monkeypatch):
    monkeypatch.setattr(
        "bot.services.pod_format_schedule.FORMATS_BY_DAY",
        {day: (schedule.LATEST, "PEASANT") for day in (FRIDAY, SATURDAY)},
    )


def _seed_signal(
    session, time_key, signal_date, *, message_id, status=STATUS_OPEN, set_code=None, bucket_key=None,
):
    set_code = set_code or LATEST
    signal = PodSignal(
        kind=KIND_POLL, bucket=bucket_key or named_bucket_key(time_key, set_code), guild_id="g",
        channel_id="c", message_id=message_id, signal_date=signal_date,
        slot_time=slot_event_time(signal_date, time_key), status=status, set_code=set_code,
    )
    session.add(signal)
    session.flush()
    return signal


def _seed_pod(session, slot_time, *, set_code, socket_status="pending", name=None, created_at=None):
    """A scheduled pod at a slot, as a fired signal points at it: the launcher reflects the event, and the
    card signal carrying the slot_time is what ties it to the column. `created_at` is worth passing when two
    pods sit at one slot: rows written in one transaction share the server default, and which pod is the
    newer one is exactly what the launcher reads."""
    event = PodDraftEvent(
        event_date=slot_time.date(), event_time=slot_time, set_code=set_code,
        name=name or f"{set_code} pod", draftmancer_session="s1", discord_thread_id="tid-1",
        socket_status=socket_status,
    )
    if created_at is not None:
        event.created_at = created_at
    session.add(event)
    session.flush()
    session.add(PodSignal(
        kind=KIND_SCHEDULED, bucket=SCHEDULED_BUCKET, guild_id="g", channel_id="c",
        message_id=f"card-{event.id}", signal_date=slot_time.date(), slot_time=slot_time,
        status=STATUS_FIRED, event_id=event.id,
    ))
    session.flush()
    return event


def _marker_slot(set_code, names, *, committed=False):
    return LauncherSlot(
        named_bucket_key("LATE", set_code), committed=committed,
        status=STATUS_FIRED if committed else STATUS_OPEN, count=len(names),
        slot_time=FRIDAY_AFTERNOON, names=names, thread_id=None, signal_id=None, set_code=set_code,
    )


def _join(session, signal, discord_user_id, display_name):
    """One roster row for a player who may already sit on another pod under another display name — the
    marker has to key on the id, not the name."""
    session.add(PodSignalMember(
        signal_id=signal.id, discord_user_id=discord_user_id, display_name=display_name,
    ))
    session.flush()


def _member_ids(session, signal):
    session.expire_all()
    return [
        member.discord_user_id for member in session.execute(
            select(PodSignalMember).where(PodSignalMember.signal_id == signal.id)
        ).scalars().all()
    ]


def _fill(session, signal, count, prefix="member"):
    for index in range(count):
        session.add(PodSignalMember(
            signal_id=signal.id, discord_user_id=f"{prefix}-{index}",
            display_name=HALL_OF_FAME[index % len(HALL_OF_FAME)],
        ))
    session.flush()


def _buckets_of(session, bound):
    return [
        session.get(PodSignal, signal_id).bucket for signal_id, _slot_time in bound
    ]


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
