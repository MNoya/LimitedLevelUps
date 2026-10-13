"""Export a locally staged fantasy event as the static demo the site's DEMO presets read before an event has results

    DATABASE_URL=postgresql://postgres:devpw@localhost:5433/dischord \\
        python -m bot.scripts.fantasy_demo_snapshot

Stage the event first with `fantasy_dry_run --through-round 17 --revealed 17`.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from sqlalchemy import text

from bot.config import settings
from bot.database import SessionLocal
from bot.scripts.local_supabase_proxy import DEV_JWT_CLAIMS, DEV_USER_ID

OUTPUT = Path(__file__).resolve().parents[2] / "frontend" / "src" / "data" / "fantasyDemo.json"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--event", default="WC32")
    args = parser.parse_args()
    if not any(host in settings.database_url for host in ("localhost", "127.0.0.1")):
        raise SystemExit("fantasy_demo_snapshot reads a staged dry run, so it only runs against a local database")

    queries = {
        "field": """
            SELECT id, slug, first_name AS "firstName", last_name AS "lastName", short_name AS "shortName", country,
                   country_code AS "countryCode", sources, photo_url AS "photoUrl", deck_name AS "deckName",
                   decklist_id AS "decklistId"
            FROM public_fantasy_players WHERE event_code = :event ORDER BY id
        """,
        "results": """
            SELECT round_number AS round, player_id AS "playerId", opponent_id AS "opponentId", stage, result,
                   game_wins AS "gameWins", game_losses AS "gameLosses", game_draws AS "gameDraws", is_bye AS "isBye",
                   bracket_position AS "bracketPosition"
            FROM public_fantasy_results WHERE event_code = :event ORDER BY round_number, player_id
        """,
        "members": """
            SELECT member_key AS "memberKey", is_me AS "isMe", name, avatar_url AS "avatarUrl", rank
            FROM public_fantasy_standings WHERE event_code = :event ORDER BY rank
        """,
        "lineups": """
            SELECT member_key AS "memberKey", is_me AS "isMe", slot, from_round AS "fromRound", player_id AS "playerId"
            FROM public_fantasy_lineups WHERE event_code = :event
        """,
        "brackets": """
            SELECT member_key AS "memberKey", is_me AS "isMe", position, winner_id AS "winnerId", games
            FROM public_fantasy_bracket_picks WHERE event_code = :event
        """,
        "ownLineup": """
            SELECT slot, player_id AS "playerId", from_round AS "fromRound"
            FROM fantasy_picks WHERE event_code = :event AND user_id = CAST(:user AS uuid)
        """,
        "ownBracket": """
            SELECT position, winner_id AS "winnerId", games
            FROM fantasy_bracket_picks WHERE event_code = :event AND user_id = CAST(:user AS uuid)
        """,
    }
    with SessionLocal() as session:
        session.execute(text("SELECT set_config('request.jwt.claims', :claims, false)"), {"claims": DEV_JWT_CLAIMS})
        snapshot = {key: rows(session, sql, args.event) for key, sql in queries.items()}
    for member in snapshot["members"]:
        if member["isMe"]:
            member["name"] = "Demo Player"
    if not snapshot["results"]:
        raise SystemExit(f"{args.event} has no results, so stage it with fantasy_dry_run first")
    OUTPUT.write_text(json.dumps(snapshot, ensure_ascii=False, separators=(",", ":")) + "\n")
    counts = ", ".join(f"{len(value)} {key}" for key, value in snapshot.items())
    print(f"wrote {OUTPUT.relative_to(OUTPUT.parents[3])}: {counts}")


def rows(session, sql: str, event_code: str) -> list[dict]:
    return [dict(row) for row in session.execute(text(sql), {"event": event_code, "user": DEV_USER_ID}).mappings()]


if __name__ == "__main__":
    main()
