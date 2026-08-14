import pytest

from bot.commands.test_group import HALL_OF_FAME
from bot.services.pod_draft_manager import PodDraftManager


def _manager(seated: int, *, kind: str = "tournament") -> PodDraftManager:
    mgr = PodDraftManager(object(), "evt", "sid", 123, "SOS", 8, kind=kind)
    mgr.pairing_mode = "bracket"
    mgr.session_users = [{"userID": str(i), "userName": n} for i, n in enumerate(HALL_OF_FAME[:seated])]
    return mgr


@pytest.mark.parametrize("seated, offered", [(4, False), (6, True), (7, False), (8, False)])
def test_only_a_six_player_lobby_is_offered_a_team_draft(seated, offered):
    mgr = _manager(seated)

    assert mgr.offers_team_draft() is offered


@pytest.mark.parametrize("attribute", ["pairing_set_by_user", "drafting", "draft_complete"])
def test_a_pod_that_has_its_pairings_is_not_offered_one(attribute):
    mgr = _manager(6)
    setattr(mgr, attribute, True)

    assert mgr.offers_team_draft() is False


def test_a_pod_already_paired_as_a_team_draft_is_not_offered_one():
    mgr = _manager(6)
    mgr.pairing_mode = "team"

    assert mgr.offers_team_draft() is False


def test_a_mock_draft_is_never_offered_one():
    mgr = _manager(6, kind="mock")

    assert mgr.offers_team_draft() is False
