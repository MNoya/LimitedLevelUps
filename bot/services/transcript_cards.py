from __future__ import annotations

import logging

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from bot.models import Episode
from bot.scripts import card_index
from bot.scripts.card_links import tag_text
from bot.services.transcript_edit import CardTagger

log = logging.getLogger(__name__)


def build_card_tagger(session: Session, key: str) -> CardTagger | None:
    episode = session.execute(
        select(Episode).where(or_(Episode.youtube_id == key, Episode.guid == key))
    ).scalars().first()
    set_code = episode.set_code if episode else None
    if not set_code:
        return None
    try:
        card_names = card_index.set_card_names(set_code)
    except Exception:
        log.warning(f"card sheet fetch failed for set {set_code}, skipping card pass", exc_info=True)
        return None
    if not card_names:
        return None
    return lambda text: tag_text(text, card_names)
