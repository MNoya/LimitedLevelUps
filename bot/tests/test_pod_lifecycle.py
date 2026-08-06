import asyncio

import pytest

from bot.config import settings
from bot.services import pod_draft_manager
from bot.services.mock_lobby_card import (
    STATE_CANCELED,
    STATE_COMPLETE,
    STATE_DRAFTING,
    STATE_OPEN,
    STATE_OPENING,
)
from bot.services.pod_draft_manager import PodDraftManager


def test_pause_emits_and_sets_flag_when_drafting():
    mgr = _manager()
    mgr.drafting = True

    err = asyncio.run(mgr.pause_draft())

    assert err is None
    assert mgr.draft_paused is True
    assert mgr.sio.emitted == ["pauseDraft"]


def test_pause_rejected_when_not_drafting():
    mgr = _manager()

    err = asyncio.run(mgr.pause_draft())

    assert err is not None
    assert mgr.draft_paused is False
    assert mgr.sio.emitted == []


def test_pause_rejected_when_already_paused():
    mgr = _manager()
    mgr.drafting = True
    mgr.draft_paused = True

    err = asyncio.run(mgr.pause_draft())

    assert err is not None
    assert mgr.sio.emitted == []


def test_pause_rejected_when_disconnected():
    mgr = _manager()
    mgr.drafting = True
    mgr.sio.connected = False

    err = asyncio.run(mgr.pause_draft())

    assert err is not None
    assert mgr.sio.emitted == []


def test_resume_emits_and_clears_flag_when_paused():
    mgr = _manager()
    mgr.drafting = True
    mgr.draft_paused = True

    err = asyncio.run(mgr.resume_draft())

    assert err is None
    assert mgr.draft_paused is False
    assert mgr.sio.emitted == ["resumeDraft"]


def test_resume_rejected_when_not_paused():
    mgr = _manager()
    mgr.drafting = True

    err = asyncio.run(mgr.resume_draft())

    assert err is not None
    assert mgr.sio.emitted == []


def test_end_draft_swallowed_after_restart_stop():
    mgr = _manager()
    mgr.draft_cancelled = True

    asyncio.run(mgr._on_end_draft())

    assert mgr.draft_cancelled is False
    assert mgr.draft_complete is False


def test_pick_timer_sets_value_and_emits_pre_draft():
    mgr = _manager()

    err = asyncio.run(mgr.apply_pick_timer(45))

    assert err is None
    assert mgr.pick_timer == 45
    assert mgr.sio.emitted == ["setPickTimer"]


def test_pick_timer_rejected_once_drafting():
    mgr = _manager()
    mgr.drafting = True
    before = mgr.pick_timer

    err = asyncio.run(mgr.apply_pick_timer(45))

    assert err is not None
    assert mgr.pick_timer == before
    assert mgr.sio.emitted == []


def test_pick_timer_rejected_when_disconnected():
    mgr = _manager()
    mgr.sio.connected = False
    before = mgr.pick_timer

    err = asyncio.run(mgr.apply_pick_timer(45))

    assert err is not None
    assert mgr.pick_timer == before
    assert mgr.sio.emitted == []


def test_picks_per_pack_sets_value_and_emits_pre_draft():
    mgr = _manager()

    err = asyncio.run(mgr.apply_picks_per_pack(2))

    assert err is None
    assert mgr.picks_per_pack == 2
    assert mgr.sio.emitted == ["setPickedCardsPerRound"]


def test_picks_per_pack_rejected_once_drafting():
    mgr = _manager()
    mgr.drafting = True
    before = mgr.picks_per_pack

    err = asyncio.run(mgr.apply_picks_per_pack(2))

    assert err is not None
    assert mgr.picks_per_pack == before
    assert mgr.sio.emitted == []


def test_picks_per_pack_rejected_when_disconnected():
    mgr = _manager()
    mgr.sio.connected = False
    before = mgr.picks_per_pack

    err = asyncio.run(mgr.apply_picks_per_pack(2))

    assert err is not None
    assert mgr.picks_per_pack == before
    assert mgr.sio.emitted == []


def test_max_players_sets_value_pre_draft():
    mgr = _manager()

    err = asyncio.run(mgr.apply_max_players(10))

    assert err is None
    assert mgr.max_players == 10


def test_max_players_rejected_once_drafting():
    mgr = _manager()
    mgr.drafting = True
    before = mgr.max_players

    err = asyncio.run(mgr.apply_max_players(10))

    assert err is not None
    assert mgr.max_players == before


