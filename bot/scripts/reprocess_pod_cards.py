"""Rebuild pod card facts for every tracked event from its stored artifact.

Run after a metric definition or the extraction changes. Reads each event's compact log and replays it,
so it needs no 17lands fetch and touches only pod_card_stats.

    DATABASE_URL=... python -m bot.scripts.reprocess_pod_cards
"""
from __future__ import annotations

from sqlalchemy import select

from bot.database import SessionLocal
from bot.models import PodDraftEvent
from bot.services.pod_card_extract import tracks_card_data, rebuild_pod_card_facts


def main() -> None:
    with SessionLocal() as session:
        events = session.execute(
            select(PodDraftEvent.id, PodDraftEvent.set_code, PodDraftEvent.draft_log)
            .where(PodDraftEvent.draft_log.isnot(None))
        ).all()

        total_events = 0
        total_rows = 0
        for event_id, set_code, compact in events:
            if not tracks_card_data(set_code) or not isinstance(compact, dict):
                continue
            rows = rebuild_pod_card_facts(session, event_id, set_code, compact)
            total_events += 1
            total_rows += rows
            print(f"{event_id}  {set_code}  {rows} rows")
        session.commit()

    print(f"done — {total_rows} rows across {total_events} events")


if __name__ == "__main__":
    main()
