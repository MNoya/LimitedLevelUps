"""Debug: fetch a single player's drafts from 17lands for a set and print them.

    DATABASE_URL=postgresql://... python -m bot.scripts.fetch_player <identifier> [--set CODE]

``identifier`` is either a Discord username substring (resolved against the
``players`` table) or a raw 32-hex 17lands token. ``--set ALL`` skips the
expansion filter and reports the player's full draft history.
"""
from __future__ import annotations

import argparse
import re
import sys

from sqlalchemy import or_, select

from bot.database import SessionLocal
from bot.models import Player
from bot.scoring import DEFAULT_QUEUE_GROUPS
from bot.services.seventeenlands import SeventeenLandsClient, event_is_trophy
from bot.sets import ALL_SETS, SetSeed, active_set_code

_TOKEN_RE = re.compile(r"^[a-f0-9]{32}$")

SUPPORTED_FORMATS = {fmt for g in DEFAULT_QUEUE_GROUPS for fmt in g.formats}


def _resolve_set(code: str) -> SetSeed | None:
    target = code.upper()
    for s in ALL_SETS:
        if s.code == target:
            return s
    return None


def _resolve_token(identifier: str) -> tuple[str, str]:
    """Return (token, display_label). Hits the DB unless identifier is a raw token."""
    if _TOKEN_RE.match(identifier.strip().lower()):
        token = identifier.strip().lower()
        return token, f"token …{token[-4:]}"

    needle = f"%{identifier}%"
    with SessionLocal() as session:
        player = session.execute(
            select(Player).where(
                or_(
                    Player.discord_username.ilike(needle),
                    Player.display_name.ilike(needle),
                )
            )
        ).scalars().first()
    if player is None:
        print(f"no player matched {identifier!r}", file=sys.stderr)
        sys.exit(1)
    if not player.seventeenlands_token:
        print(f"player {player.display_name!r} has no 17lands token on file", file=sys.stderr)
        sys.exit(1)
    return player.seventeenlands_token, player.display_name


def main() -> None:
    active = active_set_code()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("identifier", help="Discord username substring or raw 32-hex 17lands token")
    parser.add_argument(
        "--set",
        default=active,
        help=f"3-4 letter set code (default: {active}). Pass ALL for full history.",
    )
    args = parser.parse_args()

    token, label = _resolve_token(args.identifier)

    set_code = args.set.upper()
    if set_code == "ALL":
        scope = "all sets"
        start_date = None
        end_date = None
        expansions: list[str | None] = [None]
    else:
        seed = _resolve_set(set_code)
        if seed is None:
            print(f"unknown set code {set_code!r}", file=sys.stderr)
            sys.exit(1)
        scope = f"{seed.code} ({seed.start_date} → {seed.end_date or 'open'})"
        start_date = seed.start_date
        end_date = seed.end_date
        expansions = list(seed.expansion_matches) or [seed.expansion_alias or seed.code]

    client = SeventeenLandsClient()
    drafts: list[dict] = []
    for expansion in expansions:
        drafts += client.fetch_drafts(
            token,
            start_date=start_date,
            end_date=end_date,
            expansion=expansion,
        )

    print(f"player: {label}")
    print(f"scope:  {scope}")
    print(f"total drafts: {len(drafts)}")

    if not drafts:
        return

    counts: dict[str, int] = {}
    for d in drafts:
        fmt = d.get("format") or "?"
        counts[fmt] = counts.get(fmt, 0) + 1
    print("\nformat breakdown:")
    for fmt, n in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])):
        marker = "" if fmt in SUPPORTED_FORMATS else "  ⚠️ unsupported"
        print(f"  {fmt:42s} {n:4d}{marker}")

    print("\nevents:")
    sorted_drafts = sorted(drafts, key=lambda d: d.get("first_event_server_time") or "")
    for d in sorted_drafts:
        fmt = d.get("format") or "?"
        when = (d.get("first_event_server_time") or "")[:16]
        wins = d.get("wins", 0)
        losses = d.get("losses", 0)
        colors = d.get("colors") or "--"
        trophy = "🏆" if event_is_trophy(d) else "  "
        unsupp = " ⚠️" if fmt not in SUPPORTED_FORMATS else ""
        exp = d.get("expansion") or "?"
        print(f"  {trophy} {when}  {exp:8s} {fmt:34s} {colors:6s} {wins}-{losses}{unsupp}")


if __name__ == "__main__":
    main()
