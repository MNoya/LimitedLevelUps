"""The pod setup blob on the event row.

SQLAlchemy does not track in-place mutation of a JSONB column, so a write that reaches into the dict
instead of reassigning it commits nothing and reports no error. This is here to catch that, not to
prove a dict merge merges.
"""
from __future__ import annotations

from datetime import date, datetime, timezone

import pytest

from bot.config import settings
from bot.models import PodDraftEvent
from bot.services import pod_event_settings


def _session_factory(session):
    class _Ctx:
        def __enter__(self):
            return session

        def __exit__(self, *exc):
            return False

    return lambda: _Ctx()


@pytest.fixture
def event(session, monkeypatch):
    row = PodDraftEvent(
        event_date=date(2026, 6, 23), event_time=datetime(2026, 6, 23, tzinfo=timezone.utc),
        set_code="MSH", name="MSH Pod Draft 1", draftmancer_session="LLU-MSH-1",
        discord_thread_id="7001", socket_status="pending", current_round=None,
    )
    session.add(row)
    session.commit()
    monkeypatch.setattr("bot.services.pod_event_settings.SessionLocal", _session_factory(session))
    return row


def test_settings_survive_the_round_trip_and_leave_the_keys_they_do_not_name(event):
    pod_event_settings.store_sync(event.id, max_players=6)
    pod_event_settings.store_sync(event.id, cards_per_pack=12)
    pod_event_settings.clear_sync(event.id, pod_event_settings.CARDS_PER_PACK)

    stored = pod_event_settings.load_sync(event.id)

    assert stored[pod_event_settings.MAX_PLAYERS] == 6
    assert stored[pod_event_settings.CARDS_PER_PACK] is None
    assert stored[pod_event_settings.PICK_TIMER] == settings.pod_draft_pick_timer
