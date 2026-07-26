"""Fetch the P0P1 card pool from Scryfall for a given set and write the frontend fixture.

Usage:
    python -m bot.scripts.fetch_p0p1_cards --set-code HOB

Writes frontend/src/data/fixtures/cards-{code_lower}.ts with common + uncommon cards
for the P0P1 contest. Excludes rares/mythics, bonus-sheet, and Special Guest printings.
All Scryfall layouts are handled (normal, adventure, saga, transform, modal_dfc, split,
prepare, class, case, etc.).
"""
from __future__ import annotations

import argparse
import json
import time
import urllib.parse
import urllib.request
from pathlib import Path

from bot.sets import ALL_SETS

FIXTURES_DIR = Path(__file__).parent.parent.parent / "frontend/src/data/fixtures"
SCRYFALL_SEARCH = "https://api.scryfall.com/cards/search"
USER_AGENT = "DischordLeaderboard/1.0"

FRONT_FACE_NAME_LAYOUTS = {"adventure", "transform", "modal_dfc", "prepare", "flip"}


def scryfall_search(query: str) -> list[dict]:
    """Paginate through Scryfall search results."""
    cards: list[dict] = []
    url = f"{SCRYFALL_SEARCH}?q={urllib.parse.quote(query)}&order=set"
    while url:
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
        with urllib.request.urlopen(req) as resp:
            data = json.loads(resp.read())
        cards.extend(data.get("data", []))
        url = data.get("next_page")
        if url:
            time.sleep(0.1)
    return cards


def extract_card(raw: dict) -> dict:
    """Extract Card fields from any Scryfall layout.

    Name/mana: front face for multi-face layouts, top-level for split and single-face.
    Images: top-level when available, otherwise front face (transform, modal_dfc).
    """
    layout = raw.get("layout", "normal")
    faces = raw.get("card_faces", [])

    if layout in FRONT_FACE_NAME_LAYOUTS and faces:
        name = faces[0].get("name", raw.get("name", ""))
        mana_cost = faces[0].get("mana_cost", "")
    else:
        name = raw.get("name", "")
        mana_cost = raw.get("mana_cost", "")

    images = raw.get("image_uris")
    if not images and faces:
        images = faces[0].get("image_uris") or {}
    images = images or {}

    return {
        "name": name,
        "manaCost": mana_cost,
        "cmc": raw.get("cmc", 0),
        "colors": raw.get("colors", []),
        "rarity": raw.get("rarity", "common"),
        "typeLine": raw.get("type_line", ""),
        "collectorNumber": raw.get("collector_number", ""),
        "imageSmall": images.get("small", ""),
        "imageNormal": images.get("normal", ""),
        "imageArtCrop": images.get("art_crop", ""),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--set-code", required=True, help="Scryfall set code, e.g. HOB")
    args = parser.parse_args()

    set_code = args.set_code.upper()
    scryfall_code = set_code.lower()
    matched = next((s for s in ALL_SETS if s.code == set_code), None)
    if matched is None:
        raise SystemExit(f"Unknown set code {set_code!r}. Add it to bot/sets.py first.")

    print(f"Set: {matched.name} ({set_code})")
    if scryfall_code != set_code.lower():
        print(f"  WARNING: Scryfall code '{scryfall_code}' may differ from 17lands expansion code")

    query = f"set:{scryfall_code} (r:common OR r:uncommon) -is:bonus -is:extra"
    print(f"Querying Scryfall: {query}")
    raw_cards = scryfall_search(query)
    print(f"Received {len(raw_cards)} cards from Scryfall")

    cards = [extract_card(raw) for raw in raw_cards]
    cards.sort(key=lambda c: c["collectorNumber"])

    layout_counts: dict[str, int] = {}
    for raw in raw_cards:
        layout = raw.get("layout", "normal")
        layout_counts[layout] = layout_counts.get(layout, 0) + 1

    commons = sum(1 for c in cards if c["rarity"] == "common")
    uncommons = sum(1 for c in cards if c["rarity"] == "uncommon")
    print(f"Extracted {len(cards)} cards: {commons} common, {uncommons} uncommon")
    if any(l != "normal" for l in layout_counts):
        for layout, count in sorted(layout_counts.items()):
            if layout != "normal":
                print(f"  {count} {layout}")

    output = FIXTURES_DIR / f"cards-{set_code.lower()}.ts"
    cards_json = json.dumps(cards, indent=2, ensure_ascii=False)
    ts_content = (
        'import type { Card } from "../../types/p0p1";\n'
        "\n"
        f"export default {cards_json} satisfies Card[];\n"
    )
    output.write_text(ts_content)
    print(f"Wrote {len(cards)} cards → {output}")


if __name__ == "__main__":
    main()
