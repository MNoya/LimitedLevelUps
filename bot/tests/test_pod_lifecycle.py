import asyncio

import pytest

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
    ],
    ids=["not-owner-yet", "owner", "drafting", "complete", "canceled"],
)
def test_mock_card_state_withholds_open_until_the_bot_owns_the_lobby(flags, expected):
    mgr = _manager()
    for flag, value in flags.items():
        setattr(mgr, flag, value)

    assert mgr._mock_card_state() == expected


def _manager() -> PodDraftManager:
    mgr = PodDraftManager(object(), "evt", "sid", 123, "SOS", 8)
    mgr.sio = _FakeSio()
    return mgr


class _FakeSio:
    def __init__(self, connected: bool = True) -> None:
        self.connected = connected
        self.emitted: list[str] = []

    async def emit(self, event: str, *args, **kwargs) -> None:
        self.emitted.append(event)
