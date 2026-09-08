"""Reconstruct pod maindecks from posted deck screenshots with local OCR.

For each tracked-set seat that has a deck_screenshot_url, this reads the image and infers main/side
from the layout geometry: an MTGA "Nx" sideboard column or a Draftmancer/MTGA "SIDEBOARD" panel on the
right. Card names are fuzzy-matched to the seat's closed drafted pool. A read is auto-applied only when
a sideboard list is found and its size matches the count the client prints; everything less confident is
flagged for manual review. Applied corrections rewrite pod_draft_events.draft_log (and its gzip mirror),
stamp decks[seat].correction, and re-derive that event's pod_card_stats.

Local tool. Install the OCR extras first (CPU torch):
    pip install -r requirements-ocr.txt --extra-index-url https://download.pytorch.org/whl/cpu

    DATABASE_URL=... DISCORD_BOT_TOKEN=... python -m bot.scripts.ocr_pod_decks [--commit] [--force] [event_id ...]

Without --commit it reports the AUTO/FLAG/SKIP verdicts and writes nothing. --force re-examines seats that
already carry a correction marker.
"""
from __future__ import annotations

import argparse
import gzip
import json
import re
import sys
import tempfile
import time
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from bot.config import settings
from bot.database import SessionLocal
from bot.models import PodDraftEvent, PodDraftParticipant
from bot.scripts.draftmancer_log import simulate
from bot.services.pod_card_extract import reingest_pod_card_facts, tracks_card_data

MATCH_MIN = 88
MAIN_FLOOR = 20
SIDE_LIST_MIN = 5
MARKER_SOURCE = "ocr-auto"
USER_AGENT = "DiscordBot (https://limitedlevelups.com, 1.0)"
# MTGA renders the sideboard quantity as "1x", which OCR often reads as "Ix"/"lx"/"|x".
NX_RE = re.compile(r"^[0-9il|]{1,2}x$")
CARDS_RE = re.compile(r"^\d+\s*cards?$")


def norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", s.lower())


def _is_nx(text: str) -> bool:
    return bool(NX_RE.match(text.replace(" ", "").lower()))


def _nx_value(text: str) -> int:
    digits = re.sub(r"\D", "", text)
    return int(digits) if digits else 1


@dataclass(frozen=True)
class Verdict:
    action: str  # AUTO | FLAG | SKIP
    layout: str
    main: frozenset[int] | None
    side: frozenset[int] | None
    note: str


def seat_pool(compact: dict, seat: int) -> dict[int, str]:
    idxs = [ci for pack in simulate(compact)[seat] for ci in pack]
    return {ci: compact["cards"][ci]["n"] for ci in idxs}


