from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable

import discord
from discord import app_commands
from discord.ext import commands
from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from bot import audit, emojis
from bot.commands import descriptions as desc
from bot.commands.messages import MSG_NOT_REGISTERED
from bot.services.player_stats import (
    latest_cube_board, process_stats, rank_cube_board, rank_players_for_set,
    render_embed as render_stats_embed, resolve_player,
)
from bot.config import settings
from bot.database import SessionLocal
from bot.discord_helpers import display_width, player_url
from bot.models import (
    DraftEvent, LeaderboardMessage, MagicSet, Player, PlayerStats, PodDraftEvent, PodDraftParticipant,
    SelfReportedEvent,
)
from bot.scoring import (
    DEFAULT_QUEUE_GROUPS, QueueGroup, boxes_for_event, compute_score, pod_points, supported_formats,
)
from bot.services.active_set import resolve_board_set
from bot.services.pod_deck_color import PAIR_EMOJI_NAME
from bot.services.pod_drafts import POD_TROPHY_WINS, pod_record_wins, pod_summary_by_set_for_player
from bot.services.pod_format import PEASANT_CODE, custom_formats, is_custom, label_for
from bot.services.self_reported_events import rank_self_reported_events
from bot.sets import (
    ALL_SETS,
    CUBE_CODE,
    CUBE_VARIANTS,
    MTGO_FLASHBACK_SETS,
    CubeVariant,
    active_set_code,
    cube_board_code,
    cube_list_name,
    cube_season_for_code,
    cube_variant,
    cube_variant_for_board,
    is_cube_board_code,
    is_mtgo_flashback_code,
    seasoned_cube_variant,
    set_name_for,
)


# Color archetype label → PlayerArchetypeScore.archetype key
COLOR_CHOICES: dict[str, str] = {
    # 2-color guilds
    "Azorius":  "WU",
    "Orzhov":   "WB",
    "Boros":    "WR",
    "Selesnya": "WG",
    "Dimir":    "UB",
    "Izzet":    "UR",
    "Simic":    "UG",
    "Rakdos":   "BR",
    "Golgari":  "BG",
    "Gruul":    "RG",
    # 3-color shards/wedges
    "Esper":    "WUB",
    "Jeskai":   "WUR",
    "Bant":     "WUG",
    "Mardu":    "WBR",
    "Abzan":    "WBG",
    "Naya":     "WRG",
    "Grixis":   "UBR",
    "Sultai":   "UBG",
    "Temur":    "URG",
    "Jund":     "BRG",
    # 4+ color soup
    "Soup":     "MULTI",
}

logger = logging.getLogger(__name__)


@dataclass
class LcqExtras:
    d1_trophies: int = 0
    d2_wins: int = 0
    d2_losses: int = 0
    cash: int = 0


@dataclass
class LeaderboardEntry:
    rank: int
    player_id: str
    slug: str
    display_name: str
    score: float
    trophies: int
    events: int = 0
    lcq: LcqExtras | None = None


@dataclass
class PersonalStanding:
    set_code: str
    score: float
    trophies: int
    events: int
    wins: int
    losses: int
    rank: int | None


@dataclass
class PersonalStandingsData:
    player_name: str
    player_slug: str
    rows: list[PersonalStanding]
    opted_out: bool = False
    format_label: str | None = None
    last_updated: datetime | None = None


@dataclass
class LeaderboardData:
    set_code: str
    set_name: str
    top: list[LeaderboardEntry]
    viewer: LeaderboardEntry | None
    last_updated: datetime | None = None
    drafter_count: int = 0
    show_score: bool = True
    filter_type: str | None = None
    filter_value: str | None = None
    trophy_board: bool = False


def process_leaderboard(
    session: Session, viewer_discord_id: str | None, top_n: int = 10,
    include_zero_scores: bool = False, magic_set: MagicSet | None = None,
) -> LeaderboardData | None:
    if magic_set is None:
        magic_set = _current_set(session)
    if magic_set is None:
        return None

    ranked = rank_players_for_set(session, magic_set.id)

    # Default view hides players with no points yet — they're "drafting but
    # not on the board". The full-DM view passes include_zero_scores=True
    # so signed-up players who haven't scored still appear
    visible = ranked if include_zero_scores else [row for row in ranked if row[5] > 0]
    top = [
        LeaderboardEntry(rank=rank, player_id=pid, slug=slug, display_name=name, score=score, trophies=trophies)
        for rank, pid, slug, name, _did, score, trophies in visible[:top_n]
    ]

    viewer_entry: LeaderboardEntry | None = None
    if viewer_discord_id is not None:
        for rank, pid, slug, name, did, score, trophies in ranked:
            if did == viewer_discord_id:
                viewer_entry = LeaderboardEntry(
                    rank=rank, player_id=pid, slug=slug, display_name=name, score=score, trophies=trophies,
                )
                break

    last_updated = magic_set.last_refreshed_at
    if last_updated is None:
        last_updated = session.execute(
            select(func.max(PlayerStats.last_fetched_at))
            .where(PlayerStats.set_id == magic_set.id)
        ).scalar()

    drafter_count = session.execute(
        select(func.count(func.distinct(PlayerStats.player_id)))
        .join(Player, Player.id == PlayerStats.player_id)
        .where(
            PlayerStats.set_id == magic_set.id,
            PlayerStats.events > 0,
            Player.active.is_(True),
            Player.leaderboard_opt_in.is_(True),
        )
    ).scalar() or 0

    return LeaderboardData(
        set_code=magic_set.code,
        set_name=magic_set.name,
        top=top,
        viewer=viewer_entry,
        last_updated=last_updated,
        drafter_count=drafter_count,
    )


def process_cube_board(
    session: Session, viewer_discord_id: str | None, top_n: int = 10, board: str | None = None,
) -> LeaderboardData | None:
    """One cube board: a variant in full (``CUBE-PLANAR``) or one declared run of it (``CUBE-SOS``,
    ``CUBE-PLANAR-ZEN``). ``board`` of None takes the ongoing cube, or the last one that ran.

    set_code is the virtual board code so the embed title and site link land on that board's page.
    No pod points (cube boards are 17lands-cube only).
    """
    target = resolve_cube_board(session, board)
    if target is None:
        return None
    variant, season = target

    ranked = rank_cube_board(session, variant, season)
    if not ranked:
        return None

    top = [
        LeaderboardEntry(
            rank=r.rank, player_id=r.player_id, slug=r.slug,
            display_name=r.display_name, score=r.score, trophies=r.trophies,
        )
        for r in ranked[:top_n]
    ]
    viewer_entry: LeaderboardEntry | None = None
    if viewer_discord_id is not None:
        for r in ranked:
            if r.discord_id == viewer_discord_id:
                viewer_entry = LeaderboardEntry(
                    rank=r.rank, player_id=r.player_id, slug=r.slug,
                    display_name=r.display_name, score=r.score, trophies=r.trophies,
                )
                break

    last_updated = session.execute(
        select(func.max(PlayerStats.last_fetched_at))
        .join(MagicSet, MagicSet.id == PlayerStats.set_id)
        .where(MagicSet.code == CUBE_CODE)
    ).scalar()

    run = cube_season_for_code(season) if season else None
    return LeaderboardData(
        set_code=cube_board_code(season or variant.slug),
        set_name=f"{variant.name} — {run[1].display_label}" if run else variant.name,
        top=top,
        viewer=viewer_entry,
        last_updated=last_updated,
        drafter_count=len(ranked),
    )


def resolve_cube_board(session: Session, board: str | None) -> tuple[CubeVariant, str | None] | None:
    """Which cube board a ``/leaderboard set:`` value names, as ``(variant, season code or None)``.

    ``CUBE`` takes the board of the cube running now, or of the last one that ran. ``CUBE-<VARIANT>``
    is that cube in full and ``CUBE-<CODE>`` one declared run of it, the powered cube's ``CUBE-SOS``
    season or the planar cube's ``CUBE-PLANAR-ZEN`` week. The retired ``CUBE-ALL`` lands on the
    flagship cube's own board. None when the value names no cube board, or when no cube has been
    drafted at all.
    """
    slug = "" if board is None else board.upper().removeprefix(f"{CUBE_CODE}-")
    if slug == LIFETIME_SET:
        return seasoned_cube_variant(), None
    if board is None or slug in ("", CUBE_CODE):
        return latest_cube_board(session)
    variant = cube_variant(slug)
    if variant is not None:
        return variant, None
    season = cube_season_for_code(slug)
    if season is not None:
        return season[0], season[1].code
    return None


def _ranked_for_format(
    session: Session, groups: tuple[QueueGroup, ...], set_id: str,
) -> list[tuple[int, str, str, str, str | None, float, int]]:
    """Rank active, opted-in players by their score in the given queue groups for a set.

    Most filters resolve to a single group; LCQ spans Draft 1 + Draft 2. Returns
    (rank, player_id, slug, display_name, discord_id, score, trophies) per
    scoring player. Shared by the public format board and the personal standings rank.
    """
    rows = session.execute(
        select(
            Player.id, Player.slug, Player.display_name, Player.discord_id,
            PlayerStats.format, PlayerStats.events, PlayerStats.wins,
            PlayerStats.losses, PlayerStats.trophies,
        )
        .join(PlayerStats, PlayerStats.player_id == Player.id)
        .where(
            Player.active.is_(True),
            Player.leaderboard_opt_in.is_(True),
            PlayerStats.set_id == set_id,
            PlayerStats.format.in_(supported_formats(groups)),
        )
    ).all()

    bucket: dict[str, dict] = {}
    for r in rows:
        b = bucket.setdefault(r.id, {
            "slug": r.slug, "display_name": r.display_name, "discord_id": r.discord_id,
            "stats": [], "trophies": 0,
        })
        b["stats"].append({
            "format": r.format, "events": int(r.events or 0),
            "wins": int(r.wins or 0), "losses": int(r.losses or 0),
            "trophies": int(r.trophies or 0),
        })
        b["trophies"] += int(r.trophies or 0)

    scored: list[tuple[float, int, str, str, str, str | None]] = []
    for pid, b in bucket.items():
        score = compute_score(b["stats"], groups=groups)
        if score <= 0:
            continue
        scored.append((score, b["trophies"], pid, b["slug"], b["display_name"], b["discord_id"]))

    scored.sort(key=lambda x: (-x[0], x[4].lower()))
    return [
        (idx + 1, pid, slug, name, did, score, trophies)
        for idx, (score, trophies, pid, slug, name, did) in enumerate(scored)
    ]


