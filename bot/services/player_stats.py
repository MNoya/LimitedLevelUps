from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Mapping, NamedTuple, Sequence

import discord
from sqlalchemy import case, func, select, text
from sqlalchemy.orm import Session

from bot.models import DraftEvent, MagicSet, Player, PlayerStats
from bot.discord_helpers import player_url
from bot.scoring import boxes_for_event, compute_score, compute_score_breakdown, pod_points
from bot.services.active_set import resolve_active_set
from bot.services.pod_drafts import PodSetSummary, players_for_names, pod_scoring_counts, pod_summary_by_set_for_player
from bot.sets import CUBE_CODE, CubeVariant, active_set_code, cube_variant_for_expansion


@dataclass
class StatsData:
    set_code: str
    set_name: str
    player_name: str
    player_slug: str
    rank: int | None
    total_score: float
    total_trophies: int
    breakdown: list[dict] = field(default_factory=list)
    last_updated: datetime | None = None
    pod: PodSetSummary | None = None
    direct_stats: dict | None = None
    opted_out: bool = False
    has_token: bool = False


class RankedPlayer(NamedTuple):
    rank: int
    player_id: str
    slug: str
    display_name: str
    discord_id: str | None
    score: float
    trophies: int


class FrozenSeed(NamedTuple):
    """One player's standing at a Set Championship's deadline: the rank it seeds them at and the figures that
    rank came from. They travel together so a seeding table cannot show a frozen rank beside a score or a
    trophy count from a later day, which reads as a table sorted wrong."""
    rank: int
    score: float | None
    trophies: int | None = None


def process_stats(
    session: Session,
    player_name: str | None,
    viewer_discord_id: str,
    set_code: str | None = None,
) -> StatsData | None:
    player = resolve_player(session, player_name, viewer_discord_id)
    if player is None:
        return None

    set_code = set_code or active_set_code()
    magic_set = session.execute(
        select(MagicSet).where(MagicSet.code == set_code)
    ).scalar_one_or_none()
    if magic_set is None:
        return None

    stats_rows = session.execute(
        select(PlayerStats).where(
            PlayerStats.player_id == player.id,
            PlayerStats.set_id == magic_set.id,
        )
    ).scalars().all()
    stat_dicts = [
        {"format": r.format, "events": r.events, "wins": r.wins, "losses": r.losses, "trophies": r.trophies}
        for r in stats_rows
    ]
    breakdown = compute_score_breakdown(stat_dicts)
    pod = pod_summary_by_set_for_player(session, player.id).get(magic_set.code)
    pod_pts = pod_points(pod.trophies, pod.wins_2_1) if pod else 0
    total_score = compute_score(stat_dicts) + pod_pts
    draft_trophies = sum(int(r.trophies or 0) for r in stats_rows)
    total_trophies = draft_trophies + (pod.trophies if pod else 0)
    last_updated = max((r.last_fetched_at for r in stats_rows if r.last_fetched_at), default=None)

    rank: int | None = None
    if total_score > 0:
        for entry in rank_players_for_set(session, magic_set.id):
            if entry.player_id == player.id:
                rank = entry.rank
                break

    direct_rows = session.execute(
        select(DraftEvent.wins, DraftEvent.losses, DraftEvent.finished_at, DraftEvent.is_trophy).where(
            DraftEvent.player_id == player.id,
            DraftEvent.set_id == magic_set.id,
            DraftEvent.format == "ArenaDirect_Sealed",
        )
    ).all()
    direct_stats: dict | None = None
    if direct_rows:
        wins = sum(int(r.wins or 0) for r in direct_rows)
        losses = sum(int(r.losses or 0) for r in direct_rows)
        boxes = 0
        for r in direct_rows:
            boxes += boxes_for_event(magic_set.code, int(r.wins or 0), r.finished_at, bool(r.is_trophy))
        direct_stats = {"events": len(direct_rows), "wins": wins, "losses": losses, "boxes": boxes}

    return StatsData(
        set_code=magic_set.code,
        set_name=magic_set.name,
        player_name=player.display_name,
        player_slug=player.slug,
        rank=rank,
        total_score=total_score,
        total_trophies=total_trophies,
        breakdown=breakdown,
        last_updated=last_updated,
        pod=pod,
        direct_stats=direct_stats,
        opted_out=not player.leaderboard_opt_in,
        has_token=player.seventeenlands_token is not None,
    )


def profile_url(data: StatsData) -> str:
    return player_url(data.player_slug, data.set_code)


