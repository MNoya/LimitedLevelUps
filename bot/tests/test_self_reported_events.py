from datetime import date, datetime, timezone

import pytest

from bot.discord_helpers import parse_message_link
from bot.models import MagicSet, Player, SelfReportedEvent
from bot.services.self_reported_events import delete_event, get_or_create_player, is_trophy_record, upsert_event


@pytest.mark.parametrize(
    "url, expected",
    [
        ("https://discord.com/channels/100/200/300", (100, 200, 300)),
        ("https://discordapp.com/channels/1/2/3", (1, 2, 3)),
        ("https://ptb.discord.com/channels/10/20/30", (10, 20, 30)),
        ("https://canary.discord.com/channels/10/20/30", (10, 20, 30)),
        ("look here https://discord.com/channels/5/6/7 thanks", (5, 6, 7)),
    ],
)
def test_parse_message_link_valid(url, expected):
    assert parse_message_link(url) == expected


@pytest.mark.parametrize("url", ["", "not a link", "https://discord.com/channels/5/6", "https://example.com/a/b/c"])
def test_parse_message_link_invalid(url):
    assert parse_message_link(url) is None


@pytest.mark.parametrize(
    "record, expected",
    [
        ("3-0", True),
        ("4-0", True),
        ("7-2", True),
        ("8-1", True),
        ("2-1", False),
        ("3-1", False),
        ("0-1", False),
        ("0-0", False),
        ("", False),
        (None, False),
        ("garbage", False),
    ],
)
def test_is_trophy_record(record, expected):
    assert is_trophy_record(record) is expected


def _seed_player(session, discord_id="111"):
    player = Player(slug=f"alice-{discord_id}", discord_id=discord_id, display_name="Alice", active=True)
    session.add(player)
    session.add(MagicSet(code="SOS", name="Secrets of Strixhaven", start_date=date(2026, 4, 21)))
    session.flush()
    return player


def test_get_or_create_player_creates_tokenless_row(session):
    player = get_or_create_player(
        session, discord_id="999", discord_username="newbie", display_name="Newbie", avatar_hash=None,
    )

    assert player.seventeenlands_token is None
    assert player.slug
    assert player.active is True


def test_get_or_create_player_returns_existing(session):
    existing = _seed_player(session, discord_id="111")

    player = get_or_create_player(
        session, discord_id="111", discord_username="alice2", display_name="Alice Renamed", avatar_hash=None,
    )

    assert player.id == existing.id
    assert session.query(Player).count() == 1


def test_upsert_resolves_set_id_from_code(session):
    player = _seed_player(session)

    event = upsert_event(
        session, player_id=player.id, set_code="SOS", record="3-0", is_trophy=True, colors="WR",
        platform="MTGO", format="Traditional", caption="finally hit it", screenshot_url="https://cdn/x.png",
        source_channel_id="c1", source_message_id="m1", source_url="u1",
    )

    assert event.set_id is not None
    assert event.caption == "finally hit it"
    assert session.get(MagicSet, event.set_id).code == "SOS"



@pytest.mark.parametrize(
    "discord_id, message_id, expected_removed",
    [
        ("111", "m1", True),
        ("111", "other", False),
        ("222", "m1", False),
    ],
)
def test_delete_event_removes_only_the_authors_saved_post(session, discord_id, message_id, expected_removed):
    player = _seed_player(session, discord_id="111")
    upsert_event(
        session, player_id=player.id, set_code="SOS", record="3-0", is_trophy=True, colors="WR",
        platform="Paper", format="Prerelease", caption=None, screenshot_url=None,
        source_channel_id="c1", source_message_id="m1", source_url="u1",
    )

    removed = delete_event(session, discord_id=discord_id, source_message_id=message_id)

    assert removed is expected_removed
    assert session.query(SelfReportedEvent).count() == (0 if expected_removed else 1)

def test_upsert_persists_is_trophy_flag(session):
    player = _seed_player(session)

    event = upsert_event(
        session, player_id=player.id, set_code="SOS", record="2-1", is_trophy=False, colors="WR",
        platform="MTGO", format="Traditional", caption=None, screenshot_url=None,
        source_channel_id="c1", source_message_id="m1", source_url="u1",
    )

    assert event.is_trophy is False


def test_upsert_is_idempotent_per_message(session):
    player = _seed_player(session)
    kwargs = dict(
        player_id=player.id, set_code="SOS", format=None, caption=None, screenshot_url=None,
        source_channel_id="c1", source_message_id="m1", source_url="u1",
    )

    upsert_event(session, record="3-0", is_trophy=True, colors="WR", platform="MTGO", **kwargs)
    upsert_event(session, record="7-2", is_trophy=True, colors="UBg", platform="MTGA", **kwargs)

    rows = session.query(SelfReportedEvent).all()
    assert len(rows) == 1
    assert (rows[0].record, rows[0].colors, rows[0].platform) == ("7-2", "UBg", "MTGA")


def test_upsert_distinct_messages_create_distinct_rows(session):
    player = _seed_player(session)

    upsert_event(
        session, player_id=player.id, set_code="SOS", record="3-0", is_trophy=True, colors=None,
        platform="Paper", format="Single Elim", caption=None, screenshot_url=None,
        source_channel_id="c1", source_message_id="m1", source_url="u1",
    )
    upsert_event(
        session, player_id=player.id, set_code="SOS", record="3-1", is_trophy=False, colors=None,
        platform="Paper", format="Traditional", caption=None, screenshot_url=None,
        source_channel_id="c1", source_message_id="m2", source_url="u2",
    )

    assert session.query(SelfReportedEvent).count() == 2


def test_upsert_timestamps_with_supplied_event_time(session):
    player = _seed_player(session)
    posted = datetime(2026, 4, 22, 15, 30, tzinfo=timezone.utc)

    event = upsert_event(
        session, player_id=player.id, set_code="SOS", record="3-0", is_trophy=True, colors=None,
        platform="MTGO", format="Traditional", caption=None, screenshot_url=None, reported_at=posted,
        source_channel_id="c1", source_message_id="m1", source_url="u1",
    )

    assert event.reported_at == posted


def test_upsert_unknown_set_code_leaves_set_id_null(session):
    player = _seed_player(session)

    event = upsert_event(
        session, player_id=player.id, set_code="ZZZ", record="3-0", is_trophy=True, colors=None,
        platform="MTGA", format="Premier", caption=None, screenshot_url=None,
        source_channel_id="c1", source_message_id="m9", source_url="u9",
    )

    assert event.set_id is None
    assert event.set_code == "ZZZ"
