"""`/roles` — self-serve toggle menu for the self-assignable ping roles in PING_ROLES.

A Components V2 LayoutView: one Section per registry role, its blurb (and local time, if it maps to a
slot) on the left and a toggle button on the right (green = subscribed). Each click toggles the role
for the caller and edits the message in place. The view is persistent (timeout=None, static custom_ids
derived from role names) and registered at startup so buttons keep dispatching after a restart.
"""
from __future__ import annotations

import asyncio
import logging

import discord
from discord import app_commands
from discord.ext import commands

from bot.commands import descriptions as desc
from bot.config import settings
from bot.database import SessionLocal
from bot.discord_helpers import extract_avatar_hash, run_detached
from bot.services.ping_roles import (
    PING_ROLES,
    announce_onboarding_welcome,
    blurb_with_time,
    button_custom_id,
    display_emoji,
    spec_named,
)
from bot.services.pod_drafts import (
    dm_draft_link_enabled,
    set_pod_roles_declined_sync,
    toggle_dm_draft_link,
)
from bot.services.pod_link_dm import dm_pref_embed
from bot.services.pod_roles import (
    consume_bot_umbrella_grant,
    find_role,
    grant_pod_drafters,
    grant_role,
    toggle_role,
)
from bot.services.pod_schedule import POD_DRAFTERS_ROLE_NAME


log = logging.getLogger(__name__)

MSG_INTRO = "Toggle your notifications. Green means subscribed. Times shown in your timezone."
MSG_NO_GUILD = "Run `/roles` in the server to manage your notifications"
MSG_ROLE_MISSING = "That role isn't set up on the server. Ask an Admin"
MSG_ROLE_TOGGLE_FAILED = "Couldn't update that role. The bot is missing the Manage Roles permission"
MSG_DM_PREF_LABEL = "Draft Link DMs"
MSG_DM_PREF_LINE = "**Draft Link DMs:** your Draftmancer link when Pod is ready to start"
DM_PREF_CUSTOM_ID = "pod_dm_draft_link"


class _RoleToggleButton(discord.ui.Button):
    """A unicode emoji rides in the label so it renders right of the name; a custom emoji can't
    appear in label text, so it stays in the emoji slot on the left."""

    def __init__(self, role_name: str, emoji: str | None, custom_id: str, held: bool) -> None:
        unicode_emoji = emoji if emoji is not None and not emoji.startswith("<") else None
        super().__init__(
            label=f"{role_name} {unicode_emoji}" if unicode_emoji else role_name,
            emoji=None if unicode_emoji else emoji,
            custom_id=custom_id,
            style=discord.ButtonStyle.success if held else discord.ButtonStyle.secondary,
        )
        self.role_name = role_name

    async def callback(self, interaction: discord.Interaction) -> None:
        member, guild = await _resolve_member(interaction)
        if member is None or guild is None:
            await interaction.response.send_message(MSG_NO_GUILD, ephemeral=True)
            return
        role = find_role(guild, self.role_name)
        if role is None:
            await interaction.response.send_message(MSG_ROLE_MISSING, ephemeral=True)
            return
        new_state = await toggle_role(member, role)
        if new_state is None:
            await interaction.response.send_message(MSG_ROLE_TOGGLE_FAILED, ephemeral=True)
            return
        _remember_role_choice(member, self.role_name, held=new_state)
        refreshed = guild.get_member(member.id) or member
        held = {held_role.name for held_role in refreshed.roles}
        held.add(self.role_name) if new_state else held.discard(self.role_name)
        if new_state and self.role_name != POD_DRAFTERS_ROLE_NAME:
            if await grant_pod_drafters(refreshed):
                held.add(POD_DRAFTERS_ROLE_NAME)
        if not new_state and self.role_name == POD_DRAFTERS_ROLE_NAME:
            held -= {spec.name for spec in PING_ROLES}
        dm_opt_in = await asyncio.to_thread(_dm_opt_in_for, str(member.id))
        await interaction.response.edit_message(
            view=RolesView(held, guild, in_guild=interaction.guild is not None, dm_opt_in=dm_opt_in),
        )


