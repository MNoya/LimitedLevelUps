from datetime import date, datetime, timezone

import pytest

from bot.commands.leaderboard import process_cube_board, resolve_cube_board
from bot.commands.test_group import HALL_OF_FAME
from bot.models import CubeSeasonWindow, DraftEvent, MagicSet, Player
from bot.services.player_stats import latest_cube_board, rank_cube_board
from bot.sets import CUBE_CODE, cube_variant

POWERED = "Cube - Powered"
PLANAR = "Cube - Planar"
ARENA = "Cube"


def _seed_set(session, code, start_date):
    s = MagicSet(code=code, name=code, start_date=start_date)
    session.add(s)
    session.flush()
    return s


def _seed_player(session, name, active=True, leaderboard_opt_in=True):
    p = Player(
        slug=name.lower().replace(" ", "-"),
        discord_id=f"cube-{name.lower()}",
        display_name=name,
        seventeenlands_token=(name.lower() * 32)[:32],
        active=active,
        leaderboard_opt_in=leaderboard_opt_in,
    )
    session.add(p)
    session.flush()
    return p


def _seed_draft(session, player, cube, expansion, started_at, trophies=1, event_id=None):
    session.add(DraftEvent(
        player_id=player.id,
        set_id=cube.id,
        seventeenlands_event_id=event_id or f"{player.slug}-{expansion}-{started_at.date()}",
        format="PremierDraft",
        expansion=expansion,
        wins=7,
        losses=1,
        is_trophy=trophies > 0,
        colors="WB",
        started_at=started_at,
        finished_at=started_at,
    ))
    session.flush()


def _seed_cube_season(session, set_code, start_date, end_date, variant="POWERED"):
    session.add(CubeSeasonWindow(
        variant=variant, set_code=set_code, start_date=start_date, end_date=end_date,
    ))
    session.flush()


def _at(year, month, day):
    return datetime(year, month, day, 18, 0, tzinfo=timezone.utc)


@pytest.fixture
def cube(session):
    return _seed_set(session, CUBE_CODE, date(2025, 10, 28))


def test_latest_cube_board_takes_the_variant_with_the_newest_draft(session, cube):
    _seed_set(session, "MSH", date(2026, 6, 23))
    finkel = _seed_player(session, HALL_OF_FAME[0])
    _seed_draft(session, finkel, cube, POWERED, _at(2026, 5, 2))
    _seed_draft(session, finkel, cube, PLANAR, _at(2026, 7, 22))
    session.commit()

    variant, season = latest_cube_board(session)

    assert (variant.slug, season) == ("PLANAR", None)


def test_latest_cube_board_resolves_the_seasoned_variant_to_its_newest_season(session, cube):
    _seed_set(session, "SOS", date(2026, 4, 21))
    _seed_set(session, "MSH", date(2026, 6, 23))
    _seed_cube_season(session, "SOS", date(2026, 4, 21), date(2026, 6, 22))
    lsv = _seed_player(session, HALL_OF_FAME[1])
    _seed_draft(session, lsv, cube, ARENA, _at(2025, 3, 2))
    _seed_draft(session, lsv, cube, POWERED, _at(2026, 5, 2))
    session.commit()

    variant, season = latest_cube_board(session)

    assert (variant.slug, season) == ("POWERED", "SOS")


def test_latest_cube_board_is_none_without_cube_drafts(session, cube):
    session.commit()

    assert latest_cube_board(session) is None


@pytest.mark.parametrize("board, expected", [
    ("CUBE-PLANAR", ("PLANAR", None)),
    ("CUBE-ARENA", ("ARENA", None)),
    ("CUBE-POWERED", ("POWERED", None)),
    ("CUBE-SOS", ("POWERED", "SOS")),
    ("CUBE", ("PLANAR", None)),
    ("CUBE-ALL", ("POWERED", None)),
    (None, ("PLANAR", None)),
    ("CUBE-NOPE", None),
])
def test_resolve_cube_board_maps_a_set_value_to_a_board(session, cube, board, expected):
    _seed_set(session, "SOS", date(2026, 4, 21))
    _seed_set(session, "MSH", date(2026, 6, 23))
    hump = _seed_player(session, HALL_OF_FAME[2])
    _seed_draft(session, hump, cube, PLANAR, _at(2026, 7, 22))
    session.commit()

    target = resolve_cube_board(session, board)

    assert (target and (target[0].slug, target[1])) == expected


