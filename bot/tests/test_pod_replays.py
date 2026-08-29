"""Tests for the time-window + match-anchored replay attribution. No live API/DB hits."""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

from bot.models import PodDraftEvent, PodDraftMatch, PodDraftParticipant, Player
from bot.services import pod_replays
from bot.services.pod_replays import attribute_games_to_rounds
from bot.services.pod_drafts import normalize_player_name


_POD = "DirectGameTournamentLimited"
_BASE = datetime(2026, 5, 14, 0, 0, tzinfo=timezone.utc)


def test_capture_event_replays_fetches_each_participant_once(monkeypatch):
    targets = [("p1", "Alice#1", "tokenA"), ("p2", "Bram#2", "tokenB")]
    monkeypatch.setattr(pod_replays, "_event_replay_targets_sync", lambda event_id: targets)
    calls = []

    async def _fake_fetch(client, event_id, player_id, seat_name, token):
        calls.append((player_id, seat_name, token))
        return 3

    monkeypatch.setattr(pod_replays, "fetch_and_persist_replays_for_player", _fake_fetch)

    total = asyncio.run(pod_replays.capture_event_replays(object(), "evt"))

    assert total == 6
    assert calls == targets


def test_capture_recent_pulls_each_recent_pod_for_the_player(monkeypatch):
    targets = [("evt-a", "Alice#1", "tokenA"), ("evt-b", "Alice#1", "tokenA")]
    monkeypatch.setattr(pod_replays, "_recent_pod_replay_targets_sync", lambda pid, lookback: targets)
    calls = []

    async def _fake_fetch(client, event_id, player_id, seat_name, token):
        calls.append((event_id, player_id, seat_name, token))
        return 2

    monkeypatch.setattr(pod_replays, "fetch_and_persist_replays_for_player", _fake_fetch)

    total = asyncio.run(pod_replays.capture_recent_pod_replays_for_player(object(), "p1"))

    assert total == 4
    assert calls == [("evt-a", "p1", "Alice#1", "tokenA"), ("evt-b", "p1", "Alice#1", "tokenA")]


def test_attributes_each_match_when_data_is_clean() -> None:
    matches = [
        _match(1, "Noya", "Niamh", "Niamh", "2-1", reported_at=_BASE + timedelta(minutes=35)),
        _match(2, "Noya", "Bacchus", "Noya", "2-1", reported_at=_BASE + timedelta(minutes=75)),
        _match(3, "Noya", "Wave", "Wave", "2-1", reported_at=_BASE + timedelta(minutes=110)),
    ]
    games = [
        _game(_BASE + timedelta(minutes=10), won=True, turns=9, gid="r1g1"),
        _game(_BASE + timedelta(minutes=20), won=False, turns=10, gid="r1g2"),
        _game(_BASE + timedelta(minutes=30), won=False, turns=12, gid="r1g3"),
        _game(_BASE + timedelta(minutes=45), won=False, turns=9, gid="r2g1"),
        _game(_BASE + timedelta(minutes=55), won=True, turns=8, gid="r2g2"),
        _game(_BASE + timedelta(minutes=70), won=True, turns=13, gid="r2g3"),
        _game(_BASE + timedelta(minutes=85), won=True, turns=13, gid="r3g1"),
        _game(_BASE + timedelta(minutes=90), won=False, turns=4, gid="r3g2"),
        _game(_BASE + timedelta(minutes=100), won=False, turns=7, gid="r3g3"),
    ]

    out = attribute_games_to_rounds(games, matches, _BASE)

    assert out == {
        "r1g1": 1, "r1g2": 1, "r1g3": 1,
        "r2g1": 2, "r2g2": 2, "r2g3": 2,
        "r3g1": 3, "r3g2": 3, "r3g3": 3,
    }


def test_handles_2_0_match_with_two_games() -> None:
    matches = [_match(1, "Noya", "X", "Noya", "2-0", reported_at=_BASE + timedelta(minutes=25))]
    games = [
        _game(_BASE + timedelta(minutes=10), won=True, turns=9, gid="g1"),
        _game(_BASE + timedelta(minutes=20), won=True, turns=8, gid="g2"),
    ]

    out = attribute_games_to_rounds(games, matches, _BASE)

    assert out == {"g1": 1, "g2": 1}


