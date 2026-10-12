import json
import sys
from types import SimpleNamespace

from sqlalchemy import func, select

from bot.models import FantasyPick, FantasyPlayer, FantasyResult
from bot.scripts import fantasy_dry_run, fantasy_sync
from bot.services.fantasy_event import event_for
from bot.services.fantasy_sync import upsert_event_row
from bot.services.melee import MeleeCompetitor, MeleeMatch, MeleeRound


class OneRoundMelee:
    def __init__(self, *args, **kwargs) -> None:
        pass

    def pairing_rounds(self, tournament_id: int) -> list[MeleeRound]:
        return [MeleeRound(round_id=1, name="Round 1", started=True)]

    def round_matches(self, round_id: int) -> list[MeleeMatch]:
        competitors = (
            MeleeCompetitor(username="Finkel", display_name="Jon Finkel", game_wins=2),
            MeleeCompetitor(username="Budde", display_name="Kai Budde", game_wins=1),
        )
        return [MeleeMatch(guid="m1", round_name="Round 1", table_number=1, has_result=True, game_draws=0,
                           competitors=competitors)]


def test_fantasy_sync_seeds_the_registry_field_and_stores_melee_results(session, monkeypatch):
    use_test_session(monkeypatch, fantasy_sync, session)
    monkeypatch.setattr(fantasy_sync, "MeleeClient", OneRoundMelee)
    monkeypatch.setattr(sys, "argv", ["fantasy_sync", "WC32"])

    fantasy_sync.main()

    players = session.scalar(select(func.count()).select_from(FantasyPlayer).where(FantasyPlayer.event_code == "WC32"))
    results = session.scalar(select(func.count()).select_from(FantasyResult).where(FantasyResult.event_code == "WC32"))
    assert players > 100
    assert results == 2


def test_fantasy_dry_run_stages_another_event_with_members(session, monkeypatch, tmp_path):
    use_test_session(monkeypatch, fantasy_sync, session)
    monkeypatch.setattr(fantasy_sync, "MeleeClient", OneRoundMelee)
    monkeypatch.setattr(sys, "argv", ["fantasy_sync", "WC32"])
    fantasy_sync.main()
    upsert_event_row(session, event_for("PTMSH"))
    session.commit()
    seed = tmp_path / "field.json"
    seed.write_text(json.dumps([{"firstName": "Jon", "lastName": "Finkel", "country": "United States",
                                 "countryCode": "US", "sources": [], "photoUrl": None, "meleeUsername": "Finkel"}]))
    use_test_session(monkeypatch, fantasy_dry_run, session)
    monkeypatch.setattr(fantasy_dry_run, "settings", SimpleNamespace(database_url="postgresql://localhost/test"))
    monkeypatch.setattr(sys, "argv", ["fantasy_dry_run", "--source", "WC32", "--target", "PTMSH",
                                      "--through-round", "1", "--members", "3", "--field-seed", str(seed)])

    fantasy_dry_run.main()

    results = session.scalar(select(func.count()).select_from(FantasyResult).where(FantasyResult.event_code == "PTMSH"))
    picks = session.scalar(select(func.count()).select_from(FantasyPick).where(FantasyPick.event_code == "PTMSH"))
    assert results == 2
    assert picks == 4 * 4


def use_test_session(monkeypatch, module, session):
    class Context:
        def __enter__(self):
            return session

        def __exit__(self, *exc):
            return False

    monkeypatch.setattr(module, "SessionLocal", lambda: Context())
