from __future__ import annotations

import argparse

from sqlalchemy import select

from bot.database import SessionLocal
from bot.models import FantasyPlayer
from bot.services.fantasy_event import STAGE_FINAL, STAGE_QUARTERFINAL, STAGE_SEMIFINAL, event_for
from bot.services.fantasy_sync import record_top8_result
from bot.services.melee import MeleeClient


def main() -> None:
    parser = argparse.ArgumentParser(description="Enter a Top 8 result Melee has not posted yet")
    parser.add_argument("event_code")
    parser.add_argument("stage", choices=(STAGE_QUARTERFINAL, STAGE_SEMIFINAL, STAGE_FINAL))
    parser.add_argument("winner_slug")
    parser.add_argument("loser_slug")
    parser.add_argument("score", help="games won by the winner and the loser, like 3-1")
    parser.add_argument("--commit", action="store_true", help="write the result; without it the run rolls back")
    args = parser.parse_args()

    event = event_for(args.event_code)
    if event is None:
        raise SystemExit(f"no fantasy event {args.event_code!r} in fantasy_events.json")
    winner_games, loser_games = (int(games) for games in args.score.split("-"))
    with SessionLocal() as session:
        winner = player_by_slug(session, event.code, args.winner_slug)
        loser = player_by_slug(session, event.code, args.loser_slug)
        position = record_top8_result(
            session, event, MeleeClient(), args.stage, winner, loser, (winner_games, loser_games),
        )
        if args.commit:
            session.commit()
        else:
            session.rollback()
    outcome = "saved" if args.commit else "dry run, rolled back"
    print(f"{event.code} {position}: {args.winner_slug} beat {args.loser_slug} {args.score} ({outcome})")


def player_by_slug(session, event_code: str, slug: str) -> FantasyPlayer:
    player = session.scalar(
        select(FantasyPlayer).where(FantasyPlayer.event_code == event_code, FantasyPlayer.slug == slug)
    )
    if player is None:
        raise SystemExit(f"no player {slug!r} in {event_code}")
    return player


if __name__ == "__main__":
    main()
