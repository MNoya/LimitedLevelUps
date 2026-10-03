from datetime import date, datetime, timedelta, timezone

import pytest

from bot.commands.test_group import HALL_OF_FAME
from bot.models import DraftEvent, MagicSet, Player
from bot.services.tracker_detail import pending_draft_ids

DECK = {"maindeck": [], "sideboard": []}
FINISHED = datetime(2026, 10, 1, 20, 0, tzinfo=timezone.utc)


@pytest.mark.parametrize(
    "wins, losses, pool_rares, matches, pending",
    [
        (2, 1, None, None, True),
        (1, 0, 3, None, True),
        (2, 1, 3, 2, True),
        (2, 1, 3, 3, False),
        (0, 0, 3, None, False),
    ],
)
def test_draft_stays_pending_until_every_match_is_stored(session, wins, losses, pool_rares, matches, pending):
    player, magic_set = _add_player_and_set(session)
    match_results = None if matches is None else [{"match_number": n + 1} for n in range(matches)]
    session.add(DraftEvent(
        player_id=player.id, set_id=magic_set.id, seventeenlands_event_id="e1", format="TradDraft",
        expansion="FRA", wins=wins, losses=losses, is_trophy=False, pool_rares=pool_rares,
        deck_cards=DECK if pool_rares is not None else None, match_results=match_results,
    ))
    session.flush()

    result = pending_draft_ids(session, player.id, "FRA", cap=None)

    assert (len(result) == 1) is pending


@pytest.mark.parametrize(
    "finished_at, checked_at, pending",
    [
        (FINISHED, None, True),
        (FINISHED, FINISHED + timedelta(minutes=30), True),
        (FINISHED, FINISHED + timedelta(hours=2), False),
        (None, FINISHED + timedelta(days=3), True),
    ],
)
def test_incomplete_draft_settles_after_a_check_an_hour_past_its_finish(session, finished_at, checked_at, pending):
    player, magic_set = _add_player_and_set(session)
    session.add(DraftEvent(
        player_id=player.id, set_id=magic_set.id, seventeenlands_event_id="e1", format="TradDraft",
        expansion="FRA", wins=2, losses=1, is_trophy=False, finished_at=finished_at, detail_checked_at=checked_at,
    ))
    session.flush()

    result = pending_draft_ids(session, player.id, "FRA", cap=None)

    assert (len(result) == 1) is pending


def _add_player_and_set(session) -> tuple[Player, MagicSet]:
    magic_set = MagicSet(code="FRA", name="Reality Fracture", start_date=date(2026, 9, 29))
    player = Player(
        slug="finkel", discord_id="1001", discord_username=HALL_OF_FAME[0], display_name=HALL_OF_FAME[0],
        seventeenlands_token="t" * 32, active=True,
    )
    session.add_all([magic_set, player])
    session.flush()
    return player, magic_set
