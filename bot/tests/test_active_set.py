import pytest

from bot.models import MagicSet, Player, PlayerStats, SelfReportedEvent
from bot.services import active_set as active_set_service
from bot.services.active_set import resolve_board_set
from bot.sets import ALL_SETS

ACTIVE = "MSH"
NEXT_UP = "HOB"
FURTHER_OUT = "FRA"


def _seed_sets(session):
    for seed in ALL_SETS:
        if seed.code in (ACTIVE, NEXT_UP, FURTHER_OUT):
            session.add(MagicSet(
                code=seed.code, name=seed.name, start_date=seed.start_date, end_date=seed.end_date,
            ))
    session.flush()


def _seed_player(session):
    player = Player(
        slug="finkel", discord_id="1", discord_username="finkel", display_name="Finkel", active=True,
    )
    session.add(player)
    session.flush()
    return player


def _add_self_reported(session, player, set_code):
    session.add(SelfReportedEvent(
        player_id=player.id, set_code=set_code, record="3-0", is_trophy=True, platform="Paper",
        source_channel_id="1", source_message_id=f"msg-{set_code}", source_url="https://example.test",
    ))
    session.flush()


def _add_player_stats(session, player, set_code):
    magic_set = session.query(MagicSet).filter_by(code=set_code).one()
    session.add(PlayerStats(
        player_id=player.id, set_id=magic_set.id, format="PremierDraft", expansion=set_code,
        events=1, wins=7, losses=0, trophies=1,
    ))
    session.flush()


@pytest.mark.parametrize("results_for, expected", [
    (None, ACTIVE),
    (NEXT_UP, NEXT_UP),
    (FURTHER_OUT, ACTIVE),
])
def test_board_flips_on_the_next_set_s_first_self_reported_trophy(
    session, monkeypatch, results_for, expected,
):
    _seed_sets(session)
    player = _seed_player(session)
    next_seed = next(s for s in ALL_SETS if s.code == NEXT_UP)
    further_seed = next(s for s in ALL_SETS if s.code == FURTHER_OUT)
    monkeypatch.setattr(active_set_service, "active_set_code", lambda: ACTIVE)
    monkeypatch.setattr(active_set_service, "upcoming_sets", lambda: (next_seed, further_seed))
    if results_for is not None:
        _add_self_reported(session, player, results_for)

    board = resolve_board_set(session)

    assert board is not None
    assert board.code == expected


def test_board_flips_on_early_access_17lands_rows(session, monkeypatch):
    _seed_sets(session)
    player = _seed_player(session)
    next_seed = next(s for s in ALL_SETS if s.code == NEXT_UP)
    monkeypatch.setattr(active_set_service, "active_set_code", lambda: ACTIVE)
    monkeypatch.setattr(active_set_service, "upcoming_sets", lambda: (next_seed,))
    _add_player_stats(session, player, NEXT_UP)

    board = resolve_board_set(session)

    assert board is not None
    assert board.code == NEXT_UP
