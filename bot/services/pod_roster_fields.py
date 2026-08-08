"""The Yes / Maybe roster columns shared by the scheduled card and the T-60 roster reminder, so both
surfaces group by format the same way. Once a signup wants flashback the roster splits into Latest Set
and Flashback columns; otherwise it stays a plain Yes / Maybe pair."""
from __future__ import annotations

import discord

from bot.commands.messages import (
    MSG_TABLE_COLUMN,
    MSG_TABLE_COLUMN_ONLY,
    MSG_TABLE_SEAT,
    MSG_TABLE_SEAT_CONFIRMED,
    MSG_TABLE_EMPTY_SEAT,
    MSG_TABLE_MORE_NAMES,
)
from bot.services import pod_format_interest as fi
from bot.services.pod_confirm import CONFIRMED, Attendance, Table, TablePlan
from bot.services.pod_signals import RSVP_MAYBE, RSVP_NO, RSVP_YES


_ATTENDANCE = ((RSVP_YES, "✅", "Yes"), (RSVP_MAYBE, "🤷", "Maybe"))
_ATTENDANCE_WITH_NO = _ATTENDANCE + ((RSVP_NO, "❌", "No"),)
_ATTENDANCE_CONFIRMING = (
    (CONFIRMED, "✅", "Confirmed"), (RSVP_YES, "☑️", "Yes"), (RSVP_MAYBE, "🤷", "Maybe"),
)


def add_roster_fields(
    embed: discord.Embed, rosters: dict[str, list[str]],
    roster_interests: dict[str, list[tuple[str, tuple[str, ...]]]] | None,
    championship: bool = False,
) -> None:
    """Yes / Maybe columns while the pod gathers, grouped by format once a signup wants flashback,
    plain otherwise. No is normally not a column — the ❌ button removes the signup instead of tracking
    a decline — but a championship shows it so declines read at a glance, and skips the format split
    since it is a single-set event.

    Once the confirmation window has answers, attendance takes the columns back from format: the hour
    before a busy draft the room needs to read who is coming, not who prefers which set."""
    if championship:
        _add_plain_rsvp_fields(embed, rosters, include_no=True)
        return
    if rosters.get(CONFIRMED):
        _add_plain_rsvp_fields(embed, rosters)
        return
    if roster_interests is None:
        _add_plain_rsvp_fields(embed, rosters)
        return
    yes = roster_interests.get(RSVP_YES) or []
    maybe = roster_interests.get(RSVP_MAYBE) or []
    comp = fi.composition([codes for _, codes in yes] + [codes for _, codes in maybe])
    if comp.flashback_only > 0:
        _add_format_split_fields(embed, yes, maybe)
    else:
        _add_plain_rsvp_fields(embed, rosters)


def add_table_plan_fields(embed: discord.Embed, attendance: Attendance, plan: TablePlan) -> None:
    """Render the roster as the tables it makes, which is the thing the room is actually deciding.

    Columns are the tables. A header says how many are on it and, when it is short, what it needs, so the
    card carries the shape without a sentence explaining it. Seats are filled confirmed-first, so the
    people who answered land on the table most likely to run and the marker beside a name says how solid
    that seat is. A leftover too small to become a table of its own is waiting, not a table.
    """
    seats = [(name, True) for name in attendance.confirmed] + [(name, False) for name in attendance.yes]
    cursor = 0
    alone = len(plan.tables) == 1
    for index, table in enumerate(plan.tables, start=1):
        _add_seat_field(embed, _table_header(index, table, alone=alone),
                        seats[cursor:cursor + table.seated], open_seats=table.empty_seats)
        cursor += table.seated
    maybe = list(attendance.maybe)
    if maybe:
        _add_lines_field(embed, f"🤷 Maybe ({len(maybe)})", list(maybe))


TABLE_NUMERALS = ("1\ufe0f\u20e3", "2\ufe0f\u20e3", "3\ufe0f\u20e3", "4\ufe0f\u20e3", "5\ufe0f\u20e3")


def _table_header(index: int, table: Table, *, alone: bool) -> str:
    """Which table it is, then how big it is. The seats still open are rows in the list below rather than a
    fraction up here, so a reader counts gaps instead of doing arithmetic on the header.

    A pod running one table drops the number. There is nothing to tell it apart from, and numbering the
    only table invites the reader to look for a second one."""
    if alone:
        return MSG_TABLE_COLUMN_ONLY.format(size=table.capacity)
    numeral = TABLE_NUMERALS[index - 1] if index <= len(TABLE_NUMERALS) else str(index)
    return MSG_TABLE_COLUMN.format(index=numeral, size=table.capacity)


