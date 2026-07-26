"""Which matches `/report-results` serves the caller, and where each pod mode commits them."""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

import pytest

from bot.commands.messages import MSG_POD_NO_MATCH_TO_REPORT, MSG_POD_RESULT_ALREADY_RECORDED
from bot.commands.test_group import HALL_OF_FAME
from bot.models import Player, PodDraftEvent, PodDraftMatch, PodDraftParticipant
from bot.services import pod_tournament
from bot.services.pod_drafts import OwnMatch, ParticipantDmInfo, latest_reported_match, own_open_matches
from bot.services.pod_tournament import POD_RESULT_LOCKED_MSG, build_own_match_report


NOW = datetime.now(timezone.utc)
FINKEL, LSV, HUMP, PAOLO = HALL_OF_FAME[:4]


def test_serves_the_unreported_match_and_skips_a_settled_earlier_round(session) -> None:
    event = _event(session, NOW - timedelta(hours=1))
    _participant(session, event, FINKEL, discord_id="d-finkel")
    _match(session, event, 1, FINKEL, LSV, winner=FINKEL)
    pending = _match(session, event, 2, FINKEL, HUMP)

    assert own_open_matches(session, "d-finkel") == [OwnMatch(event.id, 2, pending.id)]


def test_serves_every_round_a_team_draft_opens_at_once(session) -> None:
    """A team draft inserts all three rounds up front, so the caller can report whichever they played."""
    event = _event(session, NOW - timedelta(hours=1))
    _participant(session, event, FINKEL, discord_id="d-finkel")
    round_one = _match(session, event, 1, FINKEL, LSV)
    round_two = _match(session, event, 2, FINKEL, HUMP)
    round_three = _match(session, event, 3, FINKEL, PAOLO)

    assert own_open_matches(session, "d-finkel") == [
        OwnMatch(event.id, 1, round_one.id),
        OwnMatch(event.id, 2, round_two.id),
        OwnMatch(event.id, 3, round_three.id),
    ]


def test_matches_the_participant_despite_an_arena_suffix(session) -> None:
    event = _event(session, NOW - timedelta(hours=1))
    _participant(session, event, f"{FINKEL}#48087", discord_id="d-finkel")
    pending = _match(session, event, 1, FINKEL, LSV)

    assert [m.match_id for m in own_open_matches(session, "d-finkel")] == [pending.id]


def test_newest_pod_wins_and_never_mixes_pods(session) -> None:
    stale = _event(session, NOW - timedelta(hours=20))
    _participant(session, stale, FINKEL, discord_id="d-finkel")
    _match(session, stale, 3, FINKEL, PAOLO)
    fresh = _event(session, NOW - timedelta(minutes=30), thread_id="thread-2")
    _participant(session, fresh, FINKEL, discord_id="d-finkel")
    tonight = _match(session, fresh, 1, FINKEL, LSV)

    assert own_open_matches(session, "d-finkel") == [OwnMatch(fresh.id, 1, tonight.id)]


@pytest.mark.parametrize("event_age, opponents", [
    (timedelta(hours=1), (LSV, HUMP)),
    (timedelta(days=3), (FINKEL, LSV)),
], ids=["caller_not_in_the_match", "pod_outside_the_window"])
def test_serves_nothing_outside_the_callers_live_pods(session, event_age, opponents) -> None:
    event = _event(session, NOW - event_age)
    _participant(session, event, FINKEL, discord_id="d-finkel")
    _match(session, event, 1, *opponents)

    assert own_open_matches(session, "d-finkel") == []


def test_serves_nothing_for_a_player_in_no_pod(session) -> None:
    event = _event(session, NOW - timedelta(hours=1))
    _participant(session, event, FINKEL, discord_id="d-finkel")
    _match(session, event, 1, FINKEL, LSV)
    _player(session, "d-lsv", LSV)

    assert own_open_matches(session, "d-lsv") == []


def test_latest_reported_match_is_the_last_round_settled(session) -> None:
    event = _event(session, NOW - timedelta(hours=1))
    _participant(session, event, FINKEL, discord_id="d-finkel")
    _match(session, event, 1, FINKEL, LSV, winner=FINKEL)
    latest = _match(session, event, 2, HUMP, FINKEL, winner=HUMP)

    assert latest_reported_match(session, "d-finkel") == OwnMatch(event.id, 2, latest.id)


@pytest.mark.parametrize("mode, expected_submit", [
    ("swiss", pod_tournament._handle_result_submission),
    ("bracket", pod_tournament._handle_result_submission),
    ("team", "team-submit"),
], ids=["swiss", "bracket", "team"])
def test_card_commits_through_the_path_its_pod_mode_owns(monkeypatch, mode, expected_submit) -> None:
    _stub_builder(monkeypatch, [OwnMatch("evt", 1, "m1")], mode=mode)

    report = asyncio.run(build_own_match_report("d-finkel", team_submit="team-submit"))

    assert [child.on_submit for child in report.view.children] == [expected_submit]


