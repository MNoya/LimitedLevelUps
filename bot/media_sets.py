"""Content-set catalog for the episode feed — every set the channel makes content about.

Broader than the leaderboard's tracked sets (``bot/sets.py``): the podcast and YouTube cover
sets LLU never ran a leaderboard for, plus a Cube pseudo-set and an Evergreen bucket for
set-agnostic content. Episode set tagging resolves against this catalog so the Episodes page
can partition the whole back-catalogue by set. Leaderboard rotation stays independent — nothing
here feeds scoring.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date

from bot.sets import ALL_SETS


@dataclass(frozen=True)
class MediaSet:
    code: str
    name: str
    aliases: tuple[str, ...] = ()
    start_date: date | None = None


EVERGREEN = MediaSet("EVG", "Evergreen")

# Sets the channel covers that the leaderboard doesn't track — recent crossovers/supplemental
# products plus the pre-2021 back-catalogue the podcast still references. Names mirror the
# YouTube playlist / episode-title phrasing so playlist- and title-based tagging resolve them.
_EXTRA_MEDIA_SETS: tuple[MediaSet, ...] = (
    MediaSet("NEO", "Kamigawa: Neon Dynasty", start_date=date(2022, 2, 10)),
    MediaSet("SNC", "Streets of New Capenna", aliases=("new capenna",), start_date=date(2022, 4, 28)),
    MediaSet("MH3", "Modern Horizons 3", start_date=date(2024, 6, 11)),
    MediaSet("PIO", "Pioneer Masters", start_date=date(2024, 12, 10)),
    MediaSet("ZNR", "Zendikar Rising", aliases=("zendikar rising", "zendikar"), start_date=date(2020, 9, 17)),
    MediaSet("THB", "Theros Beyond Death", aliases=("theros beyond death", "theros", "thb"),
             start_date=date(2020, 1, 16)),
    MediaSet("IKO", "Ikoria: Lair of Behemoths", aliases=("ikoria",), start_date=date(2020, 4, 16)),
    MediaSet("M21", "Core Set 2021", aliases=("core set 2021", "m21"), start_date=date(2020, 6, 25)),
    MediaSet("AFR", "Adventures in the Forgotten Realms", aliases=("forgotten realms", "afr"),
             start_date=date(2021, 7, 8)),
    MediaSet("MID", "Innistrad: Midnight Hunt", aliases=("midnight hunt",), start_date=date(2021, 9, 16)),
    MediaSet("VOW", "Innistrad: Crimson Vow", aliases=("crimson vow",), start_date=date(2021, 11, 11)),
    MediaSet("DMU", "Dominaria United", aliases=("dominaria united",), start_date=date(2022, 9, 1)),
    MediaSet("BRO", "The Brothers' War", aliases=("brothers war", "brothers' war"), start_date=date(2022, 11, 15)),
    MediaSet("ONE", "Phyrexia: All Will Be One", aliases=("phyrexia", "all will be one"), start_date=date(2023, 2, 7)),
    MediaSet("MOM", "March of the Machine", aliases=("march of the machine",), start_date=date(2023, 4, 18)),
    MediaSet("LTR", "The Lord of the Rings", aliases=("lord of the rings", "middle earth"),
             start_date=date(2023, 6, 20)),
    MediaSet("SIR", "Shadows over Innistrad Remastered", aliases=("shadows over innistrad",),
             start_date=date(2023, 3, 21)),
    MediaSet("HBG", "Battle for Baldur's Gate", aliases=("baldur's gate", "baldurs gate"), start_date=date(2022, 7, 7)),
)

# Extra match aliases for sets the playlists and short-form titles name colloquially rather than
# by canonical name ("Lorwyn" for Lorwyn Eclipsed, "New Capenna" for Streets of New Capenna).
_ALIASES_BY_CODE: dict[str, tuple[str, ...]] = {
    "CUBE": ("powered cube", "arena cube", "the cube", "cube"),
    "DSK": ("duskmorne", "duskmourn"),
    "ECL": ("lorwyn",),
    "WOE": ("eldraine",),
    "OTJ": ("thunder junction",),
    "MKM": ("karlov manor",),
    "SNC": ("new capenna",),
    "SPM": ("spider-man", "spiderman", "through the omenpaths"),
    "TMT": ("ninja turtles", "tmnt"),
    "LCI": ("lost caverns of ixalan", "lost caverns"),
}

# Playlist names append a role suffix to the set name ("Bloomburrow Set Review", "OTJ Draft
# Videos"); strip the longest matching suffix to recover the bare set name. Longest first.
_PLAYLIST_SUFFIXES: tuple[str, ...] = (
    "set review 2",
    "set review",
    "draft coaching video",
    "draft coaching",
    "draft classes",
    "draft videos",
    "videos",
    "draft",
)


def resolve_set(playlists: list[str], title: str, published: date | None = None) -> MediaSet:
    """The title names the episode's own subject; playlists are the fallback for generically
    titled videos, and can cross-list one episode under several sets, so the title wins."""
    media_set = _from_title(title) or _from_playlists(playlists) or EVERGREEN
    # "Strixhaven" is shared by STX (2021) and SOS (2026) — 2026 content is Secrets of Strixhaven
    if media_set.code == "STX" and published is not None and published.year >= 2026:
        return _BY_CODE["SOS"]
    return media_set


def by_code(code: str) -> MediaSet:
    return _BY_CODE[code]


def display_name(code: str | None) -> str:
    if code is None:
        return EVERGREEN.name
    return _BY_CODE[code].name if code in _BY_CODE else code


def _build_catalog() -> tuple[MediaSet, ...]:
    seen: set[str] = set()
    catalog: list[MediaSet] = []
    for seed in ALL_SETS:
        catalog.append(MediaSet(seed.code, seed.name, _ALIASES_BY_CODE.get(seed.code, ()), seed.start_date))
        seen.add(seed.code)
    for media_set in _EXTRA_MEDIA_SETS:
        if media_set.code not in seen:
            catalog.append(media_set)
            seen.add(media_set.code)
    catalog.append(EVERGREEN)
    return tuple(catalog)


def _name_keys() -> dict[str, str]:
    keys: dict[str, str] = {}
    for media_set in MEDIA_SETS:
        if media_set.code == EVERGREEN.code:
            continue
        keys[_normalize(media_set.name)] = media_set.code
        keys.setdefault(_normalize(media_set.name.split(":")[0]), media_set.code)
        for alias in media_set.aliases:
            keys[_normalize(alias)] = media_set.code
    return keys


def _from_playlists(playlists: list[str]) -> MediaSet | None:
    for name in playlists:
        norm = _normalize(name)
        for suffix in _PLAYLIST_SUFFIXES:
            if norm.endswith(suffix):
                norm = norm[: -len(suffix)].strip()
                break
        if not norm:
            continue
        if norm in _NAME_KEYS:
            return _BY_CODE[_NAME_KEYS[norm]]
        aliased = _alias_in(norm)
        if aliased:
            return aliased
    return None


def _from_title(title: str) -> MediaSet | None:
    norm = _normalize(title)
    best_code: str | None = None
    best_len = 0
    for key, code in _NAME_KEYS.items():
        if len(key) > best_len and re.search(rf"\b{re.escape(key)}\b", norm):
            best_code = code
            best_len = len(key)
    return _BY_CODE[best_code] if best_code else None


def _alias_in(norm: str) -> MediaSet | None:
    for media_set in MEDIA_SETS:
        for alias in media_set.aliases:
            if _normalize(alias) in norm:
                return media_set
    return None


def _normalize(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()


MEDIA_SETS = _build_catalog()
_BY_CODE = {m.code: m for m in MEDIA_SETS}
_NAME_KEYS = _name_keys()
