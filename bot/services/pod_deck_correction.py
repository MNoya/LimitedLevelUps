from __future__ import annotations

import gzip
import json
from collections import Counter
from collections.abc import Iterable
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from bot.models import Player, PodDraftEvent, PodDraftParticipant
from bot.services.pod_card_extract import rebuild_pod_card_facts, tracks_card_data

STAFF_SOURCE = "organizer"
OWNER_SOURCE = "player"


def apply_correction(
    event: PodDraftEvent,
    seat: int,
    main: Iterable[int],
    side: Iterable[int],
    source: str,
    editor_discord_id: str | None = None,
) -> None:
    compact = event.draft_log
    deck = compact["decks"][seat]
    prior = deck.get("correction") or {}
    marker = {
        "source": source,
        "at": datetime.now(timezone.utc).isoformat(),
        "orig_main": prior.get("orig_main", deck.get("main")),
        "orig_side": prior.get("orig_side", deck.get("side")),
    }
    if editor_discord_id:
        marker["by"] = editor_discord_id
    deck["main"] = sorted(main)
    deck["side"] = sorted(side)
    deck["correction"] = marker
    store_draft_log(event, compact)


def revert_correction(event: PodDraftEvent, seat: int) -> None:
    compact = event.draft_log
    deck = compact["decks"][seat]
    correction = deck.pop("correction")
    deck["main"] = correction["orig_main"]
    deck["side"] = correction["orig_side"]
    store_draft_log(event, compact)


def store_draft_log(event: PodDraftEvent, compact: dict) -> None:
    flag_modified(event, "draft_log")
    event.draft_log_gz = gzip.compress(json.dumps(compact, separators=(",", ":")).encode(), compresslevel=9)


def can_edit_deck(session: Session, event_id: str, seat: int, discord_id: str, staff: bool) -> bool:
    return staff or seat in owned_seats(session, event_id, discord_id)


def owned_seats(session: Session, event_id: str, discord_id: str) -> list[int]:
    return list(
        session.execute(
            select(PodDraftParticipant.seat_index)
            .join(Player, PodDraftParticipant.player_id == Player.id)
            .where(
                PodDraftParticipant.event_id == event_id,
                PodDraftParticipant.seat_index.isnot(None),
                Player.discord_id == discord_id,
            )
        ).scalars()
    )


def save_deck_edit(
    session: Session, event_id: str, seat: int, incoming: object, editor_discord_id: str, staff: bool
) -> dict | tuple[str, int]:
    if not can_edit_deck(session, event_id, seat, editor_discord_id, staff):
        return "forbidden", 403
    split = _deck_split(incoming)
    if split is None:
        return "expected main and side card lists", 400
    main, side = split
    event = session.get(PodDraftEvent, event_id)
    if event is None or not isinstance(event.draft_log, dict):
        return "pod not found", 404
    decks = event.draft_log.get("decks") or []
    if seat < 0 or seat >= len(decks):
        return "seat has no deck", 404
    current = decks[seat]
    if Counter(main) + Counter(side) != Counter(current.get("main", [])) + Counter(current.get("side", [])):
        return "cards must come from the same pool", 400
    apply_correction(event, seat, main, side, STAFF_SOURCE if staff else OWNER_SOURCE, editor_discord_id)
    if tracks_card_data(event.set_code):
        rebuild_pod_card_facts(session, event_id, event.set_code, event.draft_log)
    session.commit()
    return {"main": sorted(main), "side": sorted(side)}


def _deck_split(incoming: object) -> tuple[list[int], list[int]] | None:
    if not isinstance(incoming, dict):
        return None
    main = incoming.get("main")
    side = incoming.get("side")
    for cards in (main, side):
        if not isinstance(cards, list) or not all(isinstance(i, int) and not isinstance(i, bool) for i in cards):
            return None
    return main, side