def test_attributes_partial_round_when_a_game_is_missing() -> None:
    """R1 has only 2 of 3 games (17lands dropped one); the window still bounds them to R1."""
    matches = [
        _match(1, "Noya", "Niamh", "Noya", "2-1", reported_at=_BASE + timedelta(minutes=35)),
        _match(2, "Noya", "Bacchus", "Noya", "2-0", reported_at=_BASE + timedelta(minutes=70)),
    ]
    games = [
        _game(_BASE + timedelta(minutes=10), won=True, turns=9, gid="r1g1"),
        _game(_BASE + timedelta(minutes=20), won=False, turns=10, gid="r1g2"),
        _game(_BASE + timedelta(minutes=50), won=True, turns=11, gid="r2g1"),
        _game(_BASE + timedelta(minutes=60), won=True, turns=8, gid="r2g2"),
    ]

    out = attribute_games_to_rounds(games, matches, _BASE)

    assert out == {"r1g1": 1, "r1g2": 1, "r2g1": 2, "r2g2": 2}


def test_caps_each_match_at_three_games_dropping_the_overflow() -> None:
    """A window with more than MAX_GAMES_PER_MATCH real games keeps the earliest three and drops the
    rest — a restart that slipped the turn filter, or players who kept queuing after the match."""
    matches = [_match(1, "Noya", "X", "Noya", "2-1", reported_at=_BASE + timedelta(minutes=60))]
    games = [
        _game(_BASE + timedelta(minutes=10), won=True, turns=9, gid="g1"),
        _game(_BASE + timedelta(minutes=20), won=False, turns=10, gid="g2"),
        _game(_BASE + timedelta(minutes=30), won=True, turns=8, gid="g3"),
        _game(_BASE + timedelta(minutes=40), won=True, turns=7, gid="g4"),
        _game(_BASE + timedelta(minutes=50), won=True, turns=6, gid="g5"),
    ]

    out = attribute_games_to_rounds(games, matches, _BASE)

    assert out == {"g1": 1, "g2": 1, "g3": 1}


def test_late_report_overflow_beyond_three_is_dropped_not_filed_under_prior_round() -> None:
    """R1 reported after R2's first game, so its window covers 4 games; the cap keeps R1's three and
    drops the straggler rather than misfiling it under R1."""
    matches = [
        _match(1, "Noya", "Niamh", "Noya", "2-1", reported_at=_BASE + timedelta(minutes=50)),
        _match(2, "Noya", "Bacchus", "Noya", "2-0", reported_at=_BASE + timedelta(minutes=80)),
    ]
    games = [
        _game(_BASE + timedelta(minutes=10), won=True, turns=9, gid="r1g1"),
        _game(_BASE + timedelta(minutes=20), won=False, turns=10, gid="r1g2"),
        _game(_BASE + timedelta(minutes=30), won=True, turns=12, gid="r1g3"),
        _game(_BASE + timedelta(minutes=45), won=True, turns=8, gid="r2g1"),
        _game(_BASE + timedelta(minutes=70), won=True, turns=11, gid="r2g2"),
    ]

    out = attribute_games_to_rounds(games, matches, _BASE)

    assert out == {"r1g1": 1, "r1g2": 1, "r1g3": 1, "r2g2": 2}


def test_excludes_games_already_claimed_by_an_earlier_pod() -> None:
    """A player who drafts a second pod the same day: games the earlier pod already owns are
    skipped here, so the same game isn't saved under both events."""
    matches = [_match(1, "Noya", "X", "Noya", "2-1", reported_at=_BASE + timedelta(minutes=35))]
    games = [
        _game(_BASE + timedelta(minutes=10), won=True, turns=9, gid="claimed"),
        _game(_BASE + timedelta(minutes=20), won=True, turns=8, gid="fresh1"),
        _game(_BASE + timedelta(minutes=30), won=False, turns=7, gid="fresh2"),
    ]

    out = attribute_games_to_rounds(games, matches, _BASE, frozenset({"claimed"}))

    assert out == {"fresh1": 1, "fresh2": 1}


def test_round_one_ignores_games_before_the_event_started() -> None:
    """Round 1's window starts at event_time, so a game the player played before this pod began
    (an earlier pod, a casual game) can't leak into round 1 through an open lower bound."""
    event_start = _BASE + timedelta(minutes=25)
    matches = [_match(1, "Noya", "X", "Noya", "2-0", reported_at=_BASE + timedelta(minutes=60))]
    games = [
        _game(_BASE + timedelta(minutes=10), won=True, turns=9, gid="before"),
        _game(_BASE + timedelta(minutes=40), won=True, turns=9, gid="r1g1"),
        _game(_BASE + timedelta(minutes=50), won=True, turns=8, gid="r1g2"),
    ]

    out = attribute_games_to_rounds(games, matches, event_start)

    assert out == {"r1g1": 1, "r1g2": 1}