def classify(frags: list[dict], width: int, pool: dict[int, str]) -> Verdict:
    from rapidfuzz import fuzz, process

    pool_names = list({v for v in pool.values()})
    name_to_idxs: dict[str, list[int]] = {}
    for idx, name in pool.items():
        name_to_idxs.setdefault(name, []).append(idx)
    all_idxs = set(pool)

    claimed: set[int] = set()
    matched: list[tuple[int, float]] = []
    for f in frags:
        if len(norm(f["t"])) < 3:
            continue
        best_name, score, _ = process.extractOne(f["t"], pool_names, scorer=fuzz.WRatio)
        if score < MATCH_MIN:
            continue
        free = [i for i in name_to_idxs[best_name] if i not in claimed]
        if not free:
            continue
        claimed.add(free[0])
        matched.append((free[0], f["cx"]))
    if not matched:
        return Verdict("SKIP", "no-cards-read", None, None, "OCR read no pool cards")

    nx_right = [f for f in frags if f["cx"] > 0.55 * width and _is_nx(f["t"])]
    sb_right = [f for f in frags if f["cx"] > 0.55 * width and "sideboard" in norm(f["t"])]
    sb_x, layout = None, None
    if len(nx_right) >= 2:
        sb_x, layout = min(f["cx"] for f in nx_right) - 40, "mtga-1x-list"
    elif sb_right:
        sb_x, layout = max(sb_right, key=lambda f: f["cx"])["x0"] - 20, "sideboard-panel"

    if sb_x is not None:
        # Split at the 1x/SIDEBOARD anchor; auto-write when the fully-read side matches the printed count
        side_read = {idx for idx, cx in matched if cx >= sb_x}
        main_read = {idx for idx, cx in matched if cx < sb_x}
        if len(side_read) >= SIDE_LIST_MIN or len(nx_right) >= 2:
            if len(main_read) < MAIN_FLOOR:
                return Verdict("SKIP", layout, None, None, f"only {len(main_read)} maindeck cards left of anchor")
            expected_side = _printed_sideboard_size(frags, width, nx_right)
            if expected_side is not None:
                if len(side_read) == expected_side:
                    main = all_idxs - side_read
                    return Verdict("AUTO", layout, frozenset(main), frozenset(side_read),
                                   f"sideboard {len(side_read)} matches printed {expected_side}")
                if len(main_read) == len(all_idxs) - expected_side:
                    side = all_idxs - main_read
                    return Verdict("AUTO", layout, frozenset(main_read), frozenset(side),
                                   f"maindeck {len(main_read)} = pool - printed {expected_side}")
            main = all_idxs - side_read
            detail = f"side {len(side_read)}, main {len(main_read)} vs printed {expected_side}"
            return Verdict("FLAG", layout, frozenset(main), frozenset(all_idxs - main), f"unverified split ({detail})")

    main = {idx for idx, _ in matched}
    if len(main) < MAIN_FLOOR:
        return Verdict("SKIP", "too-few-cards", None, None, f"only {len(main)} cards read (scrolled/partial)")
    side = all_idxs - main
    return Verdict("FLAG", "no-sideboard-region", frozenset(main), frozenset(side),
                   "no sideboard region; maindeck read is recall-limited")


def _printed_sideboard_size(frags: list[dict], width: int, nx_tokens: list[dict]) -> int | None:
    for f in frags:
        if "sideboard" in norm(f["t"]):
            found = re.search(r"\d+", f["t"])
            if found and int(found.group()) <= 40:
                return int(found.group())
    for f in frags:
        if f["cx"] > 0.55 * width and CARDS_RE.match(f["t"].strip().lower()):
            n = int(re.search(r"\d+", f["t"]).group())
            if n <= 40:
                return n
    if nx_tokens:
        return sum(_nx_value(f["t"]) for f in nx_tokens)
    return None


