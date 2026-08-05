"""Extraction for /pod-backfill — reconstructing a pod event from its Discord thread.

Pure functions over scraped message snapshots; no Discord client, no DB.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from typing import Mapping, Sequence

from bot.services import pod_swiss
from bot.services.pod_backfill import normalize_colors
from bot.services.pod_deck_color import GUILDS
from bot.services.pod_drafts import parse_caption_record


@dataclass(frozen=True)
class ScrapedMessage:
    """Snapshot of one thread message — the command layer builds these from discord.Message."""
    author_id: str
    author_display: str
    author_is_bot: bool
    content: str
    image_url: str | None
    txt_attachments: tuple[tuple[str, str], ...]
    created_at: datetime


@dataclass(frozen=True)
class DeckPost:
    author_id: str
    author_display: str
    image_url: str
    caption: str | None
    record: str | None
    colors: str | None
    posted_at: datetime


@dataclass(frozen=True)
class MatchDraft:
    """One match in the confirmation workspace. source: 'db' | 'manual'."""
    round: int
    player_a: str
    player_b: str
    winner: str | None
    score: str | None
    reported_at: datetime | None
    source: str


def extract_deck_posts(messages: Sequence[ScrapedMessage]) -> dict[str, DeckPost]:
    """Latest deck image per author, mirroring the live capture gating: a record-captioned post
    locks the slot against later record-less images; a new record-captioned post always wins."""
    out: dict[str, DeckPost] = {}
    for m in sorted(messages, key=lambda m: m.created_at):
        if m.author_is_bot or m.image_url is None:
            continue
        caption = m.content.strip() or None
        record = parse_caption_record(caption)
        prev = out.get(m.author_id)
        if prev is not None and prev.record is not None and record is None:
            continue
        out[m.author_id] = DeckPost(
            author_id=m.author_id,
            author_display=m.author_display,
            image_url=m.image_url,
            caption=caption,
            record=record,
            colors=parse_caption_colors(caption),
            posted_at=m.created_at,
        )
    return out


WUBRG_LETTERS = frozenset("WUBRGwubrg")

COLOR_NICKNAMES = {
    **{name.lower(): code for code, name in GUILDS},
    "bant": "WUG", "esper": "WUB", "grixis": "UBR", "jund": "BRG", "naya": "WRG",
    "abzan": "WBG", "jeskai": "WUR", "sultai": "UBG", "mardu": "WBR", "temur": "URG",
}
COLOR_WORDS = {"white": "W", "blue": "U", "black": "B", "red": "R", "green": "G"}


def parse_caption_colors(caption: str | None) -> str | None:
    """First color signal in a deck caption, WUBRG-normalized ('1-2 RW failed WB' -> 'WR').
    Recognizes letter combos (2-5 WUBRG letters, no repeats, not all-lowercase — rejecting
    ordinary words like 'SB' or 'GG'), guild/shard/wedge nicknames ('rakdos' -> 'BR',
    'sultai' -> 'UBG'), and 'mono <color>'."""
    if not caption:
        return None
    tokens = re.findall(r"[A-Za-z]+", caption)
    for i, token in enumerate(tokens):
        lowered = token.lower()
        nickname = COLOR_NICKNAMES.get(lowered)
        if nickname:
            return nickname
        if lowered == "mono" and i + 1 < len(tokens):
            mono = COLOR_WORDS.get(tokens[i + 1].lower())
            if mono:
                return mono
        if not 2 <= len(token) <= 5:
            continue
        if any(c not in WUBRG_LETTERS for c in token):
            continue
        if token.islower():
            continue
        deduped = set(token.upper())
        if len(deduped) != len(token):
            continue
        return normalize_colors(token)
    return None


def extract_draft_log_attachment(messages: Sequence[ScrapedMessage]) -> tuple[str, str] | None:
    """(filename, url) of the latest DraftLog .txt posted in the thread; any .txt as fallback."""
    draft_logs: list[tuple[datetime, str, str]] = []
    other_txt: list[tuple[datetime, str, str]] = []
    for m in messages:
        for filename, url in m.txt_attachments:
            if not filename.lower().endswith(".txt"):
                continue
            bucket = draft_logs if "draftlog" in filename.lower() else other_txt
            bucket.append((m.created_at, filename, url))
    candidates = draft_logs or other_txt
    if not candidates:
        return None
    latest = max(candidates, key=lambda c: c[0])
    return latest[1], latest[2]


ROUND_FALLBACK = timedelta(minutes=55)
PLACEHOLDER_SCORE = "2-1"


def fill_reported_ats(matches: Sequence[MatchDraft], event_time: datetime) -> list[MatchDraft]:
    """Give every match a realistic reported_at — replay round-attribution windows derive from these.
    Matches without replay coverage borrow the latest known time in their round; rounds with no
    coverage at all step ROUND_FALLBACK per round from the event start (or the prior round's anchor)."""
    anchors: dict[int, datetime] = {}
    for m in matches:
        if m.reported_at is not None:
            current = anchors.get(m.round)
            if current is None or m.reported_at > current:
                anchors[m.round] = m.reported_at

    prev_anchor = event_time
    out: list[MatchDraft] = []
    for round_num in sorted({m.round for m in matches}):
        anchor = anchors.get(round_num)
        if anchor is None:
            anchor = prev_anchor + ROUND_FALLBACK
        for m in [m for m in matches if m.round == round_num]:
            if m.reported_at is None:
                m = replace(m, reported_at=anchor)
            out.append(m)
        prev_anchor = anchor
    return out


def compute_placements(
    names: Sequence[str],
    matches: Sequence[MatchDraft],
    records: Mapping[str, str | None] | None = None,
) -> list[pod_swiss.Standing]:
    """Standings over the confirmed matches, same tiebreakers the live finalize uses. Matches still
    missing a winner or score are excluded — placements firm up as the admin fills gaps. With no
    completed matches at all (pre-bot reconstructions where pairings are unrecoverable), falls back
    to ordering by the seats' caption records; seats without a record stay unplaced."""
    players = [pod_swiss.Player(id=n, name=n) for n in names]
    outcomes = [
        pod_swiss.MatchOutcome(
            round_num=m.round,
            player_a_id=m.player_a,
            player_b_id=m.player_b,
            winner_id=m.winner,
            score=m.score,
        )
        for m in matches
        if m.winner and m.score
    ]
    if not outcomes and records:
        return _standings_from_records(names, records)
    return pod_swiss.compute_standings(players, outcomes)


def _standings_from_records(names: Sequence[str], records: Mapping[str, str | None]) -> list[pod_swiss.Standing]:
    recorded: list[tuple[str, int, int]] = []
    for name in names:
        record = records.get(name)
        if not record or "-" not in record:
            continue
        wins_raw, losses_raw = record.split("-", 1)
        try:
            recorded.append((name, int(wins_raw), int(losses_raw)))
        except ValueError:
            continue
    recorded.sort(key=lambda entry: (-entry[1], entry[2], entry[0].lower()))
    return [
        pod_swiss.Standing(
            rank=i + 1, player_id=name, player_name=name,
            wins=wins, losses=losses, omw_pct=0.0, gw_pct=0.0, ogw_pct=0.0,
        )
        for i, (name, wins, losses) in enumerate(recorded)
    ]
