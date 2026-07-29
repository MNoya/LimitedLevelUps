"""The Set Championship card's roster: three columns capped at the seat count, so a card with thirty
signups still answers who plays on the day.

Playing holds the seeds who take the seats if the event started now. Alternates holds everyone still in
line for a seat, Yes and Maybe together in rank order since the seats go to the highest-ranked players
who show up; a Maybe carries a marker after its name. No shows the highest-ranked players who declined,
which is the part of a decline worth reading.
"""
from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass

import discord

from bot.database import SessionLocal
from bot.discord_helpers import NBSP
from bot.services.championship import frozen_rank_by_player_sync
from bot.services.player_stats import SeededAttendee, seed_attendees
from bot.services.pod_drafts import is_championship, load_event_name_sync
from bot.services.pod_signals import RSVP_MAYBE, RSVP_NO, RSVP_YES
from bot.services.seeding_table import attendee_rnk

SEAT_COUNT = 8
COLUMN_CAP = 8
FIELD_VALUE_LIMIT = 1024

PLAYING_LABEL = f"Top {SEAT_COUNT}"
ALTERNATES_LABEL = "Alternates"
NO_LABEL = "Can't"
YES_EMOJI = "✅"
ALTERNATES_EMOJI = "🪑"
NO_EMOJI = "❌"
MAYBE_MARKER = r"\*"
EMPTY_VALUE = "-"
NAME_LIMIT = 18
ELLIPSIS = "…"
PARENTHETICAL = re.compile(r"\s*\([^)]*\)")
EMOJI_TAIL = re.compile(
    r"[←-⇿⌀-➿⬀-⯿️\U0001f000-\U0001faff].*", re.DOTALL,
)


@dataclass(frozen=True)
class Alternate:
    """One player in line for a seat, and whether they only answered Maybe."""
    attendee: SeededAttendee
    maybe: bool


@dataclass(frozen=True)
class ChampionshipRoster:
    """A championship card's RSVPs placed against the seats: `playing` take them if the event started
    now, `alternates` are next in line, `declined` answered No."""
    playing: list[SeededAttendee]
    alternates: list[Alternate]
    declined: list[SeededAttendee]


def championship_roster(
    yes: Sequence[SeededAttendee], maybe: Sequence[SeededAttendee], declined: Sequence[SeededAttendee],
    *, seats: int = SEAT_COUNT,
) -> ChampionshipRoster:
    """Split a seed-ordered Yes list at the seat count, then merge what is left with Maybe back into rank
    order for the alternates. Callers pass every list already ordered by standing with unranked trailing,
    which is what `seed_attendees` returns."""
    alternates = [Alternate(a, maybe=False) for a in yes[seats:]]
    alternates += [Alternate(a, maybe=True) for a in maybe]
    alternates.sort(key=_alternate_order)
    return ChampionshipRoster(playing=list(yes[:seats]), alternates=alternates, declined=list(declined))


def championship_roster_for_event_sync(
    event_id: str | None, rosters: dict[str, list[str]],
) -> ChampionshipRoster | None:
    """The three columns for a Set Championship card, its RSVP names placed against the seed snapshot
    frozen at creation. None for every other pod, which keeps the plain name columns. Players outside the
    snapshot fall back to their live rank, the same as the in-thread seeding table."""
    if event_id is None:
        return None
    name = load_event_name_sync(event_id)
    if name is None or not is_championship(name):
        return None
    override = frozen_rank_by_player_sync(event_id)
    with SessionLocal() as session:
        seeded = {
            state: seed_attendees(session, rosters.get(state) or [], override)
            for state in (RSVP_YES, RSVP_MAYBE, RSVP_NO)
        }
    return championship_roster(seeded[RSVP_YES], seeded[RSVP_MAYBE], seeded[RSVP_NO])


def add_championship_roster_fields(embed: discord.Embed, roster: ChampionshipRoster) -> None:
    """The three roster columns, each showing the top of its list. No counts: the rows carry how many
    seats are claimed, and the other two lists are deeper than the column shows."""
    embed.add_field(
        name=f"{YES_EMOJI} {PLAYING_LABEL}",
        value=_column([_row(a) for a in roster.playing]),
        inline=True,
    )
    embed.add_field(
        name=f"{ALTERNATES_EMOJI} {ALTERNATES_LABEL}",
        value=_column([_row(alt.attendee, maybe=alt.maybe) for alt in roster.alternates]),
        inline=True,
    )
    embed.add_field(
        name=f"{NO_EMOJI} {NO_LABEL}",
        value=_column([_row(a) for a in roster.declined]),
        inline=True,
    )


def _alternate_order(alternate: Alternate) -> tuple[bool, int, str]:
    rank = alternate.attendee.rank
    return (rank is None, rank or 0, alternate.attendee.display_name.lower())


def _row(attendee: SeededAttendee, *, maybe: bool = False) -> str:
    """The rank leads the row, so a name too long for the third-of-a-card column wraps its own tail
    instead of pushing the rank onto a line of its own. A Maybe is marked with an escaped asterisk, so a
    column of them cannot pair up into italics."""
    marker = MAYBE_MARKER if maybe else ""
    return f"> **{attendee_rnk(attendee)}** {NBSP}{short_name(attendee.display_name)}{marker}"


def short_name(display_name: str) -> str:
    """A display name cut down to what a third-of-a-card column holds: the parenthetical alias goes, so
    does everything from the first emoji on, and what is left is capped at a word boundary. Falls back to
    the raw name when a rule would leave nothing, as for a name that is only emoji."""
    name = PARENTHETICAL.sub("", display_name).strip()
    name = EMOJI_TAIL.sub("", name).strip() or name
    if len(name) <= NAME_LIMIT:
        return name
    cut = name[: NAME_LIMIT - 1]
    if not name[NAME_LIMIT - 1].isspace() and " " in cut.strip():
        cut = cut.rpartition(" ")[0]
    return f"{cut.rstrip()}{ELLIPSIS}"


def _column(rows: Sequence[str]) -> str:
    """A roster column: the top rows by seed, capped at `COLUMN_CAP` and again at Discord's field limit."""
    kept = list(rows[:COLUMN_CAP])
    while kept and len("\n".join(kept)) > FIELD_VALUE_LIMIT:
        kept.pop()
    return "\n".join(kept) or EMPTY_VALUE
