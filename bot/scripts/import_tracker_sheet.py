"""Import one set tab of the tracker spreadsheet into the draft tracker tables.

Matches each logged draft to a draft_events row, splits the note blob into per-match notes,
and copies the owned counts out of the card grid. Main Arena account only; alternate-account
drafts are noise and never match.

Needs the Google client libraries, which the bot does not ship:

    DATABASE_URL=postgresql://... uv run --no-project --with google-auth \\
        --with google-api-python-client --with sqlalchemy --with psycopg2-binary \\
        python -m bot.scripts.import_tracker_sheet --set MSH --user <uuid> [--apply]

Without --apply it prints the match table and writes nothing.
"""
from __future__ import annotations

import argparse
import json
import os
import re
from collections import defaultdict
from datetime import date, timedelta, timezone
from urllib.parse import quote
from urllib.request import Request, urlopen

from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from sqlalchemy import create_engine, text

from bot.config import OWNER_DISCORD_ID

SPREADSHEET_ID = "1ykMC8ZpbBBRrv83zpzRFe39r4Yr_z2BY5VjtijCfQeU"
KEY_PATH = os.path.expanduser("~/.config/gcloud/sheets-mcp-key.json")
LOCAL_TZ = timezone(timedelta(hours=-7))

# The spreadsheet's own queue vocabulary, which predates the 17lands format strings.
# TOKEN records how the draft was paid for, not which queue it was, so it matches any format
ENTRY_FORMATS = {
    "TRAD": "TradDraft",
    "TOKEN": None,
    "PREMIER": "PremierDraft",
    "QUICK": "QuickDraft",
    "PICK2": "PickTwoDraft",
    "CONT": "ContenderDraft",
}
MONTHS = {m: i for i, m in enumerate(
    ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"], start=1)}
SECTIONS = {"White", "Blue", "Black", "Red", "Green", "Multicolor", "Colorless"}


def sheet_service():
    creds = Credentials.from_service_account_file(
        KEY_PATH, scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"])
    return build("sheets", "v4", credentials=creds, cache_discovery=False)


def read_deck_log(svc, tab: str, year: int) -> list[dict]:
    values = svc.spreadsheets().values().get(
        spreadsheetId=SPREADSHEET_ID, range=f"{tab}!G15:Q120").execute().get("values", [])
    rows = []
    for raw in values:
        cells = [str(c).strip() for c in (raw + [""] * 11)[:11]]
        number, deck, entry, when, rares, mythics, wins, losses, _gems, _packs, note = cells
        if not number or not wins or not when:
            continue
        month, _, day = when.partition("/")
        if month not in MONTHS or not day.isdigit():
            continue
        rows.append({
            "n": int(number),
            "deck": deck,
            "format": ENTRY_FORMATS.get(entry.upper()),
            "entry": entry.upper(),
            "date": date(year, MONTHS[month], int(day)),
            "rares": int(rares) if rares.isdigit() else None,
            "mythics": int(mythics) if mythics.isdigit() else None,
            "note": note,
        })
    return rows


def set_card_names(set_code: str) -> dict[str, str]:
    """Front-face and full name to canonical name, so the grid's bonus blocks never import as cards"""
    canonical: dict[str, str] = {}
    url = ("https://api.scryfall.com/cards/search?q="
           + quote(f"set:{set_code.lower()} (rarity:rare or rarity:mythic)")
           + "&unique=cards&order=review")
    while url:
        request = Request(url, headers={"User-Agent": "LLU-tracker-import/1.0", "Accept": "application/json"})
        with urlopen(request) as response:
            page = json.load(response)
        for card in page["data"]:
            canonical[card["name"]] = card["name"]
            canonical.setdefault(card["name"].split(" // ")[0], card["name"])
        url = page["next_page"] if page.get("has_more") else None
    return canonical


def read_collection(svc, tab: str, canonical: dict[str, str]) -> tuple[dict[str, int], list[str]]:
    counts: dict[str, int] = {}
    for rng in (f"{tab}!A16:B130", f"{tab}!D16:E130"):
        for raw in svc.spreadsheets().values().get(
                spreadsheetId=SPREADSHEET_ID, range=rng).execute().get("values", []):
            cells = (raw + ["", ""])[:2]
            name, owned = str(cells[0]).strip(), str(cells[1]).strip()
            if not name or name in SECTIONS or not owned.isdigit():
                continue
            key = name if name in canonical else name.split(" // ")[0].strip()
            if key not in canonical:
                continue
            counts[canonical[key]] = max(0, min(4, int(owned)))
    missing = sorted({v for v in canonical.values()} - set(counts))
    return counts, missing


def split_note(note: str, is_bo3: bool, matches: int) -> tuple[str, dict[int, dict]]:
    """Return the draft-level preamble and per-match notes keyed on match number"""
    marker = re.compile(r"\bM(\d)\b") if is_bo3 else re.compile(r"\bG(\d)\b")
    hits = [(m.start(), int(m.group(1))) for m in marker.finditer(note)]
    hits = [(pos, n) for pos, n in hits if 1 <= n <= matches]
    if not hits:
        return note.strip(), {}

    preamble = note[: hits[0][0]].strip(" .,-")
    per_match: dict[int, dict] = {}
    for index, (pos, number) in enumerate(hits):
        end = hits[index + 1][0] if index + 1 < len(hits) else len(note)
        body = note[pos:end].strip()
        body = marker.sub("", body, count=1).strip(" .,-")
        if number in per_match:
            per_match[number]["note"] += " " + body
            continue
        opponent = re.match(r"vs\.?\s+([A-Za-z]{1,6})\b", body)
        if opponent:
            body = body[opponent.end():].strip(" .,-")
        per_match[number] = {"note": body, "opponent": opponent.group(1) if opponent else ""}
    return preamble, per_match


def load_events(conn, discord_id: str, set_code: str) -> list[dict]:
    rows = conn.execute(text("""
        SELECT de.id, de.format, de.wins, de.losses, de.finished_at, de.colors, de.account_id
        FROM draft_events de
        JOIN players p ON p.id = de.player_id
        JOIN sets s ON s.id = de.set_id
        WHERE p.discord_id = :discord_id AND s.code = :set_code
        ORDER BY de.finished_at
    """), {"discord_id": discord_id, "set_code": set_code}).mappings().all()
    events = [dict(r) for r in rows]
    by_account: dict[int, int] = defaultdict(int)
    for e in events:
        if e["account_id"] is not None:
            by_account[e["account_id"]] += 1
    if not by_account:
        return events
    main = max(by_account, key=lambda k: by_account[k])
    print(f"main account_id={main} ({by_account[main]} events); "
          f"skipping {sum(v for k, v in by_account.items() if k != main)} from other accounts")
    return [e for e in events if e["account_id"] == main]


def main_colors(value: str) -> frozenset[str]:
    return frozenset(c for c in value if c.isupper())


def match_rows(sheet_rows: list[dict], events: list[dict]) -> list[tuple[dict, dict | None]]:
    """Greedy chronological pairing, scoring each candidate on date drift then colour agreement"""
    unused = list(events)
    pairs = []
    for row in sorted(sheet_rows, key=lambda r: r["n"]):
        best = None
        best_score = None
        for event in unused:
            if row["format"] and event["format"] != row["format"]:
                continue
            drift = abs((event["finished_at"].astimezone(LOCAL_TZ).date() - row["date"]).days)
            if drift > 1:
                continue
            colors_differ = main_colors(event["colors"] or "") != main_colors(row["deck"])
            score = (drift, colors_differ, event["finished_at"])
            if best_score is None or score < best_score:
                best, best_score = event, score
        if best:
            unused.remove(best)
        pairs.append((row, best))
    return pairs


def main() -> None:
    ap = argparse.ArgumentParser(description="Import a tracker spreadsheet tab into the draft tracker")
    ap.add_argument("--set", dest="set_code", required=True)
    ap.add_argument("--tab", help="Spreadsheet tab, defaults to the set code")
    ap.add_argument("--user", required=True, help="auth user uuid the rows belong to")
    ap.add_argument("--discord-id", default=str(OWNER_DISCORD_ID))
    ap.add_argument("--year", type=int, default=2026)
    ap.add_argument("--apply", action="store_true", help="Write. Without it, print the plan only")
    args = ap.parse_args()

    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        raise SystemExit("DATABASE_URL is required")

    tab = args.tab or args.set_code
    svc = sheet_service()
    sheet_rows = read_deck_log(svc, tab, args.year)
    canonical = set_card_names(args.set_code)
    counts, missing = read_collection(svc, tab, canonical)
    print(f"sheet: {len(sheet_rows)} logged drafts, {len(counts)} of "
          f"{len(set(canonical.values()))} set cards carry a count")
    if missing:
        print(f"  no count in the grid for: {', '.join(missing[:6])}"
              + (f" and {len(missing) - 6} more" if len(missing) > 6 else ""))

    engine = create_engine(db_url)
    with engine.begin() as conn:
        events = load_events(conn, args.discord_id, args.set_code)
        print(f"database: {len(events)} events on the main account")

        pairs = match_rows(sheet_rows, events)
        matched = [(r, e) for r, e in pairs if e]
        print(f"matched {len(matched)} of {len(pairs)}\n")

        draft_writes = match_writes = 0
        for row, event in pairs:
            if not event:
                print(f"  MISS  #{row['n']:>2} {row['entry']:<8} {row['date']} {row['deck']}")
                continue
            matches = event["wins"] + event["losses"]
            preamble, per_match = split_note(row["note"], event["format"] == "TradDraft", matches)
            print(f"  ok    #{row['n']:>2} {row['entry']:<8} {row['date']} {row['deck']:<8} "
                  f"{event['wins']}-{event['losses']} -> {len(per_match)}/{matches} match notes")
            if not args.apply:
                continue

            conn.execute(text("""
                INSERT INTO tracker_draft_notes
                    (user_id, draft_event_id, note, deck_label, rares, mythics)
                VALUES (:user_id, :event_id, :note, :deck, :rares, :mythics)
                ON CONFLICT (user_id, draft_event_id)
                DO UPDATE SET note = EXCLUDED.note, deck_label = EXCLUDED.deck_label,
                              rares = EXCLUDED.rares, mythics = EXCLUDED.mythics, updated_at = now()
            """), {"user_id": args.user, "event_id": event["id"], "note": preamble, "deck": row["deck"],
                   "rares": row["rares"], "mythics": row["mythics"]})
            draft_writes += 1

            for number, payload in per_match.items():
                conn.execute(text("""
                    INSERT INTO tracker_match_notes
                        (user_id, draft_event_id, match_number, note, opponent_colors)
                    VALUES (:user_id, :event_id, :number, :note, :opponent)
                    ON CONFLICT (user_id, draft_event_id, match_number)
                    DO UPDATE SET note = EXCLUDED.note,
                                  opponent_colors = EXCLUDED.opponent_colors,
                                  updated_at = now()
                """), {"user_id": args.user, "event_id": event["id"], "number": number,
                       "note": payload["note"], "opponent": payload["opponent"]})
                match_writes += 1

        if args.apply:
            for name, owned in counts.items():
                conn.execute(text("""
                    INSERT INTO tracker_collection (user_id, set_code, card_name, owned)
                    VALUES (:user_id, :set_code, :card_name, :owned)
                    ON CONFLICT (user_id, set_code, card_name)
                    DO UPDATE SET owned = EXCLUDED.owned, updated_at = now()
                """), {"user_id": args.user, "set_code": args.set_code, "card_name": name, "owned": owned})
            print(f"\nwrote {draft_writes} draft notes, {match_writes} match notes, {len(counts)} card counts")
        else:
            print("\ndry run, nothing written. Re-run with --apply")


if __name__ == "__main__":
    main()
