"""Persistence for /trophy self-reported draft results.

Showcase-only records: a player logs a draft they posted in trophy-hype to their profile,
trophy or not. Idempotent on (player_id, source_message_id) so re-running /trophy on the same
post edits the existing row instead of stacking duplicates. Only trophies rank the MTGO
flashback board; non-trophies enrich the profile deck log.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import Integer, case, delete, func, select
from sqlalchemy.orm import Session

from bot.models import MagicSet, Player, SelfReportedEvent
from bot.services.pod_backfill import RECORD_RE
from bot.slug import disambiguate_slug, slugify


def is_trophy_record(record: str | None) -> bool:
    """Whether a W-L string counts as a trophy: a Bo3 sweep (no losses) or a 7-win MTGA run."""
    if not record or not RECORD_RE.match(record):
        return False
    wins, losses = (int(n) for n in record.split("-"))
    return wins >= 7 or (wins > 0 and losses == 0)


def rank_self_reported_events(session: Session, set_code: str) -> list[tuple[Player, int, int]]:
    """Players who logged results for a set as (player, trophy_count, deck_count). Trophies rank the
    MTGO flashback board (most first), decks break ties; everyone who logged anything is included."""
    trophy_count = func.sum(case((SelfReportedEvent.is_trophy, 1), else_=0)).cast(Integer)
    deck_count = func.count(SelfReportedEvent.id)
    rows = session.execute(
        select(Player, trophy_count, deck_count)
        .join(SelfReportedEvent, SelfReportedEvent.player_id == Player.id)
        .where(func.upper(SelfReportedEvent.set_code) == set_code.upper())
        .group_by(Player.id)
        .order_by(trophy_count.desc(), deck_count.desc(), Player.display_name)
    ).all()
    return [(player, int(trophies), decks) for player, trophies, decks in rows]


def get_or_create_player(
    session: Session,
    *,
    discord_id: str,
    discord_username: str,
    display_name: str,
    avatar_hash: str | None,
) -> Player:
    """The Player for a Discord user, creating a lightweight 17lands-less row when none exists.

    /trophy is a valid first touch: a player can showcase results before ever linking 17lands.
    Mirrors the tokenless player pods create via /link-arena.
    """
    player = session.execute(
        select(Player).where(Player.discord_id == discord_id)
    ).scalar_one_or_none()
    if player is None:
        taken_slugs = set(session.execute(select(Player.slug)).scalars().all())
        player = Player(
            slug=disambiguate_slug(slugify(display_name), taken_slugs),
            discord_id=discord_id,
            discord_username=discord_username,
            display_name=display_name,
            avatar_hash=avatar_hash,
            active=True,
            leaderboard_opt_in=False,
        )
        session.add(player)
        session.flush()
    return player


def upsert_event(
    session: Session,
    *,
    player_id: str,
    set_code: str,
    record: str,
    is_trophy: bool,
    colors: str | None,
    platform: str,
    format: str | None,
    caption: str | None,
    screenshot_url: str | None,
    source_channel_id: str,
    source_message_id: str,
    source_url: str,
    reported_at: datetime | None = None,
) -> SelfReportedEvent:
    event = session.execute(
        select(SelfReportedEvent).where(
            SelfReportedEvent.player_id == player_id,
            SelfReportedEvent.source_message_id == source_message_id,
        )
    ).scalar_one_or_none()
    if event is None:
        event = SelfReportedEvent(player_id=player_id, source_message_id=source_message_id)
        session.add(event)
    event.set_code = set_code
    event.set_id = _resolve_set_id(session, set_code)
    event.record = record
    event.is_trophy = is_trophy
    event.colors = colors
    event.platform = platform
    event.format = format
    event.caption = caption
    event.screenshot_url = screenshot_url
    if reported_at is not None:
        event.reported_at = reported_at
    event.source_channel_id = source_channel_id
    event.source_url = source_url
    session.flush()
    return event


def delete_event(session: Session, *, discord_id: str, source_message_id: str) -> bool:
    owned_by_author = select(Player.id).where(Player.discord_id == discord_id)
    result = session.execute(
        delete(SelfReportedEvent).where(
            SelfReportedEvent.player_id.in_(owned_by_author),
            SelfReportedEvent.source_message_id == source_message_id,
        )
    )
    return result.rowcount > 0


def _resolve_set_id(session: Session, set_code: str) -> str | None:
    return session.execute(
        select(MagicSet.id).where(MagicSet.code == set_code)
    ).scalar_one_or_none()
