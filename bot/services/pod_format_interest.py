"""The single format-interest vocabulary shared by the standing player preference, the launcher
composition board, and the flashback format poll, plus the pure logic each surface reads.

An interest is one of ``LATEST`` / ``FLASHBACK`` / ``CUBE``, stored as a small string array on both
``Player.format_interests`` and ``PodSignalMember.format_interest``. "Flexible" is not a stored value: a
player holding both ``LATEST`` and ``FLASHBACK`` is flexible, counted toward whichever format needs bodies
to reach a table. Cube is a first-class member so the same machinery extends to cube-first players later;
this version ships no cube-specific flow.
"""
from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import TypeVar

import discord

from bot import emojis
from bot.config import settings
from bot.services import pod_format
from bot.sets import active_set_code


LATEST = "latest"
FLASHBACK = "flashback"
CUBE = "cube"

INTEREST_ORDER = (LATEST, FLASHBACK, CUBE)
VALID_INTERESTS = frozenset(INTEREST_ORDER)

INTEREST_LABEL = {LATEST: "Latest Set", FLASHBACK: "Flashback", CUBE: "Cube"}
EXCLUSIVE_LABEL = {LATEST: "Latest Set Only", FLASHBACK: "Flashback Only"}
INTEREST_EMOJI = {LATEST: "🆕", FLASHBACK: "⏪", CUBE: "🧊"}

LATEST_SET_ROLE_NAME = "Latest Set"
FLASHBACK_ROLE_NAME = "Flashback"
CUBE_ROLE_NAME = "Cube"

FLEXIBLE_LABEL = "Any Format"
FLEXIBLE_EMOJI = "✨"
FLEXIBLE_MARKER = "◈"

DEFAULT_FLASHBACK_POLL_MIN = 3
FLASHBACK_RANKING_MAX = 3


def latest_emoji() -> "discord.Emoji | str":
    """The active set's symbol stands in for the latest-set interest, the unicode fallback until the app
    emoji load."""
    return emojis.set_symbol(active_set_code()) or INTEREST_EMOJI[LATEST]


def flashback_emoji() -> "discord.Emoji | str":
    return emojis.get_emoji("flashback") or INTEREST_EMOJI[FLASHBACK]


def cube_emoji() -> "discord.Emoji | str":
    return emojis.get_emoji("cube") or INTEREST_EMOJI[CUBE]


def format_emoji(code: str) -> "discord.Emoji | str":
    """A format's glyph for a button's emoji slot or an f-string, which take the object. A cube has no set
    symbol, so it falls back to the cube glyph rather than the flashback one. Never pass this into
    `str.join`: an Emoji is not a str, which is how the first named-pod render crashed."""
    symbol = emojis.set_symbol(code)
    if symbol is not None:
        return symbol
    return cube_emoji() if pod_format.is_custom(code) else flashback_emoji()


def normalize(values: Iterable[str] | None) -> list[str]:
    """Valid interest codes in canonical order, deduped. Unknown or empty input yields an empty list,
    which reads everywhere as "unstated"."""
    if not values:
        return []
    present = {value for value in values if value in VALID_INTERESTS}
    return [code for code in INTEREST_ORDER if code in present]


def has_latest(values: Iterable[str] | None) -> bool:
    return LATEST in normalize(values)


def has_flashback(values: Iterable[str] | None) -> bool:
    return FLASHBACK in normalize(values)


def is_flexible(values: Iterable[str] | None) -> bool:
    codes = normalize(values)
    return LATEST in codes and FLASHBACK in codes


def interest_summary(values: Iterable[str] | None) -> str:
    """A short human label for one player's interest: "Flexible" when they hold both draftable-set
    interests, otherwise the joined labels, or "No preference" when unstated."""
    codes = normalize(values)
    if not codes:
        return "No preference"
    if is_flexible(codes):
        return FLEXIBLE_LABEL
    return " and ".join(INTEREST_LABEL[code] for code in codes)


def interest_emoji(code: str) -> "discord.Emoji | str":
    if code == LATEST:
        return latest_emoji()
    if code == FLASHBACK:
        return flashback_emoji()
    if code == CUBE:
        return cube_emoji()
    return INTEREST_EMOJI[code]


def interest_summary_with_emoji(values: Iterable[str] | None) -> str:
    """interest_summary with each choice's emoji ahead of its label, for confirming a saved preference."""
    codes = normalize(values)
    if not codes:
        return interest_summary(codes)
    if is_flexible(codes):
        return f"{FLEXIBLE_MARKER} {FLEXIBLE_LABEL}"
    return " and ".join(f"{interest_emoji(code)} {INTEREST_LABEL[code]}" for code in codes)


def preference_display(values: Iterable[str] | None) -> str:
    """The wording a saved preference is shown back with: a single draftable-set choice reads as its
    exclusive picker label, everything else as the plain summary."""
    codes = normalize(values)
    if codes in ([LATEST], [FLASHBACK]):
        return f"{interest_emoji(codes[0])} {EXCLUSIVE_LABEL[codes[0]]}"
    return interest_summary_with_emoji(codes)


