import json
import uuid
from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from bot.commands.test_group import HALL_OF_FAME
from bot.models import FantasyPick, FantasyPlayer, FantasyResult, FantasyRound
from bot.services.fantasy_event import FantasyEvent
from bot.services.fantasy_sync import sync_event
from bot.services.melee import MeleeCompetitor, MeleeMatch, MeleeRound


class FakeMelee:
    def __init__(self, matches: list[MeleeMatch]) -> None:
        self.matches = matches

    def pairing_rounds(self, tournament_id: int) -> list[MeleeRound]:
        return [MeleeRound(round_id=101, name="Round 1", started=True)]

    def round_matches(self, round_id: int) -> list[MeleeMatch]:
        return self.matches


def test_a_round_counts_as_complete_only_once_every_match_has_a_result(session):
    event = sample_event()

    sync_event(session, event, FakeMelee([match("a", "Finkel", "Budde", True), match("b", "Nassif", "Ruel", False)]))
    session.commit()
    after_one_result = session.scalars(select(FantasyRound.round_number)).all()
    sync_event(session, event, FakeMelee([match("a", "Finkel", "Budde", True), match("b", "Nassif", "Ruel", True)]))
    session.commit()
    after_both = session.scalars(select(FantasyRound.round_number)).all()

    assert after_one_result == []
    assert after_both == [1]


class FakeTop8Melee:
    def __init__(self, pairings: list[tuple[int, int]]) -> None:
        self.matches = []
        for table, (high_seed, low_seed) in enumerate(pairings, start=1):
            winner, loser = HALL_OF_FAME[high_seed - 1], HALL_OF_FAME[low_seed - 1]
            self.matches.append(match(f"qf{table}", winner, loser, True, table_number=table))

    def pairing_rounds(self, tournament_id: int) -> list[MeleeRound]:
        return [MeleeRound(round_id=104, name="Round 4", started=True),
                MeleeRound(round_id=105, name="Quarterfinals", started=True)]

    def round_matches(self, round_id: int) -> list[MeleeMatch]:
        return self.matches if round_id == 105 else []

    def standings_ranks(self, round_id: int, top: int) -> dict[str, int]:
        return {name: seed for seed, name in enumerate(HALL_OF_FAME[:top], start=1)}


@pytest.mark.parametrize("pairings, positions", [
    ([(1, 8), (4, 5), (2, 7), (3, 6)], ["QF1", "QF3", "QF2", "QF4"]),
    ([(1, 8), (4, 6), (2, 7), (3, 5)], ["QF1", "QF4", "QF2", "QF3"]),
    ([(5, 6), (1, 2), (3, 8), (4, 7)], ["QF1", "QF2", "QF3", "QF4"]),
])
def test_quarterfinals_take_their_bracket_position_from_the_lower_seed(session, pairings, positions):
    event = sample_event()

    sync_event(session, event, FakeTop8Melee(pairings))
    session.commit()

    stored = {}
    for guid, position in session.execute(select(FantasyResult.melee_match_guid, FantasyResult.bracket_position)):
        stored[guid] = position
    assert [stored[f"qf{table}"] for table in range(1, 5)] == positions


def test_a_bye_is_stored_as_a_win(session):
    event = sample_event()
    bye = MeleeMatch(
        guid="bye", round_name="Round 1", table_number=None, has_result=True, game_draws=0,
        competitors=(MeleeCompetitor(username="Finkel", display_name="Finkel", game_wins=2),),
    )

    sync_event(session, event, FakeMelee([bye]))
    session.commit()

    stored = session.execute(select(FantasyResult.result, FantasyResult.is_bye, FantasyResult.opponent_id)).one()
    assert tuple(stored) == ("W", True, None)


def test_a_drafted_top8_flags_the_table_fallback_once_on_the_first_quarterfinal_results(session):
    event = sample_event()
    drafted = [(5, 6), (1, 2), (3, 8), (4, 7)]

    first = sync_event(session, event, FakeTop8Melee(drafted))
    session.commit()
    second = sync_event(session, event, FakeTop8Melee(drafted))
    session.commit()

    assert (first.unseeded_quarterfinals, second.unseeded_quarterfinals) == (True, False)


@pytest.mark.parametrize("picked", [False, True])
def test_a_player_dropped_from_the_seed_leaves_the_field_unless_someone_picked_them(session, tmp_path, picked):
    kept, dropped = HALL_OF_FAME[0], HALL_OF_FAME[1]
    seed = tmp_path / "field.json"
    event = replace(sample_event(), field_seed=seed)
    seed.write_text(json.dumps([seed_entry(kept), seed_entry(dropped)]))
    sync_event(session, event, FakeMelee([]))
    session.commit()
    if picked:
        dropped_id = session.scalar(select(FantasyPlayer.id).where(FantasyPlayer.last_name == dropped))
        session.add(FantasyPick(user_id=uuid.uuid4(), event_code=event.code, slot="player", player_id=dropped_id))
        session.commit()

    seed.write_text(json.dumps([seed_entry(kept)]))
    sync_event(session, event, FakeMelee([]))
    session.commit()

    field = set(session.scalars(select(FantasyPlayer.last_name)).all())
    assert field == ({kept, dropped} if picked else {kept})


def seed_entry(last_name: str) -> dict:
    return {"firstName": "Pro", "lastName": last_name, "country": "United States", "countryCode": "US",
            "sources": [], "meleeUsername": None, "photoUrl": None}


def match(guid: str, winner: str, loser: str, finished: bool, table_number: int = 1) -> MeleeMatch:
    competitors = (
        MeleeCompetitor(username=winner, display_name=winner, game_wins=2 if finished else 0),
        MeleeCompetitor(username=loser, display_name=loser, game_wins=0),
    )
    return MeleeMatch(
        guid=guid, round_name="Round 1", table_number=table_number, has_result=finished, game_draws=0,
        competitors=competitors,
    )


def sample_event() -> FantasyEvent:
    locked = datetime.now(timezone.utc) - timedelta(days=1)
    return FantasyEvent(
        code="TEST", name="Test Worlds", melee_tournament_id=1, picks_lock_at=locked, swiss_rounds=4, cut_round=2,
        draft_rounds=(1,), bracket_lock_at=locked, schedule_name=None, field_seed=None,
        replay_only=False, live=False, slug="test-worlds", short_name="Test Worlds", crest_url=None, set_code="TRK",
    )
