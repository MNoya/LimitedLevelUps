from datetime import datetime, timezone

import pytest

from bot.models import Player, PodDraftEvent, PodDraftParticipant
from bot.services.pod_replays import unlinked_first_finishers_sync

BEFORE_LAUNCH = datetime(2026, 9, 20, 23, 0, tzinfo=timezone.utc)
AFTER_LAUNCH = datetime(2026, 9, 29, 23, 0, tzinfo=timezone.utc)
LATER = datetime(2026, 9, 30, 23, 0, tzinfo=timezone.utc)


@pytest.mark.parametrize("linked, earlier_pods, prompted", [
    (False, [], True),
    (True, [], False),
    (False, [(AFTER_LAUNCH, "tournament")], False),
    (False, [(BEFORE_LAUNCH, "tournament")], True),
    (False, [(AFTER_LAUNCH, "mock")], True),
])
def test_only_unlinked_players_on_their_first_pod_since_launch_are_prompted(
    session, monkeypatch, linked, earlier_pods, prompted,
):
    monkeypatch.setattr("bot.services.pod_replays.SessionLocal", lambda: _Ctx(session))
    player = Player(
        slug="finkel-1", discord_id="1", discord_username="finkel", display_name="Finkel",
        seventeenlands_token="t" * 32 if linked else None, active=True,
    )
    session.add(player)
    session.flush()
    for index, (finalized_at, kind) in enumerate(earlier_pods):
        _seed_pod(session, player, f"earlier-{index}", finalized_at, kind)
    _seed_pod(session, player, "current", LATER, "tournament")
    session.commit()

    discord_ids = unlinked_first_finishers_sync("current")

    assert (discord_ids == ["1"]) is prompted


def _seed_pod(session, player, event_id, finalized_at, kind):
    session.add(PodDraftEvent(
        id=event_id, set_code="FRA", name=event_id, event_time=finalized_at, event_date=finalized_at.date(),
        discord_thread_id=event_id, socket_status="complete", draftmancer_session=f"LLU-{event_id}",
        kind=kind, finalized_at=finalized_at,
    ))
    session.flush()
    session.add(PodDraftParticipant(event_id=event_id, player_id=player.id, display_name=player.display_name))


class _Ctx:
    def __init__(self, session):
        self.session = session

    def __enter__(self):
        return self.session

    def __exit__(self, *exc):
        return False
