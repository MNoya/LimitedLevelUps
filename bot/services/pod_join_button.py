"""The Join Draft button on a lobby-open post. Clicking returns an ephemeral Draftmancer link with the
clicker's Arena name pre-filled, so pairing resolves with no manual rename. One registration dispatches
every lobby (the session id rides in the custom_id) and the button keeps working after a restart. The
shared session link stays in the post for anyone without a linked Arena name.
"""
from __future__ import annotations

import asyncio
import re

import discord
from discord import ui

from bot import emojis
from bot.commands.messages import MSG_JOIN_DRAFT_BUTTON, MSG_LINK_ARENA_PROMPT
from bot.database import SessionLocal
from bot.services.ping_roles import build_link_arena_view, format_join_line, send_mock_welcome_card
from bot.services.pod_active import ACTIVE_POD_MANAGERS
from bot.services.pod_drafts import player_arena_handle


JOIN_BUTTON_PREFIX = "podjoin"
MOCK_JOIN_BUTTON_PREFIX = "mockjoin"


class JoinDraftButton(ui.DynamicItem[ui.Button], template=rf"{JOIN_BUTTON_PREFIX}:(?P<session_id>.+)"):
    def __init__(self, session_id: str) -> None:
        super().__init__(ui.Button(
            style=discord.ButtonStyle.success, label=MSG_JOIN_DRAFT_BUTTON,
            emoji=emojis.get("draftmancer") or None, custom_id=f"{JOIN_BUTTON_PREFIX}:{session_id}",
        ))
        self.session_id = session_id

    @classmethod
    async def from_custom_id(cls, interaction: discord.Interaction, item: ui.Button, match: re.Match):
        return cls(match["session_id"])

    async def callback(self, interaction: discord.Interaction) -> None:
        handle = await asyncio.to_thread(_arena_handle_for, str(interaction.user.id))
        if handle is None:
            await interaction.response.send_message(
                MSG_LINK_ARENA_PROMPT, view=build_link_arena_view(), ephemeral=True,
            )
            return
        await interaction.response.send_message(
            format_join_line(self.session_id, handle), ephemeral=True,
        )
        await _admit_clicker_to_thread(interaction, self.session_id)


class MockJoinDraftButton(
    ui.DynamicItem[ui.Button], template=rf"{MOCK_JOIN_BUTTON_PREFIX}:(?P<session_id>.+)",
):
    """Mock-draft variant. A mock plays no Arena games, so the pre-filled name is the clicker's Discord
    display name, which `player_for_name` already resolves. Nobody is asked to link an Arena handle, and
    the click also admits the clicker to the draft thread."""

    def __init__(self, session_id: str) -> None:
        super().__init__(ui.Button(
            style=discord.ButtonStyle.success, label=MSG_JOIN_DRAFT_BUTTON,
            emoji=emojis.get("draftmancer") or None,
            custom_id=f"{MOCK_JOIN_BUTTON_PREFIX}:{session_id}",
        ))
        self.session_id = session_id

    @classmethod
    async def from_custom_id(cls, interaction: discord.Interaction, item: ui.Button, match: re.Match):
        return cls(match["session_id"])

    async def callback(self, interaction: discord.Interaction) -> None:
        join_line = format_join_line(self.session_id, interaction.user.display_name, arena=False)
        await interaction.response.defer(ephemeral=True)
        first_pod, holds_mock_ping = await _admit_clicker_to_thread(
            interaction, self.session_id, mock_only=True,
        )
        if first_pod:
            await send_mock_welcome_card(
                interaction, join_line=join_line, holds_mock_ping=holds_mock_ping,
            )
            return
        await interaction.followup.send(join_line, ephemeral=True)


def build_join_view(session_id: str) -> ui.View:
    view = ui.View(timeout=None)
    view.add_item(JoinDraftButton(session_id))
    return view


def build_mock_join_view(session_id: str) -> ui.View:
    view = ui.View(timeout=None)
    view.add_item(MockJoinDraftButton(session_id))
    return view


async def _admit_clicker_to_thread(
    interaction: discord.Interaction, session_id: str, *, mock_only: bool = False,
) -> tuple[bool, bool]:
    """Clicking Join Draft is joining the draft, so it puts the clicker in the thread right away instead of
    waiting for them to turn up in the Draftmancer lobby. Returns the manager's (first pod, holds the mock
    ping) pair. The manager is reached through the registry rather than an import: it renders the card this
    button rides on, so importing it here would cycle."""
    member = interaction.user
    if not isinstance(member, discord.Member):
        return False, False
    for manager in ACTIVE_POD_MANAGERS.values():
        if manager.session_id != session_id:
            continue
        if mock_only and manager.kind != "mock":
            continue
        return await manager.admit_to_thread(member)
    return False, False


def _arena_handle_for(discord_id: str) -> str | None:
    with SessionLocal() as session:
        return player_arena_handle(session, discord_id)
