"""Lobby-open DM carrying the personalized Draftmancer link. A DM is per-user, so it delivers the
pre-filled link as a one-click open where the in-thread Join Draft button needs two. Sent to opted-in Yes
and Maybe RSVPs when a lobby opens; the in-thread button stays as the fallback for anyone the DM can't
reach (DMs closed, drop-ins, guests). Notification changes go through `/roles`, so the only button a DM
ever carries is Link Arena. Reuses the send-with-Forbidden-skip and batching shape the tournament pairing
DMs use.
"""
from __future__ import annotations

import asyncio
import logging
import re

import discord
from discord import ui

from bot import emojis
from bot.commands.messages import (
    MSG_DM_LOBBY_HEADER,
    MSG_DM_LOBBY_LINK,
    MSG_DM_LOBBY_LINK_UNLINKED,
    MSG_DM_NOTIFY_HINT,
    MSG_DM_PREF_OFF_BODY,
    MSG_DM_PREF_OFF_TITLE,
    MSG_DM_PREF_ON_BODY,
    MSG_DM_PREF_ON_TITLE,
    MSG_DM_RSVP_MAYBE,
    MSG_DM_RSVP_YES,
)
from bot.database import SessionLocal
from bot.discord_helpers import BLANK_LINE, fetch_dm_user
from bot.services.ping_roles import build_link_arena_modal, format_join_line
from bot.services.pod_drafts import dm_draft_link_enabled, player_arena_handle


log = logging.getLogger(__name__)

DM_BATCH_SIZE = 8
DM_BATCH_DELAY = 1.0
LINK_ARENA_PREFIX = "poddmlinkarena"


async def try_dm(bot, discord_id: str, body: str, view: discord.ui.View | None = None) -> bool:
    """Send a DM, swallowing the closed-DMs case. Returns whether it landed — the player most likely to
    have DMs off is the one a time-sensitive nudge can't reach, so callers surface that where it matters."""
    try:
        user = await fetch_dm_user(bot, discord_id)
        if user is None:
            return False
        await user.send(body, view=view)
        return True
    except discord.Forbidden:
        log.info(f"[link-dm] DMs closed for {discord_id}")
        return False
    except discord.HTTPException:
        log.warning(f"[link-dm] send failed for {discord_id}", exc_info=True)
        return False


def format_thread_ref(thread) -> str:
    """The event thread as a masked link plus the manat lookup emoji."""
    emoji = emojis.get("manat")
    link = f"[**{thread.name}**]({thread.jump_url})"
    return f"{link} {emoji}" if emoji else link


def build_link_dm(
    *, session_id: str, thread_ref: str, arena_name: str | None, rsvp: str,
) -> tuple[str, discord.ui.View]:
    """The DM body and its button view for one recipient. A linked recipient gets a personalized inline
    **Your Link:** line, the join CTA, and the notification toggle; an unlinked recipient gets no link at
    all, only a Link Arena button that produces the personal link in place once clicked. `thread_ref` is
    the masked event-thread link from format_thread_ref."""
    rsvp_template = MSG_DM_RSVP_YES if rsvp == "yes" else MSG_DM_RSVP_MAYBE
    rsvp_line = rsvp_template.format(thread=thread_ref)
    if arena_name:
        link_body = MSG_DM_LOBBY_LINK.format(rsvp=rsvp_line, join_line=format_join_line(session_id, arena_name))
        body = f"{link_body}\n\n{MSG_DM_NOTIFY_HINT}"
    else:
        body = f"{MSG_DM_LOBBY_LINK_UNLINKED.format(rsvp=rsvp_line)}\n{BLANK_LINE}"
    return body, _link_dm_view(session_id, arena_name)


