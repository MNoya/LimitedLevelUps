import json
from datetime import datetime, timezone

from bot.scripts.fetch_p0p1_cards import LAYOUT_VERSION, resolve_layout
from bot.services.p0p1_contest import SCORING_WINDOW, all_contests


def _write(tmp_path, monkeypatch, entries):
    contests_json = tmp_path / "p0p1_contests.json"
    contests_json.write_text(json.dumps(entries))
    monkeypatch.setattr("bot.services.p0p1_contest.CONTESTS_JSON", contests_json)


def test_scoring_date_defaults_to_release_plus_the_scoring_window(tmp_path, monkeypatch):
    _write(tmp_path, monkeypatch, {
        "HOB": {
            "name": "The Hobbit",
            "release": "2026-08-11T16:00:00Z",
            "previewsOpen": "2026-07-31T16:00:00Z",
            "votingDeadline": "2026-08-05T16:00:00Z",
        },
    })

    contest = all_contests()[0]

    release = datetime(2026, 8, 11, 16, tzinfo=timezone.utc)
    assert contest.scoring_date == release + SCORING_WINDOW


def test_an_explicit_scoring_date_is_honored_over_the_release_default(tmp_path, monkeypatch):
    _write(tmp_path, monkeypatch, {
        "HOB": {
            "name": "The Hobbit",
            "release": "2026-08-11T16:00:00Z",
            "previewsOpen": "2026-07-31T16:00:00Z",
            "votingDeadline": "2026-08-05T16:00:00Z",
            "scoringDate": "2026-09-02T16:00:00Z",
        },
    })

    contest = all_contests()[0]

    assert contest.scoring_date == datetime(2026, 9, 2, 16, tzinfo=timezone.utc)


def test_resolve_layout():
    assert resolve_layout(None) == LAYOUT_VERSION
    assert resolve_layout({"layout": 2}) == 2
    assert resolve_layout({"name": "The Hobbit"}) == 1