def refresh_urls(urls: list[str], token: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for start in range(0, len(urls), 50):
        chunk = urls[start:start + 50]
        req = urllib.request.Request(
            "https://discord.com/api/v10/attachments/refresh-urls",
            data=json.dumps({"attachment_urls": chunk}).encode(),
            headers={"Authorization": f"Bot {token}", "Content-Type": "application/json", "User-Agent": USER_AGENT},
            method="POST",
        )
        body = json.loads(urllib.request.urlopen(req).read())
        for row in body["refreshed_urls"]:
            out[row["original"]] = row["refreshed"]
    return out


def download(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req) as resp:
        data = resp.read()
    handle = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
    handle.write(data)
    handle.close()
    return handle.name


def ocr_boxes(reader, path: str) -> list[dict]:
    out = []
    for bbox, text, conf in reader.readtext(path):
        xs = [p[0] for p in bbox]
        ys = [p[1] for p in bbox]
        out.append({"t": text, "x0": min(xs), "cx": sum(xs) / 4, "cy": sum(ys) / 4, "conf": conf})
    return out


def apply_correction(
    session: Session, event: PodDraftEvent, seat: int, main: frozenset[int], side: frozenset[int]
) -> None:
    compact = event.draft_log
    compact["decks"][seat]["main"] = sorted(main)
    compact["decks"][seat]["side"] = sorted(side)
    compact["decks"][seat]["correction"] = {"source": MARKER_SOURCE, "at": datetime.now(timezone.utc).isoformat()}
    flag_modified(event, "draft_log")
    event.draft_log_gz = gzip.compress(json.dumps(compact, separators=(",", ":")).encode(), compresslevel=9)


def target_events(session: Session, event_ids: list[str]) -> list[PodDraftEvent]:
    if event_ids:
        found = [session.get(PodDraftEvent, eid) for eid in event_ids]
        return [e for e in found if e is not None and isinstance(e.draft_log, dict)]
    rows = session.execute(
        select(PodDraftEvent).where(PodDraftEvent.draft_log.isnot(None))
    ).scalars().all()
    return [e for e in rows if tracks_card_data(e.set_code) and isinstance(e.draft_log, dict)]


def run(event_ids: list[str], commit: bool, force: bool) -> None:
    import easyocr
    from PIL import Image

    token = settings.discord_bot_token.get_secret_value() if settings.discord_bot_token else None
    if not token:
        sys.exit("DISCORD_BOT_TOKEN is required to refresh screenshot URLs")

    jobs: list[tuple[str, int, str, str, dict]] = []
    with SessionLocal() as session:
        for event in target_events(session, event_ids):
            urls = {
                p.seat_index: p.deck_screenshot_url
                for p in session.execute(
                    select(PodDraftParticipant).where(PodDraftParticipant.event_id == event.id)
                ).scalars().all()
                if p.seat_index is not None and p.deck_screenshot_url
            }
            decks = event.draft_log.get("decks") or []
            for seat, url in urls.items():
                if seat >= len(decks):
                    continue
                if decks[seat].get("correction") and not force:
                    continue
                jobs.append((event.id, seat, url, event.set_code, event.draft_log))

    if not jobs:
        print("no seats to process")
        return

    fresh = refresh_urls([j[2] for j in jobs], token)
    reader = easyocr.Reader(["en"], gpu=False, verbose=False)

    tally = {"AUTO": 0, "FLAG": 0, "SKIP": 0}
    times: list[float] = []
    touched: set[str] = set()
    flags: list[dict] = []
    for event_id, seat, url, _set_code, compact in jobs:
        path = download(fresh.get(url, url))
        width = Image.open(path).width
        t0 = time.time()
        frags = ocr_boxes(reader, path)
        times.append(time.time() - t0)
        v = classify(frags, width, seat_pool(compact, seat))
        tally[v.action] += 1
        tag = f"{event_id[:8]}#{seat}"
        main_n = len(v.main) if v.main is not None else 0
        print(f"{tag:14} {v.action:4} {v.layout:20} main={main_n:2d}  {v.note}")
        if v.action == "AUTO" and commit:
            with SessionLocal() as session:
                event = session.get(PodDraftEvent, event_id)
                apply_correction(session, event, seat, v.main, v.side)
                session.commit()
            touched.add(event_id)
        elif v.action == "FLAG":
            flags.append({"event_id": event_id, "seat": seat, "layout": v.layout, "note": v.note})

    for event_id in touched:
        reingest_pod_card_facts(event_id)

    print(f"\ntally: {tally}   auto-applied: {len(touched)} events" if commit else f"\ntally: {tally}   (dry run)")
    if times:
        print(
            f"per-screenshot OCR: avg {sum(times)/len(times):.1f}s  "
            f"min {min(times):.1f}s  max {max(times):.1f}s  n={len(times)}"
        )
    if flags:
        print(f"flagged for manual review: {len(flags)}")
        for f in flags:
            print(f"  {f['event_id'][:8]}#{f['seat']}  {f['layout']}  {f['note']}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("event_ids", nargs="*")
    parser.add_argument("--commit", action="store_true")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    run(args.event_ids, args.commit, args.force)


if __name__ == "__main__":
    main()
