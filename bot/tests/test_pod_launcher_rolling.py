from datetime import datetime, time, timedelta

import pytest

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
    next_slot_start,
    slot_can_fire,
    slot_event_time,
)
from bot.sets import active_set_code
from bot.tasks.pod_daily_poll import (
    COLUMN_FIT_BUDGET,
    _fit_row,
    _lane_order,
    _lane_slots,
    _row_units,
    _slot_by_key,
)


DAYS_TO_FRIDAY = ((4 - datetime.now(SCHEDULE_TZ).date().weekday()) % 7) or 7
FRIDAY = datetime.now(SCHEDULE_TZ).date() + timedelta(days=DAYS_TO_FRIDAY)
SATURDAY = FRIDAY + timedelta(days=1)
FRIDAY_AFTERNOON = datetime.combine(FRIDAY, time(16, 0), tzinfo=SCHEDULE_TZ)
THRESHOLD = settings.pod_signal_fire_threshold


# --- lanes ---

@pytest.mark.parametrize("lane, called_at, expected_start", [
    (LANE_EARLY, datetime(2026, 7, 26, 0, 35, tzinfo=SCHEDULE_TZ), datetime(2026, 7, 26, 14, 0)),
    (LANE_EARLY, datetime(2026, 7, 26, 15, 0, tzinfo=SCHEDULE_TZ), datetime(2026, 7, 27, 14, 0)),
    (LANE_LATE, datetime(2026, 7, 26, 15, 0, tzinfo=SCHEDULE_TZ), datetime(2026, 7, 26, 20, 0)),
    (LANE_LATE, datetime(2026, 7, 26, 21, 0, tzinfo=SCHEDULE_TZ), datetime(2026, 7, 27, 20, 0)),
    (LANE_EARLY, datetime(2026, 11, 1, 20, 0, tzinfo=SCHEDULE_TZ), datetime(2026, 11, 2, 14, 0)),
])
def test_a_slot_rolls_to_tomorrow_once_todays_start_has_passed(lane, called_at, expected_start):
    bucket = bucket_for_lane(called_at.date(), lane)

    start = next_slot_start(bucket, called_at)

    assert start == expected_start.replace(tzinfo=SCHEDULE_TZ)


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

LATEST = active_set_code()


def _played(bucket_key, day, winner="Finkel"):
    return LauncherSlot(
        named_bucket_key(bucket_key, LATEST), committed=True, status=STATUS_FIRED, count=8,
        slot_time=slot_event_time(day, bucket_key), set_code=LATEST,
        names=list(HALL_OF_FAME[:8]), thread_id="1", signal_id=None, thread_name="MSH Jul 24 Late Pod",
        finished=True, locked=True, winner=winner, winner_slug="finkel",
    )


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


LONG_HANDLE = "_".join(HALL_OF_FAME[12:15]).replace(" ", "")


@pytest.mark.parametrize("pod, winner, keeps_date, keeps_winner", [
    ("MSH Jul 25", HALL_OF_FAME[0], True, True),
    ("MSH Jul 25 2nd", HALL_OF_FAME[1], True, True),
    ("Peasant Cube Jul 25", "Android5000", False, True),
    ("Peasant Cube Jul 25 2nd", LONG_HANDLE, False, False),
    ("Peasant Cube Jul 25", "", True, True),
])
def test_a_played_row_gives_up_its_date_before_it_cuts_the_winner(pod, winner, keeps_date, keeps_winner):
    text, name = _fit_row(pod, winner)

    assert ("Jul 25" in text) is keeps_date
    assert (name == winner) is keeps_winner
    assert _row_units(text, name) <= COLUMN_FIT_BUDGET


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
    assert bucket_key == named_bucket_key(time_key, LATEST)
    assert slot_time == slot_event_time(SATURDAY, time_key)
    assert _open_signal_count(session, bucket_key, SATURDAY) == 1


