"""Debug: list who has voted in the P0P1 contest, by Discord name.

    DATABASE_URL=$SUPABASE_DB_URL python -m bot.scripts.p0p1_voters [--set CODE]

``user_id`` on ``p0p1_entries`` references ``auth.users(id)`` (the Supabase
Discord-OAuth identity), so name resolution lives in the ``auth`` schema and
only works against prod with the service-role pooler URL — local dev has no
``auth`` schema. Names resolve through the ``players`` join when the voter has
joined the leaderboard, falling back to the Discord OAuth metadata otherwise.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from sqlalchemy import text

from bot.database import engine

CONTESTS_JSON = Path(__file__).resolve().parents[2] / "p0p1_contests.json"


def full_ballot_slots(set_code: str) -> int:
    """A full ballot is 8 slots on layout 1, 12 on layout 2, keyed off p0p1_contests.json."""
    contests = json.loads(CONTESTS_JSON.read_text()) if CONTESTS_JSON.exists() else {}
    layout = contests.get(set_code, {}).get("layout", 1)
    return 12 if layout >= 2 else 8

VOTERS_SQL = text("""
    select
      coalesce(p.display_name,
               u.raw_user_meta_data->>'full_name',
               u.raw_user_meta_data->>'user_name',
               u.email)                      as name,
      e.set_code                             as set_code,
      count(*)                               as picks,
      max(e.updated_at)                      as last_pick
    from p0p1_entries e
    join auth.users u on u.id = e.user_id
    left join auth.identities i on i.user_id = u.id and i.provider = 'discord'
    left join players p on p.discord_id = i.provider_id
    where (:set_code is null or e.set_code = :set_code)
    group by 1, 2
    order by last_pick desc
""")


def main() -> None:
    parser = argparse.ArgumentParser(description="List P0P1 voters by Discord name.")
    parser.add_argument("--set", dest="set_code", default=None, help="Filter to one set code (default: all)")
    args = parser.parse_args()

    set_code = args.set_code.upper() if args.set_code else None

    with engine.connect() as conn:
        rows = conn.execute(VOTERS_SQL, {"set_code": set_code}).all()

    if not rows:
        print("No P0P1 votes found.")
        return

    print(f"{len(rows)} voter/set rows\n")
    for name, set_value, picks, last_pick in rows:
        full = full_ballot_slots(set_value)
        flag = "" if picks >= full else f"  (incomplete, {picks}/{full})"
        stamp = last_pick.strftime("%Y-%m-%d %H:%M") if last_pick else "?"
        print(f"{name or '?':24} {set_value:6} {picks} picks  last={stamp}{flag}")


if __name__ == "__main__":
    main()
