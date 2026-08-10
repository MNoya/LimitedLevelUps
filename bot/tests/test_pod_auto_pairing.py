import asyncio

import pytest

from bot.commands.test_group import HALL_OF_FAME
from bot.services.pod_draft_manager import PodDraftManager


def _manager(expected: int, *, seated: int = 0, kind: str = "tournament") -> PodDraftManager:
    mgr = PodDraftManager(object(), "evt", "sid", 123, "SOS", expected, kind=kind)
    mgr.pairing_mode = "bracket"
    _seat(mgr, seated)
    return mgr


def _seat(mgr: PodDraftManager, seated: int) -> None:
    mgr.session_users = [{"userID": str(i), "userName": n} for i, n in enumerate(HALL_OF_FAME[:seated])]


def _sync(mgr: PodDraftManager, *, present_only: bool = False) -> str | None:
    """The mode the pod moves to, with the push to Draftmancer and the thread notice stubbed out."""
    applied: list[str] = []

    async def move(mode: str, *, remembering: str | None) -> None:
        applied.append(mode)
        mgr.pairing_mode = mode
        mgr.auto_team_from = remembering

    mgr._move_pairing = move
    asyncio.run(mgr._sync_auto_pairing(present_only=present_only))
    return applied[-1] if applied else None


@pytest.mark.parametrize("expected, seated, mode", [
    (6, 0, "team"),
    (6, 6, "team"),
    (4, 6, "team"),
    (8, 6, None),
    (6, 8, None),
    (4, 0, None),
    (10, 10, None),
])
def test_only_a_six_player_pod_is_paired_as_a_team_draft(expected, seated, mode):
    mgr = _manager(expected, seated=seated)

    assert _sync(mgr) == mode


def test_a_table_capped_at_six_is_a_team_draft_however_many_signed_up():
    mgr = _manager(10)
    mgr.max_players = 6

    assert _sync(mgr) == "team"


def test_the_ready_check_reads_the_lobby_and_not_the_roster():
    mgr = _manager(8, seated=6)
    assert _sync(mgr) is None

    assert _sync(mgr, present_only=True) == "team"


def test_a_lobby_that_grows_to_eight_stops_being_a_team_draft():
    mgr = _manager(6)
    assert _sync(mgr) == "team"

    _seat(mgr, 8)

    assert _sync(mgr) == "bracket"


@pytest.mark.parametrize("attribute", ["pairing_set_by_user", "drafting", "draft_complete"])
def test_the_pod_keeps_its_pairings_once_it_has_moved_on(attribute):
    mgr = _manager(6)
    setattr(mgr, attribute, True)

    assert _sync(mgr) is None


def test_a_pairing_someone_picked_survives_the_ready_check():
    mgr = _manager(6, seated=6)
    mgr.pairing_set_by_user = True

    assert _sync(mgr, present_only=True) is None


def test_a_mock_draft_is_never_repaired():
    mgr = _manager(6, kind="mock")

    assert _sync(mgr) is None
