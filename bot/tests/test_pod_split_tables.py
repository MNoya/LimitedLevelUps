from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from bot.commands.test_group import HALL_OF_FAME
from bot.models import PodDraftEvent, PodSignal, PodSignalMember
from bot.services import pod_signals, pod_staging
from bot.services.pod_schedule import SCHEDULE_TZ
from bot.services.pod_staging import claim_seated_players_sync, table_for_rsvp_sync


TABLE_1 = "split-table-1"
TABLE_2 = "split-table-2"
LATE_PRESS = "900"


def _session_factory(session):
    class _Ctx:
        def __enter__(self):
            return session

        def __exit__(self, *exc):
            return False

    return lambda: _Ctx()


@pytest.fixture
def split_pod(session, monkeypatch):
    monkeypatch.setattr(pod_staging, "SessionLocal", _session_factory(session))
    starts_at = datetime.now(timezone.utc) + timedelta(minutes=5)
    seated = {TABLE_1: 8, TABLE_2: 6}
    names = iter(HALL_OF_FAME)
    for index, (event_id, count) in enumerate(seated.items(), start=1):
        session.add(PodDraftEvent(
            id=event_id, set_code="FRA", name=f"FRA Early Pod {index}", event_time=starts_at,
            event_date=starts_at.date(), discord_thread_id=str(index), socket_status="reminded",
            draftmancer_session=f"LLU-SPLIT-{index}",
        ))
        signal = PodSignal(
            kind=pod_signals.KIND_SCHEDULED, bucket=pod_signals.SCHEDULED_BUCKET,
            guild_id="1", channel_id="2", message_id=f"m{index}",
            signal_date=datetime.now(SCHEDULE_TZ).date(), status=pod_signals.STATUS_FIRED,
            event_id=event_id,
        )
        session.add(signal)
        session.flush()
        for seat in range(count):
            session.add(PodSignalMember(
                signal_id=signal.id, discord_user_id=f"{index}{seat:02d}", display_name=next(names),
                rsvp=pod_signals.RSVP_YES, confirmed_at=starts_at,
            ))
    session.commit()


def _tables_holding(session, discord_id: str) -> list[str]:
    session.expire_all()
    return list(session.execute(
        select(PodSignal.event_id)
        .join(PodSignalMember, PodSignalMember.signal_id == PodSignal.id)
        .where(PodSignalMember.discord_user_id == discord_id)
    ).scalars())


def test_a_late_yes_on_the_full_table_goes_to_the_table_short_of_players(split_pod):
    assert table_for_rsvp_sync(TABLE_1, LATE_PRESS, pod_signals.RSVP_YES) == TABLE_2


def test_a_player_seated_in_another_table_room_moves_to_that_table(session, split_pod):
    stray = "100"

    claimed_from = claim_seated_players_sync(TABLE_2, [stray])

    assert claimed_from == [TABLE_1]
    assert _tables_holding(session, stray) == [TABLE_2]
