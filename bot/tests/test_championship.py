from datetime import date, datetime, timedelta, timezone

from bot.models import MagicSet, Player, PlayerStats, PodChampionshipSeed, PodDraftEvent
from bot.services import championship
from bot.services.championship import (
    CREATION_LEAD_DAYS,
    championship_date_before,
    plan_due_for_creation,
    plan_for,
)
from bot.services.player_stats import rank_ordered_names, seed_attendees
from bot.sets import RELEASE_TZ


def _session_factory(session):
    class _Ctx:
        def __enter__(self):
            return session

        def __exit__(self, *exc):
            return False

    return lambda: _Ctx()


def _seed_set(session, code="MSH"):
    magic_set = MagicSet(code=code, name=code, start_date=date(2026, 6, 23))
    session.add(magic_set)
    session.flush()
    return magic_set


def _seed_player(session, name, discord_id, opt_in=True):
    player = Player(
        slug=f"{name.lower()}-{discord_id}", discord_id=discord_id, discord_username=name.lower(),
        display_name=name, seventeenlands_token=(name.lower() * 32)[:32], active=True,
        leaderboard_opt_in=opt_in,
    )
    session.add(player)
    session.flush()
    return player


def _seed_stats(session, player, magic_set, trophies, events):
    session.add(PlayerStats(
        player_id=player.id, set_id=magic_set.id, format="PremierDraft", expansion=magic_set.code,
        events=events, wins=trophies * 7, losses=max(0, events - trophies), games_played=events * 5,
        trophies=trophies,
    ))


def _seed_event(session):
    event = PodDraftEvent(
        event_date=date(2026, 8, 1), event_time=datetime(2026, 8, 1, 18, tzinfo=timezone.utc),
        set_code="MSH", name="👑 MSH Set Championship", draftmancer_session="champ",
        discord_thread_id="thread-champ", socket_status="pending", pairing_mode="swiss",
    )
    session.add(event)
    session.flush()
    return event


def test_championship_is_the_second_saturday_before_a_tuesday_release():
    # The Hobbit releases Tue 2026-08-11; prerelease weekend Aug 7-9; championship the Saturday before
    assert championship_date_before(date(2026, 8, 11)) == date(2026, 8, 1)


def test_championship_date_holds_for_other_release_weekdays():
    assert championship_date_before(date(2026, 9, 29)).weekday() == 5
    assert championship_date_before(date(2026, 11, 10)).weekday() == 5
    thursday_release = date(2026, 8, 13)
    assert championship_date_before(thursday_release) == date(2026, 8, 1)


def test_plan_for_active_set_anchors_to_its_successor():
    during_msh = datetime(2026, 7, 27, 17, 0, tzinfo=timezone.utc)

    plan = plan_for(during_msh)

    assert plan is not None
    assert (plan.set_code, plan.next_set_code) == ("MSH", "HOB")
    assert plan.event_at.astimezone(RELEASE_TZ).date() == date(2026, 8, 1)
    assert plan.event_at.astimezone(RELEASE_TZ).hour == 14
    assert plan.create_on == date(2026, 8, 1) - timedelta(days=CREATION_LEAD_DAYS)


def test_plan_is_none_without_a_registered_successor():
    far_future = datetime(2100, 1, 1, tzinfo=timezone.utc)

    assert plan_for(far_future) is None


def test_due_for_creation_only_on_the_creation_day():
    creation_day = datetime(2026, 7, 27, 17, 0, tzinfo=timezone.utc)
    other_day = datetime(2026, 7, 28, 17, 0, tzinfo=timezone.utc)

    assert plan_due_for_creation(creation_day) is not None
    assert plan_due_for_creation(other_day) is None


def test_freeze_snapshots_ranked_players_best_first(session, monkeypatch):
    monkeypatch.setattr(championship, "SessionLocal", _session_factory(session))
    magic_set = _seed_set(session, "MSH")
    alice = _seed_player(session, "Alice", "1")
    bob = _seed_player(session, "Bob", "2")
    _seed_player(session, "Carol", "3", opt_in=False)
    _seed_stats(session, alice, magic_set, trophies=2, events=4)
    _seed_stats(session, bob, magic_set, trophies=5, events=8)
    event = _seed_event(session)
    session.commit()

    count = championship.freeze_seeds_sync(event.id, "MSH")
    seeds = championship.frozen_seeds_sync(event.id)

    assert count == 2
    assert [s.display_name for s in seeds] == ["Bob", "Alice"]
    assert [s.rank for s in seeds] == [1, 2]


def test_frozen_rank_map_keys_by_player(session, monkeypatch):
    monkeypatch.setattr(championship, "SessionLocal", _session_factory(session))
    magic_set = _seed_set(session, "MSH")
    alice = _seed_player(session, "Alice", "1")
    bob = _seed_player(session, "Bob", "2")
    _seed_stats(session, alice, magic_set, trophies=2, events=4)
    _seed_stats(session, bob, magic_set, trophies=5, events=8)
    event = _seed_event(session)
    session.commit()
    championship.freeze_seeds_sync(event.id, "MSH")

    ranks = championship.rank_override(session, event.id)

    assert ranks == {bob.id: 1, alice.id: 2}


