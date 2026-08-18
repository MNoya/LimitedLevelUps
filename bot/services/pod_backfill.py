"""Utilities for scripted pod-draft seat backfills.

Use from one-off scripts or REPL sessions; there is no Discord command bound to these. A `None`
keyword preserves the current DB value (no clearing). `normalize_colors` enforces WUBRG order
(uppercase=main, lowercase=splash); `strip_cdn_dims` removes Discord CDN `width=`/`height=`
resize params from screenshot URLs.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from sqlalchemy.orm import Session

from bot.models import PodDraftEvent, PodDraftParticipant
from bot.services.pod_drafts import mark_first_pod


WUBRG_ORDER = "WUBRG"

CDN_DIM_RE = re.compile(r"&(?:width|height)=\d+")
COLORS_RE = re.compile(r"^[WUBRGwubrg]{1,5}$")
RECORD_RE = re.compile(r"^\d+-\d+$")


@dataclass(frozen=True)
class SeatResult:
    matched: bool
    changed_fields: list[str]
    error: str | None = None


def normalize_colors(s: str) -> str:
    main = sorted([c for c in s if c.isupper()], key=WUBRG_ORDER.index)
    splash = sorted([c for c in s if c.islower()], key=lambda c: WUBRG_ORDER.index(c.upper()))
    return "".join(main + splash)


def strip_cdn_dims(url: str) -> str:
    return CDN_DIM_RE.sub("", url)


def resolve_event(session: Session, slug_or_id: str) -> PodDraftEvent | None:
    event = session.get(PodDraftEvent, slug_or_id)
    if event is not None:
        return event
    target = slug_or_id.lower().strip("-")
    for ev in session.query(PodDraftEvent).all():
        if _slugify(ev.name) == target:
            return ev
    return None


def _slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def apply_seat(
    session: Session,
    event_id: str,
    seat: str,
    *,
    placement: int | None = None,
    record: str | None = None,
    colors: str | None = None,
    caption: str | None = None,
    screenshot: str | None = None,
) -> SeatResult:
    """Update one participant. Caller commits the session."""
    if colors is not None and not COLORS_RE.match(colors):
        return SeatResult(False, [], error=f"invalid colors `{colors}` (expected 1-5 of W/U/B/R/G)")
    if record is not None and not RECORD_RE.match(record):
        return SeatResult(False, [], error=f"invalid record `{record}` (expected `N-N`)")

    participant = (
        session.query(PodDraftParticipant)
        .filter(PodDraftParticipant.event_id == event_id)
        .filter(PodDraftParticipant.display_name == seat)
        .one_or_none()
    )
    if participant is None:
        return SeatResult(False, [], error=f"no participant `{seat}` in this event")

    changed: list[str] = []
    if placement is not None and participant.placement != placement:
        changed.append(f"placement {participant.placement}->{placement}")
        participant.placement = placement
    if record is not None and participant.record != record:
        changed.append(f"record {participant.record}->{record}")
        participant.record = record
    if colors is not None:
        normalized = normalize_colors(colors)
        if participant.deck_colors != normalized:
            changed.append(f"colors {participant.deck_colors}->{normalized}")
            participant.deck_colors = normalized
    if caption is not None and participant.deck_screenshot_caption != caption:
        changed.append("caption updated")
        participant.deck_screenshot_caption = caption
    if screenshot is not None:
        stripped = strip_cdn_dims(screenshot)
        if participant.deck_screenshot_url != stripped:
            changed.append("screenshot updated")
            participant.deck_screenshot_url = stripped

    if record is not None:
        session.flush()
        mark_first_pod(session, event_id)

    return SeatResult(True, changed)
