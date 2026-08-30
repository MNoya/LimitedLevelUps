"""Authorization checks shared by the moderator-facing prefix commands (`!guide`, `!championship`,
`!p0p1`). Roles are resolved against the configured guild, so a DM invocation still authorizes."""
from __future__ import annotations

import discord
from discord.ext import commands

from bot.config import settings
from bot.services.ping_roles import ORGANIZER_ROLE_NAME

MODERATOR_ROLE_NAME = "Moderator"


async def moderator_authorized(ctx: commands.Context) -> bool:
    """True for the bot owner, a guild administrator, the configured admin role or Moderator."""
    if await ctx.bot.is_owner(ctx.author):
        return True
    guild = ctx.bot.get_guild(settings.discord_guild_id) if settings.discord_guild_id else None
    member = guild.get_member(ctx.author.id) if guild is not None else None
    return _member_authorized(member)


async def moderator_authorized_interaction(interaction: discord.Interaction) -> bool:
    """`moderator_authorized` for a button or select click rather than a prefix command."""
    if await interaction.client.is_owner(interaction.user):
        return True
    member = interaction.user if isinstance(interaction.user, discord.Member) else None
    return _member_authorized(member)


async def organizer_authorized_interaction(interaction: discord.Interaction) -> bool:
    """True for the bot owner, a guild administrator or the Organizer role, for a button or select click."""
    if await interaction.client.is_owner(interaction.user):
        return True
    member = interaction.user if isinstance(interaction.user, discord.Member) else None
    if member is None:
        return False
    if member.guild_permissions.administrator:
        return True
    return any(role.name == ORGANIZER_ROLE_NAME for role in member.roles)


def _member_authorized(member: discord.Member | None) -> bool:
    if member is None:
        return False
    if member.guild_permissions.administrator:
        return True
    if settings.discord_admin_role_id and any(
            role.id == settings.discord_admin_role_id for role in member.roles):
        return True
    return any(role.name == MODERATOR_ROLE_NAME for role in member.roles)
