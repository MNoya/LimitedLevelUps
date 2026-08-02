import asyncio

from bot.services import pod_draft_manager
from bot.services.lobby_embed import ready_check_confirm_text, ready_status_banner
from bot.services.pod_draft_manager import PodDraftManager


def _ready_manager(user_ids: list[str]) -> tuple[PodDraftManager, list[bool]]:
    mgr = PodDraftManager(object(), "evt", "sid", 123, "SOS", len(user_ids))
    mgr.session_users = [{"userID": uid, "userName": uid} for uid in user_ids]
    mgr.expected_user_ids = set(user_ids)
    mgr.ready_users = set(user_ids)
    mgr.ready_check_active = True
    completed: list[bool] = []

    async def _record_complete():
        completed.append(True)
        mgr.ready_check_active = False

    mgr._complete_ready_check = _record_complete
    return mgr, completed


def test_completes_when_all_present_and_ready():
    mgr, completed = _ready_manager([str(i) for i in range(8)])

    asyncio.run(mgr._maybe_complete_ready_check())

    assert completed == [True]


def test_holds_when_a_readied_player_left_and_prunes_them():
    mgr, completed = _ready_manager([str(i) for i in range(8)])
    mgr.session_users = [u for u in mgr.session_users if u["userID"] != "7"]

    asyncio.run(mgr._maybe_complete_ready_check())

    assert completed == []
    assert "7" not in mgr.ready_users


def test_completes_after_the_player_returns_and_re_readies():
    mgr, completed = _ready_manager([str(i) for i in range(8)])
    mgr.session_users = [u for u in mgr.session_users if u["userID"] != "7"]
    asyncio.run(mgr._maybe_complete_ready_check())

    mgr.session_users.append({"userID": "7", "userName": "7"})
    mgr.ready_users.add("7")
    asyncio.run(mgr._maybe_complete_ready_check())

    assert completed == [True]


def test_odd_and_short_rosters_need_confirmation_not_refusal():
    cases = [
        (8, None, False),
        (7, None, True),
        (4, None, True),
        (5, None, True),
        (4, 2, False),
        (3, 2, True),
    ]

    for seated, min_players, expected in cases:
        mgr, _ = _ready_manager([str(i) for i in range(seated)])
        mgr.ready_check_active = False
        mgr.sio = type("_Sio", (), {"connected": True})()

        assert mgr.ready_check_blocker() is None
        assert mgr.ready_check_needs_confirm([], min_players=min_players) is expected


def test_unrecognized_seats_need_confirmation_on_a_clean_roster():
    mgr, _ = _ready_manager([str(i) for i in range(8)])
    mgr.ready_check_active = False

    assert mgr.ready_check_needs_confirm([]) is False
    assert mgr.ready_check_needs_confirm(["Stranger#12345"]) is True


def test_a_full_lobby_arms_the_ready_check_nudge_on_pods_and_mocks():
    cases = [
        ("pod", 8, 0, True),
        ("pod", 7, 0, False),
        ("pod", 8, 1, False),
        ("mock", 8, 0, True),
        ("mock", 8, 3, True),
        ("mock", 7, 1, False),
    ]

    for kind, seated, unlinked, expected in cases:
        mgr, _ = _ready_manager([])
        mgr.kind = kind
        classified = [(f"p{i}", None if i < unlinked else f"P{i}") for i in range(seated)]

        assert mgr._lobby_pod_full(classified) is expected


def test_empty_lobby_is_still_a_hard_block():
    mgr, _ = _ready_manager([])
    mgr.ready_check_active = False
    mgr.sio = type("_Sio", (), {"connected": True})()

    assert mgr.ready_check_blocker() is not None


def test_leaving_arms_grace_without_immediate_cancel():
    mgr, _ = _ready_manager([str(i) for i in range(8)])
    mgr.bot_user_id = "bot"
    aborts: list[str] = []

    async def _record(kind, *, decliner_name=None, detail=None):
        aborts.append(kind)

    async def _async_noop(*args, **kwargs):
        return None

    mgr._invalidate_ready_check = _record
    mgr._refresh_lobby_status = _async_noop
    mgr._admit_lobby_arrivals = lambda *args, **kwargs: None
    mgr._sync_leaderboard_seeding = lambda *args, **kwargs: None

    remaining = [{"userID": str(i), "userName": str(i)} for i in range(7)]
    asyncio.run(mgr._on_session_users(remaining))

    assert aborts == []
    assert mgr.ready_check_active is True
    assert mgr._ready_grace_task is not None


def test_grace_aborts_when_player_stays_gone(monkeypatch):
    monkeypatch.setattr(pod_draft_manager, "_READY_GRACE_S", 0)
    mgr, _ = _ready_manager([str(i) for i in range(8)])
    mgr.expected_user_names = {str(i): f"p{i}" for i in range(8)}
    mgr.session_users = [u for u in mgr.session_users if u["userID"] != "7"]
    aborts: list[str] = []

    async def _record(kind, *, decliner_name=None, detail=None):
        aborts.append(detail)
        mgr.ready_check_active = False

    mgr._invalidate_ready_check = _record
    asyncio.run(mgr._ready_grace_countdown())

    assert len(aborts) == 1
    assert "p7" in aborts[0]


