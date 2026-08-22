"""Per-draft objective detail for the private tracker: rarity counts, decklist and match results.

17lands serves this on two endpoints with no CORS headers, so the fetch runs server-side here.
The periodic tick never touches it: a tracker user pulls their own detail on demand from the site
refresh button, and older sets are backfilled by ``bot.scripts.backfill_tracker_detail``.
"""
from __future__ import annotations

import json
import logging
import time
import urllib.request

from sqlalchemy import and_, or_, select, update
from sqlalchemy.orm import Session

from bot.config import settings
from bot.models import DraftEvent, MagicSet

log = logging.getLogger(__name__)

PAIR_GAP_S = 1.5
DRAFT_GAP_S = 5.0
AUTO_FILL_CAP = 20


def is_tracker_player(discord_id: str | None) -> bool:
    return bool(discord_id) and discord_id in settings.tracker_discord_ids_set


def fetch_17lands(path: str) -> dict | None:
    request = urllib.request.Request(
        f"https://www.17lands.com{path}",
        headers={"Accept": "application/json", "User-Agent": "LLU-tracker/1.0"},
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.load(response)
    except Exception:
        log.warning(f"17lands fetch failed for {path}", exc_info=True)
        return None


def card_rarity(card: dict) -> str | None:
    """17lands mislabels basic lands as rare, so a basic land is forced to common"""
    if any("Basic Land" in str(kind) for kind in card.get("types") or []):
        return "common"
    return card.get("rarity")


def summarise_draft(draft_id: str) -> dict | None:
    """Rarity counts, decklist and match results for one finished draft, or None if 17lands has neither"""
    deck_body = fetch_17lands(f"/api/deck/draft/?draft_id={draft_id}&deck_index=0")
    time.sleep(PAIR_GAP_S)
    details = fetch_17lands(f"/data/details/?draft_id={draft_id}")
    deck = (deck_body or {}).get("data") or deck_body or {}
    cards = deck.get("cards") or {}

    groups: dict[str, list[dict]] = {}
    rares = mythics = 0
    for group in deck.get("groups") or []:
        entries = []
        for card_id in group.get("cards") or []:
            card = cards.get(str(card_id)) or {}
            rarity = card_rarity(card)
            entries.append({"name": card.get("name"), "rarity": rarity})
            if rarity == "rare":
                rares += 1
            elif rarity == "mythic":
                mythics += 1
        groups[str(group.get("name", "")).lower()] = entries

    matches = []
    for index, match in enumerate((details or {}).get("match_results") or [], start=1):
        games = match.get("game_results") or []
        matches.append({
            "match_number": index,
            "won": match.get("won"),
            "opponent_colors": next((g.get("opponent_colors") for g in games if g.get("opponent_colors")), None),
            "games": [{"on_play": g.get("on_play"), "won": g.get("won")} for g in games],
        })

    if not groups and not matches:
        return None
    return {"pool_rares": rares, "pool_mythics": mythics,
            "deck_cards": groups or None, "match_results": matches or None}


def pending_draft_ids(session: Session, player_id: str, set_code: str | None, cap: int | None) -> list[tuple[str, str]]:
    incomplete = or_(
        DraftEvent.pool_rares.is_(None),
        and_(DraftEvent.match_results.is_(None), (DraftEvent.wins + DraftEvent.losses) > 0),
    )
    stmt = (
        select(DraftEvent.id, DraftEvent.seventeenlands_event_id)
        .join(MagicSet, MagicSet.id == DraftEvent.set_id)
        .where(
            DraftEvent.player_id == player_id,
            DraftEvent.seventeenlands_event_id.isnot(None),
            incomplete,
        )
        .order_by(DraftEvent.finished_at.desc().nulls_last())
    )
    if set_code:
        stmt = stmt.where(MagicSet.code == set_code)
    if cap:
        stmt = stmt.limit(cap)
    return [(str(row[0]), row[1]) for row in session.execute(stmt).all()]


def refetch_draft_detail(session: Session, player_id: str, seventeenlands_event_id: str) -> bool:
    """Force a re-pull of one draft's detail, even if it already has some. True if written"""
    draft_id = session.execute(
        select(DraftEvent.id).where(
            DraftEvent.player_id == player_id,
            DraftEvent.seventeenlands_event_id == seventeenlands_event_id,
        )
    ).scalar_one_or_none()
    if draft_id is None:
        return False
    summary = summarise_draft(seventeenlands_event_id)
    if summary is None:
        return False
    session.execute(update(DraftEvent).where(DraftEvent.id == draft_id).values(**present_detail(summary)))
    session.commit()
    return True


def present_detail(summary: dict) -> dict:
    """Only the columns 17lands actually returned, so a partial re-pull never nulls stored detail"""
    values = {}
    if summary["deck_cards"] is not None:
        values["deck_cards"] = summary["deck_cards"]
        values["pool_rares"] = summary["pool_rares"]
        values["pool_mythics"] = summary["pool_mythics"]
    if summary["match_results"] is not None:
        values["match_results"] = summary["match_results"]
    return values


def fill_pending_draft_detail(
    session: Session,
    player_id: str,
    set_code: str | None = None,
    cap: int | None = AUTO_FILL_CAP,
    draft_gap_s: float = DRAFT_GAP_S,
) -> dict:
    """Fetch and store 17lands detail for a player's drafts that still lack it.

    Commits per draft so a mid-run failure keeps what it fetched. Paces requests apart to stay a
    considerate 17lands consumer. Returns ``{"pending", "filled", "missed"}``.
    """
    pending = pending_draft_ids(session, player_id, set_code, cap)
    filled = missed = 0
    for index, (draft_id, seventeenlands_event_id) in enumerate(pending):
        if index:
            time.sleep(draft_gap_s)
        summary = summarise_draft(seventeenlands_event_id)
        if summary is None:
            missed += 1
            continue
        session.execute(update(DraftEvent).where(DraftEvent.id == draft_id).values(**present_detail(summary)))
        session.commit()
        filled += 1
    return {"pending": len(pending), "filled": filled, "missed": missed}
