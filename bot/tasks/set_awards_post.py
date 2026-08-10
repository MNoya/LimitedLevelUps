"""Set Awards ceremony scheduled the eve of a rotation, with a T-15 warning.

Two APScheduler cron jobs in Pacific (MTGA's release clock): a heads-up at ``WARNING_TIME`` and the
ceremony at ``AWARDS_CEREMONY_TIME``, each firing only when a new set releases the next day. Both post into
the outgoing set's channel — the one the noon-ET rotation archives after the flip. The ceremony reuses
``run_set_awards_ceremony``, the same path ``/set-awards`` runs. The warning links the prior set's
ceremony when it can find it in that set's archived channel; otherwise it drops the link.

The warning also posts a pointer back to itself in the incoming set's channel: preview season moves
discussion there days before the flip, so the send-off runs in the quieter of the two channels.
"""
from __future__ import annotations

import logging
from datetime import datetime, time, timezone

import discord
from discord.ext import commands

from bot import emojis
from bot.commands.set_awards import run_set_awards_ceremony
from bot.config import settings
from bot.discord_helpers import message_text
from bot.services.format_schedule import (
    AWARDS_CEREMONY_TIME,
    FORMAT_ARCHIVE_CATEGORY,
    OPEN_TZ,
    awards_eve_set,
    ceremony_start,
    channel_for_set,
    set_after,
    set_before,
)

log = logging.getLogger(__name__)

WARNING_TIME = time(7, 45)
AWARDS_MARKER = "Set Awards"
MSG_CEREMONY_WARNING = "Join us for the Community Set Awards {emoji} **{name} Edition** {when}!"
MSG_CEREMONY_SUBTEXT = "-# Given out every Monday before a new set releases"
MSG_PREVIOUS_AWARDS = ". [**Previous Set Awards**]({link}) {manat}"
MSG_CEREMONY_ELSEWHERE = (
    "Community Set Awards {emoji} start {when} {link}\n\n"
    "-# Run `/set-awards` after the announcement to see your own!"
)

_bot: commands.Bot | None = None


def init_set_awards_schedule(bot: commands.Bot) -> None:
    global _bot
    _bot = bot
    if not settings.format_schedule_enabled:
        log.info("FORMAT_SCHEDULE_ENABLED=false; set-awards ceremony disabled")
        return
    bot.pod_scheduler.add_job(
        fire_warning, "cron", hour=WARNING_TIME.hour, minute=WARNING_TIME.minute,
        timezone=OPEN_TZ, id="set-awards-warning", replace_existing=True,
    )
    bot.pod_scheduler.add_job(
        fire_ceremony, "cron", hour=AWARDS_CEREMONY_TIME.hour, minute=AWARDS_CEREMONY_TIME.minute,
        timezone=OPEN_TZ, id="set-awards-ceremony", replace_existing=True,
    )
    log.info(f"set-awards armed: warning {WARNING_TIME:%H:%M}, ceremony {AWARDS_CEREMONY_TIME:%H:%M} {OPEN_TZ.key}")


async def fire_warning() -> None:
    resolved = _resolve_eve()
    if resolved is None:
        return
    guild, channel, seed = resolved
    await post_ceremony_warning(guild, channel, seed, ceremony_start())


async def post_ceremony_warning(guild: discord.Guild, ceremony_channel, seed, starts_at: datetime):
    """Send the warning into the outgoing set's channel and the pointer to it into the incoming set's.
    Returns the warning message and the channel the pointer reached, either ``None`` when that send did
    not happen. Shared with ``!test awardswarning`` so a rehearsal routes exactly like the real run."""
    try:
        text = await build_warning_text(guild, seed, starts_at)
        warning = await ceremony_channel.send(text, suppress_embeds=True)
    except discord.HTTPException:
        log.warning(f"set-awards: could not post the warning in #{ceremony_channel.name}", exc_info=True)
        return None, None
    target = incoming_set_channel(guild, seed, ceremony_channel)
    if target is None:
        return warning, None
    try:
        await target.send(build_pointer_text(seed, warning.jump_url, starts_at))
    except discord.HTTPException:
        log.warning(f"set-awards: could not post the ceremony pointer in #{target.name}", exc_info=True)
        return warning, None
    return warning, target


