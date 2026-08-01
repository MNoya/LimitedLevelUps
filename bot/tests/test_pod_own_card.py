"""Which channel card a pod renders on: the scheduled signal's, its own, or none."""
from datetime import date, datetime, timezone

import pytest

from sqlalchemy import update

from bot.models import PodDraftEvent, PodSignal
from bot.services import pod_launch, pod_signals


NOW = datetime(2026, 7, 28, 23, 0, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def launch_session(session, monkeypatch):
    class _Ctx:
        def __enter__(self):
            return session

        def __exit__(self, *exc):
            return False

    monkeypatch.setattr(pod_launch, "SessionLocal", lambda: _Ctx())


def _event(session, *, card_channel_id=None, card_message_id=None):
    event = PodDraftEvent(
        event_date=NOW.date(), event_time=NOW, set_code="MH3", name="MH3 Jul 28 Late Pod",
        draftmancer_session="s1", discord_thread_id="thread-1", socket_status="pending",
        card_channel_id=card_channel_id, card_message_id=card_message_id,
    )
    session.add(event)
    session.commit()
    return event.id


def _scheduled_signal(session, event_id):
    session.add(PodSignal(
        kind=pod_signals.KIND_SCHEDULED, bucket=pod_signals.SCHEDULED_BUCKET, guild_id="g1",
        channel_id="chan-signal", message_id="msg-signal", signal_date=date(2026, 7, 28),
        status=pod_signals.STATUS_FIRED, slot_time=NOW, event_id=event_id,
    ))
    session.commit()


def test_a_scheduled_pod_renders_on_its_signals_card(session):
    event_id = _event(session, card_channel_id="chan-own", card_message_id="msg-own")
    _scheduled_signal(session, event_id)

    assert pod_launch.pod_card_ref_sync(event_id) == ("chan-signal", "msg-signal", NOW)


def test_a_signal_less_pod_renders_on_its_own_card(session):
    event_id = _event(session, card_channel_id="chan-own", card_message_id="msg-own")

    assert pod_launch.pod_card_ref_sync(event_id) == ("chan-own", "msg-own", None)


def test_a_pod_that_posted_no_card_renders_nowhere(session):
    event_id = _event(session)

    assert pod_launch.pod_card_ref_sync(event_id) is None


@pytest.mark.parametrize("with_signal, expected", [
    (True, ("chan-signal", "msg-signal", "thread-1", None)),
    (False, ("chan-own", "msg-own", None, None)),
])
def test_card_surfaces_follow_the_same_card(session, with_signal, expected):
    event_id = _event(session, card_channel_id="chan-own", card_message_id="msg-own")
    if with_signal:
        _scheduled_signal(session, event_id)

    assert pod_launch.event_card_surfaces_sync(event_id) == expected


def test_recording_a_card_moves_the_pod_onto_it(session):
    event_id = _event(session)

    pod_launch.record_pod_card_sync(event_id, "chan-own", "msg-own")

    assert pod_launch.pod_card_ref_sync(event_id) == ("chan-own", "msg-own", None)


def test_a_mocks_reposted_card_is_not_a_pod_card(session):
    event_id = _event(session, card_channel_id="chan-own", card_message_id="msg-own")
    session.execute(update(PodDraftEvent).where(PodDraftEvent.id == event_id).values(kind="mock"))
    session.commit()

    assert pod_launch.pod_card_ref_sync(event_id) is None
