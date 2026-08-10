"""The gathering-first pod card: one anchor message that carries a slot from signups to locked tables.

Three phases on one message: a gathering card with format team blocks while players accumulate, a
seat-claim ready check where one press is both attendance and table choice, and locked tables once the
seats fill. Only embed builders and pure helpers live here, so the `!test gather` preview and the future
production wiring share every user-facing string; state and Discord plumbing stay with the caller.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

import discord

from bot.services import pod_format_interest as fi
from bot.services.pod_launch import REMINDER_LEAD_MIN
from bot.sets import active_set_code


MSG_GATHERING_INTRO = "Pick your format below. The ready check posts {lead} minutes before start"
MSG_READY_INTRO = "Press a table to claim your seat. A table locks at {seats} seats"
MSG_FLEX_FOOTER = "✨ counts toward either table"
MSG_NO_TABLE_YET = "No table has {seats} players yet"

TIME_FIELD = "Time"
WAITING_FIELD = "🕐 Not Pressed ({count})"
EMPTY_VALUE = "-"


@dataclass(frozen=True)
class GatherMember:
    name: str
    interests: tuple[str, ...] = ()
    ranking: tuple[str, ...] = ()


@dataclass
class TableCandidate:
    """One table the ready check offers. ``set_code`` is fixed at birth for the latest table and resolved
    from the pressers' standing rankings the moment a flashback table locks."""
    format_code: str
    set_code: str | None
    pressed: list[str] = field(default_factory=list)

    def locked(self, seats: int) -> bool:
        return len(self.pressed) >= seats


def neutral_pod_title(slot_label: str, slot_time: datetime) -> str:
    return f"{slot_time:%b %-d} {slot_label} Pod"


def build_gathering_embed(
    slot_label: str, slot_time: datetime, members: list[GatherMember],
) -> discord.Embed:
    embed = discord.Embed(
        title=f"🧲 {neutral_pod_title(slot_label, slot_time)}",
        description=MSG_GATHERING_INTRO.format(lead=REMINDER_LEAD_MIN),
        color=discord.Color.green(),
    )
    _add_time_field(embed, slot_time)
    latest_team, flashback_team = fi.format_teams([(m, m.interests) for m in members])
    if flashback_team:
        latest_name = f"{fi.latest_emoji()} Latest ({len(latest_team)})"
        flashback_name = f"{fi.flashback_emoji()} Flashback ({len(flashback_team)})"
        embed.add_field(name=latest_name, value=_member_lines(latest_team), inline=True)
        embed.add_field(name=flashback_name, value=_member_lines(flashback_team), inline=True)
    else:
        embed.add_field(name=f"Players ({len(members)})", value=_member_lines(latest_team), inline=False)
    if any(fi.is_flexible(m.interests) for m in members):
        embed.set_footer(text=MSG_FLEX_FOOTER)
    return embed


def build_ready_embed(
    slot_label: str, slot_time: datetime, tables: list[TableCandidate],
    waiting: list[str], absent: list[str], seats: int,
) -> discord.Embed:
    embed = discord.Embed(
        title=f"📋 {neutral_pod_title(slot_label, slot_time)}",
        description=MSG_READY_INTRO.format(seats=seats),
        color=discord.Color.green(),
    )
    _add_time_field(embed, slot_time)
    for table in tables:
        embed.add_field(
            name=table_field_name(table, seats, slot_label, slot_time),
            value=_name_lines(table.pressed),
            inline=True,
        )
    idle = [f"~~{name}~~" for name in absent]
    if waiting or idle:
        embed.add_field(
            name=WAITING_FIELD.format(count=len(waiting) + len(idle)),
            value=_name_lines(waiting + idle),
            inline=True,
        )
    return embed


def table_field_name(table: TableCandidate, seats: int, slot_label: str, slot_time: datetime) -> str:
    label = table.set_code or fi.INTEREST_LABEL[fi.FLASHBACK]
    if table.locked(seats):
        return f"✅ {label} {neutral_pod_title(slot_label, slot_time)}"
    emoji = fi.latest_emoji() if table.format_code == fi.LATEST else fi.flashback_emoji()
    return f"{emoji} {label} ({len(table.pressed)}/{seats})"


def table_button_label(table: TableCandidate, seats: int) -> str:
    label = table.set_code or fi.INTEREST_LABEL[fi.FLASHBACK]
    if table.locked(seats):
        return f"{label} ✓"
    return f"{label} {len(table.pressed)}/{seats}"


def latest_table_candidate() -> TableCandidate:
    return TableCandidate(fi.LATEST, active_set_code())


def flashback_table_candidate() -> TableCandidate:
    return TableCandidate(fi.FLASHBACK, None)


def resolve_flashback_set(rankings: list[tuple[str, ...]]) -> str | None:
    """First-choice plurality over the pressers' standing rankings; the earliest-seen top pick wins a
    tie. Preview-grade; a production resolver can weigh full rankings later."""
    counts: dict[str, int] = {}
    order: list[str] = []
    for ranking in rankings:
        if not ranking:
            continue
        top = ranking[0]
        if top not in counts:
            counts[top] = 0
            order.append(top)
        counts[top] += 1
    winner: str | None = None
    best = 0
    for code in order:
        if counts[code] > best:
            best = counts[code]
            winner = code
    return winner


def _add_time_field(embed: discord.Embed, slot_time: datetime) -> None:
    unix = int(slot_time.timestamp())
    embed.add_field(name=TIME_FIELD, value=f"<t:{unix}:F> (<t:{unix}:R>)", inline=False)


def _member_lines(team: list[GatherMember]) -> str:
    lines = []
    for member in team:
        marker = f"{fi.FLEXIBLE_EMOJI} " if fi.is_flexible(member.interests) else ""
        lines.append(f"{marker}{member.name}")
    return "\n".join(lines) or EMPTY_VALUE


def _name_lines(names: list[str]) -> str:
    return "\n".join(names) or EMPTY_VALUE
