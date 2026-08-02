"""The pod voice channel as an offer players can act on: the message a thread posts once the lobby is half
full, and the channel lookup every surface that names voice goes through.

The link is a discord.gg invite because only an invite makes Discord draw its own join card, the one
showing the avatars of whoever is already in the channel. It is a guest invite, matching what Discord's
Invite to Voice Chat button creates: someone who follows it lands in the voice channel without joining
the server. `unique=False` lets Discord hand back an invite it already holds with the same settings, so a
pod every night does not fill the server's invite list, and a missing Create Invite permission degrades
to the plain channel link, which Discord draws as a narrower card with no occupants on it.

Seven days is the ceiling the API accepts for an invite, whatever longer lifetime the Discord client
offers on the same button.
"""
from __future__ import annotations

import logging

import discord

from bot.config import settings


log = logging.getLogger("bot.pod_voice")

VOICE_INVITE_MAX_AGE = 60 * 60 * 24 * 7
VOICE_INVITE_REASON = "Pod draft voice chat offer"
VOICE_OFFER_TEMPLATE = "🔊 [**Voice chat link**]({url})"


def pod_voice_channel(guild: discord.Guild | None) -> discord.VoiceChannel | None:
    """The pod voice channel, resolved by name from the guild's cached channels so it costs no request."""
    if guild is None:
        return None
    return discord.utils.get(guild.voice_channels, name=settings.pod_draft_voice_channel_name)


def pod_voice_channel_url(guild: discord.Guild | None) -> str | None:
    """Bare jump URL for the pod voice channel. None when the channel is absent."""
    channel = pod_voice_channel(guild)
    return channel.jump_url if channel is not None else None


async def voice_invite_url(channel: discord.VoiceChannel) -> str:
    """An invite link for the channel: a guest invite first, then a plain one, then the jump URL. The guest
    invite is what Discord's own Invite to Voice Chat button creates, and it is what draws the wide join
    card with the current occupants."""
    for guest in (True, False):
        try:
            invite = await channel.create_invite(
                max_age=VOICE_INVITE_MAX_AGE, unique=False, guest=guest, reason=VOICE_INVITE_REASON,
            )
        except discord.HTTPException:
            log.warning(f"[VOICE] invite_failed guest={guest} channel={channel.name}", exc_info=True)
            continue
        log.info(f"[VOICE] invite code={invite.code} guest={invite.flags.guest}")
        return invite.url
    return channel.jump_url


async def build_voice_offer_message(channel: discord.VoiceChannel) -> str:
    """The offer as one masked link."""
    return VOICE_OFFER_TEMPLATE.format(url=await voice_invite_url(channel))
