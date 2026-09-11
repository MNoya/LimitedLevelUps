"""Persisted Scryfall card-name sources for transcript card linking.

Two products, both cached gitignored under ``cache/scryfall/``: a per-set sheet for set episodes (small, exact
universe) and the Arena-legal oracle-name index for setless evergreen episodes (for fuzzy validation of
LLM-discovered names). Set episodes match against their sheet, everything else against the Arena build.
"""
from __future__ import annotations

import gzip
import json
import time
import unicodedata
import urllib.parse
import urllib.request
from difflib import get_close_matches
from datetime import date, timedelta
from pathlib import Path

from bot.sets import release_instant, seed_for_code

SCRYFALL_SEARCH = "https://api.scryfall.com/cards/search"
SCRYFALL_BULK = "https://api.scryfall.com/bulk-data/default-cards"
CACHE_DIR = Path("cache/scryfall")
ORACLE_PATH = CACHE_DIR / "oracle_names.json"
ORACLE_MAX_AGE_DAYS = 14
SET_MAX_AGE_DAYS = 7
SET_SETTLE_DAYS = 14
FUZZY_CUTOFF = 0.88
HEADERS = {"User-Agent": "llu-transcripts/1.0", "Accept": "application/json"}
_FRAGMENTS: set[str] | None = None


def set_card_names(code: str, refresh: bool = False, stale_ok: bool = False) -> list[str]:
    path = CACHE_DIR / f"set_{code.lower()}.json"
    if not refresh and path.exists() and (stale_ok or not _set_sheet_stale(code, path)):
        return json.loads(path.read_text())
    try:
        names = _fetch_set_cards(code.lower())
    except Exception as exc:
        if path.exists():
            return json.loads(path.read_text())
        raise exc
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(names))
    return names


def all_card_names(refresh: bool = False) -> dict[str, str]:
    if not refresh and ORACLE_PATH.exists() and not _older_than(ORACLE_PATH, ORACLE_MAX_AGE_DAYS):
        return json.loads(ORACLE_PATH.read_text())
    index = _build_oracle_index()
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    ORACLE_PATH.write_text(json.dumps(index))
    return index


def resolve(name: str, index: dict[str, str]) -> str | None:
    exact = index.get(name.lower())
    if exact:
        return exact
    close = get_close_matches(name.lower(), list(index.keys()), n=1, cutoff=FUZZY_CUTOFF)
    return index[close[0]] if close else None


def name_fragments(index: dict[str, str]) -> set[str]:
    global _FRAGMENTS
    if _FRAGMENTS is None:
        _FRAGMENTS = {fold(name.split(",", 1)[0]) for name in index.values() if "," in name}
    return _FRAGMENTS


def fold(text: str) -> str:
    stripped = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return stripped.strip().lower()


def _fetch_set_cards(scryfall_set: str) -> list[str]:
    names: list[str] = []
    params = urllib.parse.urlencode({"q": f"set:{scryfall_set}", "unique": "cards"})
    url: str | None = f"{SCRYFALL_SEARCH}?{params}"
    while url:
        request = urllib.request.Request(url, headers=HEADERS)
        with urllib.request.urlopen(request) as response:
            data = json.load(response)
        for card in data.get("data", []):
            names.append(card["name"].split(" // ")[0])
        url = data.get("next_page") if data.get("has_more") else None
        if url:
            time.sleep(0.1)
    return names


def _build_oracle_index() -> dict[str, str]:
    meta_request = urllib.request.Request(SCRYFALL_BULK, headers=HEADERS)
    with urllib.request.urlopen(meta_request) as response:
        download_uri = json.load(response)["jsonl_download_uri"]
    index: dict[str, str] = {}
    bulk_request = urllib.request.Request(download_uri, headers=HEADERS)
    with urllib.request.urlopen(bulk_request) as response:
        for line in gzip.GzipFile(fileobj=response):
            card = json.loads(line)
            if "arena" not in (card.get("games") or []):
                continue
            name = card["name"].split(" // ")[0]
            index.setdefault(name.lower(), name)
    return index


def _older_than(path: Path, days: int) -> bool:
    age = time.time() - path.stat().st_mtime
    return age > days * 86400


def _set_sheet_stale(code: str, path: Path) -> bool:
    seed = seed_for_code(code)
    if seed is None:
        return False
    settled = release_instant(seed.start_date).date() + timedelta(days=SET_SETTLE_DAYS)
    if date.today() >= settled:
        return False
    return _older_than(path, SET_MAX_AGE_DAYS)
