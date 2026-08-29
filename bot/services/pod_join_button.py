"""The Join Draft button on a lobby-open post. Clicking returns an ephemeral Draftmancer link with the
clicker's Arena name pre-filled, so pairing resolves with no manual rename. One registration dispatches
every lobby (the session id rides in the custom_id) and the button keeps working after a restart. The
shared session link stays in the post for anyone without a linked Arena name.
"""
from __future__ import annotations

import asyncio
import logging
import re

import discord
from discord import ui
from sqlalchemy import select

from bot import audit, emojis
from bot.commands.messages import (
    MSG_JOIN_DRAFT_BUTTON,
    MSG_LINK_ARENA_PROMPT,
    MSG_TABLE_FULL_SEATED,
    MSG_TABLE_SEATED,
)
from bot.database import SessionLocal
from bot.discord_helpers import run_detached
from bot.models import PodDraftEvent
from bot.services.ping_roles import build_link_arena_view, format_join_line, send_mock_welcome_card
from bot.services.pod_active import ACTIVE_POD_MANAGERS
from bot.services.pod_drafts import player_arena_handle
from bot.services.pod_link_dm import pod_thread_link
from bot.services.pod_staging import (
    SeatOffer,
    confirm_seat_sync,
    pod_is_numbered,
    take_seat_sync,
)


JOIN_BUTTON_PREFIX = "podjoin"
MOCK_JOIN_BUTTON_PREFIX = "mockjoin"


log = logging.getLogger(__name__)


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
        """The link comes back on one database round trip, and everything the press also means happens
        after it. A player pressing this at ten to nine is asking for one thing, and the seat write, the
        confirmation and the thread membership are all things the room needs rather than things they are
        waiting on.

        A slot running one table needs no routing at all, and says so in the pod's own name: a pod is
        unnumbered until a second one opens. Only a numbered pod pays for resolving which table has room,
        and that press acknowledges first so the work never races the three seconds Discord allows."""
        handle, event_id, pod_name = await asyncio.to_thread(
            _join_context, self.session_id, str(interaction.user.id),
        )
        if handle is None:
            await interaction.response.send_message(
                MSG_LINK_ARENA_PROMPT, view=build_link_arena_view(), ephemeral=True,
            )
            _record_press(interaction, event_id, self.session_id, outcome="unlinked")
            return
        if event_id is None or not pod_is_numbered(pod_name):
            await interaction.response.send_message(
                format_join_line(self.session_id, handle), ephemeral=True,
            )
            run_detached(
                _seat_and_admit(interaction, event_id, self.session_id),
                f"the Join Draft seat on {self.session_id}",
            )
            _record_press(interaction, event_id, self.session_id, outcome="linked")
            return
        await interaction.response.defer(ephemeral=True, thinking=True)
        offer = await asyncio.to_thread(
            take_seat_sync, self.session_id, str(interaction.user.id), interaction.user.display_name,
        )
        session_id = offer.pod.session_id if offer is not None else self.session_id
        await interaction.followup.send(
            _join_answer(offer, session_id, handle, interaction.guild_id), ephemeral=True,
        )
        _record_press(
            interaction, offer.pod.event_id if offer else event_id, session_id,
            outcome="switched" if offer and offer.switched else "routed",
            table=offer.pod.index if offer else None,
        )
        await _admit_clicker_to_thread(interaction, session_id)


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


def _join_answer(
    offer: SeatOffer | None, session_id: str, handle: str, guild_id: int | None,
) -> str:
    """The presser's private answer. A slot running one table hands over the link and says nothing more.
    A slot running several names the table first, and says which one filled up when the press lands
    somewhere other than the room it was made in, so nobody reads the switch as the bot losing track."""
    join_line = format_join_line(session_id, handle)
    if offer is None or guild_id is None or offer.pod.index <= 1 and not offer.switched:
        return join_line
    if offer.switched and offer.pod.index > 1:
        seated = MSG_TABLE_FULL_SEATED.format(full=offer.pod.index - 1, index=offer.pod.index)
    else:
        seated = MSG_TABLE_SEATED.format(index=offer.pod.index)
    return f"{seated} {pod_thread_link(guild_id, offer.pod)}\n{join_line}"


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


def _join_context(session_id: str, discord_id: str) -> tuple[str | None, str | None, str]:
    """Everything the answer needs, on one connection: the presser's Arena handle, and the id and name of
    the pod behind the session. The name is what says whether the slot ever split."""
    with SessionLocal() as session:
        handle = player_arena_handle(session, discord_id)
        event = session.execute(
            select(PodDraftEvent.id, PodDraftEvent.name)
            .where(PodDraftEvent.draftmancer_session == session_id)
        ).first()
    return handle, (event[0] if event else None), (event[1] if event else "")


async def _seat_and_admit(
    interaction: discord.Interaction, event_id: str | None, session_id: str,
) -> None:
    """The rest of what pressing Join Draft means, run once the presser already has their link. The seat
    is recorded and the thread opened for them; neither is something they are waiting to read.

    A session no pod owns still admits the presser, since a mock draft has a thread and no event."""
    if event_id is not None:
        await asyncio.to_thread(
            confirm_seat_sync, event_id, str(interaction.user.id), interaction.user.display_name,
        )
    await _admit_clicker_to_thread(interaction, session_id)


def _record_press(
    interaction: discord.Interaction, event_id: str | None, session_id: str, *,
    outcome: str, table: int | None = None,
) -> None:
    """Leave a record that somebody pressed Join Draft, and what it got them.

    Two writes because they survive different things. The audit line is structured and queryable but
    lives on a filesystem Railway throws away on redeploy; the log line goes to stdout, which Railway
    keeps per deployment and can still be read back weeks later.

    `outcome` says which of the four a press was: unlinked and sent to link Arena, linked on a pod
    running one table, routed to a table on a pod running several, or switched to a different table than
    the one the button was pressed in."""
    audit.event(
        "pod_join_draft", user_id=str(interaction.user.id), event_id=event_id,
        session_id=session_id, outcome=outcome, table=table,
    )
    log.info(
        f"join-draft: {interaction.user} pressed on {session_id} event={event_id} "
        f"outcome={outcome} table={table}"
    )
