"""Daily Sealed: picks one finished LLU Sealed pool per day and freezes it in daily_sealed_pools"""
from __future__ import annotations

import logging
import random
import statistics
from time import sleep
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from bot.config import settings
from bot.models import DailySealedPool, DraftEvent, MagicSet
from bot.services.card_stats import gih_win_rates
from bot.services.tracker_detail import card_rarity, fetch_17lands
from bot.sets import active_set_code

log = logging.getLogger(__name__)

TURNOVER_TZ = ZoneInfo("America/New_York")
TURNOVER_TIME = time(8, 0)
PICK_LEAD = timedelta(hours=5)
MIN_POOL_CARDS = 60
SKIPPED_FORMATS = ("MidWeekSealed",)
FINAL_MAIN_KEY = "final_main_names"
FINAL_BASICS_KEY = "final_main_basics"
CANDIDATES_COMPARED = 3
FETCH_SPACING_S = 7.0
DECK_PLAYABLES = 23
MISSING_PLAYABLE_GIH = 0.45
DEEP_COLOR_PLAYABLES = 5
COLOR_PAIRS = ("WU", "UB", "BR", "RG", "WG", "WB", "UR", "BG", "WR", "UG")
BASIC_LANDS = frozenset({"Plains", "Island", "Swamp", "Mountain", "Forest", "Wastes"})
BASIC_COLORS = {"Plains": "W", "Island": "U", "Swamp": "B", "Mountain": "R", "Forest": "G"}

DeckFetcher = Callable[[str], dict | None]
GihLoader = Callable[[str], dict[str, float] | None]


def serving_day(now: datetime) -> date:
    local = now.astimezone(TURNOVER_TZ)
    return (local - timedelta(hours=TURNOVER_TIME.hour, minutes=TURNOVER_TIME.minute)).date()


def turnover_instant(day: date) -> datetime:
    return datetime.combine(day, TURNOVER_TIME, tzinfo=TURNOVER_TZ).astimezone(timezone.utc)


def days_to_pick(now: datetime) -> list[date]:
    today = serving_day(now)
    tomorrow = today + timedelta(days=1)
    if turnover_instant(tomorrow) - now <= PICK_LEAD:
        return [today, tomorrow]
    return [today]


def ensure_pools(session: Session, now: datetime, fetch_deck: DeckFetcher | None = None) -> list[DailySealedPool]:
    stored = []
    for day in days_to_pick(now):
        if session.get(DailySealedPool, day) is not None:
            continue
        pool = pick_pool(session, day, fetch_deck or fetch_17lands_deck)
        if pool is not None:
            stored.append(pool)
    return stored


def pick_pool(
    session: Session,
    day: date,
    fetch_deck: DeckFetcher,
    load_gih: GihLoader | None = None,
    pause: Callable[[float], None] = sleep,
) -> DailySealedPool | None:
    set_code = active_set_code(turnover_instant(day))
    gih = (load_gih or default_gih_loader)(set_code)
    usable = []
    for position, event in enumerate(ranked_candidates(session, day, set_code)):
        if position > 0:
            pause(FETCH_SPACING_S)
        deck = fetch_deck(event.seventeenlands_event_id)
        original = pool_from_deck(deck)
        if len(original.cards) < MIN_POOL_CARDS:
            log.info(f"daily sealed: skipping {event.seventeenlands_event_id}, pool has {len(original.cards)} cards")
            continue
        usable.append((event, original))
        if gih is None or len(usable) == CANDIDATES_COMPARED:
            break
    if not usable:
        log.warning(f"daily sealed: no usable {set_code} pool for {day}")
        return None
    event, original = usable[0] if gih is None else most_open_pool(usable, gih)
    pool = DailySealedPool(
        day=day,
        set_code=set_code,
        draft_event_id=event.id,
        player_id=event.player_id,
        format=event.format,
        cards=original.cards,
        original_main=original.main,
        original_basics=original.basics,
        colors=event.colors,
        wins=event.wins,
        losses=event.losses,
    )
    session.add(pool)
    session.commit()
    log.info(f"daily sealed: stored {set_code} pool for {day} from {event.seventeenlands_event_id}")
    return pool


def default_gih_loader(set_code: str) -> dict[str, float] | None:
    return gih_win_rates(set_code, settings)


def most_open_pool(usable: list[tuple], gih: dict[str, float]) -> tuple:
    playable_floor = statistics.median(gih.values())
    best = usable[0]
    best_rank = openness(best[1].cards, gih, playable_floor)
    for candidate in usable[1:]:
        rank = openness(candidate[1].cards, gih, playable_floor)
        if rank > best_rank:
            best, best_rank = candidate, rank
    log.info(f"daily sealed: compared {len(usable)} pools, picked {best_rank[0]} deep colors")
    return best


def openness(cards: list[dict], gih: dict[str, float], playable_floor: float) -> tuple[int, float]:
    return deep_colors(cards, gih, playable_floor), -opposite_pair_gap(cards, gih)


def deep_colors(cards: list[dict], gih: dict[str, float], playable_floor: float) -> int:
    deep = 0
    for color in "WUBRG":
        playables = 0
        for card in cards:
            if card["identity"] == color and not is_land(card) and gih.get(card["name"], 0) >= playable_floor:
                playables += 1
        if playables >= DEEP_COLOR_PLAYABLES:
            deep += 1
    return deep


