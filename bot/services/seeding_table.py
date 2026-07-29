"""The rank-ordered monospace table the pod seeding surfaces share: inline-code rows linked to each
player's page, the same trick `/leaderboard` uses. The cell formatters are public because a surface with
no room for the table still renders a rank the same way.
"""
from __future__ import annotations

from collections.abc import Callable, Sequence

from bot.discord_helpers import display_width, player_url
from bot.services.player_stats import SeededAttendee
from bot.sets import active_set_code


def attendee_rnk(attendee: SeededAttendee) -> str:
    return f"#{attendee.rank}" if attendee.rank is not None else "—"


def attendee_pts(attendee: SeededAttendee) -> str:
    return "—" if attendee.score is None else str(round(attendee.score))


def attendee_trophies(attendee: SeededAttendee) -> str:
    return "—" if attendee.trophies is None else str(attendee.trophies)


Column = tuple[str, str, Callable[[SeededAttendee], str]]

SEEDING_COLS: tuple[Column, ...] = (
    ("Rnk", "r", attendee_rnk),
    ("Player", "l", lambda attendee: attendee.display_name),
    ("Pts", "r", attendee_pts),
    ("🏆", "r", attendee_trophies),
)


def seeding_block(
    attendees: Sequence[SeededAttendee], *, seats: Sequence[int | None] | None = None,
    cut_after: int | None = None, cut_label: str | None = None, lead_label: str = "🪑",
) -> str:
    """Inline-code rows (monospace) linked to each player's page. With `seats` (aligned with `attendees`)
    a leading seat column is shown, blank for anyone past the pod cut; pass None for an unseated list.
    Unranked attendees show — and link nowhere.
    """
    numbered = seats is not None
    leads = [f"{s}." if s is not None else "" for s in (seats or [])]
    lead_w = max([display_width(lead_label), *(display_width(lead) for lead in leads)]) if numbered else 0

    def fmt(value: str, width: int, align: str) -> str:
        pad = max(0, width - display_width(value))
        return value + " " * pad if align == "l" else " " * pad + value

    header_cells: list[str] = []
    row_cells: list[list[str]] = [[] for _ in attendees]
    for header, align, cell in SEEDING_COLS:
        values = [cell(a) for a in attendees]
        is_wide = header == "🏆"
        width = max(max(display_width(v) for v in values), 2 if is_wide else len(header))
        header_cells.append(fmt(header, width - 1 if is_wide else width, "l" if align == "l" else "r"))
        for i, v in enumerate(values):
            row_cells[i].append(fmt(v, width, align))

    def line(lead: str, cells: list[str]) -> str:
        prefix = fmt(lead, lead_w, "l") + " " if numbered else ""
        return prefix + "  ".join(cells)

    header_line = line(lead_label, header_cells)
    lines = [f"`{header_line}`"]
    active = active_set_code()
    for i, a in enumerate(attendees):
        if cut_after is not None and i == cut_after:
            lines.append(f"`{'─' * display_width(header_line)}`")
            if cut_label:
                lines.append(f"**{cut_label}**")
        inner = line(leads[i] if numbered else "", row_cells[i])
        if a.slug:
            lines.append(f"[`{inner}`](<{player_url(a.slug, active)}>)")
        else:
            lines.append(f"`{inner}`")
    return "\n".join(lines)
