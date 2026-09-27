from __future__ import annotations

import json
import logging
import math
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import requests

from bot.config import Settings
from bot.services.seventeenlands import SeventeenLandsClient
from bot.sets import active_set_code

logger = logging.getLogger(__name__)

CARD_STATS_SETS_JSON = Path(__file__).resolve().parents[2] / "card_stats_sets.json"

_REGISTRY = json.loads(CARD_STATS_SETS_JSON.read_text())
CARD_STATS_SETS: tuple[str, ...] = tuple(_REGISTRY["sets"])
THREE_COLOR_SETS: tuple[str, ...] = tuple(_REGISTRY["threeColorSets"])


@dataclass(frozen=True)
class CardStatsKv:
    account_id: str
    namespace_id: str
    token: str

    @classmethod
    def from_settings(cls, settings: Settings) -> CardStatsKv | None:
        token = settings.cloudflare_kv_token
        if not (settings.cloudflare_account_id and settings.cloudflare_kv_namespace_id and token):
            return None
        return cls(settings.cloudflare_account_id, settings.cloudflare_kv_namespace_id, token.get_secret_value())

    def read(self, set_code: str) -> dict | None:
        resp = requests.get(self._value_url(set_code), headers=self._headers(), timeout=30)
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        return resp.json()

    def write(self, set_code: str, file: dict) -> None:
        resp = requests.put(self._value_url(set_code), headers=self._headers(), data=json.dumps(file), timeout=30)
        resp.raise_for_status()

    def _value_url(self, set_code: str) -> str:
        base = "https://api.cloudflare.com/client/v4/accounts"
        return f"{base}/{self.account_id}/storage/kv/namespaces/{self.namespace_id}/values/{set_code}"

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.token}"}


def refresh_live_card_stats_if_configured(client: SeventeenLandsClient, settings: Settings) -> None:
    kv = CardStatsKv.from_settings(settings)
    if kv is None:
        return
    try:
        refresh_live_card_stats(client, kv)
    except Exception:
        logger.exception("card stats refresh failed")


def refresh_live_card_stats(client: SeventeenLandsClient, kv: CardStatsKv) -> str | None:
    set_code = active_set_code()
    if set_code not in CARD_STATS_SETS:
        return None
    previous = kv.read(set_code)
    kv.write(set_code, build_card_stats_file(client, set_code, previous))
    logger.info(f"Card stats for {set_code} written to KV")
    return set_code


def build_card_stats_file(client: SeventeenLandsClient, set_code: str, previous: dict | None) -> dict:
    cards = {card["name"]: _overall_stats(card) for card in client.fetch_card_ratings(set_code)}
    updated_at = datetime.now(timezone.utc).isoformat()
    if not cards:
        return {"set": set_code, "updatedAt": updated_at, "cards": cards}
    if previous and _same_game_counts(previous, cards):
        return {**previous, "updatedAt": updated_at}

    color_pairs = ["WU", "UB", "BR", "RG", "WG", "WB", "UR", "BG", "WR", "UG"]
    color_trios = ["WUB", "WUR", "WUG", "WBR", "WBG", "WRG", "UBR", "UBG", "URG", "BRG"]
    decks = color_pairs + color_trios if set_code in THREE_COLOR_SETS else color_pairs
    for deck in decks:
        for card in client.fetch_card_ratings(set_code, colors=deck):
            stats = cards.get(card["name"])
            games = card.get("ever_drawn_game_count") or 0
            if stats and games > 0:
                stats["pairs"][deck] = {"gihWr": _rounded(card.get("ever_drawn_win_rate"), 4), "gihGames": games}
    return {"set": set_code, "updatedAt": updated_at, "cards": cards}


def _overall_stats(card: dict) -> dict:
    return {
        "mtgaId": card.get("mtga_id"),
        "seen": card.get("seen_count") or 0,
        "picked": card.get("pick_count") or 0,
        "alsa": _rounded(card.get("avg_seen"), 2),
        "ata": _rounded(card.get("avg_pick"), 2),
        "gp": card.get("game_count") or 0,
        "gpWr": _rounded(card.get("win_rate"), 4),
        "ohWr": _rounded(card.get("opening_hand_win_rate"), 4),
        "gdWr": _rounded(card.get("drawn_win_rate"), 4),
        "gihGames": card.get("ever_drawn_game_count") or 0,
        "gihWr": _rounded(card.get("ever_drawn_win_rate"), 4),
        "gnsWr": _rounded(card.get("never_drawn_win_rate"), 4),
        "iwd": _rounded(card.get("drawn_improvement_win_rate"), 4),
        "pairs": {},
    }


def _same_game_counts(previous: dict, cards: dict) -> bool:
    previous_cards = previous.get("cards", {})
    for name, stats in cards.items():
        if previous_cards.get(name, {}).get("gp") != stats["gp"]:
            return False
    return True


def _rounded(value: float | None, digits: int) -> float | None:
    if value is None:
        return None
    factor = 10**digits
    return math.floor(value * factor + 0.5) / factor