def ranking_display(codes: Iterable[str]) -> str:
    """The ranked set codes, each led by its set-symbol icon, the :flashback: glyph when a set has none."""
    return " **→** ".join(f"{format_emoji(code)} {code}" for code in codes)


@dataclass(frozen=True)
class Composition:
    """The interest breakdown of a set of signups. ``latest_only`` / ``flashback_only`` are the dedicated
    crowds, ``flexible`` the players up for either, ``cube`` those who marked cube, ``unstated`` those with
    no preference. Capacity properties fold the flexible players into each draftable-set count, since a
    flexible player is a body either table can borrow."""
    latest_only: int
    flashback_only: int
    flexible: int
    cube: int
    unstated: int
    total: int

    @property
    def latest_capacity(self) -> int:
        return self.latest_only + self.flexible

    @property
    def latest_seated(self) -> int:
        """Bodies that fill the latest table when a slot fires: dedicated Latest, Any, and no-preference.
        Unlike ``latest_capacity`` this folds in ``unstated`` — a clicker with no preference drafts the
        latest set. Flashback-only players are excluded; they wait for a flashback table."""
        return self.latest_only + self.flexible + self.unstated

    @property
    def flashback_capacity(self) -> int:
        return self.flashback_only + self.flexible

    @property
    def has_signal(self) -> bool:
        return self.total > self.unstated


def composition(member_interests: Iterable[Iterable[str] | None]) -> Composition:
    latest_only = flashback_only = flexible = cube = unstated = total = 0
    for raw in member_interests:
        total += 1
        codes = normalize(raw)
        latest = LATEST in codes
        flashback = FLASHBACK in codes
        if CUBE in codes:
            cube += 1
        if latest and flashback:
            flexible += 1
        elif latest:
            latest_only += 1
        elif flashback:
            flashback_only += 1
        elif not codes:
            unstated += 1
    return Composition(latest_only, flashback_only, flexible, cube, unstated, total)


T = TypeVar("T")


def format_teams(pairs: Iterable[tuple[T, Iterable[str] | None]]) -> tuple[list[T], list[T]]:
    """Sort (item, interests) pairs into the latest and flashback teams. Dedicated picks anchor their
    team, flexible players fill via fills_latest, no-preference riders join the latest team last.

    Riders stay out of the fills_latest decision on purpose. They asked for nothing, so counting them as
    the latest team's own crowd lets the surplus rule divert a flexible body onto a table nobody
    requested, away from a table that is one body short. Order within each team follows the input order,
    riders after the dedicated."""
    latest_team: list[T] = []
    flashback_team: list[T] = []
    riders: list[T] = []
    flexible: list[T] = []
    for item, raw in pairs:
        codes = normalize(raw)
        if is_flexible(codes):
            flexible.append(item)
        elif FLASHBACK in codes:
            flashback_team.append(item)
        elif LATEST in codes:
            latest_team.append(item)
        else:
            riders.append(item)
    for item in flexible:
        if fills_latest(len(latest_team), len(flashback_team)):
            latest_team.append(item)
        else:
            flashback_team.append(item)
    return latest_team + riders, flashback_team


def fills_latest(latest_count: int, flashback_count: int) -> bool:
    """A flexible player joins the larger team, ties to latest. A team already at the fire threshold
    stops pulling so the surplus builds the other table, but only when the other team has dedicated
    members of its own; surplus never opens a team nobody asked for. Both counts are of dedicated
    members, so a column holding only no-preference riders never reads as a crowd that asked for it."""
    threshold = settings.pod_signal_fire_threshold
    if latest_count >= threshold and 0 < flashback_count < threshold:
        return False
    if flashback_count >= threshold and 0 < latest_count < threshold:
        return True
    return latest_count >= flashback_count


def should_offer_format_poll(comp: Composition, minimum: int = DEFAULT_FLASHBACK_POLL_MIN) -> bool:
    """A freshly opened pod earns a format poll only when enough of its roster leans flashback. An
    all-latest weekday pod stays untouched and never sees the poll."""
    return comp.flashback_capacity >= minimum and comp.flashback_only > 0


def slot_fires_latest(comp: Composition, threshold: int) -> bool:
    """A launcher slot graduates only when the latest-set table can seat a full pod. Latest-only, Any,
    and no-preference players all seat it; flashback-only players never fire the latest pod on their own.
    Firing opens the latest set today, so a slot that reaches the raw threshold on flashback-only bodies
    holds instead of graduating into a set nobody there wanted."""
    return comp.latest_seated >= threshold


def format_at_fire(member_interests: Iterable[Iterable[str] | None]) -> str:
    """The set a slot fires into. This version always opens on the latest set and leaves the concrete
    choice to the in-lobby poll, so latest-only players are never moved out from under a firing pod. The
    argument is unused today and marks the seam where a future version can make firing format-aware."""
    del member_interests
    return active_set_code()
