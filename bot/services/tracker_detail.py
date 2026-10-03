"""Per-draft objective detail for the private tracker: rarity counts, decklist and match results.

17lands serves this on two endpoints with no CORS headers, so the fetch runs server-side here.
The periodic tick never touches it: a tracker user pulls their own detail on demand from the site
refresh button, and older sets are backfilled by ``bot.scripts.backfill_tracker_detail``.
"""
from __future__ import annotations

import json
import logging
import time
import urllib.error
import urllib.request
from datetime import timedelta

from sqlalchemy import case, func, or_, select, update
from sqlalchemy.orm import Session

from bot.config import settings
from bot.models import DraftEvent, MagicSet, Player
from bot.services.active_set import resolve_active_set
from bot.services.refresh import refresh_player
from bot.services.seventeenlands import SeventeenLandsClient

log = logging.getLogger(__name__)

PAIR_GAP_S = 1.5
DRAFT_GAP_S = 5.0
AUTO_FILL_CAP = 20
SETTLE_AFTER_FINISH = timedelta(hours=1)


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
    except urllib.error.HTTPError as error:
        if error.code == 404:
            log.info(f"17lands has no detail for {path}")
            return None
        log.warning(f"17lands fetch failed for {path}", exc_info=True)
        return None
    except Exception:
        log.warning(f"17lands fetch failed for {path}", exc_info=True)
        return None


def card_rarity(card: dict) -> str | None:
    """17lands mislabels basic lands as rare, so a basic land is forced to common"""
    if any("Basic Land" in str(kind) for kind in card.get("types") or []):
        return "common"
    return card.get("rarity")


def summarise_draft(draft_id: str, fetch_deck: bool = True, pair_gap_s: float = PAIR_GAP_S) -> dict | None:
    """Rarity counts, decklist and match results for one draft, or None if 17lands has neither"""
    deck_body = None
    if fetch_deck:
        deck_body = fetch_17lands(f"/api/deck/draft/?draft_id={draft_id}&deck_index=0")
        time.sleep(pair_gap_s)
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


def pending_draft_ids(
    session: Session, player_id: str, set_code: str | None, cap: int | None,
) -> list[tuple[str, str, bool]]:
    is_array = func.jsonb_typeof(DraftEvent.match_results) == "array"
    stored_matches = case((is_array, func.jsonb_array_length(DraftEvent.match_results)), else_=0)
    incomplete = or_(
        DraftEvent.pool_rares.is_(None),
        stored_matches < DraftEvent.wins + DraftEvent.losses,
    )
    unsettled = or_(
        DraftEvent.finished_at.is_(None),
        DraftEvent.detail_checked_at.is_(None),
        DraftEvent.detail_checked_at < DraftEvent.finished_at + SETTLE_AFTER_FINISH,
    )
    stmt = (
        select(DraftEvent.id, DraftEvent.seventeenlands_event_id, DraftEvent.deck_cards.isnot(None))
        .join(MagicSet, MagicSet.id == DraftEvent.set_id)
        .where(
            DraftEvent.player_id == player_id,
            DraftEvent.seventeenlands_event_id.isnot(None),
            incomplete,
            unsettled,
        )
        .order_by(DraftEvent.finished_at.desc().nulls_last())
    )
    if set_code:
        stmt = stmt.where(MagicSet.code == set_code)
    if cap:
        stmt = stmt.limit(cap)
    return [(str(row[0]), row[1], row[2]) for row in session.execute(stmt).all()]


def refetch_draft_detail(session: Session, player_id: str, seventeenlands_event_id: str) -> bool:
    """Re-pull one draft's match detail with no pacing, and its deck only if none is stored. True if written"""
    row = session.execute(
        select(DraftEvent.id, DraftEvent.deck_cards.isnot(None)).where(
            DraftEvent.player_id == player_id,
            DraftEvent.seventeenlands_event_id == seventeenlands_event_id,
        )
    ).one_or_none()
    if row is None:
        return False
    draft_id, has_deck = row
    summary = summarise_draft(seventeenlands_event_id, fetch_deck=not has_deck, pair_gap_s=0)
    store_detail(session, draft_id, summary)
    return summary is not None


def store_detail(session: Session, draft_id: str, summary: dict | None) -> None:
    """Stamp the check even when 17lands returned nothing, so a draft it can never complete settles"""
    values = {"detail_checked_at": func.now()}
    if summary is not None:
        values.update(present_detail(summary))
    session.execute(update(DraftEvent).where(DraftEvent.id == draft_id).values(**values))
    session.commit()


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
    """Fetch and store 17lands detail for a player's incomplete drafts, committing per draft"""
    pending = pending_draft_ids(session, player_id, set_code, cap)
    filled = 0
    missed_ids = []
    for index, (draft_id, seventeenlands_event_id, has_deck) in enumerate(pending):
        if index:
            time.sleep(draft_gap_s)
        summary = summarise_draft(seventeenlands_event_id, fetch_deck=not has_deck)
        store_detail(session, draft_id, summary)
        if summary is None:
            missed_ids.append(seventeenlands_event_id)
            continue
        filled += 1
    return {"pending": len(pending), "filled": filled, "missed": len(missed_ids), "missed_ids": missed_ids}


def run_tracker_refresh(session: Session, discord_id: str, set_code: str | None, event_id: str | None) -> dict:
    """One tracker refresh click: refetch a single draft when given its id, else refresh the whole set"""
    player = session.execute(select(Player).where(Player.discord_id == discord_id)).scalar_one_or_none()
    if player is None or not player.seventeenlands_token:
        return {"ingested": 0, "filled": 0, "missed": 0}
    if event_id:
        started = time.monotonic()
        written = refetch_draft_detail(session, player.id, event_id)
        elapsed = time.monotonic() - started
        log.info(f"tracker refetch {player.display_name} {event_id}: {elapsed:.1f}s written={written}")
        return {"ingested": 0, "filled": int(written), "missed": int(not written)}
    return refresh_tracker_set(session, player, set_code)


def refresh_tracker_set(session: Session, player: Player, set_code: str | None) -> dict:
    """Pull new drafts for one set into the event log, then fill their missing 17lands detail"""
    code = set_code or getattr(resolve_active_set(session), "code", None)
    started = time.monotonic()
    known_before = _count_set_drafts(session, player.id, code)
    window = session.execute(select(MagicSet.start_date, MagicSet.end_date).where(MagicSet.code == code)).one_or_none()
    start_date, end_date = window or (None, None)
    fetch_end = end_date + timedelta(days=1) if end_date else None
    refresh_player(session, SeventeenLandsClient(), player, fetch_start=start_date, fetch_end=fetch_end)
    session.commit()
    ingested = _count_set_drafts(session, player.id, code) - known_before
    ingest_s = time.monotonic() - started

    fill = fill_pending_draft_detail(session, player.id, set_code=code, cap=None)
    fill_s = time.monotonic() - started - ingest_s
    log.info(
        f"tracker refresh {player.display_name} {code}: ingest={ingest_s:.1f}s new={ingested} "
        f"detail={fill_s:.1f}s pending={fill['pending']} filled={fill['filled']} missed={fill['missed_ids']}"
    )
    return {"ingested": ingested, "filled": fill["filled"], "missed": fill["missed"]}


def _count_set_drafts(session: Session, player_id: str, set_code: str | None) -> int:
    return session.execute(
        select(func.count())
        .select_from(DraftEvent)
        .join(MagicSet, MagicSet.id == DraftEvent.set_id)
        .where(DraftEvent.player_id == player_id, MagicSet.code == set_code)
    ).scalar_one()