def test_frozen_override_seeds_against_live_standings(session):
    magic_set = _seed_set(session, "MSH")
    alice = _seed_player(session, "Alice", "1")
    bob = _seed_player(session, "Bob", "2")
    _seed_stats(session, alice, magic_set, trophies=2, events=4)
    _seed_stats(session, bob, magic_set, trophies=5, events=8)
    session.commit()
    frozen = {alice.id: 1, bob.id: 2}

    live_order = rank_ordered_names(session, ["Alice", "Bob"])
    frozen_order = rank_ordered_names(session, ["Alice", "Bob"], frozen)
    seeded = seed_attendees(session, ["Alice", "Bob"], frozen)

    assert live_order == ["Bob", "Alice"]
    assert frozen_order == ["Alice", "Bob"]
    assert [(a.display_name, a.rank) for a in seeded] == [("Alice", 1), ("Bob", 2)]


def test_the_override_is_the_frozen_snapshot_for_a_championship_and_nothing_for_a_pod(session):
    """Every surface that ranks a championship roster resolves through one override, so the seeding card,
    the launcher pointer and the seats the draft is dealt in cannot read different scales. A player who
    joined the board after the freeze is absent from it and keeps their live rank."""
    magic_set = _seed_set(session, "MSH")
    alice = _seed_player(session, "Alice", "1")
    bob = _seed_player(session, "Bob", "2")
    _seed_stats(session, alice, magic_set, trophies=2, events=4)
    _seed_stats(session, bob, magic_set, trophies=5, events=8)
    event = _seed_event(session)
    ordinary = PodDraftEvent(
        event_date=date(2026, 8, 1), event_time=datetime(2026, 8, 1, 18, tzinfo=timezone.utc),
        set_code="MSH", name="MSH Aug 1 Early Pod", draftmancer_session="pod",
        discord_thread_id="thread-pod", socket_status="pending",
    )
    session.add(ordinary)
    session.flush()
    session.add(PodChampionshipSeed(
        event_id=event.id, player_id=alice.id, discord_id="1", display_name="Alice", rank=1, score=9.0,
    ))
    session.commit()

    override = championship.rank_override(session, event.id)

    assert override == {alice.id: 1}
    assert championship.rank_override(session, ordinary.id) is None
    assert rank_ordered_names(session, ["Alice", "Bob"], override) == ["Alice", "Bob"]


def test_freeze_replaces_a_prior_snapshot(session, monkeypatch):
    monkeypatch.setattr(championship, "SessionLocal", _session_factory(session))
    magic_set = _seed_set(session, "MSH")
    bob = _seed_player(session, "Bob", "2")
    _seed_stats(session, bob, magic_set, trophies=5, events=8)
    event = _seed_event(session)
    session.commit()

    championship.freeze_seeds_sync(event.id, "MSH")
    championship.freeze_seeds_sync(event.id, "MSH")

    assert len(championship.frozen_seeds_sync(event.id)) == 1


def test_freeze_respects_depth(session, monkeypatch):
    monkeypatch.setattr(championship, "SessionLocal", _session_factory(session))
    magic_set = _seed_set(session, "MSH")
    for i in range(4):
        player = _seed_player(session, f"P{i}", str(100 + i))
        _seed_stats(session, player, magic_set, trophies=4 - i, events=8)
    event = _seed_event(session)
    session.commit()

    count = championship.freeze_seeds_sync(event.id, "MSH", depth=2)

    assert count == 2


def _seed_row(rank, discord_id):
    return championship.SeedRow(
        rank=rank, player_id=f"p{rank}", discord_id=discord_id, display_name=f"P{rank}", score=100.0 - rank,
    )


def test_wave_tiers_are_top_ten_then_eleven_to_twenty_then_twentyone_to_thirtytwo():
    seeds = [_seed_row(r, str(r)) for r in range(1, 33)]

    assert [s.rank for s in championship.wave_recipients(seeds, 0)] == list(range(1, 11))
    assert [s.rank for s in championship.wave_recipients(seeds, 1)] == list(range(11, 21))
    assert [s.rank for s in championship.wave_recipients(seeds, 2)] == list(range(21, 33))


def test_wave_recipients_are_ungated_by_yes_count():
    seeds = [_seed_row(r, str(r)) for r in range(1, 33)]

    # Every wave still returns its full tier no matter how many have committed
    assert len(championship.wave_recipients(seeds, 1)) == 10


def test_wave_recipients_drops_seeds_without_a_discord_id():
    seeds = [_seed_row(1, "1"), _seed_row(2, None), _seed_row(3, "3")]

    assert [s.rank for s in championship.wave_recipients(seeds, 0)] == [1, 3]
