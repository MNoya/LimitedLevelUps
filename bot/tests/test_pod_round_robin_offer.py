from bot.commands.test_group import HALL_OF_FAME
from bot.config import settings
from bot.services.pod_format import PICK_2_SETS
from bot.services.pod_draft_manager import PodDraftManager


def _lobby_manager(seated: int, *, kind: str = "tournament", set_code: str | None = None) -> PodDraftManager:
    mgr = PodDraftManager(object(), "evt", "sid", 123, set_code or PICK_2_SETS[0], 8)
    mgr.kind = kind
    mgr.session_users = [{"userID": str(i), "userName": name} for i, name in enumerate(HALL_OF_FAME[:seated])]
    return mgr


def test_round_robin_pods_ready_check_at_four_without_a_warning():
    mgr = _lobby_manager(4)
    mgr.pairing_mode = "roundrobin"

    assert mgr.ready_check_floor() == settings.pod_round_robin_size
    assert mgr.ready_check_needs_confirm([]) is False


def test_other_pods_still_warn_at_four():
    mgr = _lobby_manager(4)

    assert mgr.ready_check_floor() == settings.pod_draft_min_ready_players
    assert mgr.ready_check_needs_confirm([]) is True


def test_ready_check_offers_pick_2_on_a_four_player_pick_2_set():
    mgr = _lobby_manager(4)

    assert mgr.offers_pick_2() is True


def test_pick_2_offer_respects_a_hand_set_mode_or_pairing():
    mode_set = _lobby_manager(4)
    mode_set.picks_set_by_user = True

    pairing_set = _lobby_manager(4)
    pairing_set.pairing_set_by_user = True

    assert mode_set.offers_pick_2() is False
    assert pairing_set.offers_pick_2() is False


def test_pick_2_offer_skips_a_non_pick_2_set_and_off_sizes():
    other_set = _lobby_manager(4, set_code="EOE")
    five = _lobby_manager(5)

    assert other_set.offers_pick_2() is False
    assert five.offers_pick_2() is False
