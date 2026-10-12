import importlib.util
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from sqlalchemy import text


@pytest.fixture(scope="module")
def fantasy_views(engine):
    migration_path = Path(__file__).resolve().parents[2] / "alembic/versions/f4n7a5y1w0c1_fantasy_worlds.py"
    spec = importlib.util.spec_from_file_location("fantasy_migration", migration_path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    with engine.begin() as conn:
        for statement in migration.VIEW_STATEMENTS:
            conn.execute(text(statement))


@pytest.fixture
def event(session, fantasy_views):
    locked = datetime.now(timezone.utc) - timedelta(days=1)
    session.execute(text("""
        INSERT INTO fantasy_events (code, name, melee_tournament_id, picks_lock_at, swiss_rounds, cut_round,
                                    draft_rounds, bracket_lock_at)
        VALUES ('TEST', 'Test Worlds', 1, :locked, 4, 2, '{1,4}', :locked)
    """), {"locked": locked})
    for name in ("Finkel", "Budde", "Nassif", "Ruel"):
        session.execute(text("""
            INSERT INTO fantasy_players (event_code, slug, first_name, last_name)
            VALUES ('TEST', lower(:name), :name, :name)
        """), {"name": name})
    session.commit()
    return "TEST"


@pytest.mark.parametrize("slot, expected", [
    ("captain", 14 + 8),
    ("drafter", 9 + 8),
    ("constructed", 8 + 8),
    ("player", 7 + 8),
])
def test_lineup_points_follow_slot_multipliers_and_flat_top8_bonus(session, event, slot, expected):
    finkel = player_id(session, "Finkel")
    add_results(session, finkel, [(1, "W", "draft"), (2, "W", "constructed"), (3, "D", "constructed"),
                                  (4, "L", "draft")])
    add_result(session, finkel, 5, "W", "constructed", stage="quarterfinal", position="QF1")
    add_result(session, finkel, 6, "L", "constructed", stage="semifinal", position="SF1")
    member = add_member(session, {slot: finkel})

    standing = standing_for(session, member)

    assert standing.points == expected


@pytest.mark.parametrize("original_plays_day_two, expected_points", [
    (False, 3 + 3),
    (True, 3 + 1),
])
def test_replacement_scores_from_its_round_only_when_the_original_missed_day_two(
    session, event, original_plays_day_two, expected_points,
):
    finkel, budde = player_id(session, "Finkel"), player_id(session, "Budde")
    add_results(session, finkel, [(1, "W", "draft"), (2, "L", "constructed")])
    if original_plays_day_two:
        add_results(session, finkel, [(3, "D", "constructed"), (4, "L", "draft")])
    add_results(session, budde, [(1, "L", "draft"), (2, "L", "constructed"), (3, "W", "constructed"),
                                 (4, "L", "draft")])
    member = add_member(session, {"player": finkel})
    add_pick(session, member, "player", budde, from_round=3)

    standing = standing_for(session, member)

    assert standing.points == expected_points


def test_bracket_scores_each_correct_winner_by_round_plus_exact_games_into_the_total(session, event):
    finkel, budde, nassif, ruel = (player_id(session, name) for name in ("Finkel", "Budde", "Nassif", "Ruel"))
    add_result(session, finkel, 5, "W", "constructed", stage="quarterfinal", position="QF1", games=(3, 1))
    add_result(session, budde, 5, "W", "constructed", stage="quarterfinal", position="QF3", games=(3, 2))
    add_result(session, finkel, 6, "W", "constructed", stage="semifinal", position="SF1", games=(3, 0))
    add_result(session, nassif, 7, "W", "constructed", stage="final", position="F", games=(3, 2))
    member = add_member(session, {"player": ruel})
    for position, winner, games in (("QF1", finkel, "3-1"), ("QF3", nassif, "3-2"), ("SF1", finkel, "3-2"),
                                    ("F", nassif, "3-2")):
        add_bracket_pick(session, member, position, winner, games)

    standing = standing_for(session, member)

    bracket_points = 2 + 1 + 4 + 8 + 1
    expected = (bracket_points, bracket_points, True)
    assert (standing.bracket_points, standing.points, standing.champion_called) == expected


@pytest.mark.parametrize("from_round, minutes_after_lock, day_two_started, expected", [
    (1, -1, False, True),
    (1, 1, False, False),
    (3, -1, False, False),
    (3, 1, False, True),
    (3, 1, True, False),
    (2, 1, False, False),
])
def test_pick_window_closes_day_one_at_lock_and_replacements_at_day_two_start(
    session, event, from_round, minutes_after_lock, day_two_started, expected,
):
    lock = session.execute(text("SELECT picks_lock_at FROM fantasy_events WHERE code = 'TEST'")).scalar()
    if day_two_started:
        session.execute(text("UPDATE fantasy_events SET day_two_started_at = :at WHERE code = 'TEST'"),
                        {"at": lock + timedelta(seconds=30)})
    at = lock + timedelta(minutes=minutes_after_lock)

    is_open = session.execute(
        text("SELECT fantasy_pick_window_open('TEST', :from_round, :at)"), {"from_round": from_round, "at": at},
    ).scalar()

    assert is_open is expected


def test_a_winner_pick_without_games_scores_the_winner_points_only(session, event):
    finkel, ruel = player_id(session, "Finkel"), player_id(session, "Ruel")
    add_result(session, finkel, 5, "W", "constructed", stage="quarterfinal", position="QF1", games=(3, 1))
    member = add_member(session, {"player": ruel})
    add_bracket_pick(session, member, "QF1", finkel, None)

    standing = standing_for(session, member)

    assert standing.bracket_points == 2


def test_tied_totals_rank_by_champion_call_then_earliest_day_one_save(session, event):
    finkel, budde, nassif, ruel = (player_id(session, name) for name in ("Finkel", "Budde", "Nassif", "Ruel"))
    add_result(session, finkel, 6, "W", "constructed", stage="semifinal", position="SF1", games=(3, 0))
    add_result(session, budde, 6, "W", "constructed", stage="semifinal", position="SF2", games=(3, 0))
    add_result(session, nassif, 7, "W", "constructed", stage="final", position="F", games=(3, 0))
    lock = session.execute(text("SELECT picks_lock_at FROM fantasy_events WHERE code = 'TEST'")).scalar()
    champion_caller = add_member(session, {"player": ruel}, saved_at=lock - timedelta(hours=1))
    add_bracket_pick(session, champion_caller, "F", nassif, "3-2")
    semifinal_caller = add_member(session, {"player": ruel}, saved_at=lock - timedelta(hours=3))
    add_bracket_pick(session, semifinal_caller, "SF1", finkel, "3-2")
    add_bracket_pick(session, semifinal_caller, "SF2", budde, "3-2")
    early_saver = add_member(session, {"player": ruel}, saved_at=lock - timedelta(hours=2))
    late_saver = add_member(session, {"player": ruel}, saved_at=lock - timedelta(minutes=5))

    ranks = [standing_for(session, member).rank
             for member in (champion_caller, semifinal_caller, early_saver, late_saver)]

    assert ranks == [1, 2, 3, 4]


@pytest.mark.parametrize("revealed, top8_started, lock_passed, expected", [
    (3, False, False, False),
    (4, False, False, True),
    (4, True, False, False),
    (4, False, True, False),
])
def test_bracket_window_opens_when_the_last_swiss_round_is_revealed(
    session, event, revealed, top8_started, lock_passed, expected,
):
    now = datetime.now(timezone.utc)
    session.execute(
        text("UPDATE fantasy_events SET revealed_through_round = :revealed, top8_started_at = :started, "
             "bracket_lock_at = :lock WHERE code = 'TEST'"),
        {"revealed": revealed, "started": now - timedelta(minutes=1) if top8_started else None,
         "lock": now - timedelta(minutes=1) if lock_passed else now + timedelta(hours=1)},
    )

    is_open = session.execute(text("SELECT fantasy_bracket_window_open('TEST', :at)"), {"at": now}).scalar()

    assert is_open is expected


def player_id(session, name):
    return session.execute(text("SELECT id FROM fantasy_players WHERE first_name = :name"), {"name": name}).scalar()


def add_results(session, player, rounds):
    for round_number, result, match_format in rounds:
        add_result(session, player, round_number, result, match_format)


def add_result(session, player, round_number, result, match_format, stage="swiss", position=None, games=(0, 0)):
    session.execute(text("""
        INSERT INTO fantasy_results (event_code, round_number, player_id, stage, format, result, game_wins,
                                     game_losses, bracket_position)
        VALUES ('TEST', :round_number, :player, :stage, :format, :result, :wins, :losses, :position)
    """), {"round_number": round_number, "player": player, "stage": stage, "format": match_format,
           "result": result, "wins": games[0], "losses": games[1], "position": position})
    session.commit()


def add_member(session, lineup, saved_at=None):
    member = uuid.uuid4()
    session.execute(text("INSERT INTO fantasy_members (user_id, name) VALUES (:user_id, 'Member')"),
                    {"user_id": member})
    for slot, player in lineup.items():
        add_pick(session, member, slot, player, saved_at=saved_at)
    return member


def add_pick(session, member, slot, player, from_round=1, saved_at=None):
    session.execute(text("""
        INSERT INTO fantasy_picks (user_id, event_code, slot, from_round, player_id, updated_at)
        VALUES (:user_id, 'TEST', :slot, :from_round, :player, coalesce(:saved_at, now()))
    """), {"user_id": member, "slot": slot, "from_round": from_round, "player": player, "saved_at": saved_at})
    session.commit()


def add_bracket_pick(session, member, position, winner, games):
    session.execute(text("""
        INSERT INTO fantasy_bracket_picks (user_id, event_code, position, winner_id, games)
        VALUES (:user_id, 'TEST', :position, :winner, :games)
    """), {"user_id": member, "position": position, "winner": winner, "games": games})
    session.commit()


def standing_for(session, member):
    return session.execute(text("""
        SELECT s.* FROM public_fantasy_standings s
        WHERE s.member_key = left(encode(sha256(CAST(:user_id AS text)::bytea), 'hex'), 16)
    """), {"user_id": str(member)}).one()
