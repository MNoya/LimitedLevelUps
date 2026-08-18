from datetime import date, datetime, timedelta, timezone

import pytest

from bot.commands.test_group import HALL_OF_FAME
from bot.models import Player, PodDraftEvent, PodDraftParticipant, PodSignal, PodSignalMember
from bot.services import pod_confirm, pod_signals
from bot.services.pod_confirm import roster_attendance_for_event_sync
from bot.services.pod_drafts import classify_lobby_names, mark_first_pod
from bot.services.pod_schedule import SCHEDULE_TZ


def _session_factory(session):
    class _Ctx:
        def __enter__(self):
            return session

        def __exit__(self, *exc):
            return False

    return lambda: _Ctx()


def _player(session, name: str, discord_id: str, first_pod_at: datetime | None = None) -> Player:
    player = Player(
        slug=f"{name.lower()}-{discord_id}", discord_id=discord_id, discord_username=name.lower(),
        display_name=name, first_pod_at=first_pod_at,
    )
    session.add(player)
    session.flush()
    return player


def _finished_pod(session, seats: list[tuple[Player, str | None]]) -> PodDraftEvent:
    event = PodDraftEvent(
        event_date=date(2026, 8, 14), event_time=datetime(2026, 8, 14, tzinfo=timezone.utc),
        set_code="SOS", name="SOS Pod First", draftmancer_session="first-sess",
        discord_thread_id="first-thread", socket_status="complete",
    )
    session.add(event)
    session.flush()
    for player, record in seats:
        session.add(PodDraftParticipant(
            event_id=event.id, player_id=player.id, display_name=player.display_name, record=record,
        ))
    session.flush()
    return event


def test_a_finished_pod_stamps_only_the_seats_that_recorded_a_result(session):
    rookie = _player(session, HALL_OF_FAME[0], "801")
    dropped = _player(session, HALL_OF_FAME[1], "802")
    event = _finished_pod(session, [(rookie, "3-0"), (dropped, None)])

    marked = mark_first_pod(session, event.id)

    assert marked == 1
    assert rookie.first_pod_at is not None
    assert dropped.first_pod_at is None


def test_a_second_pod_leaves_the_first_one_standing(session):
    already = datetime(2026, 7, 1, tzinfo=timezone.utc)
    veteran = _player(session, HALL_OF_FAME[2], "803", first_pod_at=already)
    event = _finished_pod(session, [(veteran, "2-1")])

    marked = mark_first_pod(session, event.id)

    assert marked == 0
    assert veteran.first_pod_at == already


def test_a_seat_no_player_claimed_stamps_nobody(session):
    event = PodDraftEvent(
        event_date=date(2026, 8, 14), event_time=datetime(2026, 8, 14, tzinfo=timezone.utc),
        set_code="SOS", name="SOS Pod Guest", draftmancer_session="guest-sess",
        discord_thread_id="guest-thread", socket_status="complete",
    )
    session.add(event)
    session.flush()
    session.add(PodDraftParticipant(event_id=event.id, display_name="Walk-in", record="1-2"))
    session.flush()

    assert mark_first_pod(session, event.id) == 0


@pytest.mark.parametrize("first_pod_at, expected_new", [
    (None, True),
    (datetime(2026, 7, 1, tzinfo=timezone.utc), False),
])
def test_the_lobby_marks_a_seat_by_whether_it_has_finished_a_pod(session, first_pod_at, expected_new):
    player = _player(session, HALL_OF_FAME[3], "804", first_pod_at=first_pod_at)

    _, new_drafters = classify_lobby_names(session, [player.display_name])

    assert (player.display_name in new_drafters) is expected_new


def test_the_roster_marks_a_signup_with_no_player_row_at_all(session, monkeypatch):
    monkeypatch.setattr(pod_confirm, "SessionLocal", _session_factory(session))
    veteran = _player(session, HALL_OF_FAME[4], "805", first_pod_at=datetime(2026, 7, 1, tzinfo=timezone.utc))
    rookie = _player(session, HALL_OF_FAME[5], "806")
    event = PodDraftEvent(
        event_date=date(2026, 8, 18), event_time=datetime.now(timezone.utc) + timedelta(hours=1),
        set_code="SOS", name="SOS Pod Roster", draftmancer_session="roster-sess",
        discord_thread_id="roster-thread", socket_status="pending",
    )
    session.add(event)
    session.flush()
    signal = PodSignal(
        kind=pod_signals.KIND_SCHEDULED, bucket=pod_signals.SCHEDULED_BUCKET, guild_id="1",
        channel_id="2", message_id="8801", signal_date=datetime.now(SCHEDULE_TZ).date(),
        slot_time=datetime.now(timezone.utc) + timedelta(hours=1), status=pod_signals.STATUS_FIRED,
        event_id=event.id,
    )
    session.add(signal)
    session.flush()
    for discord_id, display in (
        (veteran.discord_id, veteran.display_name),
        (rookie.discord_id, rookie.display_name),
        ("899", "Stranger"),
    ):
        session.add(PodSignalMember(
            signal_id=signal.id, discord_user_id=discord_id, display_name=display,
            rsvp=pod_signals.RSVP_YES,
        ))
    session.flush()

    attendance = roster_attendance_for_event_sync(event.id)

    assert attendance.new_drafters == frozenset({rookie.display_name, "Stranger"})
