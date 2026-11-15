"""One Organizer joins each pod thread, taking turns in a fixed order keyed on how many pods came before"""
from __future__ import annotations

import asyncio
import logging
from collections.abc import Sequence

import discord
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from bot.database import SessionLocal
from bot.models import PodDraftEvent
from bot.services.pod_roles import find_role
from bot.services.pod_schedule import ORGANIZER_ROLE_NAME

log = logging.getLogger(__name__)


async def add_organizer_on_duty(thread: discord.Thread, event_id: str) -> None:
    role = find_role(thread.guild, ORGANIZER_ROLE_NAME)
    if role is None:
        return
    organizers = [member for member in role.members if not member.bot]
    if not organizers:
        return
    pod_number = await asyncio.to_thread(_pod_number_sync, event_id)
    organizer = organizer_on_duty(organizers, pod_number)
    try:
        await thread.add_user(organizer)
    except discord.HTTPException:
        log.warning(f"could not add organizer {organizer.id} to pod thread {thread.id}", exc_info=True)


def organizer_on_duty(organizers: Sequence[discord.Member], pod_number: int) -> discord.Member:
    in_turn_order = sorted(organizers, key=lambda member: member.id)
    return in_turn_order[pod_number % len(in_turn_order)]


def pod_number(session: Session, event_id: str) -> int:
    created_at = select(PodDraftEvent.created_at).where(PodDraftEvent.id == event_id).scalar_subquery()
    earlier = select(func.count()).select_from(PodDraftEvent).where(PodDraftEvent.created_at < created_at)
    return session.scalar(earlier) or 0


def _pod_number_sync(event_id: str) -> int:
    with SessionLocal() as session:
        return pod_number(session, event_id)
