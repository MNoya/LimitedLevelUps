from datetime import datetime

import pytest

from bot.commands.pod_queue import creation_ping_role
from bot.services.pod_schedule import EARLY_POD_ROLE_NAME, LATE_POD_ROLE_NAME, POD_QUEUE_ROLE_NAME
from bot.services.pod_signals import SCHEDULE_TZ, slot_event_time


def _slot(bucket_key: str, day: str) -> datetime:
    return slot_event_time(datetime.fromisoformat(day).date(), bucket_key)


@pytest.mark.parametrize("scheduled_time, expected", [
    (None, POD_QUEUE_ROLE_NAME),
    (_slot("EARLY", "2026-07-16"), EARLY_POD_ROLE_NAME),
    (_slot("LATE", "2026-07-16"), LATE_POD_ROLE_NAME),
    (_slot("EVENING", "2026-07-18"), LATE_POD_ROLE_NAME),
    (datetime(2026, 7, 16, 17, 13, tzinfo=SCHEDULE_TZ), POD_QUEUE_ROLE_NAME),
])
def test_creation_ping_role_follows_the_pod_time(scheduled_time, expected):
    assert creation_ping_role(scheduled_time, ping_on_creation=True) == expected


@pytest.mark.parametrize("scheduled_time", [
    None,
    _slot("EARLY", "2026-07-16"),
])
def test_creation_ping_off_pings_nobody(scheduled_time):
    assert creation_ping_role(scheduled_time, ping_on_creation=False) is None