def test_max_players_rejected_below_current_occupancy():
    mgr = _manager()
    mgr.player_session_users = lambda: [{}] * 9
    before = mgr.max_players

    err = asyncio.run(mgr.apply_max_players(8))

    assert err is not None
    assert mgr.max_players == before


def test_await_ownership_returns_true_once_claim_marks_owner():
    mgr = _manager()
    mgr.is_owner = True
    mgr.ownership_ready.set()

    result = asyncio.run(mgr.await_ownership(timeout_s=1.0))

    assert result is True


def test_await_ownership_returns_false_when_claim_resolved_without_ownership():
    mgr = _manager()
    mgr.is_owner = False
    mgr.ownership_ready.set()

    result = asyncio.run(mgr.await_ownership(timeout_s=1.0))

    assert result is False


def test_await_ownership_times_out_when_claim_never_resolves():
    mgr = _manager()

    result = asyncio.run(mgr.await_ownership(timeout_s=0.05))

    assert result is False


@pytest.mark.parametrize(
    "flags, expected",
    [
        ({}, STATE_OPENING),
        ({"is_owner": True}, STATE_OPEN),
        ({"drafting": True}, STATE_DRAFTING),
        ({"draft_complete": True}, STATE_COMPLETE),
        ({"canceled_by": "Finkel"}, STATE_CANCELED),
        ({"canceled_idle": True}, STATE_CANCELED),
    ],
    ids=["not-owner-yet", "owner", "drafting", "complete", "canceled", "closed-idle"],
)
def test_mock_card_state_withholds_open_until_the_bot_owns_the_lobby(flags, expected):
    mgr = _manager()
    for flag, value in flags.items():
        setattr(mgr, flag, value)

    assert mgr._mock_card_state() == expected


def test_mock_idle_timer_rearms_only_when_the_lobby_roster_changes():
    async def scenario():
        mgr = _manager(kind="mock")
        armed = []
        for roster in ((), (), ("Finkel",)):
            mgr.session_users = _session_users(*roster)
            mgr._note_mock_lobby_activity()
            armed.append(mgr._mock_idle_task)
        mgr._cancel_mock_idle_timer()
        return armed

    opened, rebroadcast, joined = asyncio.run(scenario())

    assert opened is not None
    assert rebroadcast is opened
    assert joined is not opened


@pytest.mark.parametrize(
    "flags",
    [
        {"kind": "tournament"},
        {"drafting": True},
        {"draft_complete": True},
        {"canceled_by": "Finkel"},
        {"canceled_idle": True},
    ],
    ids=["tournament-pod", "drafting", "complete", "canceled", "already-closed"],
)
def test_mock_idle_timer_stays_disarmed_when_there_is_nothing_left_to_close(flags):
    async def scenario():
        mgr = _manager(kind=flags.get("kind", "mock"))
        for flag, value in flags.items():
            setattr(mgr, flag, value)
        mgr._note_mock_lobby_activity()
        armed = mgr._mock_idle_task
        mgr._cancel_mock_idle_timer()
        return armed

    assert asyncio.run(scenario()) is None


def test_mock_idle_timer_deletes_the_event_once_the_window_passes(monkeypatch):
    monkeypatch.setattr(settings, "pod_mock_inactivity_minutes", 0)
    closed = []

    async def fake_cancel(event_id, *, actor=None, idle=False):
        closed.append((event_id, actor, idle))

    monkeypatch.setattr(pod_draft_manager, "cancel_pod_event", fake_cancel)

    async def scenario():
        mgr = _manager(kind="mock")
        mgr._note_mock_lobby_activity()
        await asyncio.wait_for(mgr._mock_idle_task, timeout=1)

    asyncio.run(scenario())

    assert closed == [("evt", None, True)]


def _manager(kind: str = "tournament") -> PodDraftManager:
    mgr = PodDraftManager(object(), "evt", "sid", 123, "SOS", 8, kind=kind)
    mgr.sio = _FakeSio()
    return mgr


def _session_users(*names: str) -> list[dict]:
    return [{"userID": name, "userName": name} for name in names]


class _FakeSio:
    def __init__(self, connected: bool = True) -> None:
        self.connected = connected
        self.emitted: list[str] = []

    async def emit(self, event: str, *args, **kwargs) -> None:
        self.emitted.append(event)


