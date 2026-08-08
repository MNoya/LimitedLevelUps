"""Set up or refresh a P0P1 contest: pull the card pool from Scryfall and schedule the voting window.

Usage:
    python -m bot.scripts.fetch_p0p1_cards --set-code HOB [--deadline 2026-08-05] [--opens ...]

Safe to run repeatedly at any point in spoiler season; it works out what the set needs.

Writes cards-{code_lower}.ts with common + uncommon cards, excluding rares/mythics, bonus-sheet
and Special Guest printings. All Scryfall layouts are handled (normal, adventure, saga, transform,
modal_dfc, split, prepare, class, case).

Then decides the contest window in the shared p0p1_contests.json at the repo root, the one file the
frontend imports and a future bot task can read:

- Pool still missing a slot's worth of cards, no window yet: writes no window. The set stays hidden
  on /p0p1 rather than serving a ballot with unfillable slots.
- Pool complete, no window yet: opens voting immediately, so the contest goes live when this ships.
- Window already on disk: left alone. This is the mid-spoiler top-up, and it must not reschedule a
  window players may already be voting in.
- ``--opens`` / ``--deadline`` / ``--results``: reschedules explicitly, keeping whichever of the
  three is not given.

``--deadline`` defaults to the Arena release instant. ``--results`` (when voting closes for
results) defaults to release + 28 days, independent of the deadline, so an early deadline doesn't
shorten the 17lands data window. Bare dates mean noon ET, matching the release clock in
``bot/sets.py``.
"""
from __future__ import annotations

import argparse
import json
import re
import time
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from bot.sets import ALL_SETS, RELEASE_TZ, SetSeed, release_instant

RESULTS_WINDOW = timedelta(days=28)

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURES_DIR = REPO_ROOT / "frontend/src/data/fixtures"
CONTESTS_JSON = REPO_ROOT / "p0p1_contests.json"
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


_HYBRID_RE = re.compile(r"\{([WUBRG])/([WUBRG])\}")


def _is_hybrid_of(mana_cost: str, color: str) -> bool:
    return any(color in (m.group(1), m.group(2)) for m in _HYBRID_RE.finditer(mana_cost))


def _color_common_count(playable: list[dict], color: str, *, hybrid: bool) -> int:
    return sum(
        1
        for c in playable
        if c["rarity"] == "common"
        and (c["colors"] == [color] or (hybrid and _is_hybrid_of(c.get("manaCost", ""), color)))
    )


def report_pool_coverage(cards: list[dict], *, hybrid_common_slots: bool = False) -> list[str]:
    """Print what the 8 slots have to draw from and return the shortfalls. Mid-spoiler a set is
    mostly uncommons, which leaves the mono-color common slots unfillable — the pool has to be
    complete before voting opens, so say so here instead of on the live ballot."""
    playable = [c for c in cards if not c["typeLine"].startswith("Basic Land")]
    shortfalls: list[str] = []

    print("Slot coverage:")
    for color in ("W", "U", "B", "R", "G"):
        count = _color_common_count(playable, color, hybrid=hybrid_common_slots)
        print(f"  {color} common          {count:4}")
        if count == 0:
            shortfalls.append(f"no {color} commons")

    multicolor = sum(1 for c in playable if c["rarity"] == "uncommon" and len(c["colors"]) >= 2)
    uncommons = sum(1 for c in playable if c["rarity"] == "uncommon")
    commons = sum(1 for c in playable if c["rarity"] == "common")
    print(f"  multicolor uncommon {multicolor:4}")
    print(f"  any common          {commons:4}")
    print(f"  any uncommon        {uncommons:4}")
    if multicolor == 0:
        shortfalls.append("no multicolor uncommons")
    return shortfalls


def contest_instant(value: str) -> str:
    """A schedule argument as a UTC ISO instant. A bare date means noon ET, so a maintainer types the
    wall-clock day the community sees and gets the release clock."""
    try:
        parsed = date.fromisoformat(value)
    except ValueError:
        parsed = None
    if parsed is not None:
        moment = release_instant(parsed)
    else:
        moment = datetime.fromisoformat(value)
        if moment.tzinfo is None:
            moment = moment.replace(tzinfo=RELEASE_TZ)
    return moment.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def now_instant() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def read_contests() -> dict[str, dict[str, str]]:
    if not CONTESTS_JSON.exists():
        return {}
    return json.loads(CONTESTS_JSON.read_text())


def write_contest(seed: SetSeed, opens: str, deadline: str | None, results: str) -> None:
    """Upsert this set's window, leaving every other contest byte-identical. Newest release first so
    the live contest is the first thing a maintainer sees when opening the file."""
    contests = read_contests()
    entry = {
        "name": seed.name,
        "release": release_instant(seed.start_date).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "previewsOpen": opens,
    }
    if deadline is not None:
        entry["votingDeadline"] = deadline
    entry["scoringDate"] = results
    contests[seed.code] = entry

    ordered = dict(sorted(contests.items(), key=lambda kv: kv[1]["release"], reverse=True))
    CONTESTS_JSON.write_text(json.dumps(ordered, indent=2, ensure_ascii=False) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--set-code", required=True, help="Scryfall set code, e.g. HOB")
    parser.add_argument(
        "--deadline",
        help="When voting closes: YYYY-MM-DD (noon ET) or a full ISO timestamp. "
        "Defaults to the Arena release instant, and is the one thing that cannot be derived",
    )
    parser.add_argument(
        "--opens",
        help="Schedule voting to open later instead of as soon as this pool ships",
    )
    parser.add_argument(
        "--results",
        help="When results land: YYYY-MM-DD (noon ET) or a full ISO timestamp. "
        "Defaults to release + 28 days, independent of --deadline",
    )
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
    if any(name != "normal" for name in layout_counts):
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

    existing = read_contests().get(set_code)
    hybrid = bool(existing and existing.get("hybridCommonSlots"))
    shortfalls = report_pool_coverage(cards, hybrid_common_slots=hybrid)

    if shortfalls:
        print(f"POOL INCOMPLETE: {', '.join(shortfalls)}. Those slots have nothing to pick from.")

    default_results = (release_instant(matched.start_date) + RESULTS_WINDOW).strftime("%Y-%m-%dT%H:%M:%SZ")

    if args.opens or args.deadline or args.results:
        opens = contest_instant(args.opens) if args.opens else (
            existing["previewsOpen"] if existing else now_instant()
        )
        deadline = contest_instant(args.deadline) if args.deadline else (
            existing.get("votingDeadline") if existing else None
        )
        results = contest_instant(args.results) if args.results else (
            existing.get("scoringDate") if existing else default_results
        )
        write_contest(matched, opens, deadline, results)
        print(f"Scheduled {set_code} in {CONTESTS_JSON.name}: opens {opens}, "
              f"closes {deadline or 'at release'}, results {results}")
    elif existing:
        print(f"Voting already scheduled for {existing['previewsOpen']}, window left as is")
    elif shortfalls:
        print(f"Voting not opened: {set_code} stays hidden on /p0p1 until the pool fills in. "
              f"Re-run this when the Scryfall gallery is complete.")
    else:
        opens = now_instant()
        write_contest(matched, opens, None, default_results)
        print(f"Scheduled {set_code} in {CONTESTS_JSON.name}: voting opens at {opens}, "
              f"so it goes live as soon as this ships. Results {default_results}")


if __name__ == "__main__":
    main()
