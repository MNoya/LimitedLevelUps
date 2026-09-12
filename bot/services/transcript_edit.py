from __future__ import annotations

import re
from collections.abc import Callable

EDITABLE_FIELDS = ("text", "heading", "subheading")

CardTagger = Callable[[str], tuple[str, list[dict]]]


class TranscriptEditError(ValueError):
    pass


def word_count(segments: list[dict]) -> int:
    total = 0
    for segment in segments:
        total += len(re.sub(r">{2,}", " ", segment["text"]).split())
    return total


def merge_transcript_segments(stored: list[dict], incoming: list[dict]) -> list[dict]:
    if len(stored) != len(incoming):
        raise TranscriptEditError("segment count differs from the stored transcript")
    merged: list[dict] = []
    for stored_segment, incoming_segment in zip(stored, incoming):
        text = str(incoming_segment.get("text", "")).strip()
        if not text:
            continue
        segment = dict(stored_segment)
        segment["text"] = text
        for label in ("heading", "subheading"):
            value = str(incoming_segment.get(label, "")).strip()
            if value:
                segment[label] = value
            else:
                segment.pop(label, None)
        merged.append(segment)
    if not merged:
        raise TranscriptEditError("a transcript cannot be empty")
    return merged


def relink_changed_segments(stored: list[dict], merged: list[dict], tagger: CardTagger) -> list[dict]:
    stored_by_t = {stored_segment["t"]: stored_segment for stored_segment in stored}
    for segment in merged:
        origin = stored_by_t.get(segment["t"])
        if origin is not None and segment["text"] == origin["text"]:
            continue
        corrected, cards = tagger(segment["text"])
        segment["text"] = corrected
        if cards:
            segment["cards"] = cards
        else:
            segment.pop("cards", None)
    return merged