def _add_seat_field(
    embed: discord.Embed, header: str, seats: list[tuple[str, bool]], open_seats: int = 0,
) -> None:
    """One row per seat: who holds it and how firmly, then a row for each seat still to fill. An empty row
    is the ask made concrete, so a reader counts gaps instead of subtracting numbers in a header."""
    lines = [
        (MSG_TABLE_SEAT_CONFIRMED if confirmed else MSG_TABLE_SEAT).format(name=name)
        for name, confirmed in seats
    ]
    lines += [MSG_TABLE_EMPTY_SEAT] * open_seats
    _add_lines_field(embed, header, lines)


FIELD_VALUE_LIMIT = 1024


def _add_lines_field(embed: discord.Embed, header: str, lines: list[str]) -> None:
    embed.add_field(name=header, value=_quoted(_fit(lines)) or "-", inline=True)


def _fit(lines: list[str]) -> list[str]:
    """Keep a column inside Discord's field limit. Over it the whole message is rejected and no card posts
    at all, so a long Maybe list has to be cut. What was cut is counted rather than dropped quietly."""
    if len(_quoted(lines)) <= FIELD_VALUE_LIMIT:
        return lines
    kept = list(lines)
    while kept:
        kept.pop()
        trimmed = kept + [MSG_TABLE_MORE_NAMES.format(count=len(lines) - len(kept))]
        if len(_quoted(trimmed)) <= FIELD_VALUE_LIMIT:
            return trimmed
    return [MSG_TABLE_MORE_NAMES.format(count=len(lines))]


def _quoted(lines: list[str]) -> str:
    return "\n".join(f"> {line}" for line in lines)


def _add_plain_rsvp_fields(
    embed: discord.Embed, rosters: dict[str, list[str]], include_no: bool = False,
) -> None:
    confirming = bool(rosters.get(CONFIRMED))
    for state, emoji, word in attendance_columns(rosters, include_no=include_no):
        names = rosters.get(state) or []
        if confirming and not names:
            continue
        value = "\n".join(f"> {name}" for name in names) if names else "-"
        embed.add_field(name=f"{emoji} {word} ({len(names)})", value=value, inline=True)


def attendance_columns(
    rosters: dict[str, list[str]], include_no: bool = False,
) -> tuple[tuple[str, str, str], ...]:
    """Which attendance columns this roster renders. Once anyone has confirmed, Confirmed leads and Yes
    steps down to a lighter mark, so the two never read as the same answer. An ordinary night, where
    nobody was ever asked to confirm, looks exactly as it did before."""
    if rosters.get(CONFIRMED):
        return _ATTENDANCE_CONFIRMING
    return _ATTENDANCE_WITH_NO if include_no else _ATTENDANCE


def _add_format_split_fields(
    embed: discord.Embed, yes: list[tuple[str, tuple[str, ...]]], maybe: list[tuple[str, tuple[str, ...]]],
) -> None:
    """Latest Set / Flashback columns, each sub-grouped into Yes then Maybe with counts. Flexible
    players carry the flexible marker and fill whichever team needs bodies, same as the launcher board."""
    tagged = [(name, state, codes) for state, members in ((RSVP_YES, yes), (RSVP_MAYBE, maybe))
              for name, codes in members]
    latest_team, flashback_team = fi.format_teams([(entry, entry[2]) for entry in tagged])
    for emoji, label, team in (
        (fi.latest_emoji(), "Latest Set", latest_team), (fi.flashback_emoji(), "Flashback", flashback_team),
    ):
        blocks = []
        for state, status_emoji, word in _ATTENDANCE:
            members = [(name, codes) for (name, st, codes) in team if st == state]
            if members:
                lines = "\n".join(
                    f"> {fi.FLEXIBLE_MARKER + ' ' if fi.is_flexible(codes) else ''}{name}"
                    for name, codes in members
                )
                blocks.append(f"{status_emoji} {word} ({len(members)})\n{lines}")
        embed.add_field(name=f"{emoji} {label} ({len(team)})", value="\n".join(blocks) or "-", inline=True)