LCQ_FILTER = "LCQ"
COMBINED_FORMAT_LABELS: dict[str, tuple[str, ...]] = {LCQ_FILTER: ("LCQ Draft 1", "LCQ Draft 2")}


def _groups_for_label(format_label: str) -> tuple[QueueGroup, ...] | None:
    labels = COMBINED_FORMAT_LABELS.get(format_label, (format_label,))
    groups = tuple(g for g in DEFAULT_QUEUE_GROUPS if g.label in labels)
    return groups or None


def process_leaderboard_for_format(
    session: Session, viewer_discord_id: str | None, format_label: str, top_n: int = 10,
    magic_set: MagicSet | None = None,
) -> LeaderboardData | None:
    """Per-format leaderboard: ranks each player by their score contribution
    in the named queue group (Premier, Quick, Sealed, etc.). LCQ rolls both
    LCQ queue groups into one board.
    """
    if magic_set is None:
        magic_set = _current_set(session)
    if magic_set is None:
        return None

    groups = _groups_for_label(format_label)
    if groups is None:
        return None

    ranked = _ranked_for_format(session, groups, magic_set.id)
    top = [
        LeaderboardEntry(rank=rank, player_id=pid, slug=slug, display_name=name, score=score, trophies=trophies)
        for rank, pid, slug, name, _did, score, trophies in ranked[:top_n]
    ]
    viewer_entry: LeaderboardEntry | None = None
    if viewer_discord_id is not None:
        for rank, pid, slug, name, did, score, trophies in ranked:
            if did == viewer_discord_id:
                viewer_entry = LeaderboardEntry(
                    rank=rank, player_id=pid, slug=slug, display_name=name, score=score, trophies=trophies,
                )
                break

    last_updated = magic_set.last_refreshed_at
    if last_updated is None:
        last_updated = session.execute(
            select(func.max(PlayerStats.last_fetched_at))
            .where(PlayerStats.set_id == magic_set.id)
        ).scalar()

    return LeaderboardData(
        set_code=magic_set.code,
        set_name=magic_set.name,
        top=top,
        viewer=viewer_entry,
        last_updated=last_updated,
        drafter_count=len(ranked),
    )


def process_leaderboard_for_lcq(
    session: Session, viewer_discord_id: str | None, top_n: int = 10,
    magic_set: MagicSet | None = None,
) -> LeaderboardData | None:
    """The combined LCQ format board, decorated with the per-player Draft 1 trophy
    count, Draft 2 record, and cash winnings the generic format board can't carry.
    """
    if magic_set is None:
        magic_set = _current_set(session)
    if magic_set is None:
        return None
    data = process_leaderboard_for_format(
        session, viewer_discord_id=viewer_discord_id, format_label=LCQ_FILTER, top_n=top_n, magic_set=magic_set,
    )
    if data is None:
        return None
    extras = _lcq_extras_by_player(session, magic_set.id)
    entries = data.top if data.viewer is None else data.top + [data.viewer]
    for e in entries:
        e.lcq = extras.get(e.player_id, LcqExtras())
    return data


def _lcq_cash_for_event(wins: int, losses: int) -> int:
    """Mirrors lcqCashPrize in frontend/src/data/utils.ts: $2K at 6+ wins, $1K at 5-2."""
    if wins >= 6:
        return 2000
    if wins == 5 and losses == 2:
        return 1000
    return 0


def _lcq_extras_by_player(session: Session, set_id: str) -> dict[str, LcqExtras]:
    d2_formats = next(g.formats for g in DEFAULT_QUEUE_GROUPS if g.label == "LCQ Draft 2")
    rows = session.execute(
        select(DraftEvent.player_id, DraftEvent.format, DraftEvent.wins, DraftEvent.losses, DraftEvent.is_trophy)
        .where(
            DraftEvent.set_id == set_id,
            DraftEvent.format.in_(supported_formats(_groups_for_label(LCQ_FILTER))),
        )
    ).all()
    extras: dict[str, LcqExtras] = {}
    for r in rows:
        e = extras.setdefault(r.player_id, LcqExtras())
        wins = int(r.wins or 0)
        losses = int(r.losses or 0)
        if r.format in d2_formats:
            e.d2_wins += wins
            e.d2_losses += losses
            e.cash += _lcq_cash_for_event(wins, losses)
        elif r.is_trophy:
            e.d1_trophies += 1
    return extras


def process_leaderboard_for_archetype(
    session: Session, viewer_discord_id: str | None, archetype: str, top_n: int = 10,
    magic_set: MagicSet | None = None, groups: tuple[QueueGroup, ...] | None = None,
) -> LeaderboardData | None:
    """Per-archetype (color combo) leaderboard. Aggregates from draft_events,
    filtering by archetype, then runs compute_score per player. When ``groups`` is
    given the board is scoped to those queue groups' formats and scored within them,
    so format + color combine.
    """
    if magic_set is None:
        magic_set = _current_set(session)
    if magic_set is None:
        return None

    allowed = set(supported_formats(groups)) if groups is not None else None
    events = session.execute(
        select(
            Player.id, Player.slug, Player.display_name, Player.discord_id,
            DraftEvent.format, DraftEvent.colors, DraftEvent.wins, DraftEvent.losses,
            DraftEvent.is_trophy,
        )
        .join(DraftEvent, DraftEvent.player_id == Player.id)
        .where(
            Player.active.is_(True),
            Player.leaderboard_opt_in.is_(True),
            DraftEvent.set_id == magic_set.id,
        )
    ).all()

    bucket: dict[str, dict] = {}
    for r in events:
        if allowed is not None and r.format not in allowed:
            continue
        if not _archetype_matches(r.colors, archetype, magic_set.code == CUBE_CODE):
            continue
        b = bucket.setdefault(r.id, {
            "slug": r.slug, "display_name": r.display_name, "discord_id": r.discord_id,
            "stats_by_format": {}, "trophies": 0,
        })
        f = b["stats_by_format"].setdefault(
            r.format,
            {"format": r.format, "events": 0, "wins": 0, "losses": 0, "trophies": 0},
        )
        f["events"] += 1
        f["wins"] += int(r.wins or 0)
        f["losses"] += int(r.losses or 0)
        if r.is_trophy:
            f["trophies"] += 1
            b["trophies"] += 1

    scored: list[tuple[float, int, str, str, str, str | None]] = []
    for pid, b in bucket.items():
        score = compute_score(list(b["stats_by_format"].values()), groups=groups) if groups \
            else compute_score(list(b["stats_by_format"].values()))
        if score <= 0:
            continue
        scored.append((score, b["trophies"], pid, b["slug"], b["display_name"], b["discord_id"]))

    scored.sort(key=lambda x: (-x[0], x[4].lower()))

    ranked = [
        (idx + 1, pid, slug, name, did, score, trophies)
        for idx, (score, trophies, pid, slug, name, did) in enumerate(scored)
    ]
    top = [
        LeaderboardEntry(rank=rank, player_id=pid, slug=slug, display_name=name, score=score, trophies=trophies)
        for rank, pid, slug, name, _did, score, trophies in ranked[:top_n]
    ]
    viewer_entry: LeaderboardEntry | None = None
    if viewer_discord_id is not None:
        for rank, pid, slug, name, did, score, trophies in ranked:
            if did == viewer_discord_id:
                viewer_entry = LeaderboardEntry(
                    rank=rank, player_id=pid, slug=slug, display_name=name, score=score, trophies=trophies,
                )
                break

    last_updated = session.execute(
        select(func.max(DraftEvent.fetched_at))
        .where(DraftEvent.set_id == magic_set.id)
    ).scalar()

    return LeaderboardData(
        set_code=magic_set.code,
        set_name=magic_set.name,
        top=top,
        viewer=viewer_entry,
        last_updated=last_updated,
        drafter_count=len(scored),
    )


def process_leaderboard_for_direct(
    session: Session, viewer_discord_id: str | None, top_n: int = 10,
    magic_set: MagicSet | None = None,
) -> LeaderboardData | None:
    """Arena Direct Sealed leaderboard: ranks players by boxes won.

    Box rules live in scoring.boxes_for_event — standard 6/7-win payouts plus
    collector-booster-weekend overrides. Per-event rather than aggregate so the
    date-windowed rule can fire.
    """
    if magic_set is None:
        magic_set = _current_set(session)
    if magic_set is None:
        return None

    ranked = _ranked_for_direct(session, magic_set.code, magic_set.id)
    top = [
        LeaderboardEntry(
            rank=rank, player_id=pid, slug=slug, display_name=name,
            score=boxes, trophies=trophies, events=round(boxes),
        )
        for rank, pid, slug, name, _did, boxes, trophies in ranked[:top_n]
    ]
    viewer_entry: LeaderboardEntry | None = None
    if viewer_discord_id is not None:
        for rank, pid, slug, name, did, boxes, trophies in ranked:
            if did == viewer_discord_id:
                viewer_entry = LeaderboardEntry(
                    rank=rank, player_id=pid, slug=slug, display_name=name,
                    score=boxes, trophies=trophies, events=round(boxes),
                )
                break

    last_updated = session.execute(
        select(func.max(DraftEvent.fetched_at))
        .where(DraftEvent.set_id == magic_set.id, DraftEvent.format == "ArenaDirect_Sealed")
    ).scalar()

    return LeaderboardData(
        set_code=magic_set.code,
        set_name=magic_set.name,
        top=top,
        viewer=viewer_entry,
        last_updated=last_updated,
        drafter_count=len(ranked),
        show_score=False,
    )