def test_grace_resumes_when_player_returns(monkeypatch):
    monkeypatch.setattr(pod_draft_manager, "_READY_GRACE_S", 0)
    mgr, _ = _ready_manager([str(i) for i in range(8)])
    aborts: list[str] = []

    async def _record(kind, *, decliner_name=None, detail=None):
        aborts.append(detail)

    mgr._invalidate_ready_check = _record
    asyncio.run(mgr._ready_grace_countdown())

    assert aborts == []


def test_roster_change_detail_pluralizes():
    assert "`Ada`" in pod_draft_manager.roster_change_detail(["Ada"], "joined")
    assert "2 players" in pod_draft_manager.roster_change_detail(["Ada", "Bo"], "left")
    assert pod_draft_manager.roster_change_detail([], "left")


def test_declined_banner_carries_initiator():
    lines, color = ready_status_banner("notready", decliner_name="Bob#1", initiated_by="Alice#2")

    assert any("Bob#1" in line for line in lines)
    assert any("Alice#2" in line for line in lines)


def test_blocker_passes_even_count_regardless_of_linking():
    mgr, _ = _ready_manager([str(i) for i in range(8)])
    mgr.ready_check_active = False
    mgr.sio = type("_Sio", (), {"connected": True})()

    assert mgr.ready_check_blocker() is None


def test_confirm_text_covers_every_warning_at_once():
    text = ready_check_confirm_text(5, 6, ["Stranger#12345", "Wanderer#77"])

    assert "5" in text
    assert "Stranger#12345" in text
    assert "Wanderer#77" in text


def test_confirm_text_omits_warnings_that_do_not_apply():
    text = ready_check_confirm_text(8, 6, [])

    assert "Stranger" not in text
    assert len(text.splitlines()) == 1


def _setup_manager(user_ids: list[str]) -> PodDraftManager:
    """A manager ready to run initiate_ready_check with every network call stubbed out."""
    mgr, _ = _ready_manager(user_ids)
    mgr.ready_check_active = False
    mgr.sio = type("_Sio", (), {"connected": True})()

    async def _async_noop(*args, **kwargs):
        return None

    mgr._emit_with_ack = _async_noop
    mgr._refresh_lobby_status = _async_noop
    mgr._flip_progress_card_to_declined = _async_noop
    mgr.refresh_lobby_now = _async_noop
    return mgr


def test_setup_abandoned_when_the_check_dies_mid_classification():
    mgr = _setup_manager([str(i) for i in range(8)])
    thread = type("_Thread", (), {"send": None})()

    async def _decline_during_classification(names):
        await mgr._invalidate_ready_check("declined", decliner_name="0")
        return [(name, name) for name in names]

    mgr._classify_users = _decline_during_classification
    asyncio.run(mgr.initiate_ready_check(thread))

    assert mgr.ready_check_active is False
    assert mgr.ready_check_progress_message is None
    assert mgr.last_decliner_name == "0"


def test_stale_timeout_leaves_the_next_check_alone(monkeypatch):
    monkeypatch.setattr(pod_draft_manager, "_READY_TIMEOUT_S", 0)
    mgr = _setup_manager([str(i) for i in range(8)])
    aborts: list[str] = []

    async def _record(kind, *, decliner_name=None, detail=None):
        aborts.append(kind)

    mgr._invalidate_ready_check = _record
    mgr.ready_check_active = True
    mgr.ready_check_generation = 4

    asyncio.run(mgr._ready_timeout(3))

    assert aborts == []


def test_timeout_fires_for_its_own_generation(monkeypatch):
    monkeypatch.setattr(pod_draft_manager, "_READY_TIMEOUT_S", 0)
    mgr = _setup_manager([str(i) for i in range(8)])
    aborts: list[str] = []

    async def _record(kind, *, decliner_name=None, detail=None):
        aborts.append(kind)

    mgr._invalidate_ready_check = _record
    mgr.ready_check_active = True
    mgr.ready_check_generation = 4

    asyncio.run(mgr._ready_timeout(4))

    assert aborts == ["timeout"]


def test_declined_banner_survives_a_session_users_broadcast():
    mgr, _ = _ready_manager([str(i) for i in range(8)])
    mgr.ready_check_active = False
    mgr.last_decliner_name = "0"
    mgr.last_ready_summary = (7, 8)

    async def _async_noop(*args, **kwargs):
        return None

    mgr._refresh_lobby_status = _async_noop
    mgr._admit_lobby_arrivals = lambda *args, **kwargs: None
    mgr._sync_leaderboard_seeding = lambda *args, **kwargs: None
    mgr.bot_user_id = "bot"

    asyncio.run(mgr._on_session_users([{"userID": "1", "userName": "1"}]))

    assert mgr.last_decliner_name == "0"
    assert mgr.last_ready_summary == (7, 8)


def test_progress_card_always_renders_a_clickable_state():
    mgr, _ = _ready_manager([str(i) for i in range(8)])
    cases = [
        (True, "ready", "ready"),
        (False, "notready", "notready"),
        (False, "drafting", "drafting"),
        (False, "complete", "complete"),
        (False, "linked", "notready"),
        (False, "unlinked", "notready"),
        (False, "empty", "notready"),
    ]

    for active, state, expected in cases:
        mgr.ready_check_active = active
        assert mgr._progress_card_state(state) == expected
