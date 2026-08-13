import asyncio

import pytest

from bot.services.pod_draft_manager import PodDraftManager


def _rider_manager(seated: int, planned: int) -> tuple[PodDraftManager, list[int]]:
    mgr = PodDraftManager(object(), "evt", "sid", 123, "SOS", planned)
    mgr.session_users = [{"userID": str(i), "userName": str(i)} for i in range(seated)]
    mgr.rider_seats_held = planned
    mgr.rider_mentions = ["<@1>"]
    capped: list[int] = []

    async def _apply_max_players(n: int) -> None:
        capped.append(n)
        return None

    mgr.apply_max_players = _apply_max_players
    return mgr, capped


@pytest.mark.parametrize("seated, planned, still_open, capped_to", [
    (7, 8, True, []),
    (8, 8, False, [8]),
    (9, 8, False, []),
])
def test_the_window_closes_only_once_the_table_holds_everyone_it_planned_for(
    seated, planned, still_open, capped_to,
):
    mgr, capped = _rider_manager(seated, planned)

    asyncio.run(mgr._maybe_lock_planned_table())

    assert bool(mgr.rider_seats_held) is still_open
    assert capped == capped_to