def opposite_pair_gap(cards: list[dict], gih: dict[str, float]) -> float:
    strengths = {pair: pair_strength(cards, pair, gih) for pair in COLOR_PAIRS}
    best = max(strengths, key=strengths.__getitem__)
    opposite = 0.0
    for pair, strength in strengths.items():
        if not set(pair) & set(best):
            opposite = max(opposite, strength)
    return strengths[best] - opposite


def pair_strength(cards: list[dict], pair: str, gih: dict[str, float]) -> float:
    rates = []
    for card in cards:
        playable = not is_land(card) and all(color in pair for color in card["identity"])
        if playable and card["name"] in gih:
            rates.append(gih[card["name"]])
    best = sorted(rates, reverse=True)[:DECK_PLAYABLES]
    return sum(best) + MISSING_PLAYABLE_GIH * (DECK_PLAYABLES - len(best))


def is_land(card: dict) -> bool:
    return "Land" in " ".join(card["types"])


def ranked_candidates(session: Session, day: date, set_code: str, rng: random.Random | None = None) -> list[DraftEvent]:
    used_events = select(DailySealedPool.draft_event_id)
    events = session.execute(
        select(DraftEvent)
        .join(MagicSet, MagicSet.id == DraftEvent.set_id)
        .where(
            MagicSet.code == set_code,
            DraftEvent.format.ilike("%sealed%"),
            DraftEvent.format.not_in(SKIPPED_FORMATS),
            ~DraftEvent.format.ilike("cube%"),
            DraftEvent.finished_at.is_not(None),
            DraftEvent.id.not_in(used_events),
        )
    ).scalars().all()
    previous = session.get(DailySealedPool, day - timedelta(days=1))
    pools_per_player = dict(session.execute(
        select(DailySealedPool.player_id, func.count())
        .where(DailySealedPool.set_code == set_code)
        .group_by(DailySealedPool.player_id)
    ).all())
    shuffler = rng or random.Random(day.toordinal())
    shuffled = list(events)
    shuffler.shuffle(shuffled)
    eligible = [event for event in shuffled if previous is None or event.player_id != previous.player_id]
    return sorted(eligible, key=lambda event: pools_per_player.get(event.player_id, 0))


def fetch_17lands_deck(seventeenlands_event_id: str) -> dict | None:
    first = fetch_deck_version(seventeenlands_event_id, 0)
    if first is None:
        return None
    versions = len((first.get("event_info") or {}).get("deck_links") or [])
    if versions > 1:
        final = fetch_deck_version(seventeenlands_event_id, versions - 1)
        if final is not None:
            first[FINAL_MAIN_KEY] = main_deck_names(final)
            first[FINAL_BASICS_KEY] = main_deck_basics(final)
    return first


def fetch_deck_version(seventeenlands_event_id: str, index: int) -> dict | None:
    body = fetch_17lands(f"/api/deck/draft/?draft_id={seventeenlands_event_id}&deck_index={index}")
    if body is None:
        return None
    return body.get("data") or body


def main_deck_names(deck: dict) -> list[str]:
    cards_by_id = deck.get("cards") or {}
    names = []
    for group in deck.get("groups") or []:
        if str(group.get("name", "")).lower() != "maindeck":
            continue
        for card_id in group.get("cards") or []:
            name = (cards_by_id.get(str(card_id)) or {}).get("name")
            if name and name not in BASIC_LANDS:
                names.append(name)
    return names


def main_deck_basics(deck: dict) -> dict[str, int]:
    cards_by_id = deck.get("cards") or {}
    basics = {color: 0 for color in "WUBRG"}
    for group in deck.get("groups") or []:
        if str(group.get("name", "")).lower() != "maindeck":
            continue
        for card_id in group.get("cards") or []:
            color = BASIC_COLORS.get((cards_by_id.get(str(card_id)) or {}).get("name"))
            if color:
                basics[color] += 1
    return basics


@dataclass
class OriginalPool:
    cards: list[dict]
    main: list[int]
    basics: dict[str, int] | None


def pool_from_deck(deck: dict | None) -> OriginalPool:
    if not deck:
        return OriginalPool([], [], None)
    cards_by_id = deck.get("cards") or {}
    pool = []
    original_main = []
    for group in deck.get("groups") or []:
        in_main = str(group.get("name", "")).lower() == "maindeck"
        for card_id in group.get("cards") or []:
            card = cards_by_id.get(str(card_id)) or {}
            name = card.get("name")
            if not name or name in BASIC_LANDS:
                continue
            if in_main:
                original_main.append(len(pool))
            pool.append({
                "name": name,
                "cmc": int(card.get("cmc") or 0),
                "identity": "".join(card.get("color_identity") or []),
                "cost": card.get("mana_cost") or "",
                "image": card.get("image_url") or "",
                "back": card.get("url_back") or None,
                "rarity": card_rarity(card),
                "types": card.get("types") or [],
            })
    if FINAL_MAIN_KEY in deck:
        original_main = indexes_for_names(pool, deck[FINAL_MAIN_KEY])
    return OriginalPool(pool, original_main, deck.get(FINAL_BASICS_KEY) or main_deck_basics(deck))


def indexes_for_names(pool: list[dict], names: list[str]) -> list[int]:
    remaining = list(names)
    indexes = []
    for index, card in enumerate(pool):
        if card["name"] in remaining:
            remaining.remove(card["name"])
            indexes.append(index)
    return indexes
