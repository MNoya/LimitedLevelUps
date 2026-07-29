import discord
import pytest

from bot.services.championship_roster_card import (
    COLUMN_CAP,
    FIELD_VALUE_LIMIT,
    MAYBE_MARKER,
    SEAT_COUNT,
    add_championship_roster_fields,
    championship_roster,
)
from bot.services.player_stats import SeededAttendee


def _attendee(name, rank=None):
    score = None if rank is None else float(200 - rank)
    trophies = None if rank is None else 20 - rank
    return SeededAttendee(slug=None, display_name=name, rank=rank, score=score, trophies=trophies)


def _roster(yes_count, maybe_count=0, declined_count=5, name_length=1):
    yes = [_attendee(f"P{i}" * name_length, rank=i) for i in range(1, yes_count + 1)]
    maybe = [_attendee(f"M{i}" * name_length, rank=100 + i) for i in range(1, maybe_count + 1)]
    declined = [_attendee(f"N{i}" * name_length, rank=50 + i) for i in range(1, declined_count + 1)]
    return championship_roster(yes, maybe, declined)


def test_yes_splits_at_the_seat_count():
    roster = _roster(yes_count=SEAT_COUNT + 6)

    assert len(roster.playing) == SEAT_COUNT
    assert len(roster.alternates) == 6
    assert not any(alternate.maybe for alternate in roster.alternates)


def test_maybe_joins_the_alternates_in_rank_order():
    yes = [_attendee(f"P{rank}", rank=rank) for rank in (1, 2, 40)]
    maybe = [_attendee("M20", rank=20)]

    roster = championship_roster(yes, maybe, [], seats=2)

    assert [alternate.attendee.display_name for alternate in roster.alternates] == ["M20", "P40"]
    assert [alternate.maybe for alternate in roster.alternates] == [True, False]


def test_unranked_alternates_trail_the_ranked_ones():
    yes = [_attendee("P1", rank=1), _attendee("Ghost"), _attendee("P30", rank=30)]

    roster = championship_roster(yes, [], [], seats=1)

    assert [alternate.attendee.display_name for alternate in roster.alternates] == ["P30", "Ghost"]


def test_maybe_rows_carry_the_marker():
    roster = _roster(yes_count=SEAT_COUNT, maybe_count=2)
    embed = discord.Embed(description="body")

    add_championship_roster_fields(embed, roster)

    playing, alternates, _ = embed.fields
    assert alternates.value.count(MAYBE_MARKER) == 2
    assert MAYBE_MARKER not in playing.value


@pytest.mark.parametrize("yes_count,maybe_count,declined_count", [(0, 0, 0), (5, 3, 3), (40, 20, 40)])
def test_columns_stay_within_the_cap_and_the_field_limit(yes_count, maybe_count, declined_count):
    roster = _roster(yes_count, maybe_count, declined_count, name_length=12)
    embed = discord.Embed(description="body")

    add_championship_roster_fields(embed, roster)

    assert len(embed.fields) == 3
    for field in embed.fields:
        assert field.inline
        assert 0 < len(field.value) <= FIELD_VALUE_LIMIT
        assert len(field.value.splitlines()) <= COLUMN_CAP


def test_no_column_is_counted():
    roster = _roster(yes_count=5, maybe_count=4, declined_count=15)
    embed = discord.Embed(description="body")

    add_championship_roster_fields(embed, roster)

    assert all("(" not in field.name for field in embed.fields)
