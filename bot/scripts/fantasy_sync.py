"""Sync a fantasy event's field and Melee results into the fantasy tables

    DATABASE_URL=... python -m bot.scripts.fantasy_sync WC32
    DATABASE_URL=... python -m bot.scripts.fantasy_sync PTMSH --through-round 8 --offline
"""
from __future__ import annotations

import argparse
import logging
from pathlib import Path

from bot.database import SessionLocal
from bot.services.fantasy_event import event_for
from bot.services.fantasy_sync import sync_event
from bot.services.melee import MeleeClient

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger("fantasy_sync")

CACHE_ROOT = Path("/tmp/fantasy/melee")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("event_code")
    parser.add_argument("--through-round", type=int, default=None)
    parser.add_argument("--full", action="store_true")
    parser.add_argument("--offline", action="store_true")
    args = parser.parse_args()

    event = event_for(args.event_code)
    if event is None:
        raise SystemExit(f"no fantasy event {args.event_code!r} in fantasy_events.json")
    client = MeleeClient(cache_dir=CACHE_ROOT / str(event.melee_tournament_id), offline=args.offline)
    with SessionLocal() as session:
        summary = sync_event(session, event, client, through_round=args.through_round, full=args.full)
    log.info(f"done. rounds={summary.rounds_synced} results={summary.results_written}")
    for name in summary.players_added:
        log.info(f"added from Melee: {name}")


if __name__ == "__main__":
    main()