def test_card_carries_one_dropdown_per_open_match(monkeypatch) -> None:
    open_matches = [OwnMatch("evt", 1, "m1"), OwnMatch("evt", 2, "m2"), OwnMatch("evt", 3, "m3")]
    _stub_builder(monkeypatch, open_matches, mode="team")

    report = asyncio.run(build_own_match_report("d-finkel", team_submit="team-submit"))

    assert report.notice is None
    assert [type(child).__name__ for child in report.view.children] == ["MatchResultSelect"] * 3


@pytest.mark.parametrize("open_matches, reported, finalized, expected_notice", [
    ([], None, False, MSG_POD_NO_MATCH_TO_REPORT),
    ([], OwnMatch("evt", 2, "m2"), False, MSG_POD_RESULT_ALREADY_RECORDED.format(round_num=2)),
    ([OwnMatch("evt", 1, "m1")], None, True, POD_RESULT_LOCKED_MSG),
], ids=["no_pod_match", "result_already_recorded", "pod_finalized"])
def test_refuses_a_card_and_explains_why(
    monkeypatch, open_matches, reported, finalized, expected_notice,
) -> None:
    _stub_builder(monkeypatch, open_matches, reported=reported, finalized=finalized)

    report = asyncio.run(build_own_match_report("d-finkel", team_submit="team-submit"))

    assert report.notice == expected_notice
    assert (report.embed, report.view) == (None, None)


def test_serves_deck_colors_once_the_matches_are_in(monkeypatch) -> None:
    _stub_builder(monkeypatch, [], reported=OwnMatch("evt", 3, "m3"), owed_colors=("evt", "thread-1"))

    report = asyncio.run(build_own_match_report("d-finkel", team_submit="team-submit"))

    assert report.notice is None
    assert [type(child).__name__ for child in report.view.children] == ["DeckColorSelect"]


def test_skips_deck_colors_when_they_are_already_saved(monkeypatch) -> None:
    _stub_builder(monkeypatch, [], reported=OwnMatch("evt", 3, "m3"), owed_colors=None)

    report = asyncio.run(build_own_match_report("d-finkel", team_submit="team-submit"))

    assert report.notice == MSG_POD_RESULT_ALREADY_RECORDED.format(round_num=3)


def _stub_builder(
    monkeypatch, open_matches, *, mode="swiss", reported=None, finalized=False, owed_colors=None,
) -> None:
    """Cut build_own_match_report off from the database, leaving only its branching under test."""
    dm_info = {
        FINKEL.lower(): ParticipantDmInfo(
            participant_id="part-1", discord_id="d-finkel", display_name=FINKEL, arena_name=None,
        ),
    }

    def _states(event_id, round_num, *, bracket):
        return [{
            "match_id": f"m{round_num}", "a_name": FINKEL, "b_name": LSV,
            "a_display": FINKEL, "b_display": LSV, "a_record": "1-0", "b_record": "1-0",
            "winner_name": None, "score": None,
        }]

    monkeypatch.setattr(pod_tournament, "_own_open_matches_sync", lambda discord_id: open_matches)
    monkeypatch.setattr(pod_tournament, "_latest_reported_sync", lambda discord_id: reported)
    monkeypatch.setattr(pod_tournament, "_owed_deck_colors_sync", lambda discord_id: owed_colors)
    monkeypatch.setattr(pod_tournament, "event_result_locked", lambda match_id: finalized)
    monkeypatch.setattr(pod_tournament, "load_event_pairing_mode_sync", lambda event_id: mode)
    monkeypatch.setattr(pod_tournament, "render_round_states", _states)
    monkeypatch.setattr(pod_tournament, "load_dm_info_sync", lambda event_id: dm_info)
    monkeypatch.setattr(pod_tournament, "load_event_name_sync", lambda event_id: "Test Pod")


def _event(session, event_time, *, thread_id="thread-1") -> PodDraftEvent:
    event = PodDraftEvent(
        event_date=event_time.date(),
        event_time=event_time,
        set_code="MSH",
        name=f"Test Pod {thread_id}",
        draftmancer_session="sess",
        discord_thread_id=thread_id,
        socket_status="in_progress",
    )
    session.add(event)
    session.flush()
    return event


def _player(session, discord_id: str, display_name: str) -> Player:
    player = Player(slug=discord_id, discord_id=discord_id, display_name=display_name)
    session.add(player)
    session.flush()
    return player


def _participant(session, event, draftmancer_name: str, *, discord_id: str) -> PodDraftParticipant:
    player = session.query(Player).filter_by(discord_id=discord_id).one_or_none()
    if player is None:
        player = _player(session, discord_id, draftmancer_name)
    participant = PodDraftParticipant(
        event_id=event.id,
        player_id=player.id,
        display_name=draftmancer_name,
        draftmancer_name=draftmancer_name,
    )
    session.add(participant)
    session.flush()
    return participant


def _match(session, event, round_num: int, a: str, b: str, *, winner=None) -> PodDraftMatch:
    match = PodDraftMatch(
        event_id=event.id,
        round=round_num,
        pairing_index=0,
        player_a_name=a,
        player_b_name=b,
        winner_name=winner,
        score="2-1" if winner else None,
        reported_at=NOW if winner else None,
    )
    session.add(match)
    session.flush()
    return match
