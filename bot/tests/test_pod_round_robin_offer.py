from datetime import datetime, timedelta, timezone

import pytest

from bot.commands.test_group import HALL_OF_FAME
from bot.config import settings
from bot.services.pod_format import PICK_2_SETS
from bot.services.pod_draft_manager import PodDraftManager


def _offered_set() -> str:
    return PICK_2_SETS[0]


def _lobby_manager(seated: int, *, kind: str = "tournament", set_code: str | None = None) -> PodDraftManager:
    mgr = PodDraftManager(object(), "evt", "sid", 123, set_code or _offered_set(), 8)
    mgr.kind = kind
    mgr.session_users = [{"userID": str(i), "userName": name} for i, name in enumerate(HALL_OF_FAME[:seated])]
    return mgr


@pytest.mark.parametrize("seated, eligible", [(3, False), (4, True), (5, False), (8, False)])
def test_offer_arms_only_while_the_lobby_sits_at_four(seated, eligible):
    mgr = _lobby_manager(seated)

    assert mgr._round_robin_offer_eligible() is eligible


def test_only_the_sets_being_tried_out_are_offered():
    mgr = _lobby_manager(4, set_code="SOS")

    assert mgr._round_robin_offer_eligible() is False


def test_a_pod_is_not_asked_before_its_own_start_time():
    mgr = _lobby_manager(4)
    mgr.scheduled_start = datetime.now(timezone.utc) + timedelta(minutes=9)

    assert mgr._round_robin_offer_eligible() is False


def test_a_pod_past_its_start_time_is_asked():
    mgr = _lobby_manager(4)
    mgr.scheduled_start = datetime.now(timezone.utc) - timedelta(minutes=1)

    assert mgr._round_robin_offer_eligible() is True


def test_a_mock_draft_is_never_offered_pairings():
    mgr = _lobby_manager(4, kind="mock")

    assert mgr._round_robin_offer_eligible() is False


@pytest.mark.parametrize(
    "attribute", ["drafting", "draft_complete", "ready_check_active", "round_robin_vote_offered"])
def test_offer_holds_once_the_pod_has_moved_on(attribute):
    mgr = _lobby_manager(4)
    setattr(mgr, attribute, True)

    assert mgr._round_robin_offer_eligible() is False


def test_a_pod_already_playing_round_robin_is_not_asked_again():
    mgr = _lobby_manager(4)
    mgr.pairing_mode = "roundrobin"

    assert mgr._round_robin_offer_eligible() is False


def test_round_robin_pods_ready_check_at_four_without_a_warning():
    mgr = _lobby_manager(4)
    mgr.pairing_mode = "roundrobin"

    assert mgr.ready_check_floor() == settings.pod_round_robin_size
    assert mgr.ready_check_needs_confirm([]) is False


def test_other_pods_still_warn_at_four():
    mgr = _lobby_manager(4)

    assert mgr.ready_check_floor() == settings.pod_draft_min_ready_players
    assert mgr.ready_check_needs_confirm([]) is True