def test_attributes_regardless_of_reported_score() -> None:
    """Two observed wins inside a window reported as a 1-2 loss still attribute — players misreport
    scores, the window is what counts."""
    matches = [_match(1, "Noya", "X", "X", "2-1", reported_at=_BASE + timedelta(minutes=35))]
    games = [
        _game(_BASE + timedelta(minutes=10), won=True, turns=9, gid="g1"),
        _game(_BASE + timedelta(minutes=20), won=True, turns=10, gid="g2"),
    ]

    out = attribute_games_to_rounds(games, matches, _BASE)

    assert out == {"g1": 1, "g2": 1}


def test_skipped_match_forms_no_window() -> None:
    """A 'No Match Played' result (0-0) is invisible to attribution: games around it flow into the
    next real match's window."""
    matches = [
        _match(1, "Noya", "Niamh", "(skipped)", "0-0", reported_at=_BASE + timedelta(minutes=15)),
        _match(2, "Noya", "Bacchus", "Noya", "2-0", reported_at=_BASE + timedelta(minutes=40)),
    ]
    games = [
        _game(_BASE + timedelta(minutes=10), won=True, turns=9, gid="g1"),
        _game(_BASE + timedelta(minutes=30), won=True, turns=8, gid="g2"),
    ]

    out = attribute_games_to_rounds(games, matches, _BASE)

    assert out == {"g1": 2, "g2": 2}


def test_filters_out_misload_restarts() -> None:
    matches = [_match(1, "Noya", "X", "Noya", "2-0", reported_at=_BASE + timedelta(minutes=25))]
    games = [
        _game(_BASE + timedelta(minutes=5), won=False, turns=2, gid="misload"),  # restart, dropped
        _game(_BASE + timedelta(minutes=10), won=True, turns=9, gid="real1"),
        _game(_BASE + timedelta(minutes=20), won=True, turns=8, gid="real2"),
    ]

    out = attribute_games_to_rounds(games, matches, _BASE)

    assert "misload" not in out
    assert out == {"real1": 1, "real2": 1}


def test_skips_non_pod_event_names() -> None:
    matches = [_match(1, "Noya", "X", "Noya", "2-0", reported_at=_BASE + timedelta(minutes=25))]
    games = [
        _game(_BASE + timedelta(minutes=5), won=True, turns=9, gid="premier", event_name="PremierDraft"),
        _game(_BASE + timedelta(minutes=10), won=True, turns=9, gid="real1"),
        _game(_BASE + timedelta(minutes=20), won=True, turns=8, gid="real2"),
    ]

    out = attribute_games_to_rounds(games, matches, _BASE)

    assert out == {"real1": 1, "real2": 1}


def test_player_perspective_when_seat_is_loser() -> None:
    matches = [_match(1, "Noya", "X", "X", "2-1", reported_at=_BASE + timedelta(minutes=35))]
    games = [
        _game(_BASE + timedelta(minutes=10), won=True, turns=9, gid="g1"),
        _game(_BASE + timedelta(minutes=20), won=False, turns=10, gid="g2"),
        _game(_BASE + timedelta(minutes=30), won=False, turns=12, gid="g3"),
    ]

    out = attribute_games_to_rounds(games, matches, _BASE)

    assert out == {"g1": 1, "g2": 1, "g3": 1}


def test_real_pod3_noya_data_attributes_r2_partially() -> None:
    """Empirical Pod #3 data for Noya: 8 games captured by 17lands, but R2's third game is
    missing. R1 (W L L = 1-2 loss to Niamh) and R3 (W L L = 1-2 loss to Wave) attribute cleanly;
    R2's two observed games (L W within a 2-1 win) attribute partially."""
    def t(hhmm: str) -> datetime:
        h, m = hhmm.split(":")
        return datetime(2026, 5, 14, int(h), int(m), tzinfo=timezone.utc)

    matches = [
        _match(1, "Noya", "Niamh", "Niamh", "2-1", reported_at=t("01:05")),
        _match(2, "Noya", "Bacchus", "Noya", "2-1", reported_at=t("01:30")),
        _match(3, "Noya", "Wave", "Wave", "2-1", reported_at=t("02:05")),
    ]
    games = [
        _game(t("00:41"), won=True, turns=9, gid="g0"),
        _game(t("00:50"), won=False, turns=10, gid="g1"),
        _game(t("01:03"), won=False, turns=12, gid="g2"),
        _game(t("01:19"), won=False, turns=9, gid="g3"),
        _game(t("01:23"), won=True, turns=8, gid="g4"),
        # R2 G3 missing
        _game(t("01:52"), won=True, turns=13, gid="g5"),
        _game(t("01:54"), won=False, turns=4, gid="g6"),
        _game(t("02:01"), won=False, turns=7, gid="g7"),
    ]

    out = attribute_games_to_rounds(games, matches, t("00:00"))

    assert out == {"g0": 1, "g1": 1, "g2": 1, "g3": 2, "g4": 2, "g5": 3, "g6": 3, "g7": 3}