def render_embed(data: StatsData) -> discord.Embed:
    embed = discord.Embed(
        title=f"📊 Stats — {data.player_name} — {data.set_code}",
        url=profile_url(data),
        color=discord.Color.blurple(),
    )
    if data.opted_out:
        summary = f"{data.total_trophies} 🏆"
    elif data.rank is not None:
        summary = f"Rank **#{data.rank}** • **{data.total_score:.1f} pts** • {data.total_trophies} 🏆"
    else:
        summary = "_Not yet on the leaderboard for this set._"

    embed.description = f"{summary}\n\n{_format_breakdown(data.breakdown, data.direct_stats, data.opted_out)}"

    if data.pod and data.pod.events:
        p = data.pod
        games = p.wins + p.losses
        wr = p.wins / games if games else 0.0
        events_word = "event" if p.events == 1 else "events"
        trophy_word = "trophy" if p.trophies == 1 else "trophies"
        points = pod_points(p.trophies, p.wins_2_1)
        pod_suffix = f" · **+{points:.0f} pts**" if points else ""
        embed.description = (
            f"{embed.description}\n"
            f"**Pod** — {p.events} {events_word}, "
            f"{p.wins}-{p.losses} ({wr:.0%}), "
            f"{p.trophies} {trophy_word}{pod_suffix}"
        )

    if data.last_updated is not None:
        embed.timestamp = data.last_updated
        embed.set_footer(text=f"{data.set_code} • Last updated")
    else:
        embed.set_footer(text=data.set_code)
    return embed


def rank_players_for_set(
    session: Session, set_id: str, cutoff: datetime | None = None,
) -> list[RankedPlayer]:
    """Compute every active, opted-in player's score for the set; sort and rank.

    Score is the 17lands total (PlayerStats) plus the flat pod-draft bonus. Pod-only
    players (no 17lands drafts this set) enter the board on pod points alone.
    Shared by the /stats and /leaderboard surfaces.

    `cutoff` rebuilds the board as it stood at that instant, off the event log instead of the derived
    aggregates. A Set Championship freezes on one, so a deadline counts what a player had actually played
    by it, whenever their 17lands profile happened to be linked.
    """
    stats_by_player = (
        _stats_by_player(session, set_id) if cutoff is None
        else _stats_by_player_asof(session, set_id, cutoff)
    )
    set_code = session.execute(select(MagicSet.code).where(MagicSet.id == set_id)).scalar_one_or_none()
    pod_counts = pod_scoring_counts(session, set_code, before=cutoff) if set_code else {}

    identities = {
        p.id: (p.slug, p.display_name, p.discord_id)
        for p in session.execute(
            select(Player.id, Player.slug, Player.display_name, Player.discord_id)
            .where(
                Player.id.in_(set(stats_by_player) | set(pod_counts)),
                Player.active.is_(True),
                Player.leaderboard_opt_in.is_(True),
            )
        ).all()
    }

    standings: list[RankedPlayer] = []
    for pid, (slug, name, did) in identities.items():
        rows = stats_by_player.get(pid, [])
        pod_trophies, pod_wins_2_1 = pod_counts.get(pid, (0, 0))
        standings.append(RankedPlayer(
            rank=0,
            player_id=pid, slug=slug, display_name=name, discord_id=did,
            score=compute_score(rows) + pod_points(pod_trophies, pod_wins_2_1),
            trophies=sum(r["trophies"] for r in rows) + pod_trophies,
        ))

    standings.sort(key=lambda p: (-p.score, p.display_name.lower()))
    return [p._replace(rank=rank) for rank, p in enumerate(standings, start=1)]


CUBE_BURST_GAP_DAYS = 7


def latest_cube_board(session: Session) -> tuple[CubeVariant, str | None] | None:
    """The cube board the newest cube activity belongs to: ``(variant, season label or None)``.

    Arena runs one cube at a time, so the variant holding the newest draft is the ongoing one (or
    the last one that ran, between runs). A seasoned variant resolves further to the season of its
    latest burst; the rest are one flat board. None when no cube drafts exist.
    """
    row = session.execute(
        text("""
            SELECT de.expansion, MAX(de.started_at) AS last_at
            FROM draft_events de
            JOIN sets s ON s.id = de.set_id
            JOIN players p ON p.id = de.player_id
            WHERE s.code = :cube AND p.active = true AND de.started_at IS NOT NULL
            GROUP BY de.expansion
            ORDER BY last_at DESC
            LIMIT 1
        """),
        {"cube": CUBE_CODE},
    ).first()
    if row is None:
        return None
    variant = cube_variant_for_expansion(row.expansion)
    if variant is None:
        return None
    if not variant.seasoned:
        return variant, None
    return variant, latest_cube_season(session, variant)


