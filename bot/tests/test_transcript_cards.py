import importlib.util
from datetime import date, datetime, timezone
from pathlib import Path

import pytest
from sqlalchemy import select, text

from bot.models import Episode, EpisodeTranscript, MagicSet, TranscriptCardMention
from bot.services import transcript_cards
from bot.services.transcript_cards import apply_transcript_edit, sync_card_mentions

MENTIONS_MIGRATION = Path(__file__).parents[2] / "alembic/versions/c4rdm3nt10n1_transcript_card_mentions.py"


def test_sync_replaces_the_previous_mentions(session):
    first_pass = [{"t": 10, "text": "Next is Shock.", "cards": [{"name": "Shock"}]}]
    second_pass = [
        {"t": 10, "text": "Intro."},
        {"t": 40, "text": "Next is Opt.", "subheading": "Opt Is Fine", "cards": [{"name": "Opt"}, {"name": "Opt"}]},
    ]
    session.add(EpisodeTranscript(youtube_id="vid", segments=first_pass))
    sync_card_mentions(session, "vid", first_pass)

    sync_card_mentions(session, "vid", second_pass)
    session.commit()

    assert _mention_rows(session) == [(1, "Opt", 40, True)]


def test_transcript_edit_keeps_mentions_in_sync(session, monkeypatch):
    card_names = ["Essence Burn", "Command the Stage"]
    monkeypatch.setattr(transcript_cards.card_index, "set_card_names", lambda *_args, **_kwargs: card_names)
    segments = [{"t": 10, "text": "Next is Essence Burn.", "cards": [{"name": "Essence Burn"}]}]
    _add_episode(session, "vid", "FRA", day=1, segments=segments)

    apply_transcript_edit(session, "vid", [{"text": "Next is Command the Stage."}])

    assert _mention_rows(session) == [(0, "Command the Stage", 10, False)]


PICK_CASES = [
    pytest.param(
        [("first", 1, [(50, True)]), ("second", 2, [(10, False)])],
        ("first", 50),
        id="a paragraph that opens a subtopic beats a later passing mention",
    ),
    pytest.param(
        [("first", 1, [(30, False), (60, False)]), ("second", 2, [(10, False)])],
        ("first", 30),
        id="the episode that discusses the card most wins",
    ),
    pytest.param(
        [("first", 1, [(5, False)]), ("second", 2, [(40, False)])],
        ("second", 40),
        id="the later episode wins a tie",
    ),
    pytest.param(
        [("only", 1, [(100, True), (20, True)])],
        ("only", 20),
        id="the earliest paragraph within the episode wins",
    ),
]


@pytest.mark.parametrize(("episodes", "expected"), PICK_CASES)
def test_set_review_link_picks_the_card_discussion(session, mentions_view, episodes, expected):
    _add_set(session, "FRA", date(2026, 9, 29))
    for youtube_id, day, mentions in episodes:
        _add_episode(session, youtube_id, "FRA", day, [_segment(t, opens) for t, opens in mentions])

    rows = _linked_mentions(session, "FRA")

    assert rows == [expected]


EXCLUDED_CASES = [
    pytest.param("OLD", date(2026, 1, 1), "Set Review", "Old Set Review", id="sets released before the index start"),
    pytest.param("FRA", date(2026, 9, 29), "Draft", "FRA Draft Guide", id="episodes outside the Set Review category"),
    pytest.param("FRA", date(2026, 9, 29), "Set Review", "FRA First Impressions!", id="First Impressions episodes"),
]


@pytest.mark.parametrize(("set_code", "start_date", "category", "title"), EXCLUDED_CASES)
def test_set_review_link_excludes(session, mentions_view, set_code, start_date, category, title):
    _add_set(session, set_code, start_date)
    _add_episode(session, "vid", set_code, 1, [_segment(10, True)], category=category, title=title)

    rows = _linked_mentions(session, set_code)

    assert rows == []


@pytest.fixture
def mentions_view(session):
    spec = importlib.util.spec_from_file_location("transcript_card_mentions_migration", MENTIONS_MIGRATION)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    session.execute(text(migration.SET_REVIEW_CARD_MENTIONS_VIEW))
    session.commit()


def _segment(t: int, opens_subtopic: bool) -> dict:
    segment = {"t": t, "text": "Next is Shock.", "cards": [{"name": "Shock"}]}
    if opens_subtopic:
        segment["subheading"] = "Shock"
    return segment


def _add_set(session, code: str, start_date: date) -> None:
    session.add(MagicSet(code=code, name=code, start_date=start_date))
    session.commit()


def _add_episode(session, youtube_id, set_code, day, segments, category="Set Review", title=None):
    session.add(Episode(
        guid=f"yt:{youtube_id}", kind="video", title=title or youtube_id, link=f"https://youtu.be/{youtube_id}",
        published_at=datetime(2026, 9, day, tzinfo=timezone.utc), youtube_id=youtube_id, category=category,
        set_code=set_code,
    ))
    session.add(EpisodeTranscript(youtube_id=youtube_id, segments=segments))
    sync_card_mentions(session, youtube_id, segments)
    session.commit()


def _mention_rows(session) -> list[tuple]:
    mentions = session.execute(select(TranscriptCardMention)).scalars().all()
    return [(m.segment_index, m.card_name, m.t, m.opens_subtopic) for m in mentions]


def _linked_mentions(session, set_code: str) -> list[tuple]:
    query = text("SELECT youtube_id, t FROM public_set_review_card_mentions WHERE set_code = :code")
    return [tuple(row) for row in session.execute(query, {"code": set_code})]