def test_rank_cube_board_scopes_a_variant_board_to_its_own_cube(session, cube):
    _seed_set(session, "SOS", date(2026, 4, 21))
    paolo = _seed_player(session, HALL_OF_FAME[3])
    shota = _seed_player(session, HALL_OF_FAME[4])
    _seed_draft(session, paolo, cube, ARENA, _at(2024, 3, 2))
    _seed_draft(session, paolo, cube, ARENA, _at(2024, 3, 3))
    _seed_draft(session, shota, cube, POWERED, _at(2026, 5, 2))
    session.commit()

    arena = rank_cube_board(session, cube_variant("ARENA"), None)
    powered = rank_cube_board(session, cube_variant("POWERED"), None)

    assert [r.display_name for r in arena] == [HALL_OF_FAME[3]]
    assert [r.display_name for r in powered] == [HALL_OF_FAME[4]]


def test_rank_cube_board_scopes_a_season_to_its_declared_range(session, cube):
    _seed_set(session, "SOS", date(2026, 4, 21))
    _seed_set(session, "MSH", date(2026, 6, 23))
    _seed_cube_season(session, "SOS", date(2026, 4, 21), date(2026, 6, 22))
    _seed_cube_season(session, "MSH", date(2026, 6, 23), date(2026, 8, 10))
    reid = _seed_player(session, HALL_OF_FAME[5])
    chapin = _seed_player(session, HALL_OF_FAME[6])
    _seed_draft(session, reid, cube, POWERED, _at(2026, 5, 2))
    _seed_draft(session, chapin, cube, POWERED, _at(2026, 6, 30))
    session.commit()

    sos = rank_cube_board(session, cube_variant("POWERED"), "SOS")
    msh = rank_cube_board(session, cube_variant("POWERED"), "MSH")

    assert [r.display_name for r in sos] == [HALL_OF_FAME[5]]
    assert [r.display_name for r in msh] == [HALL_OF_FAME[6]]


def test_rank_cube_board_excludes_inactive_and_opted_out_players(session, cube):
    _seed_set(session, "SOS", date(2026, 4, 21))
    kibler = _seed_player(session, HALL_OF_FAME[10])
    levy = _seed_player(session, HALL_OF_FAME[11], active=False)
    nakamura = _seed_player(session, HALL_OF_FAME[12], leaderboard_opt_in=False)
    for player in (kibler, levy, nakamura):
        _seed_draft(session, player, cube, PLANAR, _at(2026, 7, 22))
    session.commit()

    ranked = rank_cube_board(session, cube_variant("PLANAR"), None)

    assert [r.display_name for r in ranked] == [HALL_OF_FAME[10]]


def test_process_cube_board_names_the_cube_and_its_season(session, cube):
    _seed_set(session, "SOS", date(2026, 4, 21))
    _seed_cube_season(session, "SOS", date(2026, 4, 21), date(2026, 6, 22))
    juza = _seed_player(session, HALL_OF_FAME[14])
    _seed_draft(session, juza, cube, POWERED, _at(2026, 5, 2))
    session.commit()

    season = process_cube_board(session, viewer_discord_id=None, board="CUBE-SOS")
    lifetime = process_cube_board(session, viewer_discord_id=None, board="CUBE-POWERED")

    assert (season.set_code, season.drafter_count) == ("CUBE-SOS", 1)
    assert lifetime.set_code == "CUBE-POWERED"


def test_process_cube_board_is_none_for_an_empty_board(session, cube):
    owen = _seed_player(session, HALL_OF_FAME[15])
    _seed_draft(session, owen, cube, ARENA, _at(2024, 3, 2))
    session.commit()

    assert process_cube_board(session, viewer_discord_id=None, board="CUBE-PLANAR") is None
