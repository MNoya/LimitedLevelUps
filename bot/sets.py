"""Source of truth for Magic set metadata and which set is currently active.

The active set is derived from today's date by ``active_set_code`` — no constant to
flip and no redeploy to rotate. Adding a set to ``ALL_SETS`` with its Arena dates and
pushing to master is all a rotation takes; the set turns over on its ``start_date`` on
its own. This is the set Arena is drafting, which is what pods, the refresh window, the
championship and the format schedule follow.

The leaderboard board is a separate question and runs ahead of this: players hold cards
days before the Arena drop, so the board belongs to the set results exist for. That lives
in ``bot.services.active_set.resolve_board_set`` because it needs the database, and the
``public_sets`` view computes the same answer for the site.

Dates are MTG Arena release dates (not tabletop). The newest set's ``end_date``
holds the anticipated rotation date based on the next set's announced launch;
a real ``end_date`` is filled in when a successor set is added. Keep an anticipated
``end_date`` on the newest set so it always falls inside an active window.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

# Arena drops a set around noon Eastern on its release day; the leaderboard rotates at that
# instant rather than at UTC midnight (which is the evening before in the Americas). ET, not a
# fixed UTC offset, so the boundary tracks daylight saving. The public_sets view encodes the
# same instant in SQL — keep them in lockstep.
RELEASE_TZ = ZoneInfo("America/New_York")
RELEASE_TIME = time(12, 0)


def release_instant(d: date) -> datetime:
    return datetime.combine(d, RELEASE_TIME, tzinfo=RELEASE_TZ).astimezone(timezone.utc)


FRIDAY = 4


def previous_weekday(day: date, weekday: int) -> date:
    """The latest `weekday` strictly before `day`."""
    back = (day.weekday() - weekday) % 7 or 7
    return day - timedelta(days=back)


@dataclass(frozen=True)
class SetSeed:
    """A set on the leaderboard.

    ``prerelease_date`` is the first day of the paper prerelease weekend, days before the Arena
    release: cards are in players' hands from then, and it anchors the Set Championship date. It is
    recorded for the sets whose schedule is still live and derived by ``prerelease_date_for`` for the
    rest, which is also the only sensible answer for the Arena-only sets that never had one.

    ``expansion_alias`` is a 17lands expansion string rewritten to ``code`` at ingest, for a set
    17lands files under another name (``MAT`` for MOM). ``expansion_matches`` routes several 17lands
    expansions to one set and keeps the raw string on each event, which is how the cube variants
    share the CUBE set while staying separable per board.

    ``short_name`` is the set as a person says it, for surfaces where the full name does not fit —
    the per-set champion role reads ``Marvel Set Champion``, not ``Marvel Super Heroes Set Champion``.
    Set it only where the full name is too long; there is no shortening rule worth guessing at, since
    ``Marvel Super Heroes`` keeps its first word and ``Secrets of Strixhaven`` would keep its last.
    """
    code: str
    name: str
    start_date: date
    end_date: date | None
    short_name: str | None = None
    prerelease_date: date | None = None
    expansion_alias: str | None = None
    expansion_matches: tuple[str, ...] = ()


@dataclass(frozen=True)
class CubeSeason:
    """One scheduled run of a cube, giving the board ``CUBE-<set>``.

    Declared in ``cube_variants.json`` rather than inferred from draft activity: WotC announces the
    run, so the dates are known ahead of the first draft and a board cannot drift because somebody
    played early or late. Both dates are inclusive.
    """
    set_code: str
    start_date: date
    end_date: date


@dataclass(frozen=True)
class CubeVariant:
    """One of Arena's cubes. Arena swaps the cube itself every few sets and 17lands files each under
    its own expansion, so each variant gets its own board at ``CUBE-<slug>``. ``seasoned`` splits the
    variant's drafts into the per-set season boards in ``seasons``; the rest stay one flat board.
    """
    slug: str
    name: str
    expansion: str
    glyph: str
    seasoned: bool
    seasons: tuple[CubeSeason, ...] = ()


CUBE_CODE = "CUBE"

CUBE_VARIANTS_JSON = Path(__file__).resolve().parents[1] / "cube_variants.json"

CUBE_VARIANTS: tuple[CubeVariant, ...] = tuple(
    CubeVariant(
        slug=v["slug"],
        name=v["name"],
        expansion=v["expansion"],
        glyph=v["glyph"],
        seasoned=bool(v["seasoned"]),
        seasons=tuple(
            CubeSeason(
                set_code=s["set"],
                start_date=date.fromisoformat(s["start_date"]),
                end_date=date.fromisoformat(s["end_date"]),
            )
            for s in v.get("seasons", ())
        ),
    )
    for v in json.loads(CUBE_VARIANTS_JSON.read_text())["variants"]
)

CUBE_VARIANT_EXPANSIONS: tuple[str, ...] = tuple(v.expansion for v in CUBE_VARIANTS)

CUBE_SEASONS: tuple[tuple[CubeVariant, CubeSeason], ...] = tuple(
    (variant, season) for variant in CUBE_VARIANTS for season in variant.seasons
)


ALL_SETS: tuple[SetSeed, ...] = (
    SetSeed("DOM", "Dominaria", date(2018, 4, 26), date(2019, 4, 24)),
    SetSeed("WAR", "War of the Spark", date(2019, 4, 25), date(2019, 9, 25)),
    SetSeed("ELD", "Throne of Eldraine", date(2019, 9, 26), date(2020, 1, 15)),
    SetSeed("THB", "Theros Beyond Death", date(2020, 1, 16), date(2020, 4, 15)),
    SetSeed("IKO", "Ikoria: Lair of Behemoths", date(2020, 4, 16), date(2021, 1, 27)),
    SetSeed("KHM", "Kaldheim", date(2021, 1, 28), date(2021, 4, 14)),
    SetSeed("STX", "Strixhaven: School of Mages", date(2021, 4, 15), date(2021, 7, 7)),
    SetSeed("AFR", "Adventures in the Forgotten Realms", date(2021, 7, 8), date(2021, 9, 15)),
    SetSeed("MID", "Innistrad: Midnight Hunt", date(2021, 9, 16), date(2021, 11, 10)),
    SetSeed("VOW", "Innistrad: Crimson Vow", date(2021, 11, 11), date(2022, 2, 9)),
    SetSeed("NEO", "Kamigawa: Neon Dynasty", date(2022, 2, 10), date(2022, 4, 27)),
    SetSeed("SNC", "Streets of New Capenna", date(2022, 4, 28), date(2022, 7, 6)),
    SetSeed("HBG", "Alchemy Horizons: Baldur's Gate", date(2022, 7, 7), date(2022, 8, 31)),
    SetSeed("DMU", "Dominaria United", date(2022, 9, 1), date(2022, 11, 14)),
    SetSeed("BRO", "The Brothers' War", date(2022, 11, 15), date(2023, 2, 6)),
    SetSeed("ONE", "Phyrexia: All Will Be One", date(2023, 2, 7), date(2023, 3, 20)),
    SetSeed("SIR", "Shadows over Innistrad Remastered", date(2023, 3, 21), date(2023, 4, 17)),
    SetSeed("MOM", "March of the Machine", date(2023, 4, 18), date(2023, 6, 19), expansion_alias="MAT"),
    SetSeed("LTR", "The Lord of the Rings: Tales of Middle-earth", date(2023, 6, 20), date(2023, 9, 4)),
    SetSeed("WOE", "Wilds of Eldraine", date(2023, 9, 5), date(2023, 11, 13)),
    SetSeed("LCI", "The Lost Caverns of Ixalan", date(2023, 11, 14), date(2024, 2, 5)),
    SetSeed("KTK", "Khans of Tarkir", date(2023, 12, 12), date(2024, 2, 5)),
    SetSeed("MKM", "Murders at Karlov Manor", date(2024, 2, 6), date(2024, 4, 15)),
    SetSeed("OTJ", "Outlaws of Thunder Junction", date(2024, 4, 16), date(2024, 7, 29)),
    SetSeed("MH3", "Modern Horizons 3", date(2024, 6, 11), date(2024, 7, 29)),
    SetSeed("BLB", "Bloomburrow", date(2024, 7, 30), date(2024, 9, 23)),
    SetSeed("DSK", "Duskmourn: House of Horror", date(2024, 9, 24), date(2024, 11, 11)),
    SetSeed("FDN", "Foundations", date(2024, 11, 12), date(2025, 2, 10)),
    SetSeed("PIO", "Pioneer Masters", date(2024, 12, 10), date(2025, 2, 10)),
    SetSeed("DFT", "Aetherdrift", date(2025, 2, 11), date(2025, 4, 7)),
    SetSeed("TDM", "Tarkir: Dragonstorm", date(2025, 4, 8), date(2025, 6, 8)),
    SetSeed("FIN", "Final Fantasy", date(2025, 6, 9), date(2025, 7, 28)),
    SetSeed("EOE", "Edge of Eternities", date(2025, 7, 29), date(2025, 9, 23)),
    SetSeed("SPM", "Marvel's Spider-Man", date(2025, 9, 23), date(2025, 11, 15), expansion_alias="OM1"),
    SetSeed(CUBE_CODE, "Arena Powered Cube", date(2025, 10, 28), None, expansion_matches=CUBE_VARIANT_EXPANSIONS),
    SetSeed("TLA", "Avatar: The Last Airbender", date(2025, 11, 16), date(2026, 1, 19)),
    SetSeed("ECL", "Lorwyn Eclipsed", date(2026, 1, 20), date(2026, 3, 2)),
    SetSeed("TMT", "Teenage Mutant Ninja Turtles", date(2026, 3, 3), date(2026, 4, 20)),
    SetSeed("SOS", "Secrets of Strixhaven", date(2026, 4, 21), date(2026, 6, 22)),
    SetSeed("MSH", "Marvel Super Heroes", date(2026, 6, 23), date(2026, 8, 10), short_name="Marvel"),
    SetSeed("HOB", "The Hobbit", date(2026, 8, 11), date(2026, 9, 28), prerelease_date=date(2026, 8, 7)),
    SetSeed("FRA", "Reality Fracture", date(2026, 9, 29), date(2026, 11, 9), prerelease_date=date(2026, 9, 25)),
    SetSeed("TRE", "Star Trek", date(2026, 11, 10), date(2027, 1, 4), prerelease_date=date(2026, 11, 6)),
)

# MTGO-only flashback drafts, never on Arena; kept out of ALL_SETS so they never rotate or score
MTGO_FLASHBACK_SETS: dict[str, str] = {
    "IPA": "Invasion Block",
    "USG": "Urza Block",
    "MH1": "Modern Horizons",
    "MH2": "Modern Horizons 2",
}


def active_set_code(when: datetime | None = None) -> str:
    """Set code Arena is drafting at an instant: a set with an ``end_date`` whose window holds the
    instant, where the window runs from noon ET on ``start_date`` to noon ET the day after
    ``end_date`` (i.e. until the successor's release).
    Overlapping historical ranges (alchemy/masters sets nested inside a main set) resolve to the
    latest-started match; if no window holds the instant, the newest set already released wins so
    callers always get a real code."""
    now = when or datetime.now(timezone.utc)

    in_window: SetSeed | None = None
    for seed in ALL_SETS:
        if seed.end_date is None:
            continue
        if now < release_instant(seed.start_date) or now >= release_instant(seed.end_date + timedelta(days=1)):
            continue
        if in_window is None or seed.start_date > in_window.start_date:
            in_window = seed
    if in_window is not None:
        return in_window.code

    released: SetSeed | None = None
    for seed in ALL_SETS:
        if release_instant(seed.start_date) <= now and (released is None or seed.start_date > released.start_date):
            released = seed
    return (released or ALL_SETS[-1]).code


def previous_set_code(code: str) -> str | None:
    """The leaderboard set active immediately before `code` released — the season whose championship
    most recently crowned the reigning champion. None when `code` is unknown or the earliest set."""
    upper = code.upper()
    codes = [s.code for s in ALL_SETS]
    if upper not in codes:
        return None
    seed = ALL_SETS[codes.index(upper)]
    just_before = release_instant(seed.start_date) - timedelta(seconds=1)
    if just_before < release_instant(ALL_SETS[0].start_date):
        return None
    return active_set_code(just_before)


def released_sets(when: datetime | None = None) -> tuple[SetSeed, ...]:
    """Sets whose Arena release instant has passed, newest first."""
    now = when or datetime.now(timezone.utc)
    released = [seed for seed in ALL_SETS if release_instant(seed.start_date) <= now]
    return tuple(reversed(released))


def prerelease_date_for(seed: SetSeed) -> date:
    """First day of a set's paper prerelease weekend, falling back to the Friday before its Arena
    release for sets that carry no recorded date."""
    if seed.prerelease_date is not None:
        return seed.prerelease_date
    return previous_weekday(seed.start_date, FRIDAY)


def prerelease_instant(seed: SetSeed) -> datetime:
    """Midnight ET on the prerelease date — the moment a set counts as playable, so early prerelease
    events on the eve are covered."""
    return datetime.combine(prerelease_date_for(seed), time(0, 0), tzinfo=RELEASE_TZ).astimezone(timezone.utc)


def prereleased_sets(when: datetime | None = None) -> tuple[SetSeed, ...]:
    """Sets whose prerelease weekend has started, newest first — everything a player can hold cards
    from, which runs days ahead of ``released_sets`` while the newest set is still in prerelease."""
    now = when or datetime.now(timezone.utc)
    out = [seed for seed in ALL_SETS if prerelease_instant(seed) <= now]
    return tuple(reversed(out))


def upcoming_sets(when: datetime | None = None) -> tuple[SetSeed, ...]:
    """Registered sets that rotate in after the active one — not yet the leaderboard set, but
    draftable for pod/mock previews. Empty once the active set is the newest entry."""
    active = active_set_code(when)
    codes = [s.code for s in ALL_SETS]
    if active not in codes:
        return ()
    return ALL_SETS[codes.index(active) + 1:]


def preview_set_code(when: datetime | None = None) -> str:
    """The set mock drafts are for: the nearest set still in preview season, falling back to the active
    set once nothing newer is registered. Drives the mock-draft card preview and the Mock Draft role
    symbol, so both rotate with spoiler season on their own."""
    upcoming = upcoming_sets(when)
    if upcoming:
        return upcoming[0].code
    return active_set_code(when)


def recent_released_sets(limit: int = 8, when: datetime | None = None) -> tuple[SetSeed, ...]:
    """Released sets other than the active one, newest first, capped at `limit` — the pool a set
    picker offers below the active set. Unreleased upcoming sets are excluded (no card pool to draft)."""
    active = active_set_code(when)
    others = [seed for seed in released_sets(when) if seed.code != active]
    return tuple(others[:limit])


def is_known_set(code: str) -> bool:
    return any(s.code == code.upper() for s in ALL_SETS)


def is_mtgo_flashback_code(code: str) -> bool:
    return code.upper() in MTGO_FLASHBACK_SETS


@dataclass(frozen=True)
class CollectorBoosterWindow:
    set_code: str
    start_date: date
    end_date: date


# Arena Direct box payouts. Current (7-win format):
# - play booster direct: the trophy pays 2 boxes, a 6-win finish pays 1
# - collector booster direct: 1 box for the trophy
# History:
# - 2024 sets: play booster directs on a 6-win format, the trophy pays 2 boxes
# - DFT: collector booster direct on a 6-win format, 1 box for the trophy
# - TDM: the 7-win format rolled out mid-set, so its collector booster direct stayed at 6 wins
# boxes_for_event keys off 17lands is_trophy, so the win cap is never hardcoded.
SIX_WIN_PLAY_DIRECT_SETS = frozenset({"OTJ", "FDN", "BLB", "DSK"})
SIX_WIN_COLLECTOR_DIRECT_SETS = frozenset({"DFT"})

COLLECTOR_BOOSTER_WINDOWS: tuple[CollectorBoosterWindow, ...] = (
    CollectorBoosterWindow("TDM", date(2025, 4, 18), date(2025, 4, 20)),
    CollectorBoosterWindow("FIN", date(2025, 6, 20), date(2025, 6, 22)),
    CollectorBoosterWindow("EOE", date(2025, 8, 8), date(2025, 8, 11)),
    CollectorBoosterWindow("TLA", date(2025, 11, 28), date(2025, 11, 30)),
    CollectorBoosterWindow("ECL", date(2026, 1, 30), date(2026, 2, 1)),
    CollectorBoosterWindow("TMT", date(2026, 3, 13), date(2026, 3, 15)),
    CollectorBoosterWindow("SOS", date(2026, 4, 30), date(2026, 5, 4)),
    CollectorBoosterWindow("MSH", date(2026, 6, 30), date(2026, 7, 6)),
    CollectorBoosterWindow("HOB", date(2026, 8, 14), date(2026, 8, 23)),
)

# Windows widen by a day each side so a draft finished just before/after the
# scheduled weekend still resolves to the collector payout.
COLLECTOR_WINDOW_SLACK = timedelta(days=1)


def is_collector_booster_window(set_code: str, when: date) -> bool:
    for w in COLLECTOR_BOOSTER_WINDOWS:
        if w.set_code != set_code:
            continue
        if w.start_date - COLLECTOR_WINDOW_SLACK <= when <= w.end_date + COLLECTOR_WINDOW_SLACK:
            return True
    return False


@dataclass(frozen=True)
class PreviewWindow:
    set_code: str
    start_date: date
    end_date: date


# Spoiler-season day ranges, inclusive on both ends, interpreted in US Eastern time.
# Independent of ALL_SETS — a set gets its window before it joins the rotation.
PREVIEW_WINDOWS: tuple[PreviewWindow, ...] = (
    PreviewWindow("MSH", date(2026, 6, 2), date(2026, 6, 8)),
    PreviewWindow("HOB", date(2026, 7, 18), date(2026, 7, 31)),
)


EXPANSION_ALIASES: dict[str, str] = {
    s.expansion_alias: s.code for s in ALL_SETS if s.expansion_alias
}

EXPANSION_ROUTES: dict[str, str] = {
    match: s.code for s in ALL_SETS for match in s.expansion_matches
}


def normalize_expansion(expansion: str) -> str:
    return EXPANSION_ALIASES.get(expansion, expansion)


def set_code_for_expansion(expansion: str) -> str | None:
    """The set an exactly-named 17lands expansion belongs to, for expansions kept verbatim on their
    events (the cube variants). ``None`` when the expansion carries no explicit route, leaving the
    caller's substring match on the set code to resolve it."""
    return EXPANSION_ROUTES.get(expansion)


def set_name_for(code: str) -> str:
    """Full set name for a code (e.g. SOS -> "Secrets of Strixhaven"); the bare code if unknown."""
    upper = code.upper()
    for s in ALL_SETS:
        if s.code == upper:
            return s.name
    return MTGO_FLASHBACK_SETS.get(upper, upper)


def set_short_name_for(code: str) -> str:
    """How the set is said out loud (MSH -> "Marvel"), falling back to the full name where no set
    carries a short one."""
    upper = code.upper()
    for s in ALL_SETS:
        if s.code == upper:
            return s.short_name or s.name
    return set_name_for(upper)


def cube_variant(slug: str) -> CubeVariant | None:
    upper = slug.upper()
    for variant in CUBE_VARIANTS:
        if variant.slug == upper:
            return variant
    return None


def cube_variant_for_expansion(expansion: str) -> CubeVariant | None:
    for variant in CUBE_VARIANTS:
        if variant.expansion == expansion:
            return variant
    return None


def seasoned_cube_variant() -> CubeVariant:
    """The cube whose drafts split into per-set season boards. It is the family's flagship, so a
    season code with no cube named (``CUBE-SOS``) belongs to it."""
    for variant in CUBE_VARIANTS:
        if variant.seasoned:
            return variant
    return CUBE_VARIANTS[0]


def cube_board_code(slug: str) -> str:
    return f"{CUBE_CODE}-{slug.upper()}"


def is_cube_board_code(code: str) -> bool:
    """Whether a set code names a cube board: bare ``CUBE``, a whole cube (``CUBE-PLANAR``) or one
    of the seasoned cube's per-set seasons (``CUBE-SOS``)."""
    upper = code.upper()
    return upper == CUBE_CODE or upper.startswith(f"{CUBE_CODE}-")


def cube_variant_for_board(code: str) -> CubeVariant | None:
    """The cube a whole-cube board code names. None for bare ``CUBE`` and for season boards."""
    upper = code.upper()
    if not upper.startswith(f"{CUBE_CODE}-"):
        return None
    return cube_variant(upper.removeprefix(f"{CUBE_CODE}-"))


def cube_list_name(variant: CubeVariant) -> str:
    """A cube's name where the boards list together: the leading "Arena" drops when what remains
    still names the cube, so they read as WORD+CUBE siblings. Mirrors cubeListName on the site."""
    without_arena = variant.name.removeprefix("Arena ")
    return without_arena if len(without_arena.split()) >= 2 else variant.name


def cube_glyph_emoji_name(variant: CubeVariant) -> str:
    """Application-emoji name for a cube's glyph, matching what upload_app_emojis uploads it as."""
    return variant.glyph.split(":", 1)[-1]


def parse_caption_set_code(caption: str | None) -> str | None:
    """Set code named in a trophy caption, matching known codes and set names — e.g.
    'MH1 flashback 3-0' -> 'MH1', "Urza's Saga trophy" -> 'USG'. Codes match only as
    uppercase-written tokens so ordinary words don't resolve to a code; names match
    case-insensitively, longest first. Returns None when nothing matches, letting the
    caller fall back to the active set."""
    if not caption:
        return None

    codes = {s.code for s in ALL_SETS} | set(MTGO_FLASHBACK_SETS)
    for token in re.findall(r"[A-Za-z0-9]+", caption):
        if token.isupper() and token in codes:
            return token

    names = {s.name.lower(): s.code for s in ALL_SETS}
    names.update({name.lower(): code for code, name in MTGO_FLASHBACK_SETS.items()})
    for name, code in list(names.items()):
        base = re.sub(r"\s+(block|draft)$", "", name)
        names.setdefault(base, code)
    lowered = caption.lower()
    for name in sorted(names, key=len, reverse=True):
        if re.search(rf"\b{re.escape(name)}\b", lowered):
            return names[name]
    return None
