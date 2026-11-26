from datetime import date, datetime, timedelta, timezone

import pytest

from bot.commands.test_group import HALL_OF_FAME
from bot.models import DailySealedPool, DraftEvent, MagicSet, Player
from bot.services import daily_sealed
from bot.services.daily_sealed import days_to_pick, pick_pool, ranked_candidates
from bot.sets import ALL_SETS

SET_CODE = "TRK"
DAY = date(2026, 11, 25)


@pytest.mark.parametrize("now, expected", [
    (datetime(2026, 11, 25, 9, 46, tzinfo=timezone.utc), [date(2026, 11, 24), date(2026, 11, 25)]),
    (datetime(2026, 11, 25, 5, 46, tzinfo=timezone.utc), [date(2026, 11, 24)]),
    (datetime(2026, 7, 10, 9, 46, tzinfo=timezone.utc), [date(2026, 7, 9), date(2026, 7, 10)]),
    (datetime(2026, 11, 25, 15, 30, tzinfo=timezone.utc), [date(2026, 11, 25)]),
])
def test_only_the_last_run_before_turnover_picks_the_next_day(now, expected):
    days = days_to_pick(now)

    assert days == expected


def test_candidates_skip_yesterday_s_player_used_pools_and_midweek_and_favor_new_players(session):
    trk = _seed_set(session)
    yesterday_player, repeat_player, fresh_player = (_seed_player(session, name) for name in HALL_OF_FAME[:3])
    used = _add_event(session, trk, repeat_player, "used")
    _add_pool(session, DAY - timedelta(days=2), used, repeat_player)
    yesterday_event = _add_event(session, trk, yesterday_player, "yesterday")
    _add_pool(session, DAY - timedelta(days=1), yesterday_event, yesterday_player)
    _add_event(session, trk, yesterday_player, "yesterday-again")
    _add_event(session, trk, fresh_player, "midweek", format="MidWeekSealed")
    _add_event(session, trk, fresh_player, "unfinished", finished=False)
    repeat_event = _add_event(session, trk, repeat_player, "repeat")
    fresh_event = _add_event(session, trk, fresh_player, "fresh")

    candidates = ranked_candidates(session, DAY, SET_CODE)

    assert [event.id for event in candidates] == [fresh_event.id, repeat_event.id]


def test_a_short_pool_is_skipped_for_the_next_candidate(session, monkeypatch):
    trk = _seed_set(session)
    short_player, full_player = (_seed_player(session, name) for name in HALL_OF_FAME[:2])
    _add_event(session, trk, short_player, "short")
    full = _add_event(session, trk, full_player, "full")
    monkeypatch.setattr(daily_sealed, "active_set_code", lambda when: SET_CODE)
    decks = {"short": _deck(10), "full": _deck(84)}

    pool = pick_pool(session, DAY, lambda event_id: decks[event_id], load_gih=lambda set_code: None)

    assert pool is not None
    assert pool.draft_event_id == full.id
    stored = session.get(DailySealedPool, DAY)
    assert len(stored.cards) == 84
    assert stored.original_main == [0, 1]


def test_of_three_pools_the_one_with_the_most_deep_colors_is_picked(session, monkeypatch):
    trk = _seed_set(session)
    players = [_seed_player(session, name) for name in HALL_OF_FAME[:3]]
    events = [_add_event(session, trk, player, f"pool-{i}") for i, player in enumerate(players)]
    monkeypatch.setattr(daily_sealed, "ranked_candidates", lambda session, day, set_code: events)
    monkeypatch.setattr(daily_sealed, "active_set_code", lambda when: SET_CODE)
    two_deep = _colored_deck("pool-0", {"W": 0.6, "U": 0.6, "B": 0.5, "R": 0.5, "G": 0.5})
    four_deep = _colored_deck("pool-1", {"W": 0.6, "U": 0.6, "B": 0.6, "R": 0.6, "G": 0.5})
    three_deep = _colored_deck("pool-2", {"W": 0.5, "U": 0.5, "B": 0.6, "R": 0.6, "G": 0.6})
    decks = {"pool-0": two_deep, "pool-1": four_deep, "pool-2": three_deep}
    gih = {}
    for deck in decks.values():
        gih.update(deck.pop("gih"))

    pool = pick_pool(session, DAY, decks.get, load_gih=lambda set_code: gih, pause=lambda seconds: None)

    assert pool.draft_event_id == events[1].id


def _seed_set(session):
    seed = next(s for s in ALL_SETS if s.code == SET_CODE)
    magic_set = MagicSet(code=seed.code, name=seed.name, start_date=seed.start_date, end_date=seed.end_date)
    session.add(magic_set)
    session.flush()
    return magic_set


def _seed_player(session, name):
    player = Player(slug=name.lower().replace(" ", "-"), discord_id=name, display_name=name, active=True)
    session.add(player)
    session.flush()
    return player


def _add_event(session, magic_set, player, event_id, format="Sealed", finished=True):
    event = DraftEvent(
        player_id=player.id, set_id=magic_set.id, seventeenlands_event_id=event_id, format=format,
        expansion=SET_CODE, wins=3, losses=3, is_trophy=False, colors="UB",
        finished_at=datetime(2026, 11, 20, tzinfo=timezone.utc) if finished else None,
    )
    session.add(event)
    session.flush()
    return event


def _add_pool(session, day, event, player):
    session.add(DailySealedPool(
        day=day, set_code=SET_CODE, draft_event_id=event.id, player_id=player.id, format=event.format,
        cards=[], colors="UB", wins=3, losses=3,
    ))
    session.flush()


def _deck(count):
    instant = {"cmc": 2, "color_identity": ["U"], "types": ["Instant"]}
    cards = {str(i): {"name": f"Card {i}", **instant} for i in range(count)}
    cards["basic"] = {"name": "Island", "types": ["Basic Land - Island"]}
    return {
        "groups": [
            {"name": "Maindeck", "cards": [0, 1, "basic"]},
            {"name": "Sideboard", "cards": list(range(2, count))},
        ],
        "cards": cards,
    }


def _colored_deck(prefix, rates):
    cards = {}
    gih = {}
    for color, rate in rates.items():
        for i in range(12):
            name = f"{prefix} {color} {i}"
            cards[name] = {"name": name, "cmc": 2, "color_identity": [color], "types": ["Creature"]}
            gih[name] = rate
    return {"groups": [{"name": "Sideboard", "cards": list(cards)}], "cards": cards, "gih": gih}