async def send_lobby_link_dms(
    bot, *, session_id: str, thread, recipients: list[tuple[str, str, str]],
) -> int:
    """DM the personalized link to opted-in Yes/Maybe recipients. `recipients` is (discord_id,
    display_name, rsvp); rsvp is 'yes' or 'maybe'. Returns the number delivered."""
    resolved = await asyncio.to_thread(_resolve_recipients, recipients)
    if not resolved:
        return 0
    thread_ref = format_thread_ref(thread)
    sent = 0
    for start in range(0, len(resolved), DM_BATCH_SIZE):
        batch = resolved[start:start + DM_BATCH_SIZE]
        for discord_id, arena_name, rsvp in batch:
            body, view = build_link_dm(
                session_id=session_id, thread_ref=thread_ref, arena_name=arena_name, rsvp=rsvp,
            )
            if await try_dm(bot, discord_id, body, view):
                sent += 1
        if start + DM_BATCH_SIZE < len(resolved):
            await asyncio.sleep(DM_BATCH_DELAY)
    log.info(f"[link-dm] lobby {session_id}: sent {sent}/{len(resolved)} link DMs")
    return sent


def dm_pref_embed(enabled: bool) -> discord.Embed:
    """Confirms a Draft DMs toggle, shared by the in-DM button and the /roles panel toggle."""
    if enabled:
        return discord.Embed(
            title=MSG_DM_PREF_ON_TITLE, description=MSG_DM_PREF_ON_BODY, color=discord.Color.green(),
        )
    return discord.Embed(
        title=MSG_DM_PREF_OFF_TITLE, description=MSG_DM_PREF_OFF_BODY, color=discord.Color.greyple(),
    )


class DmLinkArenaButton(ui.DynamicItem[ui.Button], template=rf"{LINK_ARENA_PREFIX}:(?P<session_id>.+)"):
    """Link Arena inside a lobby DM. On a successful link it rewrites this DM in place, so the personal
    link arrives with no extra message and no in-channel announcement. The session id rides in the
    custom_id, so it works with or without a live lobby and after a restart."""

    def __init__(self, session_id: str) -> None:
        super().__init__(ui.Button(
            style=discord.ButtonStyle.primary, label="Link Arena", emoji=emojis.get("mtga") or None,
            custom_id=f"{LINK_ARENA_PREFIX}:{session_id}",
        ))
        self.session_id = session_id

    @classmethod
    async def from_custom_id(cls, interaction: discord.Interaction, item: ui.Button, match: re.Match):
        return cls(match["session_id"])

    async def callback(self, interaction: discord.Interaction) -> None:
        session_id = self.session_id
        message = interaction.message

        async def after_link(inner: discord.Interaction, arena_name: str) -> None:
            await inner.response.defer()
            await message.edit(
                content=_relink_content(message.content, session_id, arena_name),
                view=_link_dm_view(session_id, arena_name),
            )

        await interaction.response.send_modal(build_link_arena_modal(after_link=after_link))


def _link_dm_view(session_id: str, arena_name: str | None) -> discord.ui.View | None:
    if arena_name:
        return None
    view = discord.ui.View(timeout=None)
    view.add_item(DmLinkArenaButton(session_id))
    return view


def _relink_content(content: str, session_id: str, arena_name: str) -> str:
    """Rewrite an unlinked lobby DM into its linked form after an in-place Arena link: keep the header
    and the recipient's reply line, then append the join line so the result matches the body a linked
    recipient would have gotten. The reply line is block 1 in every lobby DM."""
    reply_line = content.split("\n\n")[1]
    return "\n\n".join(
        [MSG_DM_LOBBY_HEADER, reply_line, format_join_line(session_id, arena_name), MSG_DM_NOTIFY_HINT]
    )


def _resolve_recipients(recipients: list[tuple[str, str, str]]) -> list[tuple[str, str | None, str]]:
    """Drop opted-out players and duplicates, attach each remaining player's Arena handle. One session,
    off the event loop."""
    resolved: list[tuple[str, str | None, str]] = []
    seen: set[str] = set()
    with SessionLocal() as session:
        for discord_id, _name, rsvp in recipients:
            if discord_id in seen:
                continue
            seen.add(discord_id)
            if not dm_draft_link_enabled(session, discord_id):
                continue
            resolved.append((discord_id, player_arena_handle(session, discord_id), rsvp))
    return resolved


