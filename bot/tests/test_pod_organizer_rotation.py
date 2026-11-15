from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace

from bot.models import PodDraftEvent
from bot.services.pod_organizer_rotation import organizer_on_duty, pod_number


def test_consecutive_pods_take_organizers_in_turn_and_wrap(session):
    organizers = [SimpleNamespace(id=300), SimpleNamespace(id=100), SimpleNamespace(id=200)]
    event_ids = [_seed_pod(session, index) for index in range(4)]

    on_duty = [organizer_on_duty(organizers, pod_number(session, event_id)).id for event_id in event_ids]

    assert on_duty == [100, 200, 300, 100]


def _seed_pod(session, index):
    created_at = datetime(2026, 11, 15, tzinfo=timezone.utc) + timedelta(minutes=index)
    event = PodDraftEvent(
        event_date=date(2026, 11, 15), event_time=created_at, set_code="TLA", name=f"Pod {index}",
        draftmancer_session=f"sess-{index}", discord_thread_id=f"thread-{index}", socket_status="pending",
        kind="tournament", created_at=created_at,
    )
    session.add(event)
    session.flush()
    return event.id