def latest_cube_season(session: Session, variant: CubeVariant) -> str | None:
    """Season label of a variant's latest burst — the set live when its most recent run *began*.

    A burst is community cube activity with no gap longer than ``CUBE_BURST_GAP_DAYS``; its whole
    run inherits the season of the set window holding its first event, so a tail spilling past a set
    rotation stays with the season it started in rather than minting a phantom next-set season. None
    if the variant has no drafts. Mirrors the burst-anchored public_cube_seasons view.
    """
    row = session.execute(
        text(f"{_CUBE_SEASON_BINNING_SQL} SELECT season FROM binned ORDER BY started_at DESC LIMIT 1"),
        {"expansion": variant.expansion},
    ).first()
    return row.season if row is not None else None


def rank_cube_board(
    session: Session, variant: CubeVariant, season: str | None,
) -> list[RankedPlayer] | None:
    """Rank active, opted-in players on one cube board (cube only, no pod points), so the standings
    match the site's ``CUBE-<season>`` or ``CUBE-<variant>`` board. None when the board is empty."""
    rows = session.execute(
        text(f"""
            {_CUBE_SEASON_BINNING_SQL}
            SELECT
                player_id,
                format,
                COUNT(*) AS events,
                SUM(wins) AS wins,
                SUM(losses) AS losses,
                SUM(CASE WHEN is_trophy THEN 1 ELSE 0 END) AS trophies
            FROM binned
            WHERE (:season IS NULL OR season = :season) AND leaderboard_opt_in = true
            GROUP BY player_id, format
        """),
        {"expansion": variant.expansion, "season": season},
    ).all()

    by_player: dict[str, list[dict]] = {}
    for r in rows:
        by_player.setdefault(r.player_id, []).append({
            "format": r.format, "events": int(r.events or 0),
            "wins": int(r.wins or 0), "losses": int(r.losses or 0),
            "trophies": int(r.trophies or 0),
        })
    if not by_player:
        return None

    identities = {
        p.id: (p.slug, p.display_name, p.discord_id)
        for p in session.execute(
            select(Player.id, Player.slug, Player.display_name, Player.discord_id)
            .where(Player.id.in_(by_player.keys()))
        ).all()
    }

    standings: list[RankedPlayer] = []
    for pid, stat_rows in by_player.items():
        slug, name, did = identities[pid]
        standings.append(RankedPlayer(
            rank=0, player_id=pid, slug=slug, display_name=name, discord_id=did,
            score=compute_score(stat_rows), trophies=sum(r["trophies"] for r in stat_rows),
        ))
    standings.sort(key=lambda p: (-p.score, p.display_name.lower()))
    return [p._replace(rank=rank) for rank, p in enumerate(standings, start=1)]


_CUBE_SEASON_BINNING_SQL = f"""
WITH seasons AS (
    SELECT
        code,
        start_date,
        LEAD(start_date) OVER (ORDER BY start_date) AS next_start
    FROM sets
    WHERE code <> '{CUBE_CODE}'
),
cube_events AS (
    SELECT
        de.player_id,
        de.format,
        de.started_at,
        de.wins,
        de.losses,
        de.is_trophy,
        p.leaderboard_opt_in
    FROM draft_events de
    JOIN sets s ON s.id = de.set_id
    JOIN players p ON p.id = de.player_id
    WHERE s.code = '{CUBE_CODE}'
      AND de.expansion = :expansion
      AND p.active = true
      AND de.started_at IS NOT NULL
),
marked AS (
    SELECT
        ce.*,
        CASE
            WHEN LAG(started_at) OVER w IS NULL
              OR started_at - LAG(started_at) OVER w > INTERVAL '{CUBE_BURST_GAP_DAYS} days'
            THEN 1 ELSE 0
        END AS new_burst
    FROM cube_events ce
    WINDOW w AS (ORDER BY started_at)
),
bursts AS (
    SELECT
        m.*,
        SUM(new_burst) OVER (ORDER BY started_at ROWS UNBOUNDED PRECEDING) AS burst_id
    FROM marked m
),
anchored AS (
    SELECT
        br.*,
        MIN(started_at) OVER (PARTITION BY burst_id) AS burst_start
    FROM bursts br
),
binned AS (
    SELECT
        a.*,
        seasons.code AS season
    FROM anchored a
    LEFT JOIN seasons
        ON a.burst_start::date >= seasons.start_date
       AND (seasons.next_start IS NULL OR a.burst_start::date < seasons.next_start)
)
"""


