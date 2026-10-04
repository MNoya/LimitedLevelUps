"""Pod-draft notification roles — resolve, grant, and toggle the pod ping roles.

Logic only; the role-name constants live in bot/services/pod_schedule.py and the user-facing copy
lives with each caller (sesh listener auto-grant, /pod-roles toggle).
"""
from __future__ import annotations

import logging
import re
from collections.abc import Sequence

import discord

from bot.services.pod_schedule import POD_DRAFTERS_ROLE_NAME


log = logging.getLogger(__name__)

_MENTION_RE = re.compile(r"^<@!?(\d+)>$")

_bot_grants: set[tuple[int, str]] = set()
_bot_removals: set[tuple[int, str]] = set()


def consume_bot_grant(member_id: int, role_name: str) -> bool:
    """Whether the bot added this role, consumed once, so the role listener reacts only to onboarding gains"""
    return _consume_mark(_bot_grants, (member_id, role_name))


def consume_bot_removal(member_id: int, role_name: str) -> bool:
    """Whether the bot removed this role, consumed once, so the role listener reacts only to a player's own removal"""
    return _consume_mark(_bot_removals, (member_id, role_name))


def find_role(guild: discord.Guild | None, name: str) -> discord.Role | None:
    if guild is None:
        return None
    return discord.utils.get(guild.roles, name=name)


def role_mention(guild: discord.Guild | None, name: str) -> str:
    """The role's mention, or its plain `@name` when the guild is out of reach, as in a DM. In an embed a
    role mention renders without pinging."""
    role = find_role(guild, name)
    return role.mention if role is not None else f"@{name}"


def role_holder_mention(guild: discord.Guild | None, name: str) -> str | None:
    """Mention of the first member holding `name`, or None when the role is missing or unheld. In an
    embed a mention renders the member's handle without pinging."""
    role = find_role(guild, name)
    if role is None or not role.members:
        return None
    return role.members[0].mention


async def grant_role(member: discord.Member, role: discord.Role) -> bool:
    """Add the role if the member lacks it; True when a grant actually happened."""
    if role in member.roles:
        return False
    _bot_grants.add((member.id, role.name))
    try:
        await member.add_roles(role, reason="pod-draft auto-grant")
        return True
    except discord.HTTPException:
        _bot_grants.discard((member.id, role.name))
        log.warning(f"could not grant {role.name} to {member}", exc_info=True)
        return False


async def grant_pod_drafters(member: discord.Member) -> bool:
    """Sticky umbrella grant: any pod-draft interaction makes the member a Pod Drafter. Silent —
    the umbrella carries the name color and the server-wide announce ping, nothing to celebrate."""
    role = find_role(member.guild, POD_DRAFTERS_ROLE_NAME)
    if role is None:
        return False
    return await grant_role(member, role)


async def toggle_role(member: discord.Member, role: discord.Role) -> bool | None:
    """Flip role membership for a member; returns the new held-state, or None on failure."""
    held = role in member.roles
    try:
        if held:
            await revoke_roles(member, [role], reason="pod-roles toggle")
        else:
            _bot_grants.add((member.id, role.name))
            await member.add_roles(role, reason="pod-roles toggle")
        return not held
    except discord.HTTPException:
        _bot_grants.discard((member.id, role.name))
        log.warning(f"could not toggle {role.name} for {member}", exc_info=True)
        return None


async def revoke_roles(member: discord.Member, roles: Sequence[discord.Role], *, reason: str) -> None:
    marks = {(member.id, role.name) for role in roles}
    _bot_removals.update(marks)
    try:
        await member.remove_roles(*roles, reason=reason)
    except discord.HTTPException:
        _bot_removals.difference_update(marks)
        raise


async def resolve_member(guild: discord.Guild, token: str) -> discord.Member | None:
    """Map a sesh attendee token — either a <@id> mention or a display/username — to a guild member."""
    match = _MENTION_RE.match(token)
    if match is not None:
        user_id = int(match.group(1))
        member = guild.get_member(user_id)
        if member is not None:
            return member
        try:
            return await guild.fetch_member(user_id)
        except discord.HTTPException:
            return None
    lowered = token.lower()
    for member in guild.members:
        if member.display_name.lower() == lowered or member.name.lower() == lowered:
            return member
    return None


def _consume_mark(marks: set[tuple[int, str]], key: tuple[int, str]) -> bool:
    if key in marks:
        marks.discard(key)
        return True
    return False
