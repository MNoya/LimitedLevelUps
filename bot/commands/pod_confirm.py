"""`!confirm` — say you are coming, in the pod's own thread.

Two jobs, both of which the roster card alone does badly. A player who knows at four o'clock that they are
playing at nine has no way to say so until the card posts, and a card that posted an hour ago is wherever
chat left it. So confirming also puts the card back where people can see it.

Someone who never signed up is recorded as coming rather than refused. Typing `!confirm` an hour before a
draft is a stronger statement of intent than a button pressed days ago, so it is taken at face value.

The caller's message is left up. Anything a player types around `!confirm` is their own words, and the card
lands under it either way.

An Organizer gets the roster read back and no seat: for them this is a chasing tool, not a signup.
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
from bot.commands.messages import (
    MSG_CONFIRM_NOT_A_POD,
    MSG_CONFIRM_POD_STARTED,
    MSG_CONFIRM_REPLY,
    MSG_CONFIRM_REPLY_ALL,
    MSG_CONFIRM_REPLY_CARD,
)
from bot.database import SessionLocal
from bot.models import PodSignal, PodSignalMember
from bot.services.pod_confirm import (
    Attendance,
    attendance_for_event_sync,
    roster_attendance_for_event_sync,
)
from bot.services.pod_drafts import load_event_id_by_thread_sync, load_event_socket_status_sync
from bot.services.pod_signals import RSVP_YES
from bot.services.pod_tournament import is_pod_organizer
from bot.tasks.pod_draft_reminder import refresh_or_repost_roster_reminder


NOTICE_LIFETIME_S = 20
PRE_LOBBY_STATUSES = ("pending", "reminded")


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
        if await is_pod_organizer(ctx.bot, ctx.author):
            await _organizer_roster_reply(ctx, event_id)
            return
        recorded = await asyncio.to_thread(
            confirm_seat_sync, event_id, str(ctx.author.id), ctx.author.display_name,
        )
        if not recorded:
            await ctx.send(MSG_CONFIRM_NOT_A_POD, delete_after=NOTICE_LIFETIME_S)
            return
        with contextlib.suppress(discord.HTTPException):
            await _replace_standing_reply(ctx, event_id)
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


async def _organizer_roster_reply(ctx: commands.Context, event_id: str) -> None:
    """Reads the roster back without seating the caller on it"""
    attendance = await asyncio.to_thread(roster_attendance_for_event_sync, event_id)
    if attendance is None:
        await ctx.send(MSG_CONFIRM_NOT_A_POD, delete_after=NOTICE_LIFETIME_S)
        return
    with contextlib.suppress(discord.HTTPException):
        await _replace_standing_reply(ctx, event_id, attendance)
    await refresh_or_repost_roster_reminder(event_id)
    log.info(f"confirm: {ctx.author} read the roster for event {event_id}")


_standing_replies: dict[str, int] = {}


async def _replace_standing_reply(
    ctx: commands.Context, event_id: str, attendance: Attendance | None = None,
) -> None:
    """One standing reply per pod, addressed to whoever confirmed last. Every confirm answers the same
    question, so the previous answer is already wrong. The id rather than the message, which would pin a
    whole Message per pod for the life of the process. Held in memory: a restart costs one duplicate."""
    previous = _standing_replies.pop(event_id, None)
    if previous is not None:
        with contextlib.suppress(discord.HTTPException):
            await ctx.channel.get_partial_message(previous).delete()
    reply = await ctx.reply(
        await _standing_reply(ctx, event_id, attendance), suppress_embeds=True,
        allowed_mentions=discord.AllowedMentions.none(),
    )
    _standing_replies[event_id] = reply.id


async def _standing_reply(
    ctx: commands.Context, event_id: str, attendance: Attendance | None = None,
) -> str:
    """What the room still needs, said back to whoever just confirmed.

    The press used to be answered with a tick on their own message, which said nothing about the pod and
    invited everyone else to click the same tick expecting it to count them. This names the players still
    outstanding instead, and points at the card, so the reply does the chasing the tick could not."""
    if attendance is None:
        attendance = await asyncio.to_thread(attendance_for_event_sync, event_id)
    if attendance.yes:
        lead = MSG_CONFIRM_REPLY.format(
            confirmed=len(attendance.confirmed), pending=len(attendance.yes),
            names=", ".join(f"**{name}**" for name in attendance.yes),
        )
    else:
        lead = MSG_CONFIRM_REPLY_ALL.format(confirmed=len(attendance.confirmed))
    card_url = await asyncio.to_thread(_confirm_card_url_sync, event_id, ctx.guild.id if ctx.guild else 0)
    if card_url is None:
        return lead
    return f"{lead}\n{MSG_CONFIRM_REPLY_CARD.format(url=card_url)}"


def _confirm_card_url_sync(event_id: str, guild_id: int) -> str | None:
    """A jump link to the roster card this pod is confirming against, or None when it has no card to
    point at, which is every pod whose card predates a restart."""
    with SessionLocal() as session:
        signal = session.execute(
            select(PodSignal.confirm_card_message_id, PodSignal.discussion_thread_id)
            .where(PodSignal.event_id == event_id)
        ).first()
        if signal is None:
            return None
        message_id, thread_id = signal
        if not message_id or not thread_id:
            return None
        return f"https://discord.com/channels/{guild_id}/{thread_id}/{message_id}"
