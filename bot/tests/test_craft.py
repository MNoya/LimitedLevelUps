from datetime import datetime, timezone

import pytest

from bot.commands.craft import craft_set_code


@pytest.mark.parametrize("when, expected", [
    (datetime(2026, 9, 10, tzinfo=timezone.utc), "HOB"),
    (datetime(2026, 9, 20, tzinfo=timezone.utc), "FRA"),
    (datetime(2026, 10, 5, tzinfo=timezone.utc), "FRA"),
])
def test_craft_follows_the_upcoming_set_once_its_previews_open(when, expected):
    code = craft_set_code(when)

    assert code == expected