def test_packs_per_player_sets_value_and_emits_pre_draft():
    mgr = _manager()

    err = asyncio.run(mgr.apply_packs_per_player(4))

    assert err is None
    assert mgr.packs_per_player == 4
    assert mgr.sio.emitted == ["boostersPerPlayer"]


def test_packs_per_player_rejected_once_drafting():
    mgr = _manager()
    mgr.drafting = True

    err = asyncio.run(mgr.apply_packs_per_player(4))

    assert err is not None
    assert mgr.packs_per_player is None
    assert mgr.sio.emitted == []


def test_cards_per_pack_sets_value_and_emits_on_a_cube():
    mgr = _manager()
    mgr.set_code = "PEASANT"

    err = asyncio.run(mgr.apply_cards_per_pack(12))

    assert err is None
    assert mgr.cards_per_pack == 12
    assert mgr.sio.emitted == ["cardsPerBooster"]


def test_cards_per_pack_refused_on_a_set_draft():
    mgr = _manager()

    err = asyncio.run(mgr.apply_cards_per_pack(12))

    assert err is not None
    assert mgr.cards_per_pack is None
    assert mgr.sio.emitted == []


def test_pack_shape_emitted_only_for_the_values_a_pod_set():
    mgr = _manager()
    mgr.packs_per_player = 4

    asyncio.run(mgr._emit_pack_shape())

    assert mgr.sio.emitted == ["boostersPerPlayer"]


def test_switching_to_a_set_drops_a_cards_per_pack_carried_from_a_cube(monkeypatch):
    mgr = _manager()
    mgr.set_code = "PEASANT"
    asyncio.run(mgr.apply_cards_per_pack(12))
    monkeypatch.setattr(pod_draft_manager, "_persist_format", lambda event_id, code: mgr.event_name)
    monkeypatch.setattr(PodDraftManager, "refresh_lobby_now", _noop)

    asyncio.run(mgr.apply_format("SOS"))

    assert mgr.cards_per_pack is None


async def _noop(*_args, **_kwargs) -> None:
    return None


def test_disconnect_ignored_before_the_draft_starts():
    mgr = _manager()

    asyncio.run(mgr._on_user_disconnected({"disconnectedUsers": {"u1": {"userName": "Finkel"}}}))

    assert mgr.disconnected_names == []


def test_disconnect_names_the_players_still_missing(monkeypatch):
    mgr = _drafting_manager(monkeypatch)

    asyncio.run(mgr._on_user_disconnected(
        {"disconnectedUsers": {"u1": {"userName": "Finkel"}, "u2": {"userName": "LSV"}}}))

    assert mgr.disconnected_names == ["Finkel", "LSV"]


def test_a_seat_already_given_to_a_bot_is_not_waited_on_again(monkeypatch):
    mgr = _drafting_manager(monkeypatch)
    mgr.bot_filled_names = {"Finkel"}

    asyncio.run(mgr._on_user_disconnected(
        {"disconnectedUsers": {"u1": {"userName": "Finkel"}, "u2": {"userName": "LSV"}}}))

    assert mgr.disconnected_names == ["LSV"]


def test_replacing_the_missing_seats_emits_and_records_them(monkeypatch):
    mgr = _drafting_manager(monkeypatch)
    mgr.disconnected_names = ["Finkel"]

    err = asyncio.run(mgr.replace_disconnected_with_bots())

    assert err is None
    assert mgr.sio.emitted == ["replaceDisconnectedPlayers"]
    assert mgr.bot_filled_names == {"Finkel"}


def test_replacing_refused_when_nobody_is_missing(monkeypatch):
    mgr = _drafting_manager(monkeypatch)

    err = asyncio.run(mgr.replace_disconnected_with_bots())

    assert err is not None
    assert mgr.sio.emitted == []


def _drafting_manager(monkeypatch) -> PodDraftManager:
    """A manager mid-draft with the thread posting stubbed out, so a test reads the decisions only."""
    mgr = _manager()
    mgr.drafting = True
    monkeypatch.setattr(PodDraftManager, "_open_disconnect_watch", _noop)
    monkeypatch.setattr(PodDraftManager, "_refresh_disconnect_watch", _noop)
    monkeypatch.setattr(PodDraftManager, "end_disconnect_stall", _noop)
    return mgr


@pytest.mark.parametrize("max_players,expected", [(6, 6), (8, 8), (10, 8)])
def test_a_capped_table_is_full_at_its_own_cap(max_players, expected):
    mgr = _manager()
    mgr.max_players = max_players

    assert mgr._lobby_full_count == expected
