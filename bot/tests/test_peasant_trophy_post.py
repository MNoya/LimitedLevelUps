from datetime import date

import pytest

from bot.services.peasant_trophy_post import PeasantFinish, PeasantTrophyStats, trophy_stats
from bot.sets import SetSeed

SEASON = SetSeed("MSH", "Marvel Super Heroes", date(2026, 6, 23), date(2026, 8, 10))
BEFORE = date(2026, 5, 1)
DURING = date(2026, 7, 1)


@pytest.mark.parametrize("history, expected", [
    ([(DURING, "3-0", "UG")], PeasantTrophyStats(lifetime=1, season=1, with_colors=1, streak=1)),
    (
        [(BEFORE, "3-0", "UG"), (BEFORE, "1-2", "UG"), (DURING, "3-0", "UGr")],
        PeasantTrophyStats(lifetime=2, season=1, with_colors=2, streak=1),
    ),
    (
        [(BEFORE, "3-0", "WB"), (DURING, "3-0", "UR"), (DURING, "3-0", "WB")],
        PeasantTrophyStats(lifetime=3, season=2, with_colors=2, streak=3),
    ),
    (
        [(DURING, "3-0", "UB"), (DURING, "2-1", "UB"), (DURING, "3-0", "RG")],
        PeasantTrophyStats(lifetime=2, season=2, with_colors=1, streak=1),
    ),
])
def test_trophy_stats(history, expected):
    finishes = [PeasantFinish(day, record, colors) for day, record, colors in history]

    stats = trophy_stats(finishes, SEASON)

    assert stats == expected
