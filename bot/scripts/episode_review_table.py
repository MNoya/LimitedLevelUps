"""Dump every episode with its classification for human review.

Writes ``episode-categories-review.md`` at the repo root. Read-only — it reuses the live
``classify_episode`` so the artifact reflects exactly what a sync would store, and pairs it
with the resolved set and the source playlists so each derivation can be checked by eye. Run
with DATABASE_URL pointed at the local DB.
"""

from __future__ import annotations

import re

from sqlalchemy import select

from bot.database import SessionLocal
from bot.media_sets import EVERGREEN
from bot.models import Episode
from bot.services.media_sync import classify_episode

_SHORT_MAX_S = 90
_SHORT_HASHTAG_MAX_S = 180
_HASHTAG = re.compile(r"#\w")


def episode_type(kind: str, duration_seconds: int, title: str) -> str:
    if kind != "video" or duration_seconds <= 0:
        return "podcast" if kind == "episode" else "video"
    if duration_seconds <= _SHORT_MAX_S:
        return "short"
    if duration_seconds <= _SHORT_HASHTAG_MAX_S and _HASHTAG.search(title):
        return "short"
    return "video"


def _cell(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ").strip()


def main() -> None:
    with SessionLocal() as session:
        episodes = session.execute(select(Episode).order_by(Episode.published_at.desc())).scalars().all()

    lines = [
        "# Episode categorization review",
        "",
        f"{len(episodes)} episodes, newest first. **Set**: one value, or — for none "
        "(Evergreen is NOT a set); **Category**: one value, where `Evergreen` is the catch-all for "
        "set-agnostic content (from the Evergreen Episodes playlist, or when nothing else matches). "
        "`Playlists` is the source so you can check each derivation.",
        "",
        "| # | Date | Type | Set | Category | Title | Playlists |",
        "|---|------|------|-----|----------|-------|-----------|",
    ]
    for index, episode in enumerate(episodes, 1):
        playlists = episode.playlists or []
        category, media_set = classify_episode(
            episode.guid, playlists, episode.title, episode.kind, episode.published_at
        )
        set_code = "—" if media_set.code == EVERGREEN.code else media_set.code
        kind = episode_type(episode.kind, episode.duration_seconds, episode.title)
        date = episode.published_at.strftime("%Y-%m-%d")
        playlist_cell = _cell(", ".join(playlists))
        lines.append(
            f"| {index} | {date} | {kind} | {set_code} | {category} | {_cell(episode.title)} | {playlist_cell} |"
        )

    with open("episode-categories-review.md", "w") as handle:
        handle.write("\n".join(lines) + "\n")
    print(f"wrote episode-categories-review.md ({len(episodes)} rows)")


if __name__ == "__main__":
    main()
