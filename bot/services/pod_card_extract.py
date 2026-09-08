"""Derive per-event pod card facts from a stored compact draft artifact.

One row per (event, card): the sighting aggregates that need the pack replayed (# Seen, ALSA) folded
onto the pick that took the card (ATA, maindeck), keyed on the taker's seat so the game columns join
match results at read time. Assumes a singleton pool — one taker per card per event.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

import logging

from sqlalchemy import delete
from sqlalchemy.orm import Session

from bot.database import SessionLocal
from bot.models import PodCardStat, PodDraftEvent
from bot.scripts.draftmancer_log import walk
from bot.services.pod_format import PEASANT_CODE


log = logging.getLogger(__name__)


def tracks_card_data(set_code: str | None) -> bool:
    return set_code == PEASANT_CODE


@dataclass(frozen=True)
class PodCardRow:
    event_id: str
    card_index: int
    set_code: str
    card_name: str
    card_set: str | None
    colors: str | None
    rarity: str | None
    cmc: float | None
    type_line: str | None
    seat: int | None
    pick_num: int | None
    maindecked: bool
    seen_count: int
    last_seen_sum: int
    saw_count: int


def extract_event_rows(compact: dict, set_code: str, event_id: str) -> list[PodCardRow]:
    cards = compact["cards"]
    decks = compact.get("decks") or []
    main_by_seat = [set(deck.get("main") or []) for deck in decks]

    seen_count: dict[int, int] = defaultdict(int)
    last_seen_by_seat: dict[int, dict[int, int]] = defaultdict(dict)
    taken: dict[int, tuple[int, int]] = {}
    for view in walk(compact):
        for card_idx in view.booster:
            seen_count[card_idx] += 1
            last_seen_by_seat[card_idx][view.seat] = view.pick
        for pos in view.taken_positions:
            taken[view.booster[pos]] = (view.seat, view.pick)

    rows: list[PodCardRow] = []
    for card_idx, seen in seen_count.items():
        card = cards[card_idx]
        seat: int | None = None
        pick_num: int | None = None
        maindecked = False
        if card_idx in taken:
            seat, pick_num = taken[card_idx]
            maindecked = seat < len(main_by_seat) and card_idx in main_by_seat[seat]
        last_seen = last_seen_by_seat[card_idx]
        colors = card.get("c")
        rows.append(PodCardRow(
            event_id=event_id,
            card_index=card_idx,
            set_code=set_code,
            card_name=card["n"],
            card_set=card.get("s"),
            colors="".join(colors) if colors else "",
            rarity=card.get("r"),
            cmc=card.get("cmc"),
            type_line=card.get("type"),
            seat=seat,
            pick_num=pick_num,
            maindecked=maindecked,
            seen_count=seen,
            last_seen_sum=sum(last_seen.values()),
            saw_count=len(last_seen),
        ))
    return rows


def rebuild_pod_card_facts(session: Session, event_id: str, set_code: str, compact: dict) -> int:
    session.execute(delete(PodCardStat).where(PodCardStat.event_id == event_id))
    rows = extract_event_rows(compact, set_code, event_id)
    session.add_all([
        PodCardStat(
            event_id=row.event_id,
            card_index=row.card_index,
            card_name=row.card_name,
            set_code=row.set_code,
            card_set=row.card_set,
            colors=row.colors,
            rarity=row.rarity,
            cmc=row.cmc,
            type_line=row.type_line,
            seat=row.seat,
            pick_num=row.pick_num,
            maindecked=row.maindecked,
            seen_count=row.seen_count,
            last_seen_sum=row.last_seen_sum,
            saw_count=row.saw_count,
        )
        for row in rows
    ])
    return len(rows)


def reingest_pod_card_facts(event_id: str) -> int | None:
    """Rebuild one event's pod card facts from its stored artifact. Returns the row count, 0 when the
    event carries no log yet, or None when its set is not tracked for card data. Idempotent — safe to re-run."""
    with SessionLocal() as session:
        event = session.get(PodDraftEvent, event_id)
        if event is None or not tracks_card_data(event.set_code):
            return None
        compact = event.draft_log
        if not isinstance(compact, dict):
            return 0
        count = rebuild_pod_card_facts(session, event_id, event.set_code, compact)
        session.commit()
    return count
