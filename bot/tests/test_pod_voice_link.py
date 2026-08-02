import asyncio
from types import SimpleNamespace

import discord

from bot.config import settings
from bot.services.pod_draft_manager import PodDraftManager


def test_posts_voice_link_once_at_half_table():
    mgr = _manager()
    channel = _Channel(settings.pod_draft_voice_channel_name)
    thread = _thread([channel])

    asyncio.run(mgr._maybe_post_voice_link(_classified(4), thread))
    asyncio.run(mgr._maybe_post_voice_link(_classified(6), thread))

    assert len(thread.sent) == 1
    assert channel.invite_url in thread.sent[0]


def test_voice_link_falls_back_to_a_plain_invite_without_guest_invites():
    mgr = _manager()
    channel = _Channel(settings.pod_draft_voice_channel_name, guest_invites=False)
    thread = _thread([channel])

    asyncio.run(mgr._maybe_post_voice_link(_classified(4), thread))

    assert len(thread.sent) == 1
    assert channel.plain_invite_url in thread.sent[0]


def test_voice_link_falls_back_to_the_jump_url_without_invite_permission():
    mgr = _manager()
    channel = _Channel(settings.pod_draft_voice_channel_name, can_invite=False)
    thread = _thread([channel])

    asyncio.run(mgr._maybe_post_voice_link(_classified(4), thread))

    assert len(thread.sent) == 1
    assert channel.jump_url in thread.sent[0]


def test_no_voice_link_below_half():
    mgr = _manager()
    thread = _thread([_Channel(settings.pod_draft_voice_channel_name)])

    asyncio.run(mgr._maybe_post_voice_link(_classified(3), thread))

    assert thread.sent == []


def test_voice_link_skips_and_latches_when_channel_absent():
    mgr = _manager()
    thread = _thread([])

    asyncio.run(mgr._maybe_post_voice_link(_classified(4), thread))

    assert thread.sent == []
    assert mgr._voice_link_posted is True


def _manager() -> PodDraftManager:
    return PodDraftManager(object(), "evt", "sid", 123, "SOS", 8)


def _classified(n: int) -> list[tuple[str, str]]:
    return [(f"a{i}", f"d{i}") for i in range(n)]


class _Channel:
    def __init__(self, name: str, *, can_invite: bool = True, guest_invites: bool = True) -> None:
        self.name = name
        self.jump_url = f"https://discord.com/channels/1/{name}"
        self.invite_url = "https://discord.gg/podvoice"
        self.plain_invite_url = "https://discord.gg/podvoiceplain"
        self._can_invite = can_invite
        self._guest_invites = guest_invites

    async def create_invite(self, *, guest: bool = False, **kwargs):
        if not self._can_invite:
            raise discord.HTTPException(_ForbiddenResponse(), "Missing Permissions")
        if guest and not self._guest_invites:
            raise discord.HTTPException(_ForbiddenResponse(), "Guest invites unavailable")
        url = self.invite_url if guest else self.plain_invite_url
        return SimpleNamespace(url=url, code=url.rsplit("/", 1)[-1], flags=SimpleNamespace(guest=guest))


class _Guild:
    def __init__(self, voice_channels: list) -> None:
        self.voice_channels = voice_channels


class _Thread:
    def __init__(self, guild: _Guild) -> None:
        self.guild = guild
        self.sent: list[str] = []

    async def send(self, content: str) -> None:
        self.sent.append(content)


class _ForbiddenResponse:
    status = 403
    reason = "Forbidden"


def _thread(voice_channels: list) -> _Thread:
    return _Thread(_Guild(voice_channels))