class _DmPrefToggleButton(discord.ui.Button):
    """Toggles the lobby-open link DM. Not a Discord role, so it reads and flips the DB preference
    directly, re-renders the panel, and confirms the new state with an ephemeral embed."""

    def __init__(self, held: bool) -> None:
        super().__init__(
            label=f"{MSG_DM_PREF_LABEL} ✉️",
            custom_id=DM_PREF_CUSTOM_ID,
            style=discord.ButtonStyle.success if held else discord.ButtonStyle.secondary,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        user = interaction.user
        avatar_hash = extract_avatar_hash(user)
        new_state = await asyncio.to_thread(_toggle_dm_pref, str(user.id), user.name, user.display_name, avatar_hash)
        member, guild = await _resolve_member(interaction)
        held = {role.name for role in getattr(member, "roles", [])} if member else set()
        await interaction.response.edit_message(
            view=RolesView(held, guild, in_guild=interaction.guild is not None, dm_opt_in=new_state),
        )
        await interaction.followup.send(embed=dm_pref_embed(new_state), ephemeral=True)


class RolesView(discord.ui.LayoutView):
    """In-guild the role mention leads each line (colored, clickable pill); in a DM the plain role
    name stands in, since no client can resolve a mention outside its guild's role cache."""

    def __init__(
        self, held: set[str] | None = None, guild: discord.Guild | None = None, *, in_guild: bool = True,
        dm_opt_in: bool = True,
    ) -> None:
        super().__init__(timeout=None)
        held = held or set()
        self.add_item(discord.ui.TextDisplay(MSG_INTRO))
        for spec in PING_ROLES:
            button = _RoleToggleButton(spec.name, display_emoji(spec), button_custom_id(spec), spec.name in held)
            role = find_role(guild, spec.name)
            label = role.mention if role and in_guild else f"**{spec.name}:**"
            line = f"{label} {blurb_with_time(spec)}"
            self.add_item(discord.ui.Section(discord.ui.TextDisplay(line), accessory=button))
        self.add_item(discord.ui.Section(
            discord.ui.TextDisplay(MSG_DM_PREF_LINE), accessory=_DmPrefToggleButton(dm_opt_in),
        ))


async def _resolve_member(
    interaction: discord.Interaction,
) -> tuple[discord.Member | None, discord.Guild | None]:
    if interaction.guild is not None and isinstance(interaction.user, discord.Member):
        return interaction.user, interaction.guild
    guild = interaction.client.get_guild(settings.discord_guild_id) if settings.discord_guild_id else None
    if guild is None:
        return None, None
    member = guild.get_member(interaction.user.id)
    if member is None:
        try:
            member = await guild.fetch_member(interaction.user.id)
        except discord.HTTPException:
            return None, None
    return member, guild


def _remember_role_choice(member: discord.Member, role_name: str, *, held: bool) -> None:
    """Persist a toggle so the pod auto-grant obeys it, without the panel waiting on the write. Only the
    auto-granted roles are worth storing: Pod Drafters comes back on the next pod whatever is set here,
    and no path re-adds the others behind a player's back."""
    spec = spec_named(role_name)
    if spec is None or not spec.auto_grant:
        return
    run_detached(asyncio.to_thread(
        set_pod_roles_declined_sync,
        discord_id=str(member.id), discord_username=member.name, display_name=member.display_name,
        avatar_hash=extract_avatar_hash(member), keys=[spec.key], declined=not held,
    ), f"role choice {spec.key} for {member.id}")


def _dm_opt_in_for(discord_id: str) -> bool:
    with SessionLocal() as session:
        return dm_draft_link_enabled(session, discord_id)


def _toggle_dm_pref(discord_id: str, username: str, display_name: str, avatar_hash: str | None) -> bool:
    with SessionLocal() as session:
        new_state = toggle_dm_draft_link(
            session, discord_id=discord_id, discord_username=username, display_name=display_name,
            avatar_hash=avatar_hash,
        )
        session.commit()
        return new_state


class Roles(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member) -> None:
        """Pod Drafters gained through Discord's onboarding question bypasses every interaction path,
        so its welcome fires here; bot-mediated gains are left to the path that granted them. Losing
        the umbrella means leaving pod notifications entirely: it carries the one name color for pod
        players, so the slot roles go with it instead of surviving as a colored back door."""
        before_names = {role.name for role in before.roles}
        after_names = {role.name for role in after.roles}
        if POD_DRAFTERS_ROLE_NAME not in before_names and POD_DRAFTERS_ROLE_NAME in after_names:
            if consume_bot_umbrella_grant(after.id):
                log.info(f"{after} gained {POD_DRAFTERS_ROLE_NAME} via a bot path; welcome left to that path")
            else:
                log.info(f"{after} gained {POD_DRAFTERS_ROLE_NAME} outside the bot; posting onboarding welcome")
                await announce_onboarding_welcome(self.bot, after)
            return
        if POD_DRAFTERS_ROLE_NAME not in before_names or POD_DRAFTERS_ROLE_NAME in after_names:
            return
        other_ping_roles = {spec.name for spec in PING_ROLES if spec.name != POD_DRAFTERS_ROLE_NAME}
        held = [role for role in after.roles if role.name in other_ping_roles]
        if not held:
            return
        try:
            await after.remove_roles(*held, reason="Pod Drafters removed; clearing slot roles with it")
            log.info(f"cleared {[role.name for role in held]} from {after} after {POD_DRAFTERS_ROLE_NAME} removal")
        except discord.HTTPException:
            log.warning(f"could not clear slot roles from {after}", exc_info=True)

    @app_commands.command(name="roles", description=desc.ROLES)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=False)
    @app_commands.allowed_installs(guilds=True, users=False)
    async def roles(self, interaction: discord.Interaction) -> None:
        member, guild = await _resolve_member(interaction)
        if member is None:
            await interaction.response.send_message(MSG_NO_GUILD, ephemeral=True)
            return
        held = {role.name for role in member.roles}
        dm_opt_in = await asyncio.to_thread(_dm_opt_in_for, str(member.id))
        await interaction.response.send_message(
            view=RolesView(held, guild, in_guild=interaction.guild is not None, dm_opt_in=dm_opt_in),
            ephemeral=(interaction.guild is not None),
            allowed_mentions=discord.AllowedMentions.none(),
        )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Roles(bot))

    @bot.command(name="grant-roles")
    @commands.is_owner()
    async def grant_roles(ctx: commands.Context) -> None:
        """Owner-only, idempotent: grant Pod Drafters to every member holding any other ping role,
        so anyone in anything pod-related wears the umbrella name color."""
        reports = []
        for guild in bot.guilds:
            umbrella = find_role(guild, POD_DRAFTERS_ROLE_NAME)
            if umbrella is None:
                reports.append(f"{guild.name}: missing {POD_DRAFTERS_ROLE_NAME} — run after the startup reconcile")
                continue
            holders_by_role: dict[str, set[discord.Member]] = {}
            for spec in PING_ROLES:
                if spec.name == POD_DRAFTERS_ROLE_NAME:
                    continue
                role = find_role(guild, spec.name)
                if role is not None:
                    holders_by_role[spec.name] = set(role.members)
            holders = set().union(*holders_by_role.values()) if holders_by_role else set()
            newly_granted: set[discord.Member] = set()
            for member in holders:
                if await grant_role(member, umbrella):
                    newly_granted.add(member)
            by_role = ", ".join(
                f"{name} {len(newly_granted & members)}"
                for name, members in holders_by_role.items()
                if newly_granted & members
            )
            breakdown = f" ({by_role})" if by_role else ""
            reports.append(
                f"{guild.name}: granted {umbrella.name} to {len(newly_granted)} of {len(holders)} "
                f"pod-role members{breakdown}"
            )
        await ctx.send("\n".join(reports) if reports else "No guilds.")
