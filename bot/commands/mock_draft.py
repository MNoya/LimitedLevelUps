"""/mock-draft — open an on-demand Draftmancer lobby for a set, with no rounds played.

Unlike pod drafts (scheduled through sesh, then run as a Swiss tournament), a mock draft is started
straight from the command: the bot opens a Draftmancer lobby, creates a thread, mirrors the lobby
live, and once the draft ends it records the seating + draft logs to the site. No ready windows are
required, no matches are paired. Anyone can run it; any registered set (including an unreleased one
like MSH) can be drafted.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

import discord
from discord import app_commands
from discord.ext import commands

from bot import audit
from bot.commands import descriptions as desc
from bot.commands.messages import (
    MSG_MOCK_ALREADY_ACTIVE,
    MSG_MOCK_NOT_TEXT_CHANNEL,
    MSG_MOCK_UNKNOWN_SET,
)
from bot.config import settings
from bot.database import SessionLocal
from bot.models import PodDraftEvent
from bot.services import pod_format
from bot.services.mock_lobby_card import build_mock_card
from bot.services.pod_active import ACTIVE_POD_MANAGERS
from bot.services.pod_drafts import draftmancer_url_for, pod_page_url, record_mock_event
from bot.services.pod_draft_manager import start_manager


log = logging.getLogger(__name__)


class MockDraft(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command(name="mock-draft", description=desc.MOCK_DRAFT)
    @app_commands.describe(set="Set or cube to draft; defaults to the current set")
    @app_commands.allowed_contexts(guilds=True, dms=False, private_channels=False)
    @app_commands.allowed_installs(guilds=True, users=False)
    async def mock_draft(self, interaction: discord.Interaction, set: str | None = None) -> None:
        code = pod_format.resolve_format_code(set)
        if code is None:
            await interaction.response.send_message(
                MSG_MOCK_UNKNOWN_SET.format(code=(set or "").strip().upper()), ephemeral=True,
            )
            return

        channel = interaction.channel
        if isinstance(channel, discord.Thread):
            channel = channel.parent
        if not isinstance(channel, discord.TextChannel):
            await interaction.response.send_message(MSG_MOCK_NOT_TEXT_CHANNEL, ephemeral=True)
            return

        running = next((m for m in ACTIVE_POD_MANAGERS.values() if m.kind == "mock"), None)
        if running is not None:
            await interaction.response.send_message(
                MSG_MOCK_ALREADY_ACTIVE.format(thread=f"<#{running.thread_id}>"), ephemeral=True,
            )
            return

        await interaction.response.defer(ephemeral=True, thinking=True)
        audit.event("mock_draft_invoked", user_id=str(interaction.user.id), set_code=code)

        with SessionLocal() as session:
            event = record_mock_event(
                session, set_code=code, event_time=datetime.now(timezone.utc), discord_thread_id="pending",
            )
            event_id, session_id, event_name = event.id, event.draftmancer_session, event.name
            session.commit()

        draftmancer_url = draftmancer_url_for(session_id)
        embed, view = build_mock_card(
            event_name=event_name, set_code=code, session_id=session_id, session_url=draftmancer_url,
            site_url=pod_page_url(event_name), roster=[],
            max_players=settings.pod_draft_max_players,
        )
        starter = await channel.send(embed=embed, view=view)
        thread = await starter.create_thread(name=event_name, reason=f"Mock draft started by {interaction.user}")

        with SessionLocal() as session:
            session.get(PodDraftEvent, event_id).discord_thread_id = str(thread.id)
            session.commit()

        await start_manager(
            self.bot, event_id, session_id, thread.id, code, 0,
            event_name=event_name, draftmancer_url=draftmancer_url, kind="mock",
        )

        log.info(f"mock-draft: {interaction.user} opened {session_id} (event_id={event_id})")
        await interaction.delete_original_response()

    @mock_draft.autocomplete("set")
    async def _set_autocomplete(
        self, interaction: discord.Interaction, current: str,
    ) -> list[app_commands.Choice[str]]:
        cur = current.strip().lower()
        choices = pod_format.format_choices()
        matched = [(label, code) for label, code in choices if cur in label.lower() or cur in code.lower()]
        return [app_commands.Choice(name=label, value=code) for label, code in matched[:25]]


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(MockDraft(bot))
