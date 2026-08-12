import json
from datetime import datetime, timezone

from bot.scripts.fetch_p0p1_cards import resolve_hybrid_common_slots
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


def test_resolve_hybrid_common_slots():
    existing_off = {"hybridCommonSlots": False}
    existing_missing_key = {"name": "The Hobbit"}

    # A reschedule with no explicit flag preserves what the existing entry already has.
    assert resolve_hybrid_common_slots(None, existing_off) is False
    # An existing entry that predates the field reads as off, matching buildSlots' falsy default.
    assert resolve_hybrid_common_slots(None, existing_missing_key) is False
    # No existing entry at all: brand-new contest, documented default is on.
    assert resolve_hybrid_common_slots(None, None) is True
    # An explicit flag always wins, regardless of what's on disk.
    assert resolve_hybrid_common_slots(True, existing_off) is True
