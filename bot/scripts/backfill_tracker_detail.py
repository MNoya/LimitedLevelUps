"""On-demand 17lands per-draft detail backfill for tracker users. Console-only.

    DATABASE_URL=postgresql://... python -m bot.scripts.backfill_tracker_detail --set HOB [--apply]

A tracker user fills the current board set on demand from the site refresh button; this fills an
older set from the console, so you decide when to spend the 17lands requests on history. Two requests
per draft, paced apart. Dry-run by default, prints how many drafts would be fetched. Pass --apply to run it.
"""
from __future__ import annotations

import argparse
import logging

from sqlalchemy import select

from bot.config import settings
from bot.database import SessionLocal
from bot.models import Player
from bot.services.tracker_detail import pending_draft_ids, fill_pending_draft_detail

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger("backfill")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--set", dest="set_code", required=True, help="set code to backfill, e.g. HOB")
    parser.add_argument("--discord-id", default=None, help="one tracker user (default: every configured tracker id)")
    parser.add_argument("--cap", type=int, default=None, help="max drafts to fetch this run (default: all pending)")
    parser.add_argument("--apply", action="store_true", help="fetch and write; omit for a dry run")
    args = parser.parse_args()

    discord_ids = [args.discord_id] if args.discord_id else sorted(settings.tracker_discord_ids_set)
    with SessionLocal() as session:
        for discord_id in discord_ids:
            player = session.execute(select(Player).where(Player.discord_id == discord_id)).scalar_one_or_none()
            if player is None:
                log.info(f"no player for discord id {discord_id}")
                continue
            pending = pending_draft_ids(session, player.id, args.set_code, args.cap)
            log.info(f"{player.display_name} {args.set_code}: {len(pending)} draft(s) pending detail")
            if not args.apply:
                continue
            result = fill_pending_draft_detail(session, player.id, set_code=args.set_code, cap=args.cap)
            log.info(f"{player.display_name} {args.set_code}: filled={result['filled']} missed={result['missed']}")

    if not args.apply:
        log.info("dry run — re-run with --apply to fetch and write")


if __name__ == "__main__":
    main()