async def build_warning_text(guild: discord.Guild, seed, starts_at: datetime) -> str:
    head = MSG_CEREMONY_WARNING.format(
        emoji=emojis.get(seed.code.lower()), name=seed.name, when=discord.utils.format_dt(starts_at, "R"),
    )
    subtext = MSG_CEREMONY_SUBTEXT
    link = await _previous_awards_link(guild, seed)
    if link is not None:
        subtext += MSG_PREVIOUS_AWARDS.format(link=link, manat=emojis.get("manat")).rstrip()
    return f"{head}\n\n{subtext}"


def build_pointer_text(seed, link: str, starts_at: datetime) -> str:
    """The link goes in bare so Discord renders its message preview, which is why this one is sent
    without ``suppress_embeds``. A markdown link would carry the channel name, and a channel name
    holding an emoji breaks the ``[]`` label."""
    return MSG_CEREMONY_ELSEWHERE.format(
        emoji=emojis.get(seed.code.lower()), when=discord.utils.format_dt(starts_at, "R"), link=link,
    )


def incoming_set_channel(guild: discord.Guild, outgoing_seed, ceremony_channel):
    """The channel of the set that releases tomorrow, matched in any category so a preview-season one a
    mod created outside MTG Strategy still resolves. ``None`` when that set is the newest registered, has
    no channel yet, or shares the channel the ceremony already posts in."""
    incoming = set_after(outgoing_seed)
    if incoming is None:
        return None
    channel = channel_for_set(guild.text_channels, incoming, category=None)
    if channel is None:
        log.info(f"set-awards: no channel for incoming set {incoming.code}; posting no pointer")
        return None
    if channel.id == ceremony_channel.id:
        return None
    return channel


async def _previous_awards_link(guild: discord.Guild, outgoing_seed) -> str | None:
    """A jump link to the prior set's ceremony, found among the pins of that set's archived channel, or
    ``None`` when there's no earlier set, no archived channel, or no pinned ceremony. The ceremony pins
    itself when posted, so this reads the pin board rather than paging end-of-set chat."""
    previous = set_before(outgoing_seed)
    if previous is None:
        return None
    channel = channel_for_set(guild.text_channels, previous, FORMAT_ARCHIVE_CATEGORY)
    if channel is None:
        return None
    try:
        async for message in channel.pins():
            if _bot.user is not None and message.author.id == _bot.user.id and AWARDS_MARKER in message_text(message):
                return message.jump_url
    except discord.HTTPException:
        log.warning(f"set-awards: could not read pins in #{channel.name}", exc_info=True)
        return None
    log.info(f"set-awards: no pinned ceremony in #{channel.name}")
    return None


async def fire_ceremony() -> None:
    resolved = _resolve_eve()
    if resolved is None:
        return
    guild, channel, seed = resolved
    await run_set_awards_ceremony(channel, guild, seed.code, seed, dry=False)


def _resolve_eve():
    """The (guild, outgoing channel, seed) to run tonight's ceremony against, or ``None`` when it isn't
    a rotation eve or the outgoing set has no channel."""
    if _bot is None:
        log.error("set-awards: bot reference is not initialised")
        return None
    guild = _bot.get_guild(settings.discord_guild_id) if settings.discord_guild_id else None
    if guild is None:
        log.warning("set-awards: guild unavailable; skipping")
        return None
    seed = awards_eve_set(datetime.now(timezone.utc))
    if seed is None:
        return None
    channel = channel_for_set(guild.text_channels, seed)
    if channel is None:
        log.info(f"set-awards: no channel for outgoing set {seed.code}; skipping")
        return None
    return guild, channel, seed
