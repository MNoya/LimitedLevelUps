from datetime import datetime, timezone

import pytest

from bot.services.pod_schedule import SCHEDULE_TZ
from bot.services.pod_slot import pod_display_name, pod_slot_label


def _et(year: int, month: int, day: int, hour: int, minute: int = 0) -> datetime:
    return datetime(year, month, day, hour, minute, tzinfo=SCHEDULE_TZ)


@pytest.mark.parametrize(
    "event_time, expected",
    [
        (_et(2026, 7, 16, 14, 0), "Early Pod"),
        (_et(2026, 7, 16, 20, 0), "Late Pod"),
        (_et(2026, 7, 16, 15, 30), "Early Pod"),
        (_et(2026, 7, 16, 21, 30), "Late Pod"),
        (_et(2026, 7, 16, 11, 0), "Bonus Pod"),
        (_et(2026, 7, 16, 17, 0), "Bonus Pod"),
        (_et(2026, 7, 16, 23, 0), "Bonus Pod"),
    ],
)
def test_weekday_slot_label(event_time, expected):
    assert pod_slot_label(event_time) == expected


@pytest.mark.parametrize(
    "event_time, expected",
    [
        (_et(2026, 7, 18, 14, 0), "Early Pod"),
        (_et(2026, 7, 18, 20, 0), "Late Pod"),
        (_et(2026, 7, 18, 12, 30), "Early Pod"),
        (_et(2026, 7, 18, 8, 0), "Bonus Pod"),
        (_et(2026, 7, 18, 17, 30), "Bonus Pod"),
    ],
)
def test_weekend_slot_label(event_time, expected):
    assert pod_slot_label(event_time) == expected


def test_display_name_shape():
    name = pod_display_name("msh", _et(2026, 7, 16, 14, 0))

    assert name == "MSH Jul 16 Early Pod"


def test_utc_input_converts_to_eastern_slot():
    utc_afternoon = datetime(2026, 7, 16, 18, 0, tzinfo=timezone.utc)

    assert pod_slot_label(utc_afternoon) == "Early Pod"
    assert pod_display_name("MSH", utc_afternoon) == "MSH Jul 16 Early Pod"
