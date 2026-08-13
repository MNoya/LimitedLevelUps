"""The thread a split gathered in: kept on the signal when the split orphans it, archived once every
table it made has finished drafting."""
from datetime import date, datetime, timezone

import pytest

from bot.models import PodDraftEvent, PodSignal
from bot.services import pod_launch, pod_signals, pod_staging


NOW = datetime(2026, 7, 28, 23, 0, tzinfo=timezone.utc)
BASE = "MH3 Jul 28 Late Pod"


@pytest.fixture(autouse=True)
def pod_session(session, monkeypatch):
    class _Ctx:
        def __enter__(self):
            return session

        def __exit__(self, *exc):
            return False

    monkeypatch.setattr(pod_launch, "SessionLocal", lambda: _Ctx())
    monkeypatch.setattr(pod_staging, "SessionLocal", lambda: _Ctx())


def _table(session, name, status, *, thread_id="thread-own", signup_thread=None):
    event = PodDraftEvent(
        event_date=NOW.date(), event_time=NOW, set_code="MH3", name=name,
        draftmancer_session=f"s-{name}", discord_thread_id=thread_id, socket_status=status,
    )
    session.add(event)
    session.commit()
    session.add(PodSignal(
        kind=pod_signals.KIND_SCHEDULED, bucket=pod_signals.SCHEDULED_BUCKET, guild_id="g1",
        channel_id="chan", message_id=f"msg-{name}", signal_date=date(2026, 7, 28),
        status=pod_signals.STATUS_FIRED, slot_time=NOW, event_id=event.id,
        discussion_thread_id=signup_thread,
    ))
    session.commit()
    return event.id


def test_the_split_keeps_the_thread_it_leaves_behind(session):
    event_id = _table(session, BASE, "pending", thread_id="signup-thread")

    pod_launch.move_scheduled_card_sync(event_id, "new-card", "table-1-thread")

    signal = session.query(PodSignal).filter_by(event_id=event_id).one()
    assert signal.discussion_thread_id == "signup-thread"
    assert session.get(PodDraftEvent, event_id).discord_thread_id == "table-1-thread"


@pytest.mark.parametrize("statuses, expected", [
    (("draft_done", "draft_done"), "signup-thread"),
    (("draft_done", "complete"), "signup-thread"),
    (("draft_done", "reminded"), None),
    (("pending", "pending"), None),
])
def test_the_signup_thread_waits_for_every_table_to_finish(session, statuses, expected):
    first, second = statuses
    table_one = _table(session, f"{BASE} 1", first, signup_thread="signup-thread")
    _table(session, f"{BASE} 2", second)

    assert pod_staging.signup_thread_once_family_drafted_sync(table_one) == expected


def test_a_pod_that_never_split_has_no_thread_to_stand_down(session):
    event_id = _table(session, BASE, "draft_done", signup_thread="signup-thread")

    assert pod_staging.signup_thread_once_family_drafted_sync(event_id) is None
