"""The pointer a Peasant Cube champion gets in #peasant-cube: the podium link plus their own trophy count."""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import date, datetime

import discord
from sqlalchemy import func, select

from bot.config import settings
from bot.database import SessionLocal
from bot.discord_helpers import channel_matching_name, ordinal
from bot.models import PodDraftEvent, PodDraftParticipant
from bot.services.pod_deck_color import format_deck_color_emojis
from bot.services.pod_drafts import POD_TROPHY_WINS, parse_record
from bot.services.pod_format import PEASANT_CODE, PEASANT_LABEL
from bot.sets import SetSeed, active_set_code, seed_for_code

log = logging.getLogger(__name__)

MSG_PEASANT_TROPHY = "🏆 {name} takes [__**{pod_name}**__]({podium_url}){colors}"
MSG_PEASANT_LIFETIME = "Their {nth} {cube} trophy"
MSG_PEASANT_FIRST_TROPHY = "Their **1st {cube} trophy!**"
MSG_PEASANT_SEASON = "{nth} this season"
MSG_PEASANT_FIRST_WITH_COLORS = "**1st** with these colors"
MSG_PEASANT_STREAK = "**{nth} in a row!** 🔥"


@dataclass(frozen=True)
class PeasantFinish:
    event_date: date
    record: str | None
    deck_colors: str | None

    @property
    def is_trophy(self) -> bool:
        wins, _ = parse_record(self.record)
        return wins >= POD_TROPHY_WINS

    @property
    def main_colors(self) -> str:
        return main_colors_of(self.deck_colors)


@dataclass(frozen=True)
class PeasantTrophyStats:
    lifetime: int
    season: int
    with_colors: int
    streak: int

    @property
    def on_streak(self) -> bool:
        return self.streak >= 2


@dataclass(frozen=True)
class PeasantChampion:
    name: str
    deck_colors: str | None
    stats: PeasantTrophyStats | None


async def post_peasant_trophies(
    guild: discord.Guild | None, event_id: str, pod_name: str | None, podium_url: str,
) -> None:
    if guild is None:
        return
    channel = channel_matching_name(guild, settings.pod_draft_peasant_chat_channel_name)
    if channel is None:
        log.info(f"[PEASANT] trophy.skip event={event_id} reason=no_channel")
        return
    champions = await asyncio.to_thread(load_peasant_champions_sync, event_id)
    for champion in champions:
        text = build_peasant_trophy_text(champion, pod_name or PEASANT_LABEL, podium_url)
        try:
            await channel.send(text, allowed_mentions=discord.AllowedMentions.none())
        except discord.HTTPException:
            log.warning(f"[PEASANT] trophy.post_error event={event_id} name={champion.name!r}", exc_info=True)


def is_peasant(set_code: str | None) -> bool:
    return (set_code or "").upper() == PEASANT_CODE


def build_peasant_trophy_text(champion: PeasantChampion, pod_name: str, podium_url: str) -> str:
    colors = format_deck_color_emojis(champion.deck_colors)
    headline = MSG_PEASANT_TROPHY.format(
        name=champion.name, pod_name=pod_name, podium_url=podium_url, colors=f" with {colors}" if colors else "",
    )
    if champion.stats is None:
        return headline
    if champion.stats.lifetime == 1:
        return f"{headline}\n-# {MSG_PEASANT_FIRST_TROPHY.format(cube=PEASANT_LABEL)}"
    clauses = stat_clauses(champion.stats, has_colors=bool(main_colors_of(champion.deck_colors)))
    stats_line = ", ".join(clauses)
    if not champion.stats.on_streak:
        stats_line += "!"
    return f"{headline}\n-# {stats_line}"


def stat_clauses(stats: PeasantTrophyStats, *, has_colors: bool) -> list[str]:
    clauses = [MSG_PEASANT_LIFETIME.format(nth=_bold_ordinal(stats.lifetime), cube=PEASANT_LABEL)]
    if stats.season < stats.lifetime:
        clauses.append(MSG_PEASANT_SEASON.format(nth=_bold_ordinal(stats.season)))
    if has_colors and stats.with_colors == 1 and stats.lifetime > 1:
        clauses.append(MSG_PEASANT_FIRST_WITH_COLORS)
    if stats.on_streak:
        clauses.append(MSG_PEASANT_STREAK.format(nth=ordinal(stats.streak)))
    return clauses


def trophy_stats(finishes: list[PeasantFinish], season: SetSeed | None) -> PeasantTrophyStats:
    latest = finishes[-1]
    lifetime = season_trophies = with_colors = 0
    for finish in finishes:
        if not finish.is_trophy:
            continue
        lifetime += 1
        if season is not None and _in_season(finish.event_date, season):
            season_trophies += 1
        if latest.main_colors and finish.main_colors == latest.main_colors:
            with_colors += 1
    streak = 0
    for finish in reversed(finishes):
        if not finish.is_trophy:
            break
        streak += 1
    return PeasantTrophyStats(lifetime=lifetime, season=season_trophies, with_colors=with_colors, streak=streak)


def load_peasant_champions_sync(event_id: str) -> list[PeasantChampion]:
    with SessionLocal() as session:
        event = session.get(PodDraftEvent, event_id)
        if event is None:
            return []
        participants = session.scalars(
            select(PodDraftParticipant).where(PodDraftParticipant.event_id == event_id)
        ).all()
        season = seed_for_code(active_set_code(event.event_time))
        champions = []
        for participant in participants:
            if parse_record(participant.record)[0] < POD_TROPHY_WINS:
                continue
            stats = None
            if participant.player_id is not None:
                finishes = _peasant_history(session, participant.player_id, event.event_time)
                stats = trophy_stats(finishes, season) if finishes else None
            champions.append(PeasantChampion(participant.display_name, participant.deck_colors, stats))
        return champions


def _peasant_history(session, player_id: str, through: datetime) -> list[PeasantFinish]:
    rows = session.execute(
        select(PodDraftEvent.event_date, PodDraftParticipant.record, PodDraftParticipant.deck_colors)
        .join(PodDraftParticipant, PodDraftParticipant.event_id == PodDraftEvent.id)
        .where(
            PodDraftParticipant.player_id == player_id,
            PodDraftParticipant.record.isnot(None),
            func.upper(PodDraftEvent.set_code) == PEASANT_CODE,
            PodDraftEvent.event_time <= through,
        )
        .order_by(PodDraftEvent.event_time, PodDraftEvent.id)
    ).all()
    return [PeasantFinish(event_date, record, deck_colors) for event_date, record, deck_colors in rows]


def main_colors_of(deck_colors: str | None) -> str:
    return "".join(c for c in deck_colors or "" if c.isupper())


def _bold_ordinal(number: int) -> str:
    return f"**{ordinal(number)}**"


def _in_season(day: date, season: SetSeed) -> bool:
    if day < season.start_date:
        return False
    return season.end_date is None or day <= season.end_date
