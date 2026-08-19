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
