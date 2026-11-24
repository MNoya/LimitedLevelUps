from datetime import datetime, timezone

import pytest

from bot.commands.test_group import HALL_OF_FAME
from bot.models import DraftEvent, Player
from bot.services import ping_roles, set_awards as sa


def _event(account_id, start_rank, end_rank, day):
    return DraftEvent(
        account_id=account_id, start_rank=start_rank, end_rank=end_rank,
        started_at=datetime(2026, 6, day, 12, tzinfo=timezone.utc),
        finished_at=datetime(2026, 6, day, 14, tzinfo=timezone.utc),
    )


def _ctx(events):
    return sa.PlayerCtx(player=None, events=events)


def test_climb_does_not_stitch_a_low_rank_on_one_account_to_mythic_on_another():
    events = [
        _event(1, "Bronze-4", "Gold-1", 1),
        _event(2, "Platinum-2", "Diamond-1", 3),
        _event(2, "Diamond-1", "Mythic", 4),
    ]

    _days, _floor_index, start_tier = sa._best_mythic_climb(_ctx(events))

    assert start_tier == "Platinum"


def test_single_account_bronze_to_mythic_registers_the_full_climb():
    events = [
        _event(1, "Bronze-4", "Gold-1", 1),
        _event(1, "Gold-1", "Diamond-1", 3),
        _event(1, "Diamond-1", "Mythic", 4),
    ]

    days, _floor_index, start_tier = sa._best_mythic_climb(_ctx(events))

    assert start_tier == "Bronze"
    assert days == 3


@pytest.mark.parametrize("gold_days,platinum_days,gold_wins", [(8, 4, True), (9, 4, False)])
def test_a_gold_start_counts_five_days_shorter_than_platinum(gold_days, platinum_days, gold_wins):
    gold = sa._climb_score(sa.RANK_TIERS.index("Gold"), gold_days)
    platinum = sa._climb_score(sa.RANK_TIERS.index("Platinum"), platinum_days)

    assert (gold > platinum) is gold_wins


def test_a_mythic_rank_that_appears_without_leaving_diamond_is_not_a_climb():
    events = [_event(1, "Platinum-4", "Platinum-4", 1), _event(1, "Mythic-1", "Mythic-1", 1)]

    climb = sa._best_mythic_climb(_ctx(events))

    assert climb is None


def test_a_climb_starting_in_diamond_is_not_counted():
    events = [_event(1, "Diamond-4", "Diamond-1", 1), _event(1, "Diamond-1", "Mythic-1", 2)]

    climb = sa._best_mythic_climb(_ctx(events))

    assert climb is None


def test_bronze_and_silver_starts_rank_on_days_alone():
    slow_bronze = sa._climb_score(sa.RANK_TIERS.index("Bronze"), 27)
    fast_silver = sa._climb_score(sa.RANK_TIERS.index("Silver"), 13)

    assert fast_silver > slow_bronze


def _trophy(fmt, hour, minute=0):
    when = datetime(2026, 6, 27, hour, minute, tzinfo=timezone.utc)
    return DraftEvent(format=fmt, is_trophy=True, started_at=when, finished_at=when)


def _drafter(name, events, stats=None):
    return sa.PlayerCtx(
        player=Player(discord_id=str(abs(hash(name)) % 10**17), display_name=name),
        events=events, stats_rows=stats or [],
    )


def _premier_stats(trophies, events):
    return {"format": "PremierDraft", "wins": trophies * 7, "losses": events, "trophies": trophies, "events": events}


def test_a_quick_spree_loses_to_a_smaller_premier_run():
    grinder, sniper = HALL_OF_FAME[0], HALL_OF_FAME[1]
    ctxs = [
        _drafter(grinder, [_trophy("PickTwoDraft", 1, m) for m in range(8)]),
        _drafter(sniper, [_trophy("PremierDraft", 1, m) for m in range(7)]),
    ]

    ranked = sa.seize_the_day(ctxs)

    assert [c.display_name for c in ranked] == [sniper, grinder]


def test_an_equal_run_goes_to_whoever_reached_it_first():
    early, late = HALL_OF_FAME[3], HALL_OF_FAME[4]
    ctxs = [
        _drafter(late, [_trophy("TradDraft", 10), _trophy("TradDraft", 11)], [_premier_stats(8, 10)]),
        _drafter(early, [_trophy("TradDraft", 1), _trophy("TradDraft", 2)], [_premier_stats(1, 10)]),
    ]

    ranked = sa.seize_the_day(ctxs)

    assert [c.display_name for c in ranked] == [early, late]


def test_an_equal_run_names_only_the_first_to_reach_it_as_runner_up():
    winner, first, second, third = HALL_OF_FAME[0], HALL_OF_FAME[1], HALL_OF_FAME[2], HALL_OF_FAME[3]
    ctxs = [
        _drafter(winner, [_trophy("TradDraft", hour) for hour in (1, 2, 3)]),
        _drafter(third, [_trophy("TradDraft", 9), _trophy("TradDraft", 12)]),
        _drafter(first, [_trophy("TradDraft", 9), _trophy("TradDraft", 10)]),
        _drafter(second, [_trophy("TradDraft", 5), _trophy("TradDraft", 11)]),
    ]

    _winners, runners = sa.assign({"seize_the_day": sa.seize_the_day(ctxs)})

    assert [c.display_name for c in runners["seize_the_day"]] == [first]


def test_a_same_instant_equal_run_falls_through_to_the_stronger_leaderboard_score():
    contender, also_ran = HALL_OF_FAME[5], HALL_OF_FAME[6]
    ctxs = [
        _drafter(also_ran, [_trophy("TradDraft", 1), _trophy("TradDraft", 2)], [_premier_stats(1, 10)]),
        _drafter(contender, [_trophy("TradDraft", 1), _trophy("TradDraft", 2)], [_premier_stats(8, 10)]),
    ]

    ranked = sa.seize_the_day(ctxs)

    assert [c.display_name for c in ranked] == [contender, also_ran]


def test_two_quick_trophies_still_qualify_despite_weighing_under_two():
    ctxs = [_drafter(HALL_OF_FAME[2], [_trophy("QuickDraft", 1), _trophy("QuickDraft", 2)])]

    ranked = sa.seize_the_day(ctxs)

    assert len(ranked) == 1


@pytest.mark.parametrize("holders,awarded,expected_out,expected_in", [
    ({}, ["111"], [], ["111"]),
    ({"111": object()}, ["111"], [], []),
    ({"222": object(), "333": object()}, ["111"], ["222", "333"], ["111"]),
    ({"222": object()}, [], [], []),
    ({}, ["111", "222"], [], ["111", "222"]),
    ({"111": object()}, ["111", "222"], [], ["222"]),
    ({"111": object(), "999": object()}, ["111", "222"], ["999"], ["222"]),
])
def test_award_role_swap_plan(holders, awarded, expected_out, expected_in):
    outgoing, incoming = ping_roles.plan_award_role_swap(holders, awarded)

    assert outgoing == expected_out
    assert incoming == expected_in
