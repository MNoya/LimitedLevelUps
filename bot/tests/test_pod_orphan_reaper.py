"""Which rows the mock orphan reaper selects: only an open mock old enough to be dead."""
from datetime import datetime, timedelta, timezone

import pytest

from bot.models import PodDraftEvent
from bot.services import pod_draft_manager


@pytest.fixture(autouse=True)
def manager_session(session, monkeypatch):
    class _Ctx:
        def __enter__(self):
            return session

        def __exit__(self, *exc):
            return False

    monkeypatch.setattr(pod_draft_manager, "SessionLocal", lambda: _Ctx())


def _event(session, *, kind="mock", socket_status="connected", age_minutes=240):
    created = datetime.now(timezone.utc) - timedelta(minutes=age_minutes)
    event = PodDraftEvent(
        event_date=created.date(), event_time=created, set_code="MH3", name="Mock",
        draftmancer_session="s1", discord_thread_id="t1", socket_status=socket_status,
        kind=kind, created_at=created,
    )
    session.add(event)
    session.commit()
    return event.id


def test_selects_only_old_open_mock_lobbies(session):
    stale = _event(session, age_minutes=240)
    _event(session, age_minutes=5)
    _event(session, socket_status="draft_done", age_minutes=240)
    _event(session, kind="tournament", age_minutes=240)

    rows = pod_draft_manager._load_orphan_mock_lobbies_sync(180)

    assert [row["id"] for row in rows] == [stale]
