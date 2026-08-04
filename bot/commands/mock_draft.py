"""/mock-draft — open an on-demand Draftmancer lobby for a set, with no rounds played.

Unlike pod drafts (scheduled through sesh, then run as a Swiss tournament), a mock draft is started
straight from the command: the bot opens a Draftmancer lobby, creates a thread, mirrors the lobby
live, and once the draft ends it records the seating + draft logs to the site. No ready windows are
required, no matches are paired. Anyone can run it; any registered set (including an unreleased one
like MSH) can be drafted.

`!mock` reposts the open lobby's card at the bottom of the channel, for when chat buries it.

A lobby is closed by anyone from the pod Settings panel, or by the manager's own inactivity timer once
nobody has entered or left the Draftmancer session for `pod_mock_inactivity_minutes`. Both delete the
event, so a channel never accumulates lobbies that were never drafted.
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
    MSG_MOCK_NONE_RUNNING,
    MSG_MOCK_NOT_TEXT_CHANNEL,
    MSG_MOCK_REPOST_FAILED,
    MSG_MOCK_UNKNOWN_SET,
)
from bot.config import settings
from bot.database import SessionLocal
from bot.models import PodDraftEvent
from bot.services import pod_format
from bot.services.mock_lobby_card import MOCK_CARD_PING, STATE_OPENING, build_mock_card
from bot.services.pod_active import ACTIVE_POD_MANAGERS
from bot.services.pod_drafts import (
    draftmancer_url_for,
    pod_page_url,
    record_mock_event,
    reroll_session_suffix,
)
from bot.services.pod_draft_manager import PodDraftManager, start_manager
from bot.services.pod_roles import role_mention
from bot.services.pod_schedule import MOCK_DRAFT_ROLE_NAME
from bot.sets import preview_set_code


log = logging.getLogger(__name__)


class MockDraft(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command(name="mock-draft", description=desc.MOCK_DRAFT)
    @app_commands.describe(set="Set or cube to draft; defaults to the set in preview")
    @app_commands.allowed_contexts(guilds=True, dms=False, private_channels=False)
    @app_commands.allowed_installs(guilds=True, users=False)
    async def mock_draft(self, interaction: discord.Interaction, set: str | None = None) -> None:
        code = pod_format.resolve_format_code(set or preview_set_code())
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

        await interaction.response.defer(ephemeral=True, thinking=True)
        audit.event("mock_draft_invoked", user_id=str(interaction.user.id), set_code=code)

        with SessionLocal() as session:
            event = record_mock_event(
                session, set_code=code, event_time=datetime.now(timezone.utc), discord_thread_id="pending",
            )
            event_id, session_id, event_name = event.id, event.draftmancer_session, event.name
            session.commit()

        content, embed, view = build_mock_card(
            event_name=event_name, set_code=code, session_id=session_id,
            session_url=draftmancer_url_for(session_id), site_url=pod_page_url(event_name), roster=[],
            max_players=settings.pod_draft_max_players, state=STATE_OPENING,
            role_mention=role_mention(interaction.guild, MOCK_DRAFT_ROLE_NAME),
        )
        starter = await channel.send(
            content=content, embed=embed, view=view, allowed_mentions=MOCK_CARD_PING,
        )
        thread = await starter.create_thread(name=event_name, reason=f"Mock draft started by {interaction.user}")

        with SessionLocal() as session:
            session.get(PodDraftEvent, event_id).discord_thread_id = str(thread.id)
            session.commit()

        manager = await _seat_bot_in_lobby(self.bot, event_id, session_id, thread.id, code, event_name)

        opened_session = manager.session_id if manager is not None else session_id
        log.info(f"mock-draft: {interaction.user} opened {opened_session} (event_id={event_id})")
        await interaction.delete_original_response()

    @mock_draft.autocomplete("set")
    async def _set_autocomplete(
        self, interaction: discord.Interaction, current: str,
    ) -> list[app_commands.Choice[str]]:
        cur = current.strip().lower()
        choices = pod_format.format_choices()
        matched = [(label, code) for label, code in choices if cur in label.lower() or cur in code.lower()]
        return [app_commands.Choice(name=label, value=code) for label, code in matched[:25]]


def latest_mock_manager() -> PodDraftManager | None:
    """The most recently opened live mock draft, or None. Several can run at once, so `!mock` bumps the
    newest. Ordered by each event's own start instant, since the restart sweep restores managers in no
    particular order."""
    latest = None
    for manager in ACTIVE_POD_MANAGERS.values():
        if manager.kind != "mock":
            continue
        if latest is None or _opened_after(manager, latest):
            latest = manager
    return latest


async def _delete_invocation(ctx: commands.Context) -> None:
    """Remove the `!mock` message once the card is up. The point of the command is to leave the card at
    the bottom of the channel, which the invocation sitting under it would undo."""
    try:
        await ctx.message.delete()
    except discord.HTTPException:
        log.info("mock: could not delete the invocation", exc_info=True)


def _opened_after(manager: PodDraftManager, other: PodDraftManager) -> bool:
    if manager.scheduled_start is None:
        return False
    if other.scheduled_start is None:
        return True
    return manager.scheduled_start >= other.scheduled_start


async def _seat_bot_in_lobby(
    bot: commands.Bot, event_id: str, session_id: str, thread_id: int, set_code: str, event_name: str,
) -> PodDraftManager | None:
    """Connect the bot to the Draftmancer session and hold it until ownership resolves. The card posts
    with no link until that lands, so the bot is always the first one in the lobby and stays its owner.
    A session it could not own is abandoned for a fresh one, since Draftmancer never hands ownership to
    a later arrival."""
    manager = await start_manager(
        bot, event_id, session_id, thread_id, set_code, 0,
        event_name=event_name, draftmancer_url=draftmancer_url_for(session_id), kind="mock",
    )
    if manager is None or await manager.await_ownership():
        return manager

    await manager.disconnect_safely()
    with SessionLocal() as session:
        fresh_session_id = reroll_session_suffix(session, event_id)
        session.commit()
    if fresh_session_id is None:
        return None
    log.warning(f"mock-draft: {session_id} could not be owned; reseating on {fresh_session_id}")
    manager = await start_manager(
        bot, event_id, fresh_session_id, thread_id, set_code, 0,
        event_name=event_name, draftmancer_url=draftmancer_url_for(fresh_session_id), kind="mock",
    )
    if manager is not None:
        await manager.await_ownership()
    return manager


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(MockDraft(bot))

    @bot.command(name="mock")
    async def mock(ctx: commands.Context) -> None:
        """Repost the newest open mock draft's card at the bottom of the channel, for a lobby that chat
        has buried. The thread and its anchor card stay put, an earlier repost is retired, and no role
        is pinged: the lobby was announced when it opened."""
        running = latest_mock_manager()
        if running is None:
            await ctx.send(MSG_MOCK_NONE_RUNNING)
            return
        reposted = await running.repost_mock_card()
        if reposted is None:
            await ctx.send(MSG_MOCK_REPOST_FAILED)
            return
        await _delete_invocation(ctx)
        log.info(f"mock: {ctx.author} reposted the card for event {running.event_id}")