@dataclass
class SeededAttendee:
    """One pod RSVP placed against the active leaderboard. rank/score/trophies are None for
    anyone not on the board (unlinked, opted out, or no score yet). slug is None when the
    sesh name matches no Player row, so their row links nowhere."""
    slug: str | None
    display_name: str
    rank: int | None
    score: float | None
    trophies: int | None

    @property
    def is_ranked(self) -> bool:
        return self.rank is not None


def seed_attendees(
    session: Session, names: Sequence[str], rank_override: Mapping[str, FrozenSeed] | None = None,
) -> list[SeededAttendee]:
    """Place sesh RSVP names against the active-set leaderboard, ordered by standing.

    Each name is resolved to a Player by the same matching the pod pipeline uses; ranked players
    sort by leaderboard rank, everyone else falls to the bottom by display name. The raw sesh name
    is shown when no Player matches.

    `rank_override` is the only scale when it is given: a Set Championship seeds off the board frozen at its
    deadline, so every figure printed comes from that day, and a player absent from it did not rank by the
    deadline, so they trail the players who did instead of being placed among them on a live rank the
    deadline never saw. A seed frozen before trophies were stored keeps showing the live count, which is
    closer to the truth than a blank.
    """
    active = resolve_active_set(session)
    set_id = active.id if active else None
    ranked = {r.player_id: r for r in rank_players_for_set(session, set_id)} if set_id else {}

    seeded: list[SeededAttendee] = []
    seen: set[str] = set()
    for name, player in players_for_names(session, names):
        if player is not None:
            if player.id in seen:
                continue
            seen.add(player.id)
        rp = ranked.get(player.id) if player is not None else None
        if rp is not None:
            frozen = rank_override.get(player.id) if rank_override else None
            if frozen is not None:
                trophies = frozen.trophies if frozen.trophies is not None else rp.trophies
                seeded.append(SeededAttendee(rp.slug, rp.display_name, frozen.rank, frozen.score, trophies))
            elif rank_override:
                seeded.append(SeededAttendee(rp.slug, rp.display_name, None, None, None))
            else:
                seeded.append(SeededAttendee(rp.slug, rp.display_name, rp.rank, rp.score, rp.trophies))
        else:
            slug = player.slug if player is not None else None
            display = player.display_name if player is not None else name
            seeded.append(SeededAttendee(slug, display, None, None, None))

    seeded.sort(key=lambda a: (a.rank is None, a.rank or 0, a.display_name.lower()))
    return seeded


def seated_ring_order(ranked: Sequence) -> list:
    """Map a rank-ordered sequence (best first, unranked already trailing) onto the seeded ring: top
    half in seat order, bottom half reversed. For an 8-pod also swap seats 3<->4 and 5<->6 so the top
    seed's round-2 bracket is the weakest (4*5), the conventional seeded reward. Returns items in seat
    order (seat 0 first). Sizes other than 8 get top-in-order + bottom-reversed with no swap. Works on
    any list (Draftmancer userNames for setSeating, or seeded attendees for the seating embed)."""
    items = list(ranked)
    half = len(items) // 2
    ring = items[:half] + items[half:][::-1]
    if len(items) == 8:
        ring[2], ring[3] = ring[3], ring[2]
        ring[6], ring[7] = ring[7], ring[6]
    return ring


def rank_ordered_names(
    session: Session, names: Sequence[str], rank_override: Mapping[str, FrozenSeed] | None = None,
) -> list[str]:
    """The given names sorted by active-set leaderboard rank, best first, unranked trailing by name.

    Unranked players (unlinked, opted out, no score, or an unresolvable handle) fall to the end —
    same treatment as `/pod-seeding`. Returns the original names, just reordered.

    `rank_override` replaces the live board rather than overlaying it, so a Set Championship orders off the
    standings frozen at its deadline alone and a player who ranked only after it trails, the same rule the
    seeding table places them by.
    """
    if rank_override:
        ranks = {player_id: seed.rank for player_id, seed in rank_override.items()}
    else:
        active = resolve_active_set(session)
        ranks = {r.player_id: r.rank for r in rank_players_for_set(session, active.id)} if active else {}
    resolved = players_for_names(session, names)

    def sort_key(item: tuple[str, Player | None]) -> tuple:
        name, player = item
        rank = ranks.get(player.id) if player is not None else None
        return (rank is None, rank or 0, name.lower())

    return [name for name, _ in sorted(resolved, key=sort_key)]