def _ranked_for_direct(
    session: Session, set_code: str, set_id: str,
) -> list[tuple[int, str, str, str, str | None, float, int]]:
    """Rank active, opted-in players by Arena Direct Sealed boxes won for a set.

    Returns (rank, player_id, slug, display_name, discord_id, boxes, trophies); a trophy is
    17lands' event win, so the 6-win-era ladders count too. Shared by the public Direct
    board and the personal standings rank.
    """
    rows = session.execute(
        select(
            Player.id, Player.slug, Player.display_name, Player.discord_id,
            DraftEvent.wins, DraftEvent.finished_at, DraftEvent.is_trophy,
        )
        .join(DraftEvent, DraftEvent.player_id == Player.id)
        .where(
            Player.active.is_(True),
            Player.leaderboard_opt_in.is_(True),
            DraftEvent.set_id == set_id,
            DraftEvent.format == "ArenaDirect_Sealed",
        )
    ).all()

    bucket: dict[str, dict] = {}
    for r in rows:
        b = bucket.setdefault(r.id, {
            "slug": r.slug, "display_name": r.display_name, "discord_id": r.discord_id,
            "boxes": 0, "trophies": 0,
        })
        wins = int(r.wins or 0)
        b["boxes"] += boxes_for_event(set_code, wins, r.finished_at, bool(r.is_trophy))
        if r.is_trophy:
            b["trophies"] += 1

    scored = [
        (b["boxes"], b["trophies"], pid, b["slug"], b["display_name"], b["discord_id"])
        for pid, b in bucket.items()
        if b["boxes"] > 0
    ]
    scored.sort(key=lambda x: (-x[0], -x[1], x[4].lower()))
    return [
        (idx + 1, pid, slug, name, did, float(boxes), trophies)
        for idx, (boxes, trophies, pid, slug, name, did) in enumerate(scored)
    ]


def process_leaderboard_for_pod(
    session: Session, viewer_discord_id: str | None, top_n: int = 10,
    magic_set: MagicSet | None = None,
) -> LeaderboardData | None:
    """Pod-draft leaderboard for the active set: ranked by trophies, no score column."""
    if magic_set is None:
        magic_set = _current_set(session)
    if magic_set is None:
        return None
    return _pod_board(session, viewer_discord_id, top_n, set_code=magic_set.code, set_name=magic_set.name)


def process_leaderboard_for_custom(
    session: Session, code: str, viewer_discord_id: str | None, top_n: int = 10,
) -> LeaderboardData:
    """A custom-format pod board: a single season-long board, independent of the selected set."""
    return _pod_board(session, viewer_discord_id, top_n, set_code=code, set_name=label_for(code) or code)


def process_leaderboard_for_peasant(
    session: Session, viewer_discord_id: str | None, top_n: int = 10,
) -> LeaderboardData:
    return process_leaderboard_for_custom(session, PEASANT_CODE, viewer_discord_id, top_n)


def process_leaderboard_for_mtgo(session: Session, set_code: str, top_n: int = 25) -> LeaderboardData:
    """MTGO flashback board: self-reported results ranked by trophy count, a snapshot with no scored
    data. Non-trophy decks don't lift the standing but keep their loggers on the board."""
    ranked = rank_self_reported_events(session, set_code)
    top = [
        LeaderboardEntry(
            rank=idx + 1,
            player_id=player.discord_id or player.id,
            slug=player.slug,
            display_name=player.display_name,
            score=0.0,
            trophies=trophy_count,
        )
        for idx, (player, trophy_count, _deck_count) in enumerate(ranked[:top_n])
    ]
    return LeaderboardData(
        set_code=set_code.upper(),
        set_name=set_name_for(set_code),
        top=top,
        viewer=None,
        drafter_count=len(ranked),
        show_score=False,
        trophy_board=True,
    )


def process_leaderboard_for_trophies(session: Session, magic_set: MagicSet, top_n: int = 10) -> LeaderboardData:
    """Trophy count board for a set: every trophy from every source, summed and ranked, no score.

    17lands drafts and pod wins come from the scored board, so a player's count matches the trophy
    column there. Self-reports are added on top with no opt-in gate: a mobile or paper player with no
    17lands profile has nothing else to stand on, and a `/trophy` row is already a post they made
    themselves.
    """
    tallies: dict[str, _TrophyTally] = {}
    for row in rank_players_for_set(session, magic_set.id):
        if row.trophies > 0:
            tallies[row.player_id] = _TrophyTally(
                row.player_id, row.slug, row.display_name, row.discord_id, row.trophies,
            )
    for player, self_reported, _deck_count in rank_self_reported_events(session, magic_set.code):
        if self_reported == 0:
            continue
        tally = tallies.get(player.id)
        if tally is None:
            tallies[player.id] = _TrophyTally(
                player.id, player.slug, player.display_name, player.discord_id, self_reported,
            )
        else:
            tally.trophies += self_reported

    ranked = sorted(tallies.values(), key=lambda tally: (-tally.trophies, tally.display_name.lower()))
    top = [
        LeaderboardEntry(
            rank=rank,
            player_id=tally.discord_id or tally.player_id,
            slug=tally.slug,
            display_name=tally.display_name,
            score=0.0,
            trophies=tally.trophies,
        )
        for rank, tally in enumerate(ranked[:top_n], start=1)
    ]
    return LeaderboardData(
        set_code=magic_set.code.upper(),
        set_name=magic_set.name,
        top=top,
        viewer=None,
        last_updated=_trophy_board_last_updated(session, magic_set),
        drafter_count=len(ranked),
        show_score=False,
        trophy_board=True,
    )


@dataclass
class _TrophyTally:
    player_id: str
    slug: str
    display_name: str
    discord_id: str | None
    trophies: int


def _trophy_board_last_updated(session: Session, magic_set: MagicSet) -> datetime | None:
    """When the trophy board last moved. Self-reports land whenever a player runs `/trophy`, between
    17lands refreshes, so the newer of the two stamps is the one the footer can stand behind."""
    refreshed_at = magic_set.last_refreshed_at
    if refreshed_at is None:
        refreshed_at = session.execute(
            select(func.max(PlayerStats.last_fetched_at))
            .where(PlayerStats.set_id == magic_set.id)
        ).scalar()
    reported_at = session.execute(
        select(func.max(SelfReportedEvent.reported_at))
        .where(func.upper(SelfReportedEvent.set_code) == magic_set.code.upper())
    ).scalar()

    stamps = [stamp for stamp in (refreshed_at, reported_at) if stamp is not None]
    return max(stamps) if stamps else None


def _pod_board(
    session: Session, viewer_discord_id: str | None, top_n: int, set_code: str, set_name: str,
) -> LeaderboardData:
    trophy_expr = func.coalesce(func.sum(case((pod_record_wins() >= POD_TROPHY_WINS, 1), else_=0)), 0)
    events_expr = func.count(PodDraftParticipant.id)

    rows = session.execute(
        select(
            Player.id, Player.slug, Player.display_name, Player.discord_id,
            trophy_expr.label("trophies"),
            events_expr.label("events"),
        )
        .join(PodDraftParticipant, PodDraftParticipant.player_id == Player.id)
        .join(PodDraftEvent, PodDraftEvent.id == PodDraftParticipant.event_id)
        .where(
            Player.active.is_(True),
            PodDraftParticipant.record.is_not(None),
            func.upper(PodDraftEvent.set_code) == set_code.upper(),
        )
        .group_by(Player.id, Player.slug, Player.display_name, Player.discord_id)
        .order_by(trophy_expr.desc(), events_expr.desc(), Player.display_name.asc())
    ).all()

    ranked = [
        (idx + 1, r.id, r.slug, r.display_name, r.discord_id, int(r.trophies), int(r.events))
        for idx, r in enumerate(rows)
    ]
    top = [
        LeaderboardEntry(
            rank=rank, player_id=pid, slug=slug, display_name=name,
            score=float(trophies), trophies=trophies, events=events,
        )
        for rank, pid, slug, name, _did, trophies, events in ranked[:top_n]
    ]
    viewer_entry: LeaderboardEntry | None = None
    if viewer_discord_id is not None:
        for rank, pid, slug, name, did, trophies, events in ranked:
            if did == viewer_discord_id:
                viewer_entry = LeaderboardEntry(
                    rank=rank, player_id=pid, slug=slug, display_name=name,
                    score=float(trophies), trophies=trophies, events=events,
                )
                break

    last_updated = session.execute(
        select(func.max(PodDraftEvent.event_time))
        .where(
            func.upper(PodDraftEvent.set_code) == set_code.upper(),
            PodDraftEvent.event_time <= func.now(),
        )
    ).scalar()

    return LeaderboardData(
        set_code=set_code,
        set_name=set_name,
        top=top,
        viewer=viewer_entry,
        last_updated=last_updated,
        drafter_count=0,
        show_score=False,
    )


PERSONAL_STANDINGS_LIMIT = 10
DIRECT_FILTER = "Direct"
LIFETIME_SET = "ALL"


