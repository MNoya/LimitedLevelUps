"""Guard that !confirm's write actually lands, since a stamp nobody reads yet cannot be seen to fail."""
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from bot.commands import pod_confirm
from bot.commands.pod_confirm import confirm_seat_sync
from bot.models import PodDraftEvent, PodSignal, PodSignalMember
from bot.services import pod_signals
from bot.services.pod_schedule import SCHEDULE_TZ


EVENT_ID = "smoke-event-1"


def _session_factory(session):
    class _Ctx:
        def __enter__(self):
            return session

        def __exit__(self, *exc):
            return False

    return lambda: _Ctx()


@pytest.fixture
def signal(session, monkeypatch):
    monkeypatch.setattr(pod_confirm, "SessionLocal", _session_factory(session))
    starts_at = datetime.now(timezone.utc) + timedelta(hours=1)
    event = PodDraftEvent(
        id=EVENT_ID, set_code="MSH", name="Smoke Pod", event_time=starts_at,
        event_date=starts_at.date(), discord_thread_id="42", socket_status="pending",
        draftmancer_session="LLU-SMOKE-1",
    )
    session.add(event)
    signal = PodSignal(
        kind=pod_signals.KIND_SCHEDULED, bucket=pod_signals.SCHEDULED_BUCKET,
        guild_id="1", channel_id="2", message_id="m1",
        signal_date=datetime.now(SCHEDULE_TZ).date(), status=pod_signals.STATUS_FIRED,
        event_id=EVENT_ID,
    )
    session.add(signal)
    session.commit()
    return signal


def test_a_walk_in_who_never_signed_up_is_recorded_as_coming(session, signal):
    assert confirm_seat_sync(EVENT_ID, "999", "Finkel") is True

    member = session.execute(select(PodSignalMember)).scalar_one()
    assert (member.rsvp, member.confirmed_at is not None) == (pod_signals.RSVP_YES, True)


def test_confirming_twice_keeps_the_first_answer(session, signal):
    confirm_seat_sync(EVENT_ID, "999", "Finkel")
    first = session.execute(select(PodSignalMember)).scalar_one().confirmed_at

    confirm_seat_sync(EVENT_ID, "999", "Finkel")

    session.expire_all()
    assert session.execute(select(PodSignalMember)).scalar_one().confirmed_at == first


def test_a_pod_with_no_signup_roster_is_refused(session, signal):
    assert confirm_seat_sync("no-such-event", "999", "Finkel") is False
