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
    MSG_TABLE_SEAT_ODD_ONE_OUT,
    MSG_TABLE_MORE_NAMES,
    MSG_TABLE_WAITING_COLUMN,
)
from bot import emojis
from bot.discord_helpers import ZWSP
from bot.services import pod_format_interest as fi
from bot.services.pod_confirm import CONFIRMED, MIN_TABLE, Attendance, Table, TablePlan
from bot.services.pod_signals import RSVP_MAYBE, RSVP_NO, RSVP_YES


_YES_COLUMN = (RSVP_YES, "✅", "Yes")
_MAYBE_COLUMN = (RSVP_MAYBE, "🤷", "Maybe")
_NO_COLUMN = (RSVP_NO, "❌", "No")
_PENDING_COLUMN = (RSVP_YES, "☑️", "Pending")
_ATTENDANCE = (_YES_COLUMN, _MAYBE_COLUMN)
_ATTENDANCE_WITH_NO = _ATTENDANCE + (_NO_COLUMN,)
_ANSWER_COLUMNS = (_MAYBE_COLUMN, _NO_COLUMN)
_ATTENDANCE_CONFIRMING = (
    (CONFIRMED, "✅", "Confirmed"), (RSVP_YES, "☑️", "Yes"), (RSVP_MAYBE, "🤷", "Maybe"),
)


def add_roster_fields(
    embed: discord.Embed, rosters: dict[str, list[str]],
    roster_interests: dict[str, list[tuple[str, tuple[str, ...]]]] | None,
    championship: bool = False, playing_only: bool = False,
) -> None:
    """Yes / Maybe columns while the pod gathers, grouped by format once a signup wants flashback,
    plain otherwise, with a No column from the first Leave. A championship always carries No and skips
    the format split, since it is a single-set event.

    Once the confirmation window has answers, attendance takes the columns back from format: the hour
    before a busy draft the room needs to read who is coming, not who prefers which set.

    `playing_only` is a table already at its start time: one column of the players it holds, confirmed
    and not, since a maybe on a draft about to begin is not an answer anybody is waiting for."""
    if playing_only:
        _add_playing_field(embed, (rosters.get(CONFIRMED) or []) + (rosters.get(RSVP_YES) or []))
        return
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


def _add_playing_field(embed: discord.Embed, names: list[str]) -> None:
    _add_lines_field(embed, f"{_YES_COLUMN[1]} {_YES_COLUMN[2]} ({len(names)})", names)


def add_table_plan_fields(
    embed: discord.Embed, attendance: Attendance, plan: TablePlan, seat_pending: bool = False,
    set_code: str = "",
) -> None:
    """Render the roster as the tables it makes, which is the thing the room is actually deciding.

    Columns are the tables. A header says how many are on it and, when it is short, what it needs, so the
    card carries the shape without a sentence explaining it. Seats are filled confirmed-first and the
    plan orders its tables by which can start soonest, so the people who answered early land on a table
    that is already whole and the one still needing a player falls to whoever answered last.

    Eleven players is the one count where a table cannot hold everybody, since ten seats is the whole
    Draftmancer session. Whoever is over gets their own column, because a name the card silently drops is
    a person nobody knows is there.

    Only confirmed players are seated. A signup who has not answered sits in Pending, because that is what
    they are to the plan right now: an answer the pod is still waiting on. Shown in a seat instead, they
    read as a place already held, which is the one thing a card must not imply about somebody it cannot
    count on.

    Pending sits immediately right of the tables and the waitlist after it, the two things that can still
    change the seating. Two tables own their row instead, since three columns of names read as three
    tables. Maybe and No go on a row below.
    """
    seats = [(name, True) for name in attendance.confirmed]
    if seat_pending:
        seats += [(name, False) for name in attendance.yes]
    cursor = 0
    alone = len(plan.tables) == 1
    columns = 0
    for index, table in enumerate(plan.tables, start=1):
        _add_seat_field(embed, _table_header(index, table, alone=alone, set_code=set_code),
                        seats[cursor:cursor + table.seated], open_seats=table.empty_seats,
                        marks_odd_one_out=True)
        cursor += table.seated
        columns += 1
    if columns > 1:
        _end_row(embed, columns)
        columns = 0
    if attendance.yes and not seat_pending:
        _add_answer_field(embed, _PENDING_COLUMN, list(attendance.yes))
        columns += 1
    if plan.waiting:
        _add_seat_field(embed, MSG_TABLE_WAITING_COLUMN, seats[cursor:cursor + plan.waiting])
        columns += 1
    answered = {RSVP_MAYBE: list(attendance.maybe), RSVP_NO: list(attendance.declined)}
    answers = [(column, answered[column[0]]) for column in _ANSWER_COLUMNS if answered[column[0]]]
    if answers:
        _end_row(embed, columns)
        for column, names in answers:
            _add_answer_field(embed, column, names)


