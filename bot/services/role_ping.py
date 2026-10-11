"""Ping a chosen audience through a role: grant it, post one mention, strip it again.

Targeting rides on a role, not DMs: a bot can only message a user who shares a guild with it, so a DM sweep
reaches nobody a role grant misses, and the burst reads to Discord as spam. The role is emptied after the post
but never deleted, since a deleted role renders as ``@deleted-role`` in history.
"""
from __future__ import annotations

import asyncio
import logging

import discord

from bot.config import PRODUCTION_GUILD_ID
from bot.services.ping_roles import REMINDER_COLOR, REMINDER_ROLE_NAME

log = logging.getLogger(__name__)


async def ping_audience(
    guild: discord.Guild, role: discord.Role, discord_ids: list[str], build_post,
) -> tuple[int, list[discord.Member]]:
    """Grant the role to every reachable id, fire one ping through ``build_post``, then strip the role again.
    Returns how many were granted and the members reached. The role is emptied before the grants too, so a
    run that died mid-strip starts clean, and never deleted, so the live post keeps a real pill."""
    await ensure_member_cache(guild)
    members = _members_for(guild, discord_ids)
    await _empty_role(role)
    pinged = await _grant_all(role, members)
    await _post_ping(role, build_post)
    await _empty_role(role)
    return pinged, members


def audience(
    guild: discord.Guild, discord_ids: list[str], restrict_to: discord.Member | None,
) -> list[str]:
    """Off the production guild the ping reaches only whoever asked for it, and nobody at all when a
    scheduled tick fires. A test server holds real people who never signed up for the nudge, and its
    audience comes from dev data anyway, so a full sweep there pings the wrong crowd."""
    if guild.id == PRODUCTION_GUILD_ID:
        return discord_ids
    if restrict_to is None:
        log.info(f"role-ping: {guild.name} is not the production guild, pinging nobody")
        return []
    log.info(f"role-ping: {guild.name} is not the production guild, pinging only {restrict_to}")
    return [str(restrict_to.id)]


async def reminder_role(guild: discord.Guild) -> discord.Role | None:
    """The shared reminder role, not mentionable outside the post itself. `MANAGED_ROLES` owns its name and
    color once a reconcile has run."""
    return await ensure_ping_role(guild, REMINDER_ROLE_NAME, REMINDER_COLOR)


async def ensure_ping_role(guild: discord.Guild, name: str, color: str) -> discord.Role | None:
    """The ping role by name, created non-mentionable when a guild has none yet"""
    role = discord.utils.get(guild.roles, name=name)
    if role is not None:
        return role
    try:
        role = await guild.create_role(
            name=name, colour=discord.Colour.from_str(color), mentionable=False, reason="role ping",
        )
    except discord.HTTPException:
        log.warning(f"role-ping: could not create {name!r} in {guild.name}", exc_info=True)
        return None
    log.info(f"role-ping: created {name!r} in {guild.name}")
    return role


async def ensure_member_cache(guild: discord.Guild) -> None:
    """Both the target lookup and the strip read the member cache, so an unchunked guild would silently
    report most of the audience as absent and leave stale holders on the role."""
    if guild.chunked:
        return
    try:
        await guild.chunk()
    except (discord.ClientException, asyncio.TimeoutError):
        log.warning(f"role-ping: could not chunk {guild.name}, reach will be understated", exc_info=True)


def _members_for(guild: discord.Guild, discord_ids: list[str]) -> list[discord.Member]:
    members = []
    for discord_id in discord_ids:
        if not discord_id.isdigit():
            log.warning(f"role-ping: skipping non-numeric discord id {discord_id!r}")
            continue
        member = guild.get_member(int(discord_id))
        if member is not None:
            members.append(member)
    return members


async def _post_ping(role: discord.Role, build_post) -> None:
    """Make the role mentionable only for the send. Leaving it mentionable would let any member fire it,
    and the alternative — posting a silent role and relying on Mention Everyone — makes the ping depend on
    a permission the bot has no other reason to hold."""
    try:
        await role.edit(mentionable=True, reason="role ping")
    except discord.HTTPException:
        log.warning(f"role-ping: could not make {role.name!r} mentionable", exc_info=True)
    try:
        await build_post(role.mention)
    finally:
        try:
            await role.edit(mentionable=False, reason="role ping sent")
        except discord.HTTPException:
            log.warning(f"role-ping: {role.name!r} left mentionable", exc_info=True)


async def _grant_all(role: discord.Role, members: list[discord.Member]) -> int:
    granted = 0
    for member in members:
        try:
            await member.add_roles(role, reason="role ping")
            granted += 1
        except discord.HTTPException:
            log.warning(f"role-ping: could not grant {role.name!r} to {member}", exc_info=True)
    return granted


async def _empty_role(role: discord.Role) -> None:
    """Strip every holder. Run before the grants as well as after, so a run that died mid-strip leaves the
    next one a clean role instead of pinging the last run's list."""
    for member in list(role.members):
        try:
            await member.remove_roles(role, reason="role ping sent")
        except discord.HTTPException:
            log.warning(f"role-ping: could not strip {role.name!r} from {member}", exc_info=True)
