"""Rebuild ``player_stats`` from ``draft_events`` for every active player.

    DATABASE_URL=postgresql://... python -m bot.scripts.rebuild_player_stats

No 17lands HTTP. Pure SQL re-aggregation against existing ``draft_events`` rows.

Use cases:
  - Restoring after a refresh that wrote a narrow window into ``player_stats``
    (the additive ``draft_events`` rows survive — this rebuilds the aggregates).
  - Adding new format strings to scoring_buckets.json without re-pulling 17lands.
  - Sanity check that ``player_stats`` matches ``draft_events``.

Per-player commit boundary so a mid-run crash keeps already-rebuilt rows.
"""
from __future__ import annotations

import logging
import time as _time

from sqlalchemy import distinct, select

from bot.database import SessionLocal
from bot.models import DraftEvent, Player
from bot.services.refresh import rebuild_player_stats

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
log = logging.getLogger("rebuild")


def main() -> None:
    t0 = _time.monotonic()
    with SessionLocal() as session:
        players = session.execute(
            select(Player).where(Player.active.is_(True))
        ).scalars().all()
        log.info(f"rebuilding stats for {len(players)} active players")

        total_pairs = 0
        for player in players:
            routed = DraftEvent.set_id.isnot(None)
            set_ids = session.execute(
                select(distinct(DraftEvent.set_id)).where(DraftEvent.player_id == player.id, routed)
            ).scalars().all()

            for set_id in set_ids:
                rebuild_player_stats(session, player.id, set_id)

            session.commit()
            total_pairs += len(set_ids)
            log.info(f"  {player.display_name}: rebuilt {len(set_ids)} (player, set) pairs")

    log.info(f"done. pairs={total_pairs} elapsed={_time.monotonic() - t0:.1f}s")


if __name__ == "__main__":
    main()