def process_personal_standings(
    session: Session, viewer_discord_id: str, *, player_name: str | None = None,
    format_label: str | None = None,
) -> PersonalStandingsData | None:
    """A player's best sets: score and trophies per set they've drafted, top points first.

    Subject is ``player_name`` when given, else the caller. Aggregates the player's
    PlayerStats per set (alchemy variants bucket under their parent set via set_id),
    sorts by score then trophies, and caps at the top 10. When ``format_label`` names a
    format filter, each row is scoped to its queue groups' formats and ranked against
    that set's per-format board.
    """
    player = resolve_player(session, player_name, viewer_discord_id)
    if player is None:
        return None

    opted_out = not player.leaderboard_opt_in
    last_updated = session.execute(
        select(func.max(PlayerStats.last_fetched_at)).where(PlayerStats.player_id == player.id)
    ).scalar()

    if format_label == DIRECT_FILTER:
        return _personal_direct_standings(session, player, opted_out, last_updated)

    groups: tuple[QueueGroup, ...] | None = None
    if format_label is not None:
        groups = _groups_for_label(format_label)
        if groups is None:
            return None
    allowed = set(supported_formats(groups)) if groups is not None else None

    stats_rows = session.execute(
        select(
            MagicSet.id, MagicSet.code, PlayerStats.format, PlayerStats.events,
            PlayerStats.wins, PlayerStats.losses, PlayerStats.trophies,
        )
        .join(MagicSet, MagicSet.id == PlayerStats.set_id)
        .where(PlayerStats.player_id == player.id)
    ).all()

    by_set: dict[str, dict] = {}
    for r in stats_rows:
        if allowed is not None and r.format not in allowed:
            continue
        b = by_set.setdefault(r.id, {
            "code": r.code, "stats": [], "trophies": 0, "events": 0, "wins": 0, "losses": 0,
        })
        b["stats"].append({
            "format": r.format, "events": int(r.events or 0),
            "wins": int(r.wins or 0), "losses": int(r.losses or 0), "trophies": int(r.trophies or 0),
        })
        b["trophies"] += int(r.trophies or 0)
        b["events"] += int(r.events or 0)
        b["wins"] += int(r.wins or 0)
        b["losses"] += int(r.losses or 0)

    pod_by_set = pod_summary_by_set_for_player(session, player.id) if groups is None else {}
    missing_pod_codes = [code for code in pod_by_set if code not in {b["code"] for b in by_set.values()}]
    if missing_pod_codes:
        for s in session.execute(
            select(MagicSet.id, MagicSet.code).where(MagicSet.code.in_(missing_pod_codes))
        ).all():
            by_set.setdefault(s.id, {
                "code": s.code, "stats": [], "trophies": 0, "events": 0, "wins": 0, "losses": 0,
            })

    rows: list[PersonalStanding] = []
    for set_id, b in by_set.items():
        if groups is not None:
            if b["events"] == 0:
                continue
            score = compute_score(b["stats"], groups=groups)
            rank = None if opted_out else _set_rank_for_format(session, groups, set_id, player.id, score)
        else:
            pod = pod_by_set.get(b["code"])
            pod_pts = pod_points(pod.trophies, pod.wins_2_1) if pod else 0
            score = compute_score(b["stats"]) + pod_pts
            rank = None if opted_out else _set_rank(session, set_id, player.id, score)
        rows.append(PersonalStanding(
            set_code=b["code"], score=score, trophies=b["trophies"],
            events=b["events"], wins=b["wins"], losses=b["losses"], rank=rank,
        ))
    if opted_out:
        rows.sort(key=lambda r: (-r.trophies, -r.score, r.set_code))
    else:
        rows.sort(key=lambda r: (-r.score, -r.trophies, r.set_code))
    return PersonalStandingsData(
        player_name=player.display_name, player_slug=player.slug,
        rows=rows[:PERSONAL_STANDINGS_LIMIT], opted_out=opted_out,
        format_label=format_label if groups is not None else None,
        last_updated=last_updated,
    )


def _set_rank(session: Session, set_id: str, player_id: str, score: float) -> int | None:
    """The player's standing on a set's public board. Opted-in players read straight
    from rank_players_for_set; an opted-out viewer gets the slot their score would take.
    """
    ranked = rank_players_for_set(session, set_id)
    return _rank_of(ranked, player_id, score)


def _set_rank_for_format(
    session: Session, groups: tuple[QueueGroup, ...], set_id: str, player_id: str, score: float,
) -> int | None:
    """The player's standing on a set's per-format board, same opted-out fallback as _set_rank."""
    ranked = _ranked_for_format(session, groups, set_id)
    return _rank_of(ranked, player_id, score)


def _set_rank_for_direct(
    session: Session, set_code: str, set_id: str, player_id: str, boxes: float,
) -> int | None:
    """The player's standing on a set's Direct board, same opted-out fallback as _set_rank."""
    ranked = _ranked_for_direct(session, set_code, set_id)
    return _rank_of(ranked, player_id, boxes)


def _personal_direct_standings(
    session: Session, player: Player, opted_out: bool, last_updated: datetime | None = None,
) -> PersonalStandingsData:
    """Per-set Arena Direct Sealed standings for one player, ranked by boxes won.

    Mirrors the public Direct board: ``score`` carries boxes (the headline metric, no
    points), a trophy is 17lands' event win so the 6-win-era ladders count too, ranked
    against each set's Direct board.
    """
    rows_q = session.execute(
        select(
            MagicSet.id, MagicSet.code,
            DraftEvent.wins, DraftEvent.losses, DraftEvent.finished_at, DraftEvent.is_trophy,
        )
        .join(MagicSet, MagicSet.id == DraftEvent.set_id)
        .where(
            DraftEvent.player_id == player.id,
            DraftEvent.format == "ArenaDirect_Sealed",
        )
    ).all()

    by_set: dict[str, dict] = {}
    for r in rows_q:
        b = by_set.setdefault(r.id, {
            "code": r.code, "events": 0, "wins": 0, "losses": 0, "boxes": 0, "trophies": 0,
        })
        wins = int(r.wins or 0)
        b["events"] += 1
        b["wins"] += wins
        b["losses"] += int(r.losses or 0)
        b["boxes"] += boxes_for_event(r.code, wins, r.finished_at, bool(r.is_trophy))
        if r.is_trophy:
            b["trophies"] += 1

    rows: list[PersonalStanding] = []
    for set_id, b in by_set.items():
        boxes = float(b["boxes"])
        rank = None if opted_out else _set_rank_for_direct(session, b["code"], set_id, player.id, boxes)
        rows.append(PersonalStanding(
            set_code=b["code"], score=boxes, trophies=b["trophies"],
            events=b["events"], wins=b["wins"], losses=b["losses"], rank=rank,
        ))
    rows.sort(key=lambda r: (-r.score, -r.trophies, r.set_code))
    return PersonalStandingsData(
        player_name=player.display_name, player_slug=player.slug,
        rows=rows[:PERSONAL_STANDINGS_LIMIT], opted_out=opted_out, format_label=DIRECT_FILTER,
        last_updated=last_updated,
    )


def _rank_of(
    ranked: list[tuple[int, str, str, str, str | None, float, int]], player_id: str, score: float,
) -> int | None:
    for entry in ranked:
        if entry[1] == player_id:
            return entry[0]
    if score <= 0:
        return None
    return sum(1 for e in ranked if e[5] > score) + 1


MEDAL_EMOJIS = {1: "🥇", 2: "🥈", 3: "🥉"}

ALL_FORMATS_VALUE = "__all__"
ALL_COLORS_VALUE = "__all__"

_FORMAT_FILTERS: list[tuple[str, str | None]] = [
    ("All Formats", None),
    ("Premier", "Premier"),
    ("Traditional", "Trad"),
    ("Sealed", "Sealed"),
    ("Quick", "Quick"),
    ("LCQ", "LCQ"),
    ("Pod", "Pod"),
    ("Direct", "Direct"),
]

_UNSET = object()

# 3-color emoji names are WUBRG-canonical; the assets may not be uploaded yet, in which
# case get_emoji returns None and the option renders without an icon.
TRI_EMOJI_NAME: dict[frozenset[str], str] = {
    frozenset("WUB"): "manawub",
    frozenset("WUR"): "manawur",
    frozenset("WUG"): "manawug",
    frozenset("WBR"): "manawbr",
    frozenset("WBG"): "manawbg",
    frozenset("WRG"): "manawrg",
    frozenset("UBR"): "manaubr",
    frozenset("UBG"): "manaubg",
    frozenset("URG"): "manaurg",
    frozenset("BRG"): "manabrg",
}
SOUP_EMOJI_NAME = "manawubrg"


def _archetype_emoji(code: str) -> discord.Emoji | None:
    if code == "MULTI":
        name = SOUP_EMOJI_NAME
    elif len(code) == 2:
        name = PAIR_EMOJI_NAME.get(frozenset(code))
    elif len(code) == 3:
        name = TRI_EMOJI_NAME.get(frozenset(code))
    else:
        name = None
    return emojis.get_emoji(name) if name else None


def _render_ephemeral_board(
    session: Session, set_code: str, format_value: str | None, color_value: str | None,
    viewer_discord_id: str | None,
) -> discord.Embed | None:
    """Render the leaderboard embed for a personal, ephemeral filter view.

    Powers the 🔎 Filter button's per-user explorer: nothing shared is touched, so
    one viewer's filtering never mutates the posted snapshot for everyone else.
    """
    magic_set = session.execute(
        select(MagicSet).where(func.upper(MagicSet.code) == set_code.upper())
    ).scalar_one_or_none()
    filter_type, filter_value = encode_filter(format_value, color_value)
    data, suffix = render_filtered_data(
        session, filter_type=filter_type, filter_value=filter_value,
        viewer_discord_id=viewer_discord_id, magic_set=magic_set,
    )
    if data is None:
        return None
    embed = render_public_embed(data)
    if suffix:
        embed.title = f"{embed.title} {suffix}"
    return embed


MAX_SELECT_OPTIONS = 25


class _SetSelect(discord.ui.Select):
    def __init__(self, current_code: str) -> None:
        newest_first = list(reversed(ALL_SETS))
        shown = newest_first[:MAX_SELECT_OPTIONS]
        if all(s.code != current_code for s in shown):
            for s in newest_first:
                if s.code == current_code:
                    shown = [s, *shown[: MAX_SELECT_OPTIONS - 1]]
                    break
        options = [
            discord.SelectOption(
                label=s.code, description=s.name[:100], value=s.code,
                default=(s.code == current_code),
            )
            for s in shown
        ]
        super().__init__(placeholder="Set", min_values=1, max_values=1, options=options, row=0)

    async def callback(self, interaction: discord.Interaction) -> None:
        await self.view.apply(interaction, set_code=self.values[0])