TABLE_NUMERALS = ("1\ufe0f\u20e3", "2\ufe0f\u20e3", "3\ufe0f\u20e3", "4\ufe0f\u20e3", "5\ufe0f\u20e3")


def _table_header(index: int, table: Table, *, alone: bool, set_code: str = "") -> str:
    """Which table it is and how big it is. The seats still open are rows in the list below rather than a
    fraction up here, so a reader counts gaps instead of doing arithmetic on the header.

    A pod running one table drops the number and wears the set symbol instead, since numbering the only
    table invites the reader to look for a second one. Numbered tables all draft the same set, so the
    symbol would only repeat."""
    if not alone:
        numeral = TABLE_NUMERALS[index - 1] if index <= len(TABLE_NUMERALS) else str(index)
        return MSG_TABLE_COLUMN.format(index=numeral, size=table.capacity)
    symbol = emojis.set_symbol(set_code) if set_code else None
    header = MSG_TABLE_COLUMN_ONLY.format(symbol=symbol or "", size=table.capacity)
    return " ".join(header.split())


def _add_seat_field(
    embed: discord.Embed, header: str, seats: list[tuple[str, bool]], open_seats: int = 0,
    marks_odd_one_out: bool = False,
) -> None:
    """One row per seat: who holds it and how firmly, then a row for each seat still to fill. An empty row
    is the ask made concrete, so a reader counts gaps instead of subtracting numbers in a header.

    An odd table marks who drops if it stays odd, last by signup order, as a default rather than a
    verdict. Odd is counted off the confirmed alone, so a pending player cannot clear the mark, and only
    once the table could actually fire: five confirmed is a pod nobody drops from, it is one short."""
    lines = [
        (MSG_TABLE_SEAT_CONFIRMED if confirmed else MSG_TABLE_SEAT).format(name=name)
        for name, confirmed in seats
    ]
    held = [index for index, (_, confirmed) in enumerate(seats) if confirmed]
    if marks_odd_one_out and len(held) % 2 != 0 and len(held) >= MIN_TABLE:
        odd = held[-1]
        lines[odd] = MSG_TABLE_SEAT_ODD_ONE_OUT.format(seat=lines[odd])
    lines += [MSG_TABLE_EMPTY_SEAT] * open_seats
    _add_lines_field(embed, header, lines)


FIELD_VALUE_LIMIT = 1024


def _add_answer_field(embed: discord.Embed, column: tuple[str, str, str], names: list[str]) -> None:
    _add_lines_field(embed, f"{column[1]} {column[2]} ({len(names)})", names)


def _add_lines_field(embed: discord.Embed, header: str, lines: list[str]) -> None:
    embed.add_field(name=header, value=_quoted(_fit(lines)) or "-", inline=True)


FIELDS_PER_ROW = 3


def _end_row(embed: discord.Embed, columns: int) -> None:
    """Fill out the row with blank columns so the next field starts a new one. Discord packs inline fields
    three to a row and gives no way to break one."""
    for _ in range(-columns % FIELDS_PER_ROW):
        embed.add_field(name=ZWSP, value=ZWSP, inline=True)


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
    steps down to a lighter mark, so the two never read as the same answer.

    No appears the moment anybody presses Leave, after the maybes. A pod counting on somebody who has
    already said they are not coming is the shape of every table that opened one player short, and the
    card is where that is caught. It stays absent while nobody has left, so an ordinary night looks
    exactly as it did before."""
    declined = bool(include_no or rosters.get(RSVP_NO))
    if rosters.get(CONFIRMED):
        return _ATTENDANCE_CONFIRMING + (_NO_COLUMN,) if declined else _ATTENDANCE_CONFIRMING
    return _ATTENDANCE_WITH_NO if declined else _ATTENDANCE


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