def test_recent_targets_includes_recent_seat_and_excludes_stale_pod(session):
    player = _seed_player(session, token="tok-1", arena_name="Alice#1")
    recent = _seed_event(session, event_time=_now() - timedelta(hours=3))
    stale = _seed_event(session, event_time=_now() - timedelta(days=5))
    _seed_participant(session, recent.id, player_id=player.id, draftmancer_name="Alice#1")
    _seed_participant(session, stale.id, player_id=player.id, draftmancer_name="Alice#1")
    session.flush()

    targets = pod_replays._recent_pod_replay_targets(session, player.id, pod_replays.POD_REPLAY_LOOKBACK)

    assert targets == [(recent.id, "Alice#1", "tok-1")]


def test_recent_targets_empty_without_token(session):
    player = _seed_player(session, token=None, arena_name="Alice#1")
    event = _seed_event(session, event_time=_now() - timedelta(hours=1))
    _seed_participant(session, event.id, player_id=player.id, draftmancer_name="Alice#1")
    session.flush()

    targets = pod_replays._recent_pod_replay_targets(session, player.id, pod_replays.POD_REPLAY_LOOKBACK)

    assert targets == []


def test_recent_targets_adopts_unlinked_seat_matching_the_player(session):
    player = _seed_player(session, token="tok-1", arena_name="Alice#1")
    event = _seed_event(session, event_time=_now() - timedelta(hours=2))
    seat = _seed_participant(session, event.id, player_id=None, draftmancer_name="Alice#1")
    session.flush()

    targets = pod_replays._recent_pod_replay_targets(session, player.id, pod_replays.POD_REPLAY_LOOKBACK)

    assert targets == [(event.id, "Alice#1", "tok-1")]
    assert seat.player_id == player.id


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _seed_player(session, *, token, arena_name):
    player = Player(
        slug=f"alice-{arena_name}",
        discord_id=f"d-{arena_name}",
        discord_username="alice",
        display_name="Alice",
        arena_name=arena_name,
        arena_aliases=[normalize_player_name(arena_name)],
        seventeenlands_token=token,
        active=True,
    )
    session.add(player)
    session.flush()
    return player


def _seed_event(session, *, event_time):
    event = PodDraftEvent(
        event_date=event_time.date(),
        event_time=event_time,
        set_code="MSH",
        name=f"Pod {event_time.isoformat()}",
        draftmancer_session="sess",
        discord_thread_id=f"thread-{event_time.timestamp()}",
        socket_status="closed",
    )
    session.add(event)
    session.flush()
    return event


def _seed_participant(session, event_id, *, player_id, draftmancer_name):
    participant = PodDraftParticipant(
        event_id=event_id,
        player_id=player_id,
        display_name=draftmancer_name,
        draftmancer_name=draftmancer_name,
    )
    session.add(participant)
    session.flush()
    return participant


def _match(round_num: int, player_a: str, player_b: str, winner: str, score: str,
           reported_at: datetime) -> PodDraftMatch:
    return PodDraftMatch(
        id=f"m{round_num}",
        event_id="evt-1",
        round=round_num,
        pairing_index=0,
        player_a_name=player_a,
        player_b_name=player_b,
        winner_name=winner,
        score=score,
        reported_at=reported_at,
    )


def _game(ts: datetime, won: bool, turns: int, gid: str, event_name: str = _POD) -> dict:
    return {
        "event_name": event_name,
        "game_time": ts.strftime("%Y-%m-%d %H:%M"),
        "link": f"/user/game_replay/20260514/{gid}/0",
        "won": won,
        "turns": turns,
        "on_play": True,
        "account_name": "Noya",
    }
