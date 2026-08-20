from datetime import date, datetime, timedelta, timezone

from bot.commands.pod_schedule import championship_line
from bot.commands.test_group import HALL_OF_FAME
from bot.models import (
    DraftEvent,
    MagicSet,
    Player,
    PlayerStats,
    PodChampionshipSeed,
    PodDraftEvent,
    PodDraftParticipant,
)
from bot.services import championship
from bot.services.championship import (
    CREATION_LEAD_DAYS,
    championship_date_before,
    plan_due_for_creation,
    plan_for,
)
from bot.services.player_stats import FrozenSeed, rank_ordered_names, seed_attendees
from bot.services.pod_format_schedule import calendar_days
from bot.services.pod_season import rank_pod_season
from bot.sets import RELEASE_TZ, SetSeed


_ACTIVE_SET: dict = {}


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


def _seed_drafts(session, player, magic_set, *, finished_at, trophies, events):
    """Individual drafts, which is what an as-of-deadline board is rebuilt from. `player_stats` is left
    alone on purpose: a cutoff has to reach past the derived aggregates to the event log."""
    for index in range(events):
        session.add(DraftEvent(
            player_id=player.id, set_id=magic_set.id,
            seventeenlands_event_id=f"{player.id}-{finished_at:%m%d}-{index}",
            format="PremierDraft", expansion=magic_set.code,
            wins=7 if index < trophies else 3, losses=0 if index < trophies else 3,
            is_trophy=index < trophies, finished_at=finished_at,
        ))
    session.flush()


def _seed_event(session):
    event = PodDraftEvent(
        event_date=date(2026, 8, 1), event_time=datetime(2026, 8, 1, 18, tzinfo=timezone.utc),
        set_code="MSH", name="👑 MSH Set Championship", draftmancer_session="champ",
        discord_thread_id="thread-champ", socket_status="pending", pairing_mode="swiss",
    )
    session.add(event)
    session.flush()
    return event


def test_championship_is_the_saturday_before_the_prerelease_weekend():
    friday_prerelease = date(2026, 8, 7)
    thursday_prerelease = date(2026, 8, 6)

    assert championship_date_before(friday_prerelease) == date(2026, 8, 1)
    assert championship_date_before(thursday_prerelease) == date(2026, 8, 1)


def test_championship_date_holds_for_the_upcoming_prerelease_weekends():
    assert championship_date_before(date(2026, 9, 25)).weekday() == 5
    assert championship_date_before(date(2026, 11, 6)).weekday() == 5


def test_plan_for_active_set_anchors_to_its_successor():
    during_msh = datetime(2026, 7, 27, 17, 0, tzinfo=timezone.utc)

    plan = plan_for(during_msh)

    assert plan is not None
    assert (plan.set_code, plan.next_set_code) == ("MSH", "HOB")
    assert plan.event_at.astimezone(RELEASE_TZ).date() == date(2026, 8, 1)
    assert plan.event_at.astimezone(RELEASE_TZ).hour == 14
    assert plan.create_on == date(2026, 8, 1) - timedelta(days=CREATION_LEAD_DAYS)


def test_schedule_names_a_championship_the_set_live_today_does_not_hold():
    span = calendar_days(date(2026, 8, 10), 8)
    hob_championship = datetime(2026, 9, 19, 14, 0, tzinfo=RELEASE_TZ)

    line = championship_line(None, span, datetime(2026, 8, 10, 12, 0, tzinfo=RELEASE_TZ))

    assert str(int(hob_championship.timestamp())) in line


def test_schedule_drops_the_championship_once_it_has_been_played():
    week = calendar_days(date(2026, 7, 31), 1)

    before = championship_line(None, week, datetime(2026, 7, 31, 12, 0, tzinfo=RELEASE_TZ))
    after = championship_line(None, week, datetime(2026, 8, 2, 12, 0, tzinfo=RELEASE_TZ))

    assert before != ""
    assert after == ""


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

    assert [(ranks[bob.id].rank, ranks[bob.id].trophies), (ranks[alice.id].rank, ranks[alice.id].trophies)] == [
        (1, 5), (2, 2),
    ]
    assert ranks[bob.id].score > ranks[alice.id].score


def test_frozen_override_seeds_against_live_standings(session):
    magic_set = _seed_set(session, "MSH")
    alice = _seed_player(session, "Alice", "1")
    bob = _seed_player(session, "Bob", "2")
    _seed_stats(session, alice, magic_set, trophies=2, events=4)
    _seed_stats(session, bob, magic_set, trophies=5, events=8)
    session.commit()
    frozen = {alice.id: FrozenSeed(1, 40.0), bob.id: FrozenSeed(2, 30.0)}

    live_order = rank_ordered_names(session, ["Alice", "Bob"])
    frozen_order = rank_ordered_names(session, ["Alice", "Bob"], frozen)
    seeded = seed_attendees(session, ["Alice", "Bob"], frozen)

    assert live_order == ["Bob", "Alice"]
    assert frozen_order == ["Alice", "Bob"]
    assert [(a.display_name, a.rank, a.score) for a in seeded] == [("Alice", 1, 40.0), ("Bob", 2, 30.0)]


