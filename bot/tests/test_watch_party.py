import asyncio
from datetime import date, datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import discord
import pytest

from bot.services.mtgscribe import ScribeEvent
from bot.services.watch_party import channel_name, covered_events, coverage_windows, upcoming_windows
from bot.tasks import watch_party_post
from bot.tasks.watch_party_post import TICK, window_embed_state


def _event(title, tags, first_day, last_day):
    start = datetime.combine(first_day, datetime.min.time())
    end = datetime.combine(last_day, datetime.max.time())
    format_label, _, group_label = title.partition(": ")
    return ScribeEvent(
        title=title, format_label=format_label, group_label=group_label,
        start=start.replace(tzinfo=timezone.utc), end=end.replace(tzinfo=timezone.utc),
        start_local=start, end_local=end, tag_slugs=tuple(tags),
    )


@pytest.mark.parametrize("title, tags, counted", [
    ("World Championship 32: Standard", (), True),
    ("Pro Tour Nauctis: Draft", ("tabletop",), True),
    ("Arena Championship 13: Standard", ("arena-championship",), True),
    ("ACQ Weekend: Standard", ("arena-championship", "qualifier"), False),
    ("Arena Championship Qualifier Weekend: Standard", ("arena",), False),
    ("US Regional Championship: Baltimore – Modern", ("regional-championship",), False),
    ("US Regional Championship: Los Angeles – Modern", ("regional-championship", "coverage"), True),
    ("Spotlight Series Hartford: Standard", ("coverage",), True),
    ("Premier Draft: Reality Fracture", ("arena", "coverage"), False),
])
def test_an_event_counts_by_tag_or_title(title, tags, counted):
    event = _event(title, tags, date(2026, 10, 23), date(2026, 10, 25))

    covered = covered_events([event])

    assert bool(covered) is counted


CALENDAR = [
    _event("Spotlight Series Hartford: Standard", ("coverage", "magic-spotlight-series"),
           date(2026, 10, 23), date(2026, 10, 25)),
    _event("Arena Championship 13: Standard", ("coverage", "arena-championship"),
           date(2026, 10, 24), date(2026, 10, 25)),
    _event("World Championship 32: Standard", ("coverage", "magic-world-championship"),
           date(2026, 11, 13), date(2026, 11, 15)),
]


@pytest.mark.parametrize("today, expected", [
    (date(2026, 10, 1), "📺🎉-ac13-watch-party"),
    (date(2026, 10, 23), "📺🎉-ac13-watch-party"),
    (date(2026, 10, 25), "📺🎉-ac13-watch-party"),
    (date(2026, 10, 26), "📺🎉-worlds-watch-party"),
    (date(2026, 11, 16), "📺🎉-watch-party"),
])
def test_the_channel_holds_the_headliner_until_the_day_after_its_window(today, expected):
    windows = upcoming_windows(CALENDAR, today)

    name = channel_name(windows[0] if windows else None)

    assert name == expected


def test_each_window_posts_its_upcoming_and_live_embeds_on_exactly_one_tick():
    windows = coverage_windows(CALENDAR)
    ticks = [datetime(2026, 10, 1, tzinfo=timezone.utc) + TICK * step for step in range(60 * 24 * 4)]

    posts = []
    for previous, window in zip([None, *windows], windows):
        states = [window_embed_state(window, previous, tick) for tick in ticks]
        posts.append([state for state in states if state is not None])

    assert posts == [[False, True]] * len(windows)


def test_an_unreadable_pin_list_posts_no_new_coverage_pin(monkeypatch):
    monkeypatch.setattr(watch_party_post, "_bot", SimpleNamespace(fetch_application_emojis=AsyncMock(return_value=[])))
    channel = _UnreachablePinsChannel()

    asyncio.run(watch_party_post._refresh_coverage_pin(channel, CALENDAR))

    channel.send.assert_not_awaited()


class _UnreachablePinsChannel:
    name = "watch-party"

    def __init__(self):
        self.send = AsyncMock()

    async def pins(self):
        outage = SimpleNamespace(status=503, reason="Service Unavailable")
        raise discord.DiscordServerError(outage, "upstream connect error")
        yield
