from dataclasses import dataclass

import pytest

from bot.services.pod_active import ACTIVE_POD_MANAGERS
from bot.services.pod_rally import (
    KIND_LOBBY,
    KIND_STARTED,
    RallyTarget,
    live_lobby_targets,
    lobby_is_full,
)


GUILD_ID = "775371722065051658"


@dataclass
class FakeManager:
    event_name: str
    thread_id: int
    session_id: str
    seated: int
    kind: str = "tournament"
    drafting: bool = False
    draft_complete: bool = False
    event_id: str = "event"

    def player_session_users(self) -> list[dict]:
        return [{"userID": f"u{i}"} for i in range(self.seated)]


@pytest.fixture
def registry():
    ACTIVE_POD_MANAGERS.clear()
    yield ACTIVE_POD_MANAGERS
    ACTIVE_POD_MANAGERS.clear()


@pytest.mark.parametrize("seated,expected", [
    (0, False),
    (7, False),
    (8, True),
    (9, True),
])
def test_lobby_is_full_at_the_target_and_above(seated, expected):
    target = RallyTarget(KIND_LOBBY, "Late Pod", "url", seated=seated, session_id="s")

    assert lobby_is_full(target) is expected


def test_a_running_draft_is_never_reported_as_a_full_lobby():
    target = RallyTarget(KIND_STARTED, "Late Pod", "url", seated=8)

    assert lobby_is_full(target) is False


def test_live_lobby_targets_leads_with_the_pod_closest_to_a_full_table(registry):
    registry["a"] = FakeManager("Early Pod", 1, "sess-a", seated=4)
    registry["b"] = FakeManager("Late Pod", 2, "sess-b", seated=7)

    targets = live_lobby_targets(GUILD_ID)

    assert [target.name for target in targets] == ["Late Pod", "Early Pod"]


def test_live_lobby_targets_sinks_a_full_lobby_below_one_still_short(registry):
    registry["a"] = FakeManager("Full Pod", 1, "sess-a", seated=8)
    registry["b"] = FakeManager("Short Pod", 2, "sess-b", seated=6)

    targets = live_lobby_targets(GUILD_ID)

    assert [target.name for target in targets] == ["Short Pod", "Full Pod"]


def test_live_lobby_targets_sinks_a_running_draft_below_every_open_lobby(registry):
    registry["a"] = FakeManager("Running Pod", 1, "sess-a", seated=8, drafting=True)
    registry["b"] = FakeManager("Open Pod", 2, "sess-b", seated=3)

    targets = live_lobby_targets(GUILD_ID)

    assert [(target.name, target.kind) for target in targets] == [
        ("Open Pod", KIND_LOBBY), ("Running Pod", KIND_STARTED),
    ]


def test_live_lobby_targets_drops_mocks_and_completed_drafts(registry):
    registry["a"] = FakeManager("Mock Draft", 1, "sess-a", seated=5, kind="mock")
    registry["b"] = FakeManager("Done Pod", 2, "sess-b", seated=8, draft_complete=True)
    registry["c"] = FakeManager("Open Pod", 3, "sess-c", seated=5)

    targets = live_lobby_targets(GUILD_ID)

    assert [target.name for target in targets] == ["Open Pod"]


def test_live_lobby_targets_carries_the_session_id_only_for_joinable_lobbies(registry):
    registry["a"] = FakeManager("Open Pod", 1, "sess-a", seated=5)
    registry["b"] = FakeManager("Running Pod", 2, "sess-b", seated=8, drafting=True)

    by_name = {target.name: target for target in live_lobby_targets(GUILD_ID)}

    assert by_name["Open Pod"].session_id == "sess-a"
    assert by_name["Running Pod"].session_id is None
