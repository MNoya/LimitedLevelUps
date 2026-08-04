import asyncio

import pytest

from bot.config import settings
from bot.tasks.gateway_watchdog import ALERT_COOLDOWN_S, QUIET_SECONDS, GatewayWatchdog

GUILD_ID = 775371722065051658


class StubClock:
    def __init__(self):
        self.now = 1_000.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


class StubBotLog:
    def __init__(self):
        self.posts = []

    async def post(self, summary: str, *, fingerprint: str | None = None, tag: str = "INFO") -> None:
        self.posts.append((fingerprint, tag))


class StubGuild:
    def __init__(self, *, answers: bool):
        self.answers = answers
        self.probes = 0

    async def query_members(self, **kwargs):
        self.probes += 1
        if not self.answers:
            raise asyncio.TimeoutError
        return []


class StubUser:
    id = 1466076574372724819


class StubBot:
    def __init__(self, *, guild: StubGuild):
        self.user = StubUser()
        self.bot_log = StubBotLog()
        self._guild = guild

    def get_guild(self, guild_id: int):
        return self._guild if guild_id == GUILD_ID else None


@pytest.fixture(autouse=True)
def guild_id(monkeypatch):
    monkeypatch.setattr(settings, "discord_guild_id", GUILD_ID, raising=False)


def build_watchdog(*, gateway_answers: bool):
    guild = StubGuild(answers=gateway_answers)
    bot = StubBot(guild=guild)
    clock = StubClock()
    return GatewayWatchdog(bot, clock=clock), bot, guild, clock


def test_a_recent_event_skips_the_probe():
    watchdog, bot, guild, clock = build_watchdog(gateway_answers=True)

    clock.advance(QUIET_SECONDS - 1)
    asyncio.run(watchdog.check())

    assert guild.probes == 0
    assert bot.bot_log.posts == []


def test_a_quiet_gateway_that_answers_the_probe_raises_nothing():
    watchdog, bot, guild, clock = build_watchdog(gateway_answers=True)

    clock.advance(QUIET_SECONDS + 1)
    asyncio.run(watchdog.check())

    assert guild.probes == 1
    assert bot.bot_log.posts == []
    assert watchdog.last_event_at == clock.now


def test_a_silent_gateway_alerts_once_per_cooldown():
    watchdog, bot, guild, clock = build_watchdog(gateway_answers=False)

    clock.advance(QUIET_SECONDS + 1)
    asyncio.run(watchdog.check())
    clock.advance(ALERT_COOLDOWN_S - 1)
    asyncio.run(watchdog.check())

    assert bot.bot_log.posts == [("gateway-silence", "GATEWAY")]

    clock.advance(2)
    asyncio.run(watchdog.check())

    assert len(bot.bot_log.posts) == 2


def test_a_missing_guild_alerts_nothing():
    watchdog, bot, guild, clock = build_watchdog(gateway_answers=False)
    bot._guild = None

    clock.advance(QUIET_SECONDS + 1)
    asyncio.run(watchdog.check())

    assert guild.probes == 0
    assert bot.bot_log.posts == []


def test_an_event_marks_the_gateway_alive():
    watchdog, bot, guild, clock = build_watchdog(gateway_answers=False)

    clock.advance(QUIET_SECONDS + 1)
    asyncio.run(watchdog.mark_event("MESSAGE_CREATE"))
    asyncio.run(watchdog.check())

    assert guild.probes == 0
    assert bot.bot_log.posts == []
