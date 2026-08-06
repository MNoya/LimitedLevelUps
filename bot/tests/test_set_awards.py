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
        _event(2, "Diamond-2", "Mythic", 4),
    ]

    _days, _floor_index, start_tier = sa._best_mythic_climb(_ctx(events))

    assert start_tier == "Diamond"


def test_single_account_bronze_to_mythic_registers_the_full_climb():
    events = [
        _event(1, "Bronze-4", "Gold-1", 1),
        _event(1, "Gold-1", "Mythic", 4),
    ]

    days, _floor_index, start_tier = sa._best_mythic_climb(_ctx(events))

    assert start_tier == "Bronze"
    assert days == 3


def test_lower_start_tier_always_outranks_a_faster_higher_start():
    slow_gold = sa._climb_score(sa.RANK_TIERS.index("Gold"), 20)
    fast_platinum = sa._climb_score(sa.RANK_TIERS.index("Platinum"), 0)

    assert slow_gold > fast_platinum


def _trophy(fmt, hour, minute=0):
    when = datetime(2026, 6, 27, hour, minute, tzinfo=timezone.utc)
    return DraftEvent(format=fmt, is_trophy=True, started_at=when, finished_at=when)


def _drafter(name, events):
    return sa.PlayerCtx(player=Player(discord_id=str(abs(hash(name)) % 10**17), display_name=name), events=events)


def test_a_quick_spree_loses_to_a_smaller_premier_run():
    grinder, sniper = HALL_OF_FAME[0], HALL_OF_FAME[1]
    ctxs = [
        _drafter(grinder, [_trophy("PickTwoDraft", 1, m) for m in range(8)]),
        _drafter(sniper, [_trophy("PremierDraft", 1, m) for m in range(7)]),
    ]

    ranked = sa.seize_the_day(ctxs)

    assert [c.display_name for c in ranked] == [sniper, grinder]


def test_two_quick_trophies_still_qualify_despite_weighing_under_two():
    ctxs = [_drafter(HALL_OF_FAME[2], [_trophy("QuickDraft", 1), _trophy("QuickDraft", 2)])]

    ranked = sa.seize_the_day(ctxs)

    assert len(ranked) == 1


@pytest.mark.parametrize("holders,winner,expected_out,expected_in", [
    ({}, "111", [], "111"),
    ({"111": object()}, "111", [], None),
    ({"222": object(), "333": object()}, "111", ["222", "333"], "111"),
    ({"222": object()}, None, [], None),
])
def test_award_role_swap_plan(holders, winner, expected_out, expected_in):
    outgoing, incoming = ping_roles.plan_award_role_swap(holders, winner)

    assert outgoing == expected_out
    assert incoming == expected_in
