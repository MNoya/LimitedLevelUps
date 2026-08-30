from datetime import datetime, time, timedelta
from types import SimpleNamespace

from bot.services import pod_format_vote as vote
from bot.services.championship_dates import (
    plan_for,
    vote_opens_at,
    vote_ping_due,
    vote_reminder_due,
    voting_open,
)
from bot.sets import RELEASE_TZ

SEASON = "HOB"


def _user(uid, name):
    return SimpleNamespace(id=uid, name=name, display_name=name.title(), avatar=None)


def test_a_vote_toggles_on_then_off(session):
    voter = _user(1, "finkel")

    on = vote.toggle_vote(session, voter, SEASON, "PEASANT")
    off = vote.toggle_vote(session, voter, SEASON, "PEASANT")

    assert on is True
    assert off is False
    assert vote.tally(session, SEASON).get("PEASANT", 0) == 0


def test_the_tally_counts_one_per_voter_per_format(session):
    vote.toggle_vote(session, _user(1, "lsv"), SEASON, "NEO")
    vote.toggle_vote(session, _user(2, "reid"), SEASON, "NEO")
    vote.toggle_vote(session, _user(2, "reid"), SEASON, "MH3")

    counts = vote.tally(session, SEASON)

    assert counts["NEO"] == 2
    assert counts["MH3"] == 1


def test_a_player_reads_back_only_their_own_votes(session):
    vote.toggle_vote(session, _user(3, "finkel"), SEASON, "PEASANT")
    vote.toggle_vote(session, _user(3, "finkel"), SEASON, "NEO")
    vote.toggle_vote(session, _user(4, "lsv"), SEASON, "MH3")

    assert vote.player_votes(session, "3", SEASON) == {"PEASANT", "NEO"}


def test_the_ballot_is_ordered_newest_release_first_regardless_of_votes():
    order = vote.ballot_order({"NEO": 5, "FIN": 1})

    assert order.index("FIN") < order.index("NEO")
    assert "DSK" in order
    assert "PEASANT" not in order
    assert "MEMA" not in order


def test_the_ballot_keeps_voted_options_when_it_overflows_the_grid():
    old_voted = {"DOM": 1, "ELD": 1, "KTK": 1}

    order = vote.ballot_order(old_voted)

    assert len(order) == vote.MAX_ROWED_OPTIONS
    assert {"DOM", "ELD", "KTK"} <= set(order)


def test_voting_is_open_from_the_ballot_instant():
    plan = plan_for(datetime(2026, 8, 29, 15, tzinfo=RELEASE_TZ))
    opens_at = vote_opens_at(plan)

    assert voting_open(opens_at) is True
    assert voting_open(opens_at - timedelta(minutes=1)) is False


def test_the_ping_and_reminder_fire_on_their_own_dates():
    plan = plan_for(datetime(2026, 8, 29, 15, tzinfo=RELEASE_TZ))
    open_date = vote_opens_at(plan).date()

    def at(day):
        return datetime.combine(day, time(11), tzinfo=RELEASE_TZ)

    assert vote_ping_due(at(open_date)) is not None
    assert vote_ping_due(at(open_date + timedelta(days=1))) is None
    assert vote_reminder_due(at(open_date + timedelta(days=2))) is not None
    assert vote_reminder_due(at(open_date)) is None
