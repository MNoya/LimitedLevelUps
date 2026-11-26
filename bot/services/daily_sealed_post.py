"""The morning Daily Sealed post: today's pool link plus yesterday's community breakdown"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from bot import emojis
from bot.config import settings
from bot.models import DailySealedBuild, DailySealedPool
from bot.services.pod_deck_color import format_deck_color_emojis

DAILY_SEALED_ROLE_NAME = "Daily Sealed"
COLOR_ORDER = "WUBRG"
TOP_PAIRS = 3

MSG_HEADER = "### {role}: {set_code} #{number}"
MSG_BUILD_LINK = "[**Build today's pool**]({url}) {llu}"
MSG_YESTERDAY = "[**Yesterday**]({url}) {event} {record} {colors}"
MSG_BUILDS = "👷 [**Builds**]({url}): {pairs}"
BREAKDOWN_ANCHOR = "on-color"
PAIR_SEPARATOR = "    "
SEALED_EVENT_NAMES = {
    "Sealed": "Sealed",
    "TradSealed": "Traditional Sealed",
    "ArenaDirect_Sealed": "Arena Direct",
    "QualifierPlayInSealed": "Qualifier Play-In",
    "QualifierPlayInTradSealed": "Qualifier Play-In Bo3",
    "Qualifier_D1_Sealed": "Qualifier Weekend Day 1",
    "Qualifier_D2_Sealed": "Qualifier Weekend Day 2",
    "OpenSealed_D1_Bo1": "Day 1 Sealed Bo1",
    "OpenSealed_D1_Bo3": "Day 1 Sealed Bo3",
    "OpenSealed_D2_Bo3": "Day 2 Sealed Bo3",
    "OpenSealed_D2_Sealed1_Bo3": "Day 2 Sealed 1 Bo3",
}


@dataclass(frozen=True)
class PoolSummary:
    day: date
    set_code: str
    number: int
    build_count: int
    pair_counts: list[tuple[str, int]]
    colors: str | None
    event_format: str
    wins: int
    losses: int


def pool_url(day: date) -> str:
    return f"{settings.public_site_url.rstrip('/')}/daily-sealed/{day.isoformat()}"


def pool_summary(session: Session, day: date) -> PoolSummary | None:
    pool = session.get(DailySealedPool, day)
    if pool is None:
        return None
    number = session.execute(
        select(func.count()).where(DailySealedPool.set_code == pool.set_code, DailySealedPool.day <= day)
    ).scalar_one()
    build_colors = session.execute(select(DailySealedBuild.colors).where(DailySealedBuild.day == day)).scalars().all()
    return PoolSummary(
        day=day,
        set_code=pool.set_code,
        number=number,
        build_count=len(build_colors),
        pair_counts=pair_counts(build_colors),
        colors=pool.colors,
        event_format=pool.format,
        wins=pool.wins,
        losses=pool.losses,
    )


def pair_counts(build_colors: list[str]) -> list[tuple[str, int]]:
    counts: dict[str, int] = {}
    for colors in build_colors:
        pair = main_colors(colors)
        counts[pair] = counts.get(pair, 0) + 1
    ranked = sorted(counts.items(), key=lambda item: -item[1])
    return ranked[:TOP_PAIRS]


def main_colors(colors: str) -> str:
    present = {letter for letter in colors if letter.isupper()}
    ordered = "".join(letter for letter in COLOR_ORDER if letter in present)
    return ordered or "C"


def build_daily_sealed_post(today: PoolSummary, yesterday: PoolSummary | None, role_mention: str) -> str:
    lines = [
        MSG_HEADER.format(role=role_mention, set_code=today.set_code, number=today.number),
        MSG_BUILD_LINK.format(url=pool_url(today.day), llu=emojis.get("llu")).rstrip(),
    ]
    if yesterday is not None:
        lines.extend(yesterday_lines(yesterday))
    return "\n".join(lines)


def yesterday_lines(summary: PoolSummary) -> list[str]:
    url = pool_url(summary.day)
    lines = []
    if summary.colors:
        event = SEALED_EVENT_NAMES.get(summary.event_format, summary.event_format)
        record = f"{summary.wins}-{summary.losses}"
        lines.append(MSG_YESTERDAY.format(url=url, event=event, record=record, colors=color_glyph(summary.colors)))
    if summary.pair_counts:
        pairs = PAIR_SEPARATOR.join(f"{color_glyph(pair)} {count}" for pair, count in summary.pair_counts)
        lines.append(MSG_BUILDS.format(url=f"{url}#{BREAKDOWN_ANCHOR}", pairs=pairs))
    return [""] + lines if lines else []


def color_glyph(colors: str) -> str:
    return format_deck_color_emojis(colors) or colors