class _FormatSelect(discord.ui.Select):
    def __init__(self, format_value: str | None) -> None:
        options = [
            discord.SelectOption(
                label=label, value=value or ALL_FORMATS_VALUE,
                default=(format_value == value),
            )
            for label, value in _FORMAT_FILTERS
        ]
        super().__init__(placeholder="Format", min_values=1, max_values=1, options=options, row=1)

    async def callback(self, interaction: discord.Interaction) -> None:
        value = self.values[0]
        await self.view.apply(interaction, format_value=None if value == ALL_FORMATS_VALUE else value)


class _ColorSelect(discord.ui.Select):
    def __init__(self, color_value: str | None, with_emoji: bool = True) -> None:
        options = [discord.SelectOption(label="All colors", value=ALL_COLORS_VALUE)]
        options += [
            discord.SelectOption(
                label="Soup (4+ color)" if code == "MULTI" else f"{label} ({code})",
                value=code,
                emoji=_archetype_emoji(code) if with_emoji else None,
                default=(color_value == code),
            )
            for label, code in COLOR_CHOICES.items()
        ]
        super().__init__(placeholder="Color", min_values=1, max_values=1, options=options, row=2)

    async def callback(self, interaction: discord.Interaction) -> None:
        value = self.values[0]
        await self.view.apply(interaction, color_value=None if value == ALL_COLORS_VALUE else value)


class _FilterPanel(discord.ui.View):
    """Per-user ephemeral control panel + leaderboard, private to the clicker.

    Set picks which board; format and color combine (Pod/Direct stay standalone, so
    selecting one clears the color). Each pick re-renders the ephemeral message —
    the posted snapshot everyone sees is never touched.
    """

    def __init__(
        self, set_code: str, format_value: str | None, color_value: str | None,
        with_emoji: bool = True,
    ) -> None:
        super().__init__(timeout=180)
        self.set_code = set_code
        self.format_value = format_value
        self.color_value = color_value
        self.with_emoji = with_emoji
        self.add_item(_SetSelect(set_code))
        self.add_item(_FormatSelect(format_value))
        self.add_item(_ColorSelect(color_value, with_emoji))

    async def apply(
        self, interaction: discord.Interaction, *, set_code=_UNSET, format_value=_UNSET, color_value=_UNSET,
    ) -> None:
        new_set = self.set_code if set_code is _UNSET else set_code
        new_fmt = self.format_value if format_value is _UNSET else format_value
        new_color = self.color_value if color_value is _UNSET else color_value
        if new_fmt in SPECIAL_FORMATS:
            new_color = None

        await interaction.response.defer()
        with SessionLocal() as session:
            embed = _render_ephemeral_board(session, new_set, new_fmt, new_color, str(interaction.user.id))
        if embed is None:
            await interaction.followup.send("Could not render that leaderboard", ephemeral=True)
            return
        try:
            await interaction.edit_original_response(
                embed=embed, view=_FilterPanel(new_set, new_fmt, new_color, self.with_emoji),
            )
        except discord.HTTPException:
            await interaction.edit_original_response(
                embed=embed, view=_FilterPanel(new_set, new_fmt, new_color, with_emoji=False),
            )


# Most recent leaderboard ephemeral per user (personal stats card / filter panel) so
# opening a new one clears the prior, avoiding a confusing ephemeral stack.
_LAST_EPHEMERAL: dict[int, discord.Message] = {}


async def _clear_prev_ephemeral(user_id: int) -> None:
    prev = _LAST_EPHEMERAL.pop(user_id, None)
    if prev is not None:
        try:
            await prev.delete()
        except discord.HTTPException:
            pass


