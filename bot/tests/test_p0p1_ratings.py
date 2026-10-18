import json
from datetime import datetime, timedelta, timezone

import pytest

from bot.models import P0P1Ratings
from bot.services import p0p1_ratings
from bot.services.p0p1_contest import Contest

RELEASE = datetime(2026, 9, 29, 16, tzinfo=timezone.utc)
SCORING = datetime(2026, 10, 21, 16, tzinfo=timezone.utc)
CONTEST = Contest(
    code="TST", name="Test Set", release=RELEASE, previews_open=RELEASE - timedelta(days=10),
    voting_deadline=RELEASE - timedelta(days=5), scoring_date=SCORING,
)


@pytest.mark.parametrize("now, expected", [
    (RELEASE + timedelta(days=10), None),
    (RELEASE + timedelta(days=11), "midway"),
    (SCORING - timedelta(minutes=1), "midway"),
    (SCORING, "final"),
])
def test_due_phase_is_midway_from_the_halfway_point_and_final_from_the_scoring_date(now, expected):
    assert p0p1_ratings.due_phase(CONTEST, now) == expected


def test_a_captured_snapshot_is_never_rewritten(session, tmp_path, monkeypatch):
    _use_pool(tmp_path, monkeypatch, ["Pool Common", "Pool Uncommon"])
    client = _StubClient([
        {"name": "Pool Common", "ever_drawn_win_rate": 0.55, "drawn_game_count": 900},
        {"name": "Pool Uncommon", "ever_drawn_win_rate": 0.6, "drawn_game_count": 700},
        {"name": "Off-pool Rare", "ever_drawn_win_rate": 0.7, "drawn_game_count": 800},
    ])
    p0p1_ratings.capture_due_snapshots(session, client, SCORING)
    client.rows = [{"name": "Pool Common", "ever_drawn_win_rate": 0.4, "drawn_game_count": 9000}]

    captured_again = p0p1_ratings.capture_due_snapshots(session, client, SCORING + timedelta(hours=1))

    assert captured_again == []
    stored = session.get(P0P1Ratings, ("TST", "final"))
    assert [card["card_name"] for card in stored.cards] == ["Pool Common", "Pool Uncommon"]
    assert stored.cards[0]["gihwr"] == 0.55


class _StubClient:
    def __init__(self, rows):
        self.rows = rows

    def fetch_card_ratings(self, expansion):
        return self.rows


def _use_pool(tmp_path, monkeypatch, names):
    pool = json.dumps([{"name": name} for name in names])
    (tmp_path / "cards-tst.ts").write_text(f"export default {pool} satisfies Card[];\n")
    monkeypatch.setattr(p0p1_ratings, "FIXTURES_DIR", tmp_path)
    monkeypatch.setattr(p0p1_ratings.p0p1_contest, "all_contests", lambda: [CONTEST])
