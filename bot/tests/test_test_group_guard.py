import asyncio
from types import SimpleNamespace

import pytest

from bot.commands import test_group as group
from bot.config import PRODUCTION_GUILD_ID


class _Ctx(SimpleNamespace):
    async def send(self, *args, **kwargs):
        self.sent = True


def _ctx(guild_id: int | None) -> _Ctx:
    guild = SimpleNamespace(id=guild_id) if guild_id is not None else None
    return _Ctx(guild=guild, sent=False)


@pytest.mark.parametrize(
    "guild_id, name, expected",
    [
        (PRODUCTION_GUILD_ID, "launcher", True),
        (PRODUCTION_GUILD_ID, "poll", True),
        (PRODUCTION_GUILD_ID, "podswiss", True),
        (PRODUCTION_GUILD_ID, "rolling", False),
        (PRODUCTION_GUILD_ID, "reminders", False),
        (123456789, "launcher", False),
        (None, "launcher", False),
    ],
)
def test_production_refusal(guild_id, name, expected):
    ctx = _ctx(guild_id)

    refused = asyncio.run(group.refused_on_production(ctx, name))

    assert refused is expected
    assert ctx.sent is expected
