"""Tag one episode transcript's cards against a chosen set's sheet.

Many evergreen episodes draw their examples from a recent set without being tagged to it. This links their
card mentions deterministically against that set's card list, a safe whitelist that cannot produce the common-word
false positives the full oracle index does. Previews by default; ``--apply`` writes to the database the
``DATABASE_URL`` points at, after backing the transcript up under ``cache/transcript_backups/``.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import or_, select

from bot.database import SessionLocal
from bot.models import Episode, EpisodeTranscript
from bot.scripts import card_index
from bot.scripts.card_links import tag_text
from bot.services.transcript_edit import word_count

BACKUP_DIR = Path("cache/transcript_backups")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("episode", help="youtube_id, guid, or a title substring")
    parser.add_argument("set_code", help="set code whose sheet to match against, e.g. PIO")
    parser.add_argument("--apply", action="store_true", help="write to the database (default previews only)")
    args = parser.parse_args()

    with SessionLocal() as session:
        key, title = _resolve_episode(session, args.episode)
        if key is None:
            return
        row = session.get(EpisodeTranscript, key)
        if row is None:
            print(f"no transcript for {key} ({title})")
            return
        names = card_index.set_card_names(args.set_code)
        tagged, linked = _tag(row.segments, names)

        print(f"{title}\n  set {args.set_code.upper()} ({len(names)} cards) -> {len(linked)} distinct linked")
        for name in sorted(linked):
            mark = "  (single word, check)" if len(name.split()) == 1 else ""
            print(f"    {name}{mark}")

        if not args.apply:
            print("\npreview only; rerun with --apply to write")
            return

        _backup(key, row.segments)
        row.segments = tagged
        row.word_count = word_count(tagged)
        session.commit()
        print(f"\nwritten to prod; backup under {BACKUP_DIR}")


def _resolve_episode(session, identifier: str) -> tuple[str | None, str | None]:
    episode = session.execute(
        select(Episode).where(or_(Episode.youtube_id == identifier, Episode.guid == identifier))
    ).scalars().first()
    if episode is None:
        matches = session.execute(
            select(Episode).where(Episode.title.ilike(f"%{identifier}%"))
        ).scalars().all()
        if not matches:
            print(f"no episode matching {identifier!r}")
            return None, None
        if len(matches) > 1:
            print(f"{identifier!r} matches {len(matches)} episodes, be more specific:")
            for match in matches:
                print(f"  {match.youtube_id or match.guid}  {match.title}")
            return None, None
        episode = matches[0]
    return episode.youtube_id or episode.guid, episode.title


def _tag(segments: list[dict], names: list[str]) -> tuple[list[dict], list[str]]:
    linked: list[str] = []
    out: list[dict] = []
    for segment in segments:
        updated = dict(segment)
        corrected, cards = tag_text(segment["text"], names)
        updated["text"] = corrected
        if cards:
            updated["cards"] = cards
            for card in cards:
                if card["name"] not in linked:
                    linked.append(card["name"])
        else:
            updated.pop("cards", None)
        out.append(updated)
    return out, linked


def _backup(key: str, segments: list[dict]) -> None:
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    (BACKUP_DIR / f"{key}-{stamp}.json").write_text(json.dumps(segments))


if __name__ == "__main__":
    main()
