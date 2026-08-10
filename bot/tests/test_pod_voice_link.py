import asyncio
from types import SimpleNamespace

import discord
import pytest

from bot.config import settings
from bot.services.pod_draft_manager import PodDraftManager


def test_posts_voice_link_once():
    mgr, thread, channel = _manager()

    asyncio.run(mgr.post_voice_offer())
    asyncio.run(mgr.post_voice_offer())

    assert len(thread.sent) == 1
    assert channel.invite_url in thread.sent[0]


@pytest.mark.parametrize("guest_invites, can_invite, expected_url", [
    (True, True, "invite_url"),
    (False, True, "plain_invite_url"),
    (True, False, "jump_url"),
])
def test_voice_link_falls_back_by_invite_permission(guest_invites, can_invite, expected_url):
    mgr, thread, channel = _manager(guest_invites=guest_invites, can_invite=can_invite)

    asyncio.run(mgr.post_voice_offer())

    assert len(thread.sent) == 1
    assert getattr(channel, expected_url) in thread.sent[0]


def test_voice_link_skips_and_latches_when_channel_absent():
    mgr, thread, _ = _manager(voice_channel=False)

    asyncio.run(mgr.post_voice_offer())

    assert thread.sent == []
    assert mgr._voice_link_posted is True


def test_voice_offer_posts_after_the_draft_ends():
    mgr, thread, _ = _manager()
    mgr.drafting = False
    mgr.draft_complete = True

    asyncio.run(mgr.post_voice_offer())

    assert len(thread.sent) == 1


@pytest.mark.parametrize("occupied, claimed", [
    ((), ["Room 1", "Room 2"]),
    (("Room 1",), ["Room 2", "Room 3"]),
    (("Room 1", "Room 2"), ["Room 3", "Room 4"]),
    (("Room 2", "Room 3"), ["Room 1", "Room 4"]),
])
def test_a_team_draft_claims_the_first_two_free_rooms(occupied, claimed):
    mgr, thread, _ = _team_manager(occupied)

    asyncio.run(mgr.post_voice_offer())

    assert [room.name for room in mgr.team_voice_rooms] == claimed
    assert thread.sent == []


def test_a_decorated_room_name_still_counts_as_a_room():
    mgr, _, _ = _team_manager((), names=("🔊 Room 1", "Lobby", "🔊 Room 2"))

    asyncio.run(mgr.post_voice_offer())

    assert [room.name for room in mgr.team_voice_rooms] == ["🔊 Room 1", "🔊 Room 2"]


def test_a_team_draft_without_two_free_rooms_falls_back_to_the_shared_channel():
    mgr, thread, channel = _team_manager(("Room 1", "Room 2", "Room 3", "Room 4"))

    asyncio.run(mgr.post_voice_offer())

    assert mgr.team_voice_rooms == []
    assert channel.invite_url in thread.sent[0]


def _manager(
    *, voice_channel: bool = True, can_invite: bool = True, guest_invites: bool = True,
    rooms: list["_Channel"] | None = None,
) -> tuple[PodDraftManager, "_Thread", "_Channel | None"]:
    channel = (
        _Channel(settings.pod_draft_voice_channel_name, can_invite=can_invite, guest_invites=guest_invites)
        if voice_channel else None
    )
    voice_channels = ([channel] if channel else []) + (rooms or [])
    thread = _Thread(_Guild(voice_channels))
    mgr = PodDraftManager(object(), "evt", "sid", 123, "SOS", 8)
    mgr._fetch_thread = lambda: _resolved(thread)
    return mgr, thread, channel


def _team_manager(
    occupied: tuple[str, ...], *, names: tuple[str, ...] = ("Room 1", "Room 2", "Room 3", "Room 4"),
) -> tuple[PodDraftManager, "_Thread", "_Channel | None"]:
    rooms = [_Channel(name, members=["someone"] if name in occupied else []) for name in names]
    mgr, thread, channel = _manager(rooms=rooms)
    mgr.pairing_mode = "team"
    return mgr, thread, channel


async def _resolved(value):
    return value


class _Channel:
    def __init__(
        self, name: str, *, can_invite: bool = True, guest_invites: bool = True, members: list | None = None,
    ) -> None:
        self.name = name
        self.members = members or []
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
