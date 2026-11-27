from __future__ import annotations

import logging
from time import sleep

from sqlalchemy import select

from bot.database import SessionLocal
from bot.models import DailySealedPool, DraftEvent
from bot.services.daily_sealed import FETCH_SPACING_S, fetch_17lands_deck, pool_from_deck

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
log = logging.getLogger("backfill_daily_sealed_basics")


def main() -> None:
    with SessionLocal() as session:
        rows = session.execute(
            select(DailySealedPool, DraftEvent.seventeenlands_event_id)
            .join(DraftEvent, DraftEvent.id == DailySealedPool.draft_event_id)
            .where(DailySealedPool.original_basics.is_(None))
            .order_by(DailySealedPool.day)
        ).all()
        log.info(f"{len(rows)} pools without original basics")
        for position, (pool, event_id) in enumerate(rows):
            if position > 0:
                sleep(FETCH_SPACING_S)
            basics = pool_from_deck(fetch_17lands_deck(event_id)).basics
            if basics is None:
                log.warning(f"{pool.day}: no 17lands deck for {event_id}, left empty")
                continue
            pool.original_basics = basics
            session.commit()
            log.info(f"{pool.day}: {basics}")


if __name__ == "__main__":
    main()
