"""`!confirm` — say you are coming, in the pod's own thread.

Two jobs, both of which the roster card alone does badly. A player who knows at four o'clock that they are
playing at nine has no way to say so until the card posts, and a card that posted an hour ago is wherever
chat left it. So confirming also puts the card back where people can see it.

Someone who never signed up is recorded as coming rather than refused. Typing `!confirm` an hour before a
draft is a stronger statement of intent than a button pressed days ago, so it is taken at face value.

The caller's message is left up. Anything a player types around `!confirm` is their own words, and the card
lands under it either way.
"""
from __future__ import annotations

import asyncio
import contextlib
import logging
from datetime import datetime, timezone

import discord
from discord.ext import commands
from sqlalchemy import select

from bot import audit
from bot.database import SessionLocal
from bot.models import PodSignal, PodSignalMember
from bot.services.pod_drafts import load_event_id_by_thread_sync, load_event_socket_status_sync
from bot.services.pod_signals import RSVP_YES
from bot.tasks.pod_draft_reminder import refresh_or_repost_roster_reminder


MSG_CONFIRM_NOT_A_POD = "Run `!confirm` inside a pod draft thread."
MSG_CONFIRM_POD_STARTED = "This pod has already opened its lobby."

NOTICE_LIFETIME_S = 20
PRE_LOBBY_STATUSES = ("pending", "reminded")
CONFIRMED_REACTION = "✅"


log = logging.getLogger(__name__)


async def setup(bot: commands.Bot) -> None:
    @bot.command(name="confirm")
    async def confirm_cmd(ctx: commands.Context) -> None:
        """Record the caller as coming to the pod this thread belongs to."""
        if not isinstance(ctx.channel, discord.Thread):
            await ctx.send(MSG_CONFIRM_NOT_A_POD, delete_after=NOTICE_LIFETIME_S)
            return
        event_id = await asyncio.to_thread(load_event_id_by_thread_sync, str(ctx.channel.id))
        if event_id is None:
            await ctx.send(MSG_CONFIRM_NOT_A_POD, delete_after=NOTICE_LIFETIME_S)
            return
        status = await asyncio.to_thread(load_event_socket_status_sync, event_id)
        if status not in PRE_LOBBY_STATUSES:
            await ctx.send(MSG_CONFIRM_POD_STARTED, delete_after=NOTICE_LIFETIME_S)
            return
        recorded = await asyncio.to_thread(
            confirm_seat_sync, event_id, str(ctx.author.id), ctx.author.display_name,
        )
        if not recorded:
            await ctx.send(MSG_CONFIRM_NOT_A_POD, delete_after=NOTICE_LIFETIME_S)
            return
        with contextlib.suppress(discord.HTTPException):
            await ctx.message.add_reaction(CONFIRMED_REACTION)
        await refresh_or_repost_roster_reminder(event_id)
        audit.event("pod_confirm", user_id=str(ctx.author.id), event_id=event_id)
        log.info(f"confirm: {ctx.author} confirmed for event {event_id}")


def confirm_seat_sync(event_id: str, discord_id: str, display_name: str) -> bool:
    """Stamp the caller as confirmed on this pod's roster, adding them if they never signed up.

    The stamp is only ever set once, so confirming twice does not move the time and the first answer stays
    the one on record. False when the pod has no signup roster, which is what a queue or poll pod is."""
    with SessionLocal() as session:
        signal = session.execute(
            select(PodSignal).where(PodSignal.event_id == event_id)
        ).scalar_one_or_none()
        if signal is None:
            return False
        member = session.execute(
            select(PodSignalMember).where(
                PodSignalMember.signal_id == signal.id,
                PodSignalMember.discord_user_id == discord_id,
            )
        ).scalar_one_or_none()
        if member is None:
            session.add(PodSignalMember(
                signal_id=signal.id, discord_user_id=discord_id, display_name=display_name,
                rsvp=RSVP_YES, confirmed_at=datetime.now(timezone.utc),
            ))
        else:
            member.rsvp = RSVP_YES
            member.display_name = display_name
            if member.confirmed_at is None:
                member.confirmed_at = datetime.now(timezone.utc)
        session.commit()
        return True
