"""Slug derivation for `players.slug`.

Rule:
  1. Lowercase the display_name.
  2. Replace runs of any non-[a-z0-9] characters with a single `-`.
  3. Trim leading/trailing `-`.
  4. If the result is empty (e.g. all-emoji name), fall back to
     `player-{first 8 chars of players.id}`.
  5. Collisions are resolved by the caller via `disambiguate_slug` — append
     `-2`, `-3`, ... until unique.

Frozen at first sight: renames don't update the slug. URLs stay stable.
"""
from __future__ import annotations

import re
from typing import Iterable


_NON_ALNUM = re.compile(r"[^a-z0-9]+")


def slugify(display_name: str, player_id: str = "") -> str:
    """Return the base slug for a display_name. Never returns empty string."""
    s = _NON_ALNUM.sub("-", display_name.lower()).strip("-")
    if s:
        return s
    fallback_seed = player_id[:8] if player_id else "x"
    return f"player-{fallback_seed}"


def disambiguate_slug(base: str, taken: Iterable[str]) -> str:
    """Append -2/-3/... until the result isn't in `taken`. Returns base unchanged
    if no collision. The caller is responsible for adding the chosen slug to
    `taken` before checking the next candidate."""
    taken_set = set(taken)
    if base not in taken_set:
        return base
    n = 2
    while f"{base}-{n}" in taken_set:
        n += 1
    return f"{base}-{n}"
