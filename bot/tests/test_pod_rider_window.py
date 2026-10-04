import asyncio

import pytest

from bot.services.pod_draft_manager import PodDraftManager, ready_check_strands_nobody


class _Thread:
    def __init__(self) -> None:
        self.sent: list[str] = []

    async def send(self, content: str, **_kwargs) -> None:
        self.sent.append(content)


def _rider_manager(seated: int, planned: int) -> tuple[PodDraftManager, list[int], _Thread]:
    mgr = PodDraftManager(object(), "evt", "sid", 123, "SOS", planned)
    mgr.session_users = [{"userID": str(i), "userName": str(i)} for i in range(seated)]
    mgr.rider_seats_held = planned
    mgr.rider_mentions = ["<@1>"]
    capped: list[int] = []

    async def _apply_max_players(n: int) -> None:
        capped.append(n)
        return None

    thread = _Thread()

    async def _fetch_thread() -> _Thread:
        return thread

    mgr.apply_max_players = _apply_max_players
    mgr._fetch_thread = _fetch_thread
    return mgr, capped, thread


@pytest.mark.parametrize("seated, planned, still_open, capped_to, riders_asked", [
    (7, 8, True, [], False),
    (8, 8, False, [8], False),
    (9, 8, False, [], False),
    (6, 6, False, [], True),
    (7, 7, False, [], True),
])
def test_the_window_closes_once_the_table_holds_everyone_it_planned_for(
    seated, planned, still_open, capped_to, riders_asked,
):
    mgr, capped, thread = _rider_manager(seated, planned)

    asyncio.run(mgr._maybe_lock_planned_table())

    assert bool(mgr.rider_seats_held) is still_open
    assert capped == capped_to
    assert bool(thread.sent) is riders_asked


@pytest.mark.parametrize("present, room_size, waiting, safe", [
    (8, 10, 1, False),
    (9, 10, 0, True),
    (10, 10, 1, True),
    (8, 8, 3, True),
])
def test_ready_check_only_offered_when_it_strands_nobody(present, room_size, waiting, safe):
    assert ready_check_strands_nobody(present, room_size, waiting) is safe