def test_the_override_is_the_frozen_snapshot_for_a_championship_and_nothing_for_a_pod(session):
    """Every surface that ranks a championship roster resolves through one override, so the seeding card,
    the launcher pointer and the seats the draft is dealt in cannot read different scales. A player absent
    from the snapshot did not rank by the deadline, so they trail the players who did."""
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

    assert override == {alice.id: FrozenSeed(1, 9.0)}
    assert championship.rank_override(session, ordinary.id) is None
    assert rank_ordered_names(session, ["Alice", "Bob"], override) == ["Alice", "Bob"]


def test_the_freeze_counts_what_was_played_by_the_deadline_whenever_the_profile_was_linked(
    session, monkeypatch,
):
    """The deadline is a time, not a guest list. A player who linked 17lands after it is ranked on the drafts
    they had already finished before it, and drafts finished after it count for nobody."""
    monkeypatch.setattr(championship, "SessionLocal", _session_factory(session))
    monkeypatch.setattr(
        "bot.services.player_stats.resolve_active_set", lambda _session: _ACTIVE_SET.get("row")
    )
    magic_set = _seed_set(session, "MSH")
    _ACTIVE_SET["row"] = magic_set
    deadline = datetime(2026, 7, 27, 16, tzinfo=timezone.utc)
    early = _seed_player(session, "Early", "1")
    late_linker = _seed_player(session, "LateLinker", "2")
    after_only = _seed_player(session, "AfterOnly", "3")
    _seed_drafts(session, early, magic_set, finished_at=deadline - timedelta(days=2), trophies=2, events=8)
    _seed_drafts(
        session, late_linker, magic_set, finished_at=deadline - timedelta(days=1), trophies=5, events=8,
    )
    _seed_drafts(
        session, late_linker, magic_set, finished_at=deadline + timedelta(days=1), trophies=0, events=6,
    )
    _seed_drafts(session, after_only, magic_set, finished_at=deadline + timedelta(hours=2), trophies=6, events=8)
    event = _seed_event(session)
    session.commit()

    championship.freeze_seeds_sync(event.id, "MSH", deadline)
    seeds = championship.frozen_seeds_sync(event.id)
    order = rank_ordered_names(
        session, ["Early", "LateLinker", "AfterOnly"], championship.rank_override(session, event.id),
    )

    assert [seed.display_name for seed in seeds] == ["LateLinker", "Early"]
    assert order == ["LateLinker", "Early", "AfterOnly"]


def test_a_championship_seats_only_its_top_eight_and_any_other_pod_keeps_everyone(session):
    """A championship is one table of eight, so the lobby ping, the Draftmancer waiting list and the link
    DMs all address the eight best seeds and leave the rest as alternates. A seat passes down the frozen
    order when someone above drops out, and a Yes carrying no seed at all sorts last."""
    event = _seed_event(session)
    ordinary = PodDraftEvent(
        event_date=date(2026, 8, 1), event_time=datetime(2026, 8, 1, 18, tzinfo=timezone.utc),
        set_code="MSH", name="MSH Aug 1 Early Pod", draftmancer_session="pod",
        discord_thread_id="thread-pod", socket_status="pending",
    )
    session.add(ordinary)
    for rank, name in enumerate(HALL_OF_FAME[:10], 1):
        session.add(PodChampionshipSeed(
            event_id=event.id, player_id=None, discord_id=f"d{rank}", display_name=name,
            rank=rank, score=100.0 - rank,
        ))
    session.commit()
    roster = [(f"d{rank}", name) for rank, name in reversed(list(enumerate(HALL_OF_FAME[:10], 1)))]
    roster.append(("unseeded", "Walk On"))

    seated = championship.playing_roster(session, event.id, roster)

    assert [name for _, name in seated] == list(HALL_OF_FAME[:8])
    assert championship.playing_roster(session, ordinary.id, roster) == roster


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


def _seed_pod(session, *, event_date, set_code="MSH", kind="tournament", name="Pod"):
    event = PodDraftEvent(
        event_date=event_date, event_time=datetime.combine(event_date, datetime.min.time(), timezone.utc),
        set_code=set_code, name=name, draftmancer_session=f"s-{event_date}-{set_code}-{name}",
        discord_thread_id=f"t-{event_date}-{set_code}-{name}", socket_status="pending", kind=kind,
    )
    session.add(event)
    session.flush()
    return event