def test_rolling_a_lane_opens_every_format_the_next_day_offers(session, monkeypatch, latest_and_peasant):
    monkeypatch.setattr("bot.services.pod_launch.SessionLocal", _session_factory(session))

    rolled = pod_launch.roll_slot_forward_sync(
        lane=LANE_LATE, from_day=FRIDAY, guild_id="g", channel_id="c", message_id="today",
    )

    time_key = bucket_for_lane(SATURDAY, LANE_LATE).key
    assert [bucket_key for _signal_id, bucket_key, _slot_time in rolled] == [
        named_bucket_key(time_key, LATEST), named_bucket_key(time_key, "PEASANT"),
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
        slot_event_time(FRIDAY, "LATE"), slot_event_time(SATURDAY, "EVENING"),
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


def test_a_player_on_both_formats_of_a_slot_is_marked_on_both_rosters(session, monkeypatch, latest_and_peasant):
    monkeypatch.setattr("bot.services.pod_launch.SessionLocal", _session_factory(session))
    early = bucket_for_lane(FRIDAY, LANE_EARLY).key
    latest = _seed_signal(session, early, FRIDAY, message_id="today")
    peasant = _seed_signal(session, early, FRIDAY, message_id="today", set_code="PEASANT")
    _fill(session, latest, 1, prefix="own")
    _join(session, latest, "flex", HALL_OF_FAME[4])
    _join(session, peasant, "flex", HALL_OF_FAME[5])
    session.commit()

    slots = pod_launch.launcher_snapshot_sync("today", FRIDAY)

    marked = {slot.set_code: slot.shared_names for slot in slots if slot.set_code in (LATEST, "PEASANT")}
    assert marked == {LATEST: (HALL_OF_FAME[4],), "PEASANT": (HALL_OF_FAME[5],)}


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


@pytest.mark.parametrize(
    "dedicated, other_dedicated, shared, expected_kept, expected_released",
    [
        (THRESHOLD - 1, THRESHOLD - 1, 2, THRESHOLD, 1),
        (THRESHOLD, THRESHOLD, 2, THRESHOLD + 2, 0),
        (THRESHOLD, 0, 2, THRESHOLD + 2, 0),
        (0, 0, THRESHOLD + 2, THRESHOLD + 2, 0),
        (THRESHOLD - 3, THRESHOLD - 3, 3, THRESHOLD, 0),
    ],
)
def test_a_firing_pod_takes_only_the_shared_signups_it_needs(
    session, monkeypatch, latest_and_peasant,
    dedicated, other_dedicated, shared, expected_kept, expected_released,
):
    monkeypatch.setattr("bot.services.pod_launch.SessionLocal", _session_factory(session))
    firing = _seed_signal(session, "EARLY", FRIDAY, message_id="today")
    beside = _seed_signal(session, "EARLY", FRIDAY, message_id="today", set_code="PEASANT")
    _fill(session, firing, dedicated, prefix="own")
    _fill(session, beside, other_dedicated, prefix="theirs")
    _fill(session, firing, shared, prefix="both")
    _fill(session, beside, shared, prefix="both")
    session.commit()

    kept, released = pod_launch.allocate_fire_roster_sync(firing.id)

    assert (kept, released) == (expected_kept, expected_released)
    assert len(firing.members) == expected_kept
    assert len(beside.members) == other_dedicated + expected_released


def test_the_pod_beside_a_fire_is_offered_the_release_it_needs_to_fill(
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
    pod_launch.allocate_fire_roster_sync(firing.id)
    pod_launch.claim_fire_sync(firing.id)

    candidates = pod_launch.sibling_fire_candidates_sync(firing.id)

    assert [(state.signal_id, state.count) for state in candidates] == [(beside.id, THRESHOLD)]


def test_a_fired_pod_is_never_offered_a_second_time(session, monkeypatch, latest_and_peasant):
    monkeypatch.setattr("bot.services.pod_launch.SessionLocal", _session_factory(session))
    firing = _seed_signal(session, "EARLY", FRIDAY, message_id="today")
    beside = _seed_signal(
        session, "EARLY", FRIDAY, message_id="today", set_code="PEASANT", status=STATUS_FIRED,
    )
    _fill(session, firing, THRESHOLD, prefix="own")
    _fill(session, beside, THRESHOLD, prefix="theirs")
    session.commit()

    assert pod_launch.sibling_fire_candidates_sync(firing.id) == []


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


def _seed_pod(session, slot_time, *, set_code, socket_status="pending"):
    """A scheduled pod at a slot, as a fired signal points at it: the launcher reflects the event, and the
    card signal carrying the slot_time is what ties it to the column."""
    event = PodDraftEvent(
        event_date=slot_time.date(), event_time=slot_time, set_code=set_code,
        name=f"{set_code} pod", draftmancer_session="s1", discord_thread_id="tid-1",
        socket_status=socket_status,
    )
    session.add(event)
    session.flush()
    session.add(PodSignal(
        kind=KIND_SCHEDULED, bucket=SCHEDULED_BUCKET, guild_id="g", channel_id="c", message_id="card",
        signal_date=slot_time.date(), slot_time=slot_time, status=STATUS_FIRED, event_id=event.id,
    ))
    session.flush()
    return event


def _join(session, signal, discord_user_id, display_name):
    """One roster row for a player who may already sit on another pod under another display name — the
    marker has to key on the id, not the name."""
    session.add(PodSignalMember(
        signal_id=signal.id, discord_user_id=discord_user_id, display_name=display_name,
    ))
    session.flush()


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
