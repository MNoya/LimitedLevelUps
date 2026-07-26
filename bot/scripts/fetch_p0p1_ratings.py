"""Fetch 17lands card ratings for the P0P1 contest and write the frontend ratings fixture.

Usage:
    python -m bot.scripts.fetch_p0p1_ratings --set-code MSH [--phase midway|final] [--end-date YYYY-MM-DD]

Writes frontend/src/data/fixtures/p0p1-ratings-{set_code_lower}.ts. Only cards present in
the matching card fixture (cards-{code}.ts) are included — rares, mythics, and bonus sheet
reprints are stripped. Commit the result and redeploy to flip the contest into midway or
final phase. dateRange is display-only (the 17lands query uses --time-period, not dates).
"""
from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path

from bot.services.seventeenlands import SeventeenLandsClient
from bot.sets import ALL_SETS

FORMAT = "PremierDraft"
FIXTURES_DIR = Path(__file__).parent.parent.parent / "frontend/src/data/fixtures"

GIHWR_FIELD = "ever_drawn_win_rate"
GIH_FIELD = "drawn_game_count"


def load_card_names(fixture_path: Path) -> set[str]:
    """Extract card names from a cards-*.ts fixture."""
    text = fixture_path.read_text()
    start = text.index("[")
    end = text.index("] satisfies") + 1
    return {c["name"] for c in json.loads(text[start:end])}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--set-code", required=True, help="17lands expansion code, e.g. MSH")
    parser.add_argument("--phase", choices=["midway", "final"], default="midway")
    parser.add_argument(
        "--end-date",
        default=date.today().isoformat(),
        help="End date shown in the fixture's display-only dateRange (default: today)",
    )
    parser.add_argument(
        "--time-period",
        choices=["ALL_TIME", "LAST_TWO_WEEKS"],
        default="ALL_TIME",
        help="17lands query window (default: ALL_TIME)",
    )
    args = parser.parse_args()

    set_code = args.set_code.upper()
    matched = next((s for s in ALL_SETS if s.code == set_code), None)
    if matched is None:
        raise SystemExit(f"Unknown set code {set_code!r}. Add it to bot/sets.py first.")

    card_fixture = FIXTURES_DIR / f"cards-{set_code.lower()}.ts"
    if not card_fixture.exists():
        raise SystemExit(
            f"Card fixture not found: {card_fixture}\n"
            f"Run  python -m bot.scripts.fetch_p0p1_cards --set-code {set_code}  first."
        )
    pool_names = load_card_names(card_fixture)
    print(f"Card fixture has {len(pool_names)} cards")

    start = matched.start_date.isoformat()
    end = args.end_date
    output = FIXTURES_DIR / f"p0p1-ratings-{set_code.lower()}.ts"

    client = SeventeenLandsClient()
    print(f"Fetching {set_code} {FORMAT} card ratings from 17lands ({args.time_period})...")
    raw = client.fetch_card_ratings(set_code, FORMAT, time_period=args.time_period)
    print(f"Received {len(raw)} card rows")

    cards = []
    missing = 0
    filtered = 0
    for row in raw:
        name = row.get("name")
        gihwr = row.get(GIHWR_FIELD)
        gih = row.get(GIH_FIELD) or 0
        if not name:
            missing += 1
            continue
        if name not in pool_names:
            filtered += 1
            continue
        cards.append({
            "card_name": name,
            "gihwr": round(float(gihwr), 5) if gihwr is not None else None,
            "gih": int(gih),
        })

    if missing:
        print(f"Skipped {missing} rows with no card name")
    if filtered:
        print(f"Filtered {filtered} non-C/U cards (rares, mythics, bonus sheet)")

    payload = {
        "setCode": set_code,
        "phase": args.phase,
        "dateRange": {"start": start, "end": end},
        "cards": cards,
    }
    payload_json = json.dumps(payload, indent=2, ensure_ascii=False)
    ts_content = (
        'import type { RatingsSnapshot } from "../p0p1Results";\n'
        "\n"
        f"export default {payload_json} satisfies RatingsSnapshot;\n"
    )
    output.write_text(ts_content)
    print(f"Wrote {len(cards)} cards → {output}")
    print(f"phase={args.phase!r}  dateRange={start} → {end}")


if __name__ == "__main__":
    main()
