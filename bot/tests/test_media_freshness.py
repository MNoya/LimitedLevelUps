from datetime import datetime, timezone

from sqlalchemy import select

from bot.models import Episode
from bot.services.media_sync import _Item, _ingest_fresh


def _item(guid, title, published_at, *, kind="episode", category="Metagame"):
    return _Item(
        guid=guid,
        kind=kind,
        number=None,
        title=title,
        link="",
        summary="",
        image="",
        published_at=published_at,
        duration_seconds=1800,
        audio_url=None,
        youtube_id=None,
        category=category,
    )


def _row(guid, title, published_at, category):
    return Episode(
        guid=guid,
        kind="episode",
        title=title,
        link="",
        published_at=published_at,
        duration_seconds=10,
        category=category,
    )


def test_ingest_fresh_adds_only_unseen_guids(session):
    now = datetime(2026, 6, 20, tzinfo=timezone.utc)
    session.add(_row("pod-1", "Already here", now, "Metagame"))
    session.commit()

    result = _ingest_fresh(session, [_item("pod-1", "Already here", now), _item("pod-2", "Brand new drop", now)])

    assert set(session.execute(select(Episode.guid)).scalars()) == {"pod-1", "pod-2"}
    assert result.total == 1


def test_ingest_fresh_skips_existing_podcast_when_no_video_arrives(session):
    now = datetime(2026, 6, 20, tzinfo=timezone.utc)
    session.add(_row("pod-1", "Original title", now, "Coaching"))
    session.commit()

    _ingest_fresh(session, [_item("pod-1", "Title edited by full sync only", now, category="Metagame")])

    row = session.execute(select(Episode).where(Episode.guid == "pod-1")).scalar_one()
    assert row.title == "Original title"
    assert row.category == "Coaching"


def test_ingest_fresh_backfills_late_video_onto_podcast_row(session):
    now = datetime(2026, 6, 20, tzinfo=timezone.utc)
    session.add(_row("pod-1", "State of the Format", now, "Coaching"))
    session.commit()

    item = _item("pod-1", "State of the Format", now, category="Metagame")
    item.youtube_id = "abc123"
    item.image = "https://img/abc123.jpg"
    _ingest_fresh(session, [item])

    row = session.execute(select(Episode).where(Episode.guid == "pod-1")).scalar_one()
    assert row.youtube_id == "abc123"
    assert row.image == "https://img/abc123.jpg"
    assert row.category == "Metagame"


def test_ingest_fresh_drops_standalone_video_when_podcast_claims_it(session):
    now = datetime(2026, 6, 20, tzinfo=timezone.utc)
    standalone = _row("yt:abc123", "Draft Guide", now, "Metagame")
    standalone.kind = "video"
    standalone.youtube_id = "abc123"
    session.add(standalone)
    session.commit()

    item = _item("pod-1", "Draft Guide", now)
    item.youtube_id = "abc123"
    _ingest_fresh(session, [item])

    assert set(session.execute(select(Episode.guid)).scalars()) == {"pod-1"}


def test_ingest_fresh_leaves_already_videoed_rows_untouched(session):
    now = datetime(2026, 6, 20, tzinfo=timezone.utc)
    row = _row("pod-1", "Original title", now, "Coaching")
    row.youtube_id = "existing"
    session.add(row)
    session.commit()

    item = _item("pod-1", "Edited", now, category="Metagame")
    item.youtube_id = "replacement"
    _ingest_fresh(session, [item])

    saved = session.execute(select(Episode).where(Episode.guid == "pod-1")).scalar_one()
    assert saved.title == "Original title"
    assert saved.youtube_id == "existing"
    assert saved.category == "Coaching"
