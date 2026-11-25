"""Recompute ``episodes.category`` and ``set_code`` in place from the current classifier.

    DATABASE_URL=postgresql://... python -m bot.scripts.recategorize_episodes

No feed fetch — re-runs ``classify_episode`` over existing rows, so it
reflects seed / rule / set changes without a full media sync. Use to backfill after editing the
categorizer, the seed, or the set catalog.
"""

from __future__ import annotations

import collections
import logging

from sqlalchemy import select

from bot.database import SessionLocal
from bot.media_sets import EVERGREEN
from bot.models import Episode
from bot.services.media_sync import classify_episode

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
log = logging.getLogger("recategorize")


def main() -> None:
    counts: collections.Counter[str] = collections.Counter()
    category_changed = 0
    set_changed = 0
    with SessionLocal() as session:
        episodes = session.execute(select(Episode)).scalars().all()
        for episode in episodes:
            playlists = episode.playlists or []
            category, media_set = classify_episode(
                episode.guid, playlists, episode.title, episode.kind, episode.published_at
            )
            if episode.category != category:
                episode.category = category
                category_changed += 1
            counts[category] += 1

            set_code = None if media_set is EVERGREEN else media_set.code
            if episode.set_code != set_code:
                episode.set_code = set_code
                episode.set_name = None if media_set is EVERGREEN else media_set.name
                episode.set_released_at = None if media_set is EVERGREEN else media_set.start_date
                set_changed += 1
        session.commit()

    log.info(f"reclassified {len(episodes)} episodes — {category_changed} category, {set_changed} set changed")
    for category, count in counts.most_common():
        log.info(f"  {category}: {count}")


if __name__ == "__main__":
    main()
