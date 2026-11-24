import asyncio
from datetime import date, datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import discord
import pytest

from bot.services.pro_events import load_pro_events, parse_pro_events
from bot.services.watch_party import channel_name, coverage_windows, named_window
from bot.tasks import watch_party_post
from bot.tasks.watch_party_post import TICK, window_embed_state


CALENDAR = [
    {"name": "Spotlight Series Hartford", "kind": "spotlight", "days": ["2026-10-23", "2026-10-25"]},
    {"name": "Arena Championship 13", "kind": "ac", "days": ["2026-10-24", "2026-10-25"]},
    {"name": "World Championship 32", "kind": "worlds", "days": ["2026-11-13", "2026-11-15"]},
]
AC_AFTER_WORLDS = {"name": "Arena Championship 14", "kind": "ac", "days": ["2026-11-20", "2026-11-22"]}


@pytest.mark.parametrize("calendar, today, expected", [
    (CALENDAR, date(2026, 10, 1), "📺🎉-ac13-watch-party"),
    (CALENDAR, date(2026, 10, 25), "📺🎉-ac13-watch-party"),
    (CALENDAR, date(2026, 11, 5), "📺🎉-ac13-watch-party"),
    (CALENDAR, date(2026, 11, 6), "📺🎉-worlds-watch-party"),
    (CALENDAR, date(2027, 1, 30), "📺🎉-worlds-watch-party"),
    ([*CALENDAR, AC_AFTER_WORLDS], date(2026, 11, 19), "📺🎉-worlds-watch-party"),
    ([*CALENDAR, AC_AFTER_WORLDS], date(2026, 11, 20), "📺🎉-ac14-watch-party"),
])
def test_the_channel_keeps_the_last_name_until_the_next_window_is_a_week_out_after_a_premier_holds_a_week(
    calendar, today, expected,
):
    windows = coverage_windows(_pro_events(calendar))

    name = channel_name(named_window(windows, today))

    assert name == expected


def test_each_window_posts_its_upcoming_and_live_embeds_on_exactly_one_tick():
    windows = coverage_windows(_pro_events(CALENDAR))
    ticks = [datetime(2026, 10, 1, tzinfo=timezone.utc) + TICK * step for step in range(60 * 24 * 4)]

    posts = []
    for previous, window in zip([None, *windows], windows):
        states = [window_embed_state(window, previous, tick) for tick in ticks]
        posts.append([state for state in states if state is not None])

    assert posts == [[False, True]] * len(windows)


def test_an_unreadable_pin_list_posts_no_new_coverage_pin(monkeypatch):
    monkeypatch.setattr(watch_party_post, "_bot", SimpleNamespace(fetch_application_emojis=AsyncMock(return_value=[])))
    channel = _UnreachablePinsChannel()

    asyncio.run(watch_party_post._refresh_coverage_pin(channel, _pro_events(CALENDAR)))

    channel.send.assert_not_awaited()


def test_the_bundled_pro_events_file_parses_with_known_kinds_and_ordered_days():
    events = load_pro_events.__wrapped__()

    assert events
    assert all(list(covered.schedule.days) == sorted(covered.schedule.days, key=lambda day: day.day)
               for covered in events)


def _pro_events(calendar: list[dict]) -> list:
    raw = []
    for entry in calendar:
        days = [{"date": day, "start": "09:00", "end": "18:00", "subject": ""} for day in entry["days"]]
        raw.append({"name": entry["name"], "kind": entry["kind"], "details": "Standard", "draft": False,
                    "timezone": "America/New_York", "stream": None, "estimated": False, "days": days})
    return parse_pro_events(raw)


class _UnreachablePinsChannel:
    name = "watch-party"

    def __init__(self):
        self.send = AsyncMock()

    async def pins(self):
        outage = SimpleNamespace(status=503, reason="Service Unavailable")
        raise discord.DiscordServerError(outage, "upstream connect error")
        yield
