"""Populate pod_draft_events.draft_log (the v2 artifact) for events stored before it existed.

    DATABASE_URL=... python -m bot.scripts.backfill_pod_draft_log [event_id ...]

Runs off the database plus Scryfall. The gzipped legacy compact (draft_log_gz) carries the card
table, packs, and the full pick sequence for every event; the built decks were captured separately
into pod_draft_participants.mainboard_card_ids, so they are merged back in here while that column
still exists (run before the migration that drops it). The legacy compact never stored cmc/type, so
those are looked up from Scryfall by set + collector number — the deck view needs them to group by
mana value and split lands. Events with no mainboard data keep their picks but get decks=null.
Overwrites draft_log, so re-running is safe.

mainboard_card_ids is read by raw SQL because the ORM model no longer maps it; once dropped, the
backfill still runs and simply leaves decks=null.
"""
from __future__ import annotations

import gzip
import json
import sys
import time
import urllib.request

from sqlalchemy import select, text

from bot.config import USER_AGENT
from bot.database import SessionLocal
from bot.models import PodDraftEvent


SCRYFALL_COLLECTION_URL = "https://api.scryfall.com/cards/collection"
SCRYFALL_BATCH = 75


def build_artifact(old: dict, deck_rows: list) -> dict:
    id_to_index = {card["id"]: i for i, card in enumerate(old.get("cards", []))}
    cards = [
        {"n": c.get("n"), "cn": c.get("cn"), "s": c.get("s"), "r": c.get("r"),
         "c": c.get("c"), "cmc": None, "type": None}
        for c in old.get("cards", [])
    ]

    seats = old.get("seats", [])
    decks: list[dict] | None = [{"main": [], "side": []} for _ in seats]
    any_deck = False
    for row in deck_rows:
        seat_index, ids = row["seat_index"], row["mainboard_card_ids"]
        if seat_index is None or not ids or not (0 <= seat_index < len(seats)):
            continue
        decks[seat_index] = {"main": [id_to_index[cid] for cid in ids if cid in id_to_index], "side": []}
        any_deck = True
    if not any_deck:
        decks = None

    return {
        "v": 2, "sid": old.get("sid"), "t": old.get("t"), "set": old.get("set"),
        "seats": seats, "cards": cards,
        "packs": old.get("packs", []), "picks": old.get("picks", []), "decks": decks,
    }


def fetch_cmc_type(identifiers: set) -> dict:
    """Map (set, collector_number) -> (cmc, type_line) via Scryfall's collection endpoint. Returns
    what it can; on any network error returns the partial map so cmc/type just stay null."""
    resolved: dict = {}
    batch = sorted(i for i in identifiers if i[0] and i[1])
    for start in range(0, len(batch), SCRYFALL_BATCH):
        chunk = batch[start:start + SCRYFALL_BATCH]
        body = json.dumps({
            "identifiers": [{"set": s, "collector_number": cn} for s, cn in chunk]
        }).encode()
        request = urllib.request.Request(
            SCRYFALL_COLLECTION_URL, data=body, method="POST",
            headers={"Content-Type": "application/json", "Accept": "application/json",
                     "User-Agent": USER_AGENT},
        )
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                payload = json.load(response)
        except Exception as exc:
            print(f"  scryfall: batch failed ({exc}); cmc/type left null for it")
            continue
        for card in payload.get("data", []):
            resolved[(card.get("set"), card.get("collector_number"))] = (
                card.get("cmc"), card.get("type_line"),
            )
        time.sleep(0.1)
    return resolved


def _mainboard_ids_present(session) -> bool:
    found = session.execute(text("""
        SELECT count(*) FROM information_schema.columns
        WHERE table_name = 'pod_draft_participants' AND column_name = 'mainboard_card_ids'
    """)).scalar()
    return found == 1


def _deck_rows(session, event_id: str) -> list:
    return session.execute(text("""
        SELECT seat_index, mainboard_card_ids
        FROM pod_draft_participants WHERE event_id = :event_id
    """), {"event_id": event_id}).mappings().all()


def main(event_ids: list[str]) -> int:
    with SessionLocal() as session:
        have_mainboard = _mainboard_ids_present(session)
        if not have_mainboard:
            print("note: mainboard_card_ids already dropped — decks cannot be recovered, picks only")
        if event_ids:
            targets = event_ids
        else:
            targets = [
                e.id for e in session.execute(
                    select(PodDraftEvent).where(PodDraftEvent.draft_log_gz.isnot(None))
                ).scalars().all()
            ]
        if not targets:
            print("no events with a stored draft_log_gz")
            return 0

        built: list[tuple[str, dict]] = []
        identifiers: set = set()
        for event_id in targets:
            event = session.get(PodDraftEvent, event_id)
            if event is None or event.draft_log_gz is None:
                print(f"  {event_id}: no draft_log_gz, skipping")
                continue
            old = json.loads(gzip.decompress(event.draft_log_gz).decode("utf-8"))
            rows = _deck_rows(session, event_id) if have_mainboard else []
            artifact = build_artifact(old, rows)
            built.append((event_id, artifact))
            for card in artifact["cards"]:
                identifiers.add((card["s"], card["cn"]))

        print(f"scryfall: looking up cmc/type for {len(identifiers)} unique cards…")
        cmc_type = fetch_cmc_type(identifiers)

        with_decks = picks_only = 0
        for event_id, artifact in built:
            for card in artifact["cards"]:
                cmc, type_line = cmc_type.get((card["s"], card["cn"]), (None, None))
                card["cmc"], card["type"] = cmc, type_line
            session.get(PodDraftEvent, event_id).draft_log = artifact
            if artifact["decks"] is None:
                picks_only += 1
            else:
                with_decks += 1
        session.commit()
        enriched = sum(1 for v in cmc_type.values() if v[0] is not None)
        print(f"\ndone: {with_decks} with decks, {picks_only} picks-only, "
              f"{len(built)} events; cmc/type resolved for {enriched}/{len(identifiers)} cards")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