def _seed_pod_result(session, event, player, record):
    session.add(PodDraftParticipant(
        event_id=event.id, player_id=player.id, display_name=player.display_name, record=record,
    ))
    session.flush()


MSH_SEED = SetSeed("MSH", "Marvel Super Heroes", date(2026, 6, 23), date(2026, 8, 10))


def test_the_pod_season_counts_every_pod_in_the_window_and_the_set_outside_it(session):
    """Cube and flashback pods played inside the set's window count, a pod drafting the set outside its
    window still counts, a pod outside both does not, and a mock carries no record so it never scores."""
    grinder = _seed_player(session, "Finkel", "1")
    _seed_pod_result(session, _seed_pod(session, event_date=date(2026, 7, 1), set_code="CUBE"), grinder, "3-0")
    _seed_pod_result(session, _seed_pod(session, event_date=date(2026, 7, 2), set_code="ECL"), grinder, "2-1")
    _seed_pod_result(session, _seed_pod(session, event_date=date(2026, 9, 1), set_code="MSH"), grinder, "3-0")
    _seed_pod_result(session, _seed_pod(session, event_date=date(2026, 9, 2), set_code="SOS"), grinder, "3-0")
    mock = _seed_pod(session, event_date=date(2026, 7, 3), kind="mock")
    session.add(PodDraftParticipant(
        event_id=mock.id, player_id=grinder.id, display_name=grinder.display_name, record=None,
    ))
    session.commit()

    standings = rank_pod_season(session, MSH_SEED)

    assert [(s.rank, s.events, s.trophies) for s in standings] == [(1, 3, 2)]


def test_the_pod_season_ranks_on_points_then_trophies(session):
    points_leader = _seed_player(session, "LSV", "1")
    trophy_leader = _seed_player(session, "Reid", "2")
    for _ in range(3):
        _seed_pod_result(session, _seed_pod(session, event_date=date(2026, 7, 1)), points_leader, "3-0")
    for _ in range(2):
        _seed_pod_result(session, _seed_pod(session, event_date=date(2026, 7, 2)), trophy_leader, "3-0")
    session.commit()

    standings = rank_pod_season(session, MSH_SEED)

    assert [s.display_name for s in standings] == ["LSV", "Reid"]
    assert standings[0].points > standings[1].points


def test_the_wildcard_is_the_best_pod_player_outside_the_seat_cut(session, monkeypatch):
    """The seat cut is the qualification: a pod leader already seeded inside the eight is skipped, and the
    seat goes to the next name down the pod standings."""
    monkeypatch.setattr(championship, "SessionLocal", _session_factory(session))
    monkeypatch.setattr(championship, "seed_for_code", lambda code: MSH_SEED)
    event = _seed_event(session)
    qualified = _seed_player(session, "Finkel", "1")
    outsider = _seed_player(session, "Kibler", "2")
    session.add(PodChampionshipSeed(
        event_id=event.id, player_id=qualified.id, discord_id="1", display_name="Finkel",
        rank=1, score=100.0,
    ))
    session.add(PodChampionshipSeed(
        event_id=event.id, player_id=outsider.id, discord_id="2", display_name="Kibler",
        rank=12, score=40.0,
    ))
    for _ in range(3):
        _seed_pod_result(session, _seed_pod(session, event_date=date(2026, 7, 1)), qualified, "3-0")
    _seed_pod_result(session, _seed_pod(session, event_date=date(2026, 7, 2)), outsider, "3-0")
    session.commit()

    wildcard = championship.freeze_pod_wildcard_sync(event.id, "MSH")

    assert (wildcard.display_name, wildcard.rank, wildcard.wildcard) == ("Kibler", 12, True)
    assert [s.display_name for s in championship.frozen_seeds_sync(event.id) if s.wildcard] == ["Kibler"]


def test_the_wildcard_takes_the_last_seat_and_bumps_the_eighth_seed(session):
    event = _seed_event(session)
    for rank, name in enumerate(HALL_OF_FAME[:10], 1):
        session.add(PodChampionshipSeed(
            event_id=event.id, player_id=None, discord_id=f"d{rank}", display_name=name,
            rank=rank, score=100.0 - rank, wildcard=(rank == 10),
        ))
    session.commit()
    roster = [(f"d{rank}", name) for rank, name in enumerate(HALL_OF_FAME[:10], 1)]

    seated = championship.playing_roster(session, event.id, roster)

    assert [name for _, name in seated] == list(HALL_OF_FAME[:7]) + [HALL_OF_FAME[9]]
