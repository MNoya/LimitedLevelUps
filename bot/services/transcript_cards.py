from __future__ import annotations

import logging

from sqlalchemy import delete, or_, select
from sqlalchemy.orm import Session

from bot.models import Episode, EpisodeTranscript, TranscriptCardMention
from bot.scripts import card_index
from bot.scripts.card_links import tag_text
from bot.services.transcript_edit import (
    CardTagger,
    TranscriptEditError,
    merge_transcript_segments,
    relink_changed_segments,
    word_count,
)

log = logging.getLogger(__name__)


def build_card_tagger(session: Session, key: str) -> CardTagger | None:
    episode = session.execute(
        select(Episode).where(or_(Episode.youtube_id == key, Episode.guid == key))
    ).scalars().first()
    set_code = episode.set_code if episode else None
    if not set_code:
        return None
    try:
        card_names = card_index.set_card_names(set_code, stale_ok=True)
    except Exception:
        log.warning(f"card sheet fetch failed for set {set_code}, skipping card pass", exc_info=True)
        return None
    if not card_names:
        return None
    return lambda text: tag_text(text, card_names)



def apply_transcript_edit(session: Session, key: str, incoming: list[dict]) -> tuple[str, int] | list[dict]:
    row = session.get(EpisodeTranscript, key)
    if row is None:
        return ("transcript not found", 404)
    stored = row.segments
    try:
        merged = merge_transcript_segments(stored, incoming)
    except TranscriptEditError as exc:
        return (str(exc), 400)
    tagger = build_card_tagger(session, key)
    if tagger is not None:
        relink_changed_segments(stored, merged, tagger)
    row.segments = merged
    row.word_count = word_count(merged)
    sync_card_mentions(session, key, merged)
    session.commit()
    return merged

def sync_card_mentions(session: Session, youtube_id: str, segments: list[dict]) -> None:
    session.flush()
    session.execute(delete(TranscriptCardMention).where(TranscriptCardMention.youtube_id == youtube_id))
    session.add_all(_card_mentions(youtube_id, segments))


def _card_mentions(youtube_id: str, segments: list[dict]) -> list[TranscriptCardMention]:
    mentions: list[TranscriptCardMention] = []
    for index, segment in enumerate(segments):
        opens_subtopic = bool(segment.get("heading") or segment.get("subheading"))
        names = {card["name"] for card in segment.get("cards", [])}
        for name in sorted(names):
            mention = TranscriptCardMention(
                youtube_id=youtube_id, segment_index=index, card_name=name, t=segment["t"],
                opens_subtopic=opens_subtopic,
            )
            mentions.append(mention)
    return mentions