class _FilterButton(discord.ui.Button):
    def __init__(self) -> None:
        super().__init__(
            label="Filter", style=discord.ButtonStyle.primary,
            custom_id="leaderboard:filter", emoji="🔎",
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        user_id = str(interaction.user.id)
        msg_id = str(interaction.message.id)
        set_code: str | None = None
        format_value: str | None = None
        color_value: str | None = None
        with SessionLocal() as session:
            tracked = session.execute(
                select(LeaderboardMessage).where(LeaderboardMessage.message_id == msg_id)
            ).scalar_one_or_none()
            if tracked is not None:
                if tracked.set_id is not None:
                    ms = session.get(MagicSet, tracked.set_id)
                    if ms is not None:
                        set_code = ms.code
                format_value, color_value = decode_filter(tracked.filter_type, tracked.filter_value)
            if set_code is None:
                board = resolve_board_set(session)
                set_code = board.code if board is not None else active_set_code()
            embed = _render_ephemeral_board(session, set_code, format_value, color_value, user_id)

        if embed is None:
            await interaction.response.send_message(
                "Could not render that leaderboard", ephemeral=True,
            )
            return

        await _clear_prev_ephemeral(user_id)
        try:
            await interaction.response.send_message(
                embed=embed, view=_FilterPanel(set_code, format_value, color_value), ephemeral=True,
            )
        except discord.HTTPException:
            await interaction.response.send_message(
                embed=embed, view=_FilterPanel(set_code, format_value, color_value, with_emoji=False),
                ephemeral=True,
            )
        try:
            _LAST_EPHEMERAL[user_id] = await interaction.original_response()
        except discord.HTTPException:
            pass


def _player_url(
    slug: str, set_code: str | None = None, filter_type: str | None = None, filter_value: str | None = None,
) -> str:
    if is_custom(set_code):
        return _custom_board_url(set_code)
    return player_url(slug, set_code) + _site_query(filter_type, filter_value)


def _custom_board_url(code: str) -> str:
    return f"{settings.public_site_url.rstrip('/')}/pods/{code.upper()}"


def board_site_url(set_code: str | None, filter_type: str | None, filter_value: str | None) -> str:
    """Public-site URL for a board: a custom-format pods page, or the set page plus the filter query."""
    if is_custom(set_code):
        return _custom_board_url(set_code)
    base = settings.leaderboard_url
    set_base = base if set_code is None or set_code == active_set_code() else f"{base}/{set_code}"
    return set_base + _site_query(filter_type, filter_value)


@dataclass(frozen=True)
class _Column:
    header: str
    align: str
    cell: Callable[..., str]
    pad: int = 0


# Emoji headers render ~1 col wider than a digit: min value width 2, header padded one less
EMOJI_HEADERS = ("🏆", "📦", "💰")


def _cell_text(value: str, width: int, align: str) -> str:
    if align == "l":
        return f"{value:<{width}}"
    if align == "c":
        return _center_right_bias(value, width)
    return f"{value:>{width}}"


def _table_cells(cols: list[_Column], rows: list) -> tuple[list[str], list[list[str]]]:
    """Header + per-row cells with shared widths, ready to be '  '-joined into lines."""
    header_cells: list[str] = []
    row_cells: list[list[str]] = [[] for _ in rows]
    for col in cols:
        values = [col.cell(r) for r in rows]
        is_wide = col.header in EMOJI_HEADERS
        width = max(max(len(v) for v in values), 2 if is_wide else len(col.header)) + col.pad
        header_cells.append(_cell_text(col.header, width - 1 if is_wide else width, "l" if col.align == "l" else "r"))
        for i, v in enumerate(values):
            row_cells[i].append(_cell_text(v, width, col.align))
    return header_cells, row_cells


def _lcq_d2_record(e: LeaderboardEntry) -> str:
    if e.lcq is None or (e.lcq.d2_wins == 0 and e.lcq.d2_losses == 0):
        return "—"
    return f"{e.lcq.d2_wins}-{e.lcq.d2_losses}"


def _lcq_cash_label(e: LeaderboardEntry) -> str:
    if e.lcq is None or e.lcq.cash == 0:
        return "—"
    return f"{e.lcq.cash // 1000}K"


def _board_columns(
    show_score: bool, filter_type: str | None, filter_value: str | None, trophy_board: bool = False,
) -> list[_Column]:
    """Column specs per board variant: scored boards carry Points, Pod counts drafts,
    Direct counts boxes, LCQ adds the Draft 2 record + cash columns, and the MTGO flashback
    board carries only its trophy count.
    """
    if trophy_board:
        return [_Column("🏆", "c", lambda e: str(e.trophies))]
    if filter_type == "format" and filter_value == LCQ_FILTER:
        return [
            _Column("Pts", "c", lambda e: str(round(e.score))),
            _Column("🏆", "r", lambda e: str(e.lcq.d1_trophies) if e.lcq else str(e.trophies)),
            _Column("Day2", "r", _lcq_d2_record, pad=1),
            _Column("💰", "r", _lcq_cash_label),
        ]
    if show_score:
        counter = _Column("Points", "c", lambda e: str(round(e.score)))
    elif filter_type == "format" and filter_value == DIRECT_FILTER:
        counter = _Column("📦", "c", lambda e: str(e.events))
    else:
        counter = _Column("Drafts", "c", lambda e: str(e.events))
    return [counter, _Column("🏆", "r", lambda e: str(e.trophies))]


def _format_leaderboard(
    top: list[LeaderboardEntry], set_code: str | None = None, show_score: bool = True,
    filter_type: str | None = None, filter_value: str | None = None, trophy_board: bool = False,
) -> str:
    """Wrap each row in inline code (single backticks) — renders as monospace
    without the code-block brick, and spaces are preserved so columns align.
    Same trick scoreboards.dev uses to get tabular layout in an embed.

    Scores are rounded to the nearest integer for display; tie-breaking still
    works because the underlying ORDER BY in process_leaderboard uses the raw
    float value, not this rendered string.
    """
    rank_col_width = max(max(len(f"{e.rank}.") for e in top), len("#"))
    name_width = max(max(display_width(e.display_name) for e in top), len("Name"))
    columns = _board_columns(show_score, filter_type, filter_value, trophy_board)
    header_cells, row_cells = _table_cells(columns, top)

    lines = [f"`{'#':<{rank_col_width}} {'Name':<{name_width}}  " + "  ".join(header_cells) + "`"]
    for i, e in enumerate(top):
        medal = MEDAL_EMOJIS.get(e.rank)
        if medal is not None:
            # emoji takes ~1 col more than digit-pair in monospace rendering, so pad shorter
            rank = f"{medal:<{rank_col_width - 1}}"
        else:
            rank = f"{e.rank}.".ljust(rank_col_width)
        name = e.display_name + " " * max(0, name_width - display_width(e.display_name))
        inner = f"{rank} {name}  " + "  ".join(row_cells[i])
        lines.append(f"[`{inner}`](<{_player_url(e.slug, set_code, filter_type, filter_value)}>)")
    return "\n".join(lines)


def _center_right_bias(s: str, width: int) -> str:
    """Center s in width chars, putting any leftover padding on the LEFT.

    Python's built-in centering biases right (extra space ends up on the right),
    which makes single-digit values inside wider header columns look offset to
    the left. Right-biasing the padding shifts those values one space rightward
    so they read closer to the column's visual center.
    """
    pad = max(0, width - len(s))
    right = pad // 2
    left = pad - right
    return ' ' * left + s + ' ' * right


def _apply_footer(embed: discord.Embed, data: LeaderboardData, show_note: bool = True) -> None:
    """Two-line footer:

      Row 1: ``N active drafters``
      Row 2: ``Last updated | Today at HH:MM``  (timestamp appended by Discord)

    The clickable site link is on the embed title (via ``embed.url``); the URL
    no longer appears in the footer to avoid redundancy. ``show_note`` drops the
    drafter-count line, used when many boards post together (the set send-off) and
    the repeated call-to-action would be noise.
    """
    rows: list[str] = []
    if show_note and data.drafter_count > 0:
        label = "player" if data.drafter_count == 1 else "players"
        rows.append(f"{data.drafter_count} {label} sharing their drafts · /join to add yours")
    if data.last_updated is not None:
        embed.timestamp = data.last_updated
        rows.append("Last updated")
    if rows:
        embed.set_footer(text="\n".join(rows))


def render_embed(data: LeaderboardData, show_note: bool = True) -> discord.Embed:
    base_url = settings.public_site_url.rstrip("/")
    site_url = board_site_url(data.set_code, data.filter_type, data.filter_value)
    set_emoji = emojis.set_symbol(data.set_code)
    prefix = f"{set_emoji} " if set_emoji else ""
    embed = discord.Embed(
        title=f"🏆 Leaderboard {prefix}{board_title(data.set_code)}",
        url=site_url,
        color=discord.Color.gold(),
    )
    if not data.top:
        embed.description = (
            "_No trophies logged yet for this set._" if data.trophy_board
            else "_No players have scored yet for this set._"
        )
    else:
        rows = _format_leaderboard(
            data.top, data.set_code, show_score=data.show_score,
            filter_type=data.filter_type, filter_value=data.filter_value, trophy_board=data.trophy_board,
        )
        if show_note:
            site_display = base_url.split("://", 1)[-1].split("/", 1)[0]
            link = f"[{site_display}]({site_url})"
            embed.description = f"{rows}\n\nCheck the full leaderboard at {link}"
        else:
            embed.description = rows
    _apply_footer(embed, data, show_note=show_note)
    return embed


def board_title(set_code: str) -> str:
    """How a board names itself in a title. A set goes by its code, which players read as the set;
    a whole cube goes by name, since ``CUBE-ARENA`` names nothing to a reader."""
    variant = cube_variant_for_board(set_code)
    return cube_list_name(variant) if variant is not None else set_code


# Alias kept so external callers asking for the 'public' variant still resolve;
# the personalized variant retired when stats embed took over the per-viewer info
render_public_embed = render_embed


def _winrate(r: PersonalStanding) -> str:
    games = r.wins + r.losses
    return f"{round(r.wins / games * 100)}%" if games else "—"


def _personal_columns(data: PersonalStandingsData) -> list[_Column]:
    """Ordered column specs for the standings table. Opted-out players are excluded
    from public rank sequences, so Rnk and the ranking metric (Pts, or 📦 boxes for
    Direct) are dropped; Win% only reads cleanly under a single format filter.
    """
    cols = [_Column("Set", "l", lambda r: r.set_code)]
    if not data.opted_out:
        cols.append(_Column("Rnk", "r", lambda r: f"#{r.rank}" if r.rank is not None else "—"))
    cols.append(_Column("Ev", "r", lambda r: str(r.events)))
    if data.format_label is not None:
        cols.append(_Column("Win%", "r", _winrate))
    if data.format_label == DIRECT_FILTER:
        cols.append(_Column("📦", "r", lambda r: str(round(r.score))))
    elif not data.opted_out:
        cols.append(_Column("Pts", "c", lambda r: str(round(r.score))))
    cols.append(_Column("🏆", "r", lambda r: str(r.trophies)))
    return cols


def render_personal_embed(data: PersonalStandingsData) -> discord.Embed:
    title = f"🏆 Lifetime Sets — {data.player_name}"
    if data.format_label:
        title = f"{title} · {data.format_label}"
    embed = discord.Embed(title=title, color=discord.Color.gold())
    if data.last_updated is not None:
        embed.timestamp = data.last_updated
        embed.set_footer(text="Last updated")
    if not data.rows:
        embed.description = "_No scored drafts yet_"
        return embed

    rows = data.rows
    ord_width = max(len(f"{len(rows)}."), len("#"))
    header_cells, row_cells = _table_cells(_personal_columns(data), rows)

    link_filter_type = "format" if data.format_label else None
    lines = [f"`{'#':<{ord_width}} " + "  ".join(header_cells) + "`"]
    for i, r in enumerate(rows):
        inner = f"{f'{i + 1}.':<{ord_width}} " + "  ".join(row_cells[i])
        url = _player_url(data.player_slug, r.set_code, link_filter_type, data.format_label)
        lines.append(f"[`{inner}`](<{url}>)")

    embed.description = "\n".join(lines)
    return embed


async def _send_personal_followup(
    interaction: discord.Interaction, viewer_discord_id: str,
) -> None:
    """Ephemeral follow-up to the invoker — rich stats breakdown for any registered
    player, including one who's opted out of the rankings; /join prompt otherwise.
    Re-uses the /stats embed so the two commands stay visually consistent. Keys off
    process_stats rather than the ranked standings, which exclude opted-out players."""
    with SessionLocal() as session:
        stats_data = process_stats(session, player_name=None, viewer_discord_id=viewer_discord_id)
    ephemeral = interaction.guild is not None
    if stats_data is None:
        msg = await interaction.followup.send(content=MSG_NOT_REGISTERED, ephemeral=ephemeral)
    else:
        msg = await interaction.followup.send(embed=render_stats_embed(stats_data), ephemeral=ephemeral)
    await _clear_prev_ephemeral(interaction.user.id)
    _LAST_EPHEMERAL[interaction.user.id] = msg


class LeaderboardView(discord.ui.View):
    """Persistent view for leaderboard messages — buttons keep working across bot restarts.

    The Join button calls back into the Signup cog so it behaves identically to the
    /join slash command (DM-flow signup, reactivation, already-signed-up handling).
    The Stats button is a URL link handled client-side by Discord.
    """

    def __init__(
        self,
        filter_type: str | None = None,
        filter_value: str | None = None,
        set_code: str | None = None,
        include_filter: bool = True,
    ) -> None:
        super().__init__(timeout=None)
        if include_filter:
            self.add_item(_FilterButton())
        stats_url = board_site_url(set_code, filter_type, filter_value)
        # URL buttons are exempt from the persistent-view custom_id requirement
        self.add_item(discord.ui.Button(
            label="Stats", url=stats_url,
            style=discord.ButtonStyle.link,
            emoji=emojis.get_emoji("llu"),
        ))

    @discord.ui.button(label="Join", style=discord.ButtonStyle.success, custom_id="leaderboard:join")
    async def join_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        # Already signed-up users clicking Join are usually misclicks or curious
        # — show their personal stats instead of starting the signup flow
        user_id = str(interaction.user.id)
        with SessionLocal() as session:
            existing = session.execute(
                select(Player).where(
                    Player.discord_id == user_id, Player.active.is_(True),
                )
            ).scalar_one_or_none()

        if existing is not None:
            stats_cog = interaction.client.get_cog("Stats")
            if stats_cog is not None:
                await stats_cog.stats.callback(stats_cog, interaction)
                return

        signup_cog = interaction.client.get_cog("Signup")
        if signup_cog is None:
            await interaction.response.send_message(
                "Sign-up isn't available right now", ephemeral=(interaction.guild is not None),
            )
            return
        await signup_cog.signup.callback(signup_cog, interaction)


def render_view(
    filter_type: str | None = None,
    filter_value: str | None = None,
    set_code: str | None = None,
    include_filter: bool = True,
) -> discord.ui.View:
    return LeaderboardView(
        filter_type=filter_type, filter_value=filter_value,
        set_code=set_code, include_filter=include_filter,
    )


CODE_TO_COLOR_LABEL: dict[str, str] = {code: label for label, code in COLOR_CHOICES.items()}

FORMAT_COLOR_FILTER = "format+color"
SPECIAL_FORMATS = ("Pod", "Direct")


def encode_filter(format_value: str | None, color_value: str | None) -> tuple[str | None, str | None]:
    """(format, color) → the (filter_type, filter_value) pair stored on tracked messages.
    Color is dropped for Pod/Direct, which are standalone boards.
    """
    if format_value in SPECIAL_FORMATS:
        color_value = None
    if format_value and color_value:
        return FORMAT_COLOR_FILTER, f"{format_value}|{color_value}"
    if format_value:
        return "format", format_value
    if color_value:
        return "color", color_value
    return None, None


def decode_filter(filter_type: str | None, filter_value: str | None) -> tuple[str | None, str | None]:
    """(filter_type, filter_value) → (format, color)."""
    if filter_type == FORMAT_COLOR_FILTER and filter_value:
        fmt, _, color = filter_value.partition("|")
        return fmt or None, color or None
    if filter_type == "format":
        return filter_value, None
    if filter_type == "color":
        return None, filter_value
    return None, None


def _site_query(filter_type: str | None, filter_value: str | None) -> str:
    """Query string mirroring the active filter on the public site (?format=&colors=)."""
    format_value, color_value = decode_filter(filter_type, filter_value)
    params = []
    if format_value:
        params.append(f"format={format_value}")
    if color_value:
        params.append(f"colors={color_value}")
    return ("?" + "&".join(params)) if params else ""


def _drafter_count(
    session: Session, magic_set: MagicSet | None = None,
    *, format_value: str | None = None, color_value: str | None = None,
) -> int:
    """Distinct opted-in players whose drafts match the active filter for the set.
    Color matching needs per-row archetype logic, so it scans draft_events directly.
    """
    if magic_set is None:
        magic_set = _current_set(session)
    if magic_set is None:
        return 0

    groups = None
    if format_value and format_value not in SPECIAL_FORMATS:
        groups = _groups_for_label(format_value)

    if color_value is not None:
        allowed = set(supported_formats(groups)) if groups is not None else None
        rows = session.execute(
            select(DraftEvent.player_id, DraftEvent.format, DraftEvent.colors)
            .join(Player, Player.id == DraftEvent.player_id)
            .where(
                DraftEvent.set_id == magic_set.id,
                Player.active.is_(True),
                Player.leaderboard_opt_in.is_(True),
            )
        ).all()
        players = {
            r.player_id for r in rows
            if (allowed is None or r.format in allowed)
            and _archetype_matches(r.colors, color_value, magic_set.code == CUBE_CODE)
        }
        return len(players)

    conditions = [
        PlayerStats.set_id == magic_set.id,
        PlayerStats.events > 0,
        Player.active.is_(True),
        Player.leaderboard_opt_in.is_(True),
    ]
    if groups is not None:
        conditions.append(PlayerStats.format.in_(supported_formats(groups)))
    return session.execute(
        select(func.count(func.distinct(PlayerStats.player_id)))
        .join(Player, Player.id == PlayerStats.player_id)
        .where(*conditions)
    ).scalar() or 0


def render_filtered_data(
    session: Session,
    *,
    filter_type: str | None,
    filter_value: str | None,
    viewer_discord_id: str | None,
    magic_set: MagicSet | None = None,
) -> tuple["LeaderboardData | None", str | None]:
    """Resolve a filter into the matching processor + display suffix.

    Returns (data, suffix). suffix is the human label appended to the embed
    title (e.g. "Premier", "Boros", "Premier · Simic"). Both are None when no
    matching set exists. ``magic_set`` overrides the active set so historical
    boards can be rendered. Format and color combine; Pod/Direct stay standalone.
    """
    format_value, color_value = decode_filter(filter_type, filter_value)
    groups = None
    if format_value and format_value not in SPECIAL_FORMATS:
        groups = _groups_for_label(format_value)

    if format_value == "Pod":
        data = process_leaderboard_for_pod(session, viewer_discord_id=viewer_discord_id, magic_set=magic_set)
        suffix = "Pod"
    elif format_value == DIRECT_FILTER:
        data = process_leaderboard_for_direct(session, viewer_discord_id=viewer_discord_id, magic_set=magic_set)
        suffix = "Direct"
    elif format_value == LCQ_FILTER and color_value is None:
        data = process_leaderboard_for_lcq(session, viewer_discord_id=viewer_discord_id, magic_set=magic_set)
        suffix = LCQ_FILTER
    elif color_value is not None:
        data = process_leaderboard_for_archetype(
            session, viewer_discord_id=viewer_discord_id, archetype=color_value, magic_set=magic_set, groups=groups,
        )
        label = CODE_TO_COLOR_LABEL.get(color_value, color_value)
        emoji = _archetype_emoji(color_value)
        color_suffix = f"{label} {emoji}" if emoji else label
        suffix = f"{format_value} · {color_suffix}" if format_value else color_suffix
    elif format_value:
        data = process_leaderboard_for_format(
            session, viewer_discord_id=viewer_discord_id, format_label=format_value, magic_set=magic_set,
        )
        suffix = format_value
    else:
        data = process_leaderboard(session, viewer_discord_id=viewer_discord_id, magic_set=magic_set)
        suffix = None

    if data is not None:
        data.drafter_count = _drafter_count(session, magic_set, format_value=format_value, color_value=color_value)
        data.filter_type = filter_type
        data.filter_value = filter_value

    return data, suffix


SEND_OFF_FORMATS: tuple[str | None, ...] = (None, "Premier", "Trad", "Direct", LCQ_FILTER)
TROPHY_BOARD_LABEL = "Trophies"


def build_set_send_off_embeds(session: Session, magic_set: MagicSet) -> list[discord.Embed]:
    """The final standings for a set that just rotated out — the overall board followed by Premier,
    Traditional, Direct and LCQ, each rendered through the same path `/leaderboard` uses so they can't
    drift, and the trophy count board last. A format with no scored players is dropped, so a set that
    ran no Direct or LCQ simply omits that board. The repeated site call-to-action is suppressed since
    many boards post at once.

    The trophy board is built outside the filter loop: it is not a format filter, and giving the embed
    title a `?format=` the site doesn't serve would link players to an empty board.

    "Last updated" carries the post instant instead of the last 17lands fetch. These boards post hours
    after the final refresh of a set nobody is still drafting, so the real fetch time reads as lost data.
    """
    embeds: list[discord.Embed] = []
    for format_value in SEND_OFF_FORMATS:
        filter_type, filter_value = encode_filter(format_value, None)
        data, suffix = render_filtered_data(
            session, filter_type=filter_type, filter_value=filter_value,
            viewer_discord_id=None, magic_set=magic_set,
        )
        if data is None or not data.top:
            continue
        embed = render_embed(data, show_note=False)
        if suffix:
            embed.title = f"{embed.title} {suffix}"
        embeds.append(embed)

    trophy_data = process_leaderboard_for_trophies(session, magic_set)
    if trophy_data.top:
        trophy_embed = render_embed(trophy_data, show_note=False)
        trophy_embed.title = f"{trophy_embed.title} {TROPHY_BOARD_LABEL}"
        embeds.append(trophy_embed)
    posted_at = datetime.now(timezone.utc)
    for embed in embeds:
        embed.timestamp = posted_at
    return embeds


def _filter_clause(filter_type: str | None, filter_value: str | None):
    """Postgres `IS NULL` vs `=` differ; build the right one for nullable filters."""
    type_clause = (
        LeaderboardMessage.filter_type.is_(None) if filter_type is None
        else LeaderboardMessage.filter_type == filter_type
    )
    value_clause = (
        LeaderboardMessage.filter_value.is_(None) if filter_value is None
        else LeaderboardMessage.filter_value == filter_value
    )
    return type_clause, value_clause


async def _replace_tracked_message(
    interaction: discord.Interaction,
    channel_id: str,
    set_id: str,
    embed: discord.Embed,
    view: discord.ui.View,
    filter_type: str | None = None,
    filter_value: str | None = None,
) -> None:
    """Post a fresh leaderboard and reconcile prior tracked messages with the
    same (channel, set, filter_type, filter_value).

    For each matching prior row:
      - if the message is pinned, leave the message and keep the tracking row
        so !refresh continues to edit it in place.
      - otherwise delete the message and drop the tracking row.

    The freshly-posted message gets its own tracking row carrying the filter
    so refresh can re-render it with the correct data later.

    A NotFound on fetch is normal (mod or user wiped it); we drop the row.
    """
    sent = await interaction.followup.send(embed=embed, view=view, wait=True)
    new_message_id = str(sent.id)

    type_clause, value_clause = _filter_clause(filter_type, filter_value)

    with SessionLocal() as session:
        prior_rows = session.execute(
            select(LeaderboardMessage).where(
                LeaderboardMessage.channel_id == channel_id,
                LeaderboardMessage.set_id == set_id,
                type_clause,
                value_clause,
            )
        ).scalars().all()
        prior_targets = [(row.id, row.message_id) for row in prior_rows]

        session.add(LeaderboardMessage(
            channel_id=channel_id, set_id=set_id, message_id=new_message_id,
            filter_type=filter_type, filter_value=filter_value,
        ))
        session.commit()

    for row_id, prior_message_id in prior_targets:
        if prior_message_id == new_message_id:
            continue
        keep_row = False
        try:
            old = await interaction.channel.fetch_message(int(prior_message_id))
            if old.pinned:
                logger.info(f"prior leaderboard message {prior_message_id} is pinned, leaving in place")
                keep_row = True
            else:
                await old.delete()
        except discord.NotFound:
            pass
        except discord.HTTPException as e:
            logger.warning(f"could not delete prior leaderboard message {prior_message_id}: {e}")
            keep_row = True

        if not keep_row:
            with SessionLocal() as session:
                stale = session.get(LeaderboardMessage, row_id)
                if stale is not None:
                    session.delete(stale)
                    session.commit()


class Leaderboard(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command(name="leaderboard", description=desc.LEADERBOARD)
    @app_commands.describe(
        format="Show only one queue (Premier, Trad, Sealed, Quick, LCQ, Pod, Direct)",
        color="Filter by archetype: guilds, shards/wedges, or Soup (4+ colors)",
        set="A set code, or ALL for your lifetime standings",
    )
    @app_commands.choices(
        format=[
            app_commands.Choice(name="Premier", value="Premier"),
            app_commands.Choice(name="Traditional", value="Trad"),
            app_commands.Choice(name="Sealed", value="Sealed"),
            app_commands.Choice(name="Quick", value="Quick"),
            app_commands.Choice(name="LCQ", value="LCQ"),
            app_commands.Choice(name="Pod", value="Pod"),
            app_commands.Choice(name="Direct", value="Direct"),
        ],
        color=[
            app_commands.Choice(
                name="Soup (4+ color)" if code == "MULTI" else f"{label} ({code})",
                value=code,
            )
            for label, code in COLOR_CHOICES.items()
        ],
    )
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=False)
    @app_commands.allowed_installs(guilds=True, users=False)
    async def leaderboard(
        self,
        interaction: discord.Interaction,
        format: app_commands.Choice[str] | None = None,
        color: app_commands.Choice[str] | None = None,
        set: str | None = None,
    ) -> None:
        user_id = str(interaction.user.id)
        audit.event(
            "leaderboard_invoked",
            user_id=user_id,
            format=format.value if format else None,
            color=color.value if color else None,
            set=set,
        )

        # set:ALL → your lifetime standings across every set
        if set is not None and set.upper() == LIFETIME_SET:
            ephemeral = interaction.guild is not None
            fmt_value = format.value if format is not None else None
            if color is not None:
                await interaction.response.send_message(
                    "Lifetime standings support the `format` filter, not `color` yet", ephemeral=ephemeral,
                )
                return
            if fmt_value == "Pod":
                await interaction.response.send_message(
                    "Lifetime standings don't cover Pod yet", ephemeral=ephemeral,
                )
                return
            await interaction.response.defer()
            with SessionLocal() as session:
                data = process_personal_standings(session, user_id, format_label=fmt_value)
            if data is None:
                await interaction.followup.send(MSG_NOT_REGISTERED, ephemeral=ephemeral)
                return
            await interaction.followup.send(embed=render_personal_embed(data))
            return

        in_guild = interaction.guild is not None
        ephemeral = in_guild

        # set:PEASANT / MEMA / … → a season-long custom-format pod board, posted as a snapshot
        if set is not None and is_custom(set):
            code = set.upper()
            if format is not None or color is not None:
                await interaction.response.send_message(
                    f"Format and color filters aren't available for `{code}`", ephemeral=ephemeral,
                )
                return
            await interaction.response.defer()
            with SessionLocal() as session:
                data = process_leaderboard_for_custom(session, code, viewer_discord_id=user_id)
            await interaction.followup.send(
                embed=render_public_embed(data),
                view=render_view(set_code=code, include_filter=False),
            )
            return

        # set:MH1 / IPA / … → MTGO flashback trophy board, posted as a snapshot
        if set is not None and is_mtgo_flashback_code(set):
            if format is not None or color is not None:
                await interaction.response.send_message(
                    f"Format and color filters aren't available for `{set.upper()}`", ephemeral=ephemeral,
                )
                return
            await interaction.response.defer()
            with SessionLocal() as session:
                data = process_leaderboard_for_mtgo(session, set.upper())
            await interaction.followup.send(
                embed=render_public_embed(data),
                view=render_view(set_code=set.upper(), include_filter=False),
            )
            return

        format_value = format.value if format is not None else None
        color_value = color.value if color is not None else None
        if format_value in SPECIAL_FORMATS and color_value is not None:
            await interaction.response.send_message(
                f"Color filtering isn't available for `{format_value}` yet", ephemeral=ephemeral,
            )
            return
        # set:CUBE takes the cube running now; set:CUBE-PLANAR and set:CUBE-SOS name a board directly
        cube_board = set.upper() if set is not None and is_cube_board_code(set) else None
        if cube_board is not None and (format_value is not None or color_value is not None):
            await interaction.response.send_message(
                f"Format and color filters aren't available for `{cube_board}`", ephemeral=ephemeral,
            )
            return

        filter_type, filter_value = encode_filter(format_value, color_value)

        await interaction.response.defer()

        with SessionLocal() as session:
            board_set = _current_set(session)
            if cube_board is not None:
                magic_set = session.execute(
                    select(MagicSet).where(MagicSet.code == CUBE_CODE)
                ).scalar_one_or_none()
            elif set is not None:
                magic_set = session.execute(
                    select(MagicSet).where(func.upper(MagicSet.code) == set.upper())
                ).scalar_one_or_none()
            else:
                magic_set = board_set

            if magic_set is None:
                msg = (
                    f"No leaderboard for `{set}` — it isn't a registered set."
                    if set is not None else
                    "No active set is configured. The date-derived active set isn't seeded in the database yet."
                )
                await interaction.followup.send(msg, ephemeral=ephemeral)
                return

            if cube_board is not None:
                data, suffix = process_cube_board(session, viewer_discord_id=user_id, board=cube_board), None
            else:
                data, suffix = render_filtered_data(
                    session,
                    filter_type=filter_type, filter_value=filter_value,
                    viewer_discord_id=user_id, magic_set=magic_set,
                )

        if data is None:
            await interaction.followup.send(
                "Could not render that leaderboard", ephemeral=ephemeral,
            )
            return

        embed = render_public_embed(data)
        if suffix:
            embed.title = f"{embed.title} {suffix}"

        # A specific past set is a post-and-forget snapshot: send it once, no
        # tracking row (so !refresh skips it) and no cycle button (cycling needs
        # the tracking row). The board set keeps the tracked, refreshable path.
        if board_set is None or magic_set.code != board_set.code:
            await interaction.followup.send(
                embed=embed,
                view=render_view(
                    filter_type=filter_type, filter_value=filter_value,
                    set_code=magic_set.code, include_filter=False,
                ),
            )
            return

        # In a guild channel: track the post (filter-aware) so !refresh keeps it
        # current. In a DM: single response, fully personalized.
        if in_guild:
            await _replace_tracked_message(
                interaction,
                channel_id=str(interaction.channel_id),
                set_id=magic_set.id,
                embed=embed,
                view=render_view(
                    filter_type=filter_type, filter_value=filter_value, set_code=magic_set.code,
                ),
                filter_type=filter_type,
                filter_value=filter_value,
            )
            if filter_type is None:
                await _send_personal_followup(interaction, viewer_discord_id=user_id)
        else:
            # In DM: send the (already filter-aware) embed as a followup,
            # then the stats embed (or /join prompt) via dm.send so it doesn't visually
            # thread as a reply under the leaderboard message. Personal followup only
            # makes sense for the unfiltered overall leaderboard.
            await interaction.followup.send(
                embed=embed,
                view=render_view(
                    filter_type=filter_type, filter_value=filter_value,
                    include_filter=False,
                ),
            )
            if filter_type is not None:
                return
            try:
                dm = interaction.channel  # already a DM channel here
                with SessionLocal() as session:
                    stats_data = process_stats(session, player_name=None, viewer_discord_id=user_id)
                if stats_data is not None:
                    await dm.send(embed=render_stats_embed(stats_data))
                else:
                    await dm.send(MSG_NOT_REGISTERED)
            except Exception:
                logger.warning("/leaderboard DM personal followup failed", exc_info=True)

    @leaderboard.autocomplete("set")
    async def _set_autocomplete(
        self, interaction: discord.Interaction, current: str,
    ) -> list[app_commands.Choice[str]]:
        cur = current.upper()

        matches: list[app_commands.Choice[str]] = []
        if cur in LIFETIME_SET:
            matches.append(app_commands.Choice(name="ALL — Lifetime Sets", value=LIFETIME_SET))
        if cur in CUBE_CODE:
            matches.append(app_commands.Choice(name=f"{CUBE_CODE} — Cube Running Now", value=CUBE_CODE))
        for variant in CUBE_VARIANTS:
            code = cube_board_code(variant.slug)
            if cur in code or cur in variant.name.upper():
                matches.append(app_commands.Choice(name=cube_list_name(variant), value=code))
        for fmt in custom_formats():
            if cur in fmt.code or cur in fmt.label.upper():
                matches.append(app_commands.Choice(name=f"{fmt.code} — {fmt.label}", value=fmt.code))
        matches += [
            app_commands.Choice(name=f"{s.code} — {s.name}", value=s.code)
            for s in reversed(ALL_SETS)
            if s.code != CUBE_CODE and (cur in s.code.upper() or cur in s.name.upper())
        ]
        matches += [
            app_commands.Choice(name=f"{code} — {name} (MTGO)", value=code)
            for code, name in MTGO_FLASHBACK_SETS.items()
            if cur in code or cur in name.upper()
        ]
        return matches[:25]


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Leaderboard(bot))


def _current_set(session: Session) -> MagicSet | None:
    return resolve_board_set(session)


_WUBRG = "WUBRG"
_MULTI_ARCHETYPE = "MULTI"


def _normalize_archetype(colors: str | None) -> str:
    if not colors:
        return ""
    return "".join(sorted((c for c in colors if c.isupper()), key=_WUBRG.index))


def _effective_color_count(colors: str | None) -> int:
    if not colors:
        return 0
    return len({c.upper() for c in colors if c.upper() in _WUBRG})


def _is_soup(colors: str | None, is_cube: bool) -> bool:
    """Standard limited counts any 4+ color deck (2 base + 2 splash). Cube affords freer
    splashing, so the bar rises to 3+ base colors plus a splash (or 4+ base outright).
    """
    if _effective_color_count(colors) < 4:
        return False
    if not is_cube:
        return True
    return len(_normalize_archetype(colors)) >= 3


def _archetype_matches(colors: str | None, archetype: str, is_cube: bool = False) -> bool:
    if archetype == _MULTI_ARCHETYPE:
        return _is_soup(colors, is_cube)
    return _normalize_archetype(colors) == archetype
