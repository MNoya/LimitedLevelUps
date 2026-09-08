"""Ingest a raw Draftmancer DraftLog into a pod_draft_events row.

Packs the log into the compact artifact build_compact emits, stores it on
pod_draft_events.draft_log (JSONB) and pod_draft_events.draft_log_gz, reconciles
pod_draft_participants.draftmancer_name to the canonical Draftmancer userName, and applies seat indexes.

Idempotent — re-ingesting overwrites the stored log and re-aligns names from the same log. Shared by
the CLI script (bot.scripts.ingest_pod_draft_log) and /pod-backfill.
"""
from __future__ import annotations

import gzip
import json
import logging
from dataclasses import dataclass

from sqlalchemy import select

from bot.database import SessionLocal
from bot.models import Player, PodDraftEvent, PodDraftParticipant
from bot.scripts.draftmancer_log import build_compact
from bot.services.pod_card_extract import tracks_card_data, rebuild_pod_card_facts
from bot.services.pod_drafts import apply_seat_indexes


log = logging.getLogger(__name__)


@dataclass(frozen=True)
class IngestSummary:
    applied: bool
    seats: int
    renamed: int
    unchanged: int
    arena_fixed: int
    unmatched: tuple[str, ...]
    stored_bytes: int
    renames: tuple[str, ...]
    arena_fixes: tuple[str, ...]


def log_user_names(draft_log: dict) -> list[str]:
    return [u["userName"] for u in draft_log["users"].values()]


def ingest_draft_log_sync(event_id: str, draft_log: dict) -> IngestSummary | None:
    """Match log seats to participants and store the compact log; one transaction. Returns None when
    the event is missing; an unapplied summary (with the unmatched names) when any log seat fails to
    match a participant — nothing is written in that case."""
    user_names = log_user_names(draft_log)
    with SessionLocal() as session:
        event = session.get(PodDraftEvent, event_id)
        if event is None:
            return None

        participants = session.execute(
            select(PodDraftParticipant).where(PodDraftParticipant.event_id == event_id)
        ).scalars().all()

        used: set[str] = set()
        renamed = 0
        unchanged = 0
        arena_fixed = 0
        unmatched: list[str] = []
        renames: list[str] = []
        arena_fixes: list[str] = []
        for name in user_names:
            p = _match_participant(name, participants, used)
            if p is None:
                unmatched.append(name)
                continue
            used.add(p.id)
            if p.draftmancer_name == name:
                unchanged += 1
            else:
                renames.append(f"{p.display_name!r}  {p.draftmancer_name!r} -> {name!r}")
                p.draftmancer_name = name
                renamed += 1
            if p.player_id is not None:
                player = session.get(Player, p.player_id)
                if player is not None and _arena_name_needs_fix(player.arena_name, name):
                    arena_fixes.append(f"{player.display_name!r}  {player.arena_name!r} -> {name!r}")
                    player.arena_name = name
                    arena_fixed += 1

        if unmatched:
            session.rollback()
            return IngestSummary(
                applied=False, seats=len(user_names), renamed=0, unchanged=0, arena_fixed=0,
                unmatched=tuple(unmatched), stored_bytes=0, renames=(), arena_fixes=(),
            )

        compact = build_compact(draft_log)
        event.draft_log_gz = gzip.compress(
            json.dumps(compact, separators=(",", ":")).encode(), compresslevel=9
        )
        event.draft_log = compact
        stored_bytes = len(event.draft_log_gz)
        apply_seat_indexes(session, event_id, compact.get("seats") or [])
        if tracks_card_data(event.set_code):
            rebuild_pod_card_facts(session, event_id, event.set_code, compact)
        session.commit()

    return IngestSummary(
        applied=True, seats=len(user_names), renamed=renamed, unchanged=unchanged,
        arena_fixed=arena_fixed, unmatched=(), stored_bytes=stored_bytes,
        renames=tuple(renames), arena_fixes=tuple(arena_fixes),
    )


def _arena_name_needs_fix(current: str | None, log_name: str) -> bool:
    """True if Player.arena_name is NULL, or if its #NNNN suffix is a strict prefix of the
    log's #NNNNN suffix AND the basename matches (truncated suffix repair). Leaves arena_name
    alone when the basename differs — that's a Draftmancer rename, not an Arena ID typo."""
    if current is None or not current.strip():
        return True
    cur_base, cur_suf = _split_name(current)
    log_base, log_suf = _split_name(log_name)
    if cur_base.casefold() != log_base.casefold():
        return False
    if cur_suf is None or log_suf is None:
        return False
    return cur_suf != log_suf and log_suf.startswith(cur_suf)


def _split_name(s: str) -> tuple[str, str | None]:
    if "#" in s:
        base, _, suf = s.rpartition("#")
        return base, suf
    return s, None


def _match_participant(
    log_name: str,
    participants: list[PodDraftParticipant],
    used: set[str],
) -> PodDraftParticipant | None:
    """Resolve a log userName to a participant row.

    Tries: exact draftmancer_name, then suffix-prefix (DB suffix is a prefix of log suffix —
    catches truncated #NNNN -> #NNNNN), then display_name basename + suffix prefix, then
    display_name basename alone, then draftmancer_name basename alone."""
    log_base, log_suf = _split_name(log_name)

    for p in participants:
        if p.id in used:
            continue
        if p.draftmancer_name and p.draftmancer_name == log_name:
            return p

    if log_suf is not None:
        for p in participants:
            if p.id in used:
                continue
            if not p.draftmancer_name or "#" not in p.draftmancer_name:
                continue
            _, db_suf = _split_name(p.draftmancer_name)
            if db_suf and log_suf.startswith(db_suf):
                return p

    if log_suf is not None:
        for p in participants:
            if p.id in used:
                continue
            db_base, db_suf = _split_name(p.display_name)
            if db_base.casefold() == log_base.casefold() and (db_suf is None or log_suf.startswith(db_suf)):
                return p

    for p in participants:
        if p.id in used:
            continue
        if p.display_name.casefold() == log_base.casefold():
            return p
        if p.draftmancer_name and _split_name(p.draftmancer_name)[0].casefold() == log_base.casefold():
            return p

    return None
