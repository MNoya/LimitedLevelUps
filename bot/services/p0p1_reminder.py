"""The T-1 day nudge for a P0P1 contest: ping everyone holding a P0P1 identity with no picks in it, through the
shared ``Reminder`` role.

Identity comes from ``auth.identities``, not ``players`` — most voters signed in on the website and never
joined the leaderboard, so it is the only place their Discord id exists.
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass

import discord
from sqlalchemy import text
from sqlalchemy.exc import ProgrammingError

from bot.config import PRODUCTION_GUILD_ID
from bot.database import SessionLocal
from bot.services import role_ping
from bot.services.ping_roles import P0P1_COLOR, P0P1_POLL_ROLE_NAME

log = logging.getLogger(__name__)

NON_VOTERS_SQL = text("""
    with known as (
        select user_id from p0p1_voters
        union
        select distinct user_id from p0p1_entries
    )
    select i.provider_id
    from known k
    join auth.identities i on i.user_id = k.user_id and i.provider = 'discord'
    where not exists (
        select 1 from p0p1_entries e
        where e.user_id = k.user_id and e.set_code = :set_code
    )
""")

ALL_VOTERS_SQL = text("""
    with known as (
        select user_id from p0p1_voters
        union
        select distinct user_id from p0p1_entries
    )
    select i.provider_id
    from known k
    join auth.identities i on i.user_id = k.user_id and i.provider = 'discord'
""")

LOCAL_NON_VOTERS_SQL = text("select discord_id from players where discord_id is not null")

VOTER_COUNT_SQL = text("select count(distinct user_id) from p0p1_entries where set_code = :set_code")

SOURCE_AUTH = "auth"
SOURCE_PLAYERS = "players"


@dataclass(frozen=True)
class ReminderOutcome:
    """``absent`` are voters not in the guild, whom no notification surface can reach. ``source`` is
    ``SOURCE_PLAYERS`` when the dev fallback supplied the audience, so it is not the real one."""
    targeted: int
    pinged: int
    absent: int
    source: str
    restricted: bool


@dataclass(frozen=True)
class AudienceIds:
    discord_ids: list[str]
    source: str


def non_voter_discord_ids_sync(set_code: str) -> AudienceIds:
    """Supabase owns ``auth``, so no developer database has it. Falling back to every local player keeps the
    role swap exercisable off production; nothing links a ``players`` row to a P0P1 identity, so that
    audience excludes nobody and is labelled ``SOURCE_PLAYERS`` instead of passing as the real list."""
    with SessionLocal() as session:
        try:
            rows = session.execute(NON_VOTERS_SQL, {"set_code": set_code.upper()}).scalars().all()
            return AudienceIds([str(row) for row in rows], SOURCE_AUTH)
        except ProgrammingError:
            session.rollback()
            log.warning(f"p0p1-reminder: no auth schema, falling back to every {SOURCE_PLAYERS} row")
            rows = session.execute(LOCAL_NON_VOTERS_SQL).scalars().all()
            return AudienceIds([str(row) for row in rows], SOURCE_PLAYERS)


def all_voter_discord_ids_sync() -> AudienceIds:
    """Every Discord id that has ever filed a P0P1 ballot, across all contests. Same ``auth`` dependency and
    every-local-player fallback as the non-voter read, so it is exercisable off production."""
    with SessionLocal() as session:
        try:
            rows = session.execute(ALL_VOTERS_SQL).scalars().all()
            return AudienceIds([str(row) for row in rows], SOURCE_AUTH)
        except ProgrammingError:
            session.rollback()
            log.warning(f"p0p1-poll: no auth schema, falling back to every {SOURCE_PLAYERS} row")
            rows = session.execute(LOCAL_NON_VOTERS_SQL).scalars().all()
            return AudienceIds([str(row) for row in rows], SOURCE_PLAYERS)


def voter_count_sync(set_code: str) -> int:
    with SessionLocal() as session:
        return session.execute(VOTER_COUNT_SQL, {"set_code": set_code.upper()}).scalar() or 0


async def ping_non_voters(
    guild: discord.Guild, role: discord.Role, set_code: str, build_post,
    *, restrict_to: discord.Member | None = None,
) -> ReminderOutcome:
    """The non-voter list is read immediately before the grants, so a ballot filed during the run is not
    pinged for being unfilled."""
    non_voters = await asyncio.to_thread(non_voter_discord_ids_sync, set_code)
    discord_ids = role_ping.audience(guild, non_voters.discord_ids, restrict_to)
    pinged, members = await role_ping.ping_audience(guild, role, discord_ids, build_post)

    outcome = ReminderOutcome(
        targeted=len(discord_ids), pinged=pinged, absent=len(discord_ids) - len(members),
        source=non_voters.source, restricted=guild.id != PRODUCTION_GUILD_ID,
    )
    log.info(f"p0p1-reminder: {set_code} pinged {outcome.pinged}/{outcome.targeted} from {outcome.source}, "
             f"{outcome.absent} not in guild")
    log.info(f"p0p1-reminder: {set_code} pinged {', '.join(str(member) for member in members) or 'nobody'}")
    return outcome


async def poll_role(guild: discord.Guild) -> discord.Role | None:
    """The transient P0P1 role the challenger poll pings, granted to past voters and stripped after the send"""
    return await role_ping.ensure_ping_role(guild, P0P1_POLL_ROLE_NAME, P0P1_COLOR)