def leaderboard_seat_order(
    session: Session, names: Sequence[str], rank_override: Mapping[str, FrozenSeed] | None = None,
) -> list[str]:
    """The given names in seeded-ring seat order (seat 0 first) by active-set leaderboard rank.

    Rank order best-first via `rank_ordered_names`, then mapped onto the seat ring — ready to map to
    Draftmancer userIDs for setSeating. `rank_override` carries a Set Championship's frozen snapshot, so
    the table is dealt in the order its seeding table published.
    """
    return seated_ring_order(rank_ordered_names(session, names, rank_override))


def _stats_by_player(session: Session, set_id: str) -> dict[str, list[dict]]:
    """17lands stat rows per active, opted-in player for the set, keyed by player_id."""
    rows = session.execute(
        select(
            PlayerStats.player_id, PlayerStats.format, PlayerStats.events,
            PlayerStats.wins, PlayerStats.losses, PlayerStats.trophies,
        )
        .join(Player, Player.id == PlayerStats.player_id)
        .where(
            Player.active.is_(True),
            Player.leaderboard_opt_in.is_(True),
            PlayerStats.set_id == set_id,
        )
    ).all()
    by_player: dict[str, list[dict]] = {}
    for r in rows:
        by_player.setdefault(r.player_id, []).append({
            "format": r.format, "events": int(r.events or 0),
            "wins": int(r.wins or 0), "losses": int(r.losses or 0),
            "trophies": int(r.trophies or 0),
        })
    return by_player


def _stats_by_player_asof(session: Session, set_id: str, cutoff: datetime) -> dict[str, list[dict]]:
    """The same rows `_stats_by_player` reads, aggregated instead from the drafts finished before `cutoff`.

    `player_stats` carries one total per (player, format) and no time dimension, so a past instant can only
    be rebuilt from `draft_events`, which keeps a row per draft with the time it finished. A draft still in
    progress has no finish time and counts for no instant."""
    rows = session.execute(
        select(
            DraftEvent.player_id,
            DraftEvent.format,
            func.count().label("events"),
            func.sum(DraftEvent.wins).label("wins"),
            func.sum(DraftEvent.losses).label("losses"),
            func.sum(case((DraftEvent.is_trophy, 1), else_=0)).label("trophies"),
        )
        .join(Player, Player.id == DraftEvent.player_id)
        .where(
            Player.active.is_(True),
            Player.leaderboard_opt_in.is_(True),
            DraftEvent.set_id == set_id,
            DraftEvent.finished_at.isnot(None),
            DraftEvent.finished_at < cutoff,
        )
        .group_by(DraftEvent.player_id, DraftEvent.format)
    ).all()
    by_player: dict[str, list[dict]] = {}
    for r in rows:
        by_player.setdefault(r.player_id, []).append({
            "format": r.format, "events": int(r.events or 0),
            "wins": int(r.wins or 0), "losses": int(r.losses or 0),
            "trophies": int(r.trophies or 0),
        })
    return by_player


def resolve_player(session: Session, player_name: str | None, viewer_discord_id: str) -> Player | None:
    if player_name:
        return session.execute(
            select(Player).where(
                func.lower(Player.display_name) == player_name.lower(),
                Player.active.is_(True),
            )
        ).scalar_one_or_none()
    return session.execute(
        select(Player).where(Player.discord_id == viewer_discord_id)
    ).scalar_one_or_none()


def _format_breakdown(breakdown: list[dict], direct_stats: dict | None = None, opted_out: bool = False) -> str:
    if not breakdown:
        return "_No drafts logged yet for this set._"
    lines: list[str] = []
    for b in breakdown:
        games = b["wins"] + b["losses"]
        winrate = b["wins"] / games if games > 0 else 0.0
        events_word = "event" if b["events"] == 1 else "events"
        trophy_word = "trophy" if b["trophies"] == 1 else "trophies"
        score_suffix = "" if opted_out else f" → {b['score']:.1f} pts"
        lines.append(
            f"**{b['label']}** — {b['events']} {events_word}, "
            f"{b['wins']}-{b['losses']} ({winrate:.0%}), "
            f"{b['trophies']} {trophy_word}{score_suffix}"
        )
        if b["label"] == "Sealed" and direct_stats is not None:
            d_events = direct_stats["events"]
            d_wins = direct_stats["wins"]
            d_losses = direct_stats["losses"]
            d_boxes = direct_stats["boxes"]
            d_games = d_wins + d_losses
            d_winrate = d_wins / d_games if d_games > 0 else 0.0
            events_word = "event" if d_events == 1 else "events"
            box_word = "box" if d_boxes == 1 else "boxes"
            lines.append(
                f"↳ **Direct** — {d_events} {events_word}, "
                f"{d_wins}-{d_losses} ({d_winrate:.0%}), "
                f"{d_boxes} {box_word}"
            )
    return "\n".join(lines)
