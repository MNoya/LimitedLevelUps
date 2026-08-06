"""Compute Set Awards winners and runner-ups from draft_events and pod drafts.

Pure logic, no Discord/presentation. The live `/set-awards` command and the
`set_awards_results` dev script both consume these, so the math lives in one place.

Five awards derive from draft_events (first_striker, seize_the_day, climber, specialist,
revel_in_riches); mvp counts pod drafts played inside the set window. Winners are assigned
greedily in ceremony order so nobody wins twice; runner-ups exclude winners, except awards in
``ALLOW_FEATURED_RUNNERS`` which show all tied. The Premier > Trad > Quick tiebreak only ever
decides a winner, never a runner-up.
"""
from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from bot.models import DraftEvent, MagicSet, Player, PlayerStats, PodDraftEvent, PodDraftParticipant
from bot.scoring import ARENA_DIRECT_SEALED_FORMAT, boxes_for_event, compute_score_breakdown
from bot.sets import SetSeed, release_instant

ET = ZoneInfo("America/New_York")
RANK_TIERS = ("Bronze", "Silver", "Gold", "Platinum", "Diamond", "Mythic")
MYTHIC_INDEX = RANK_TIERS.index("Mythic")
CLIMB_TIER_WEIGHT = 100
BO1_FORMATS = frozenset({"PremierDraft", "QuickDraft"})

MIN_ARCHETYPE_GAMES = 20
MIN_COMMUNITY_GAMES = 40

CEREMONY_ORDER = ("first_striker", "seize_the_day", "revel_in_riches", "climber", "specialist", "mvp")
ALLOW_FEATURED_RUNNERS = {"seize_the_day"}


@dataclass(frozen=True)
class AwardCandidate:
    discord_id: str | None
    display_name: str
    detail: str
    avatar_url: str | None
    tie_key: object
    tiebreak: tuple[float, float, float] = (0.0, 0.0, 0.0)
    ceremony_detail: str | None = None
    archetype: str | None = None
    when: datetime | None = None


@dataclass
class PlayerCtx:
    player: Player
    events: list[DraftEvent] = field(default_factory=list)
    stats_rows: list[dict] = field(default_factory=list)
    pod_drafts: int = 0

    @property
    def name(self) -> str:
        return self.player.display_name

    @property
    def tiebreak(self) -> tuple[float, float, float]:
        by_label = {row["label"]: row["score"] for row in compute_score_breakdown(self.stats_rows)}
        return (by_label.get("Premier", 0.0), by_label.get("Trad", 0.0), by_label.get("Quick", 0.0))

    def candidate(
        self, detail: str, tie_key: object, ceremony_detail: str | None = None,
        archetype: str | None = None, when: datetime | None = None,
    ) -> AwardCandidate:
        return AwardCandidate(
            discord_id=self.player.discord_id,
            display_name=self.name,
            detail=detail,
            avatar_url=avatar_url(self.player.discord_id, self.player.avatar_hash),
            tie_key=tie_key,
            tiebreak=self.tiebreak,
            ceremony_detail=ceremony_detail,
            archetype=archetype,
            when=when,
        )


def compute_db_awards(session: Session, mset: MagicSet, seed: SetSeed) -> dict[str, list[AwardCandidate]]:
    return rank_db_awards(load_contexts(session, mset, seed), seed, mset.code)


def rank_db_awards(ctxs: list[PlayerCtx], seed: SetSeed, code: str) -> dict[str, list[AwardCandidate]]:
    return {
        "first_striker": first_striker(ctxs, seed),
        "seize_the_day": seize_the_day(ctxs),
        "climber": climber(ctxs),
        "specialist": specialist(ctxs),
        "revel_in_riches": revel_in_riches(ctxs, code),
        "mvp": mvp(ctxs),
    }


FUN_RANKED_STATS = ("trophy_streak", "merchant_streak", "heartbreakers", "cold_run")


def personal_payload(
    session: Session, mset: MagicSet, seed: SetSeed, discord_id: str,
) -> tuple[dict, "PlayerCtx", dict] | None:
    """Award standings, the caller's own context, and field-wide fun-stat values for one player.

    None when the caller has nothing in the set: no drafts and no pod seats.
    """
    ctxs = load_contexts(session, mset, seed)
    mine = None
    for ctx in ctxs:
        if ctx.player.discord_id == discord_id:
            mine = ctx
            break
    if mine is None:
        return None
    ranked = rank_db_awards(ctxs, seed, mset.code)
    fun_values = {key: [_fun_value(c, key) for c in ctxs] for key in FUN_RANKED_STATS}
    return ranked, mine, fun_values


def rank_in(values: list[int], value: int) -> int:
    """Competition rank of `value` among `values` (ties share a rank, 1 = best)."""
    return 1 + sum(1 for v in values if v > value)


def _fun_value(ctx: PlayerCtx, key: str) -> int:
    if key == "trophy_streak":
        return _trophy_streak(ctx)[0]
    if key == "merchant_streak":
        return _merchant_streak(ctx)
    if key == "heartbreakers":
        return _heartbreakers(ctx)
    if key == "cold_run":
        return _cold_run(ctx)
    return 0


def personal_extras(ctx: PlayerCtx) -> dict:
    """Per-player fun stats shown only in the personal view, not the public ceremony."""
    streak, start, end = _trophy_streak(ctx)
    return {
        "trophy_streak": streak,
        "trophy_span": (start, end) if start is not None else None,
        "merchant_streak": _merchant_streak(ctx),
        "merchant_events": sum(1 for e in ctx.events if e.format == "TradDraft"),
        "heartbreakers": _heartbreakers(ctx),
        "heartbreakers_events": sum(1 for e in ctx.events if e.format == "PremierDraft"),
        "cold_run": _cold_run(ctx),
    }


def _trophy_streak(ctx: PlayerCtx) -> tuple[int, datetime | None, datetime | None]:
    ordered = sorted((e for e in ctx.events if e.started_at is not None), key=lambda e: e.started_at)
    best = run = 0
    best_start = best_end = run_start = None
    for e in ordered:
        if e.is_trophy:
            if run == 0:
                run_start = e.started_at
            run += 1
            if run > best:
                best, best_start, best_end = run, run_start, e.started_at
        else:
            run = 0
    return best, best_start, best_end


def _merchant_streak(ctx: PlayerCtx) -> int:
    """Longest run of consecutive 2-1 finishes in Traditional Draft."""
    ordered = sorted(
        (e for e in ctx.events if e.started_at is not None and e.format == "TradDraft"),
        key=lambda e: e.started_at,
    )
    best = run = 0
    for e in ordered:
        run = run + 1 if (e.wins == 2 and e.losses == 1) else 0
        best = max(best, run)
    return best


def _heartbreakers(ctx: PlayerCtx) -> int:
    """Total 6-3 finishes in Premier — one win short of the trophy."""
    return sum(1 for e in ctx.events if e.format == "PremierDraft" and e.wins == 6 and e.losses == 3)


def _cold_run(ctx: PlayerCtx) -> int:
    """Longest run of consecutive Premier drafts without a positive finish (4+ wins)."""
    ordered = sorted(
        (e for e in ctx.events if e.started_at is not None and e.format == "PremierDraft"),
        key=lambda e: e.started_at,
    )
    best = run = 0
    for e in ordered:
        run = 0 if e.wins >= 4 else run + 1
        best = max(best, run)
    return best


def assign(
    ranked: dict[str, list[AwardCandidate]],
) -> tuple[dict[str, AwardCandidate], dict[str, list[AwardCandidate]]]:
    winners: dict[str, AwardCandidate] = {}
    won: set[str] = set()
    for key in CEREMONY_ORDER:
        for cand in ranked.get(key, []):
            if cand.discord_id is None or cand.discord_id not in won:
                winners[key] = cand
                if cand.discord_id is not None:
                    won.add(cand.discord_id)
                break
    runners: dict[str, list[AwardCandidate]] = {}
    for key in CEREMONY_ORDER:
        winner = winners.get(key)
        if key in ALLOW_FEATURED_RUNNERS:
            eligible = [c for c in ranked.get(key, []) if winner is None or c is not winner]
        else:
            eligible = [c for c in ranked.get(key, []) if c.discord_id is None or c.discord_id not in won]
        runners[key] = [c for c in eligible if c.tie_key == eligible[0].tie_key] if eligible else []
    return winners, runners


def load_contexts(session: Session, mset: MagicSet, seed: SetSeed) -> list[PlayerCtx]:
    """Every active player who did something in the set: a 17lands draft or a pod seat.

    Pod drafts are public for everyone, so a player who opted out of the leaderboard still races for
    the pod award. Their 17lands events stay unread, which keeps them out of the five draft awards.
    """
    players = session.execute(select(Player).where(Player.active.is_(True))).scalars().all()
    by_id = {p.id: PlayerCtx(player=p) for p in players}
    drafters = {pid: ctx for pid, ctx in by_id.items() if ctx.player.leaderboard_opt_in}
    for event in session.execute(select(DraftEvent).where(DraftEvent.set_id == mset.id)).scalars():
        if event.started_at is not None and event.started_at.astimezone(ET).date() < seed.start_date:
            continue
        ctx = drafters.get(event.player_id)
        if ctx is not None:
            ctx.events.append(event)
    for stat in session.execute(select(PlayerStats).where(PlayerStats.set_id == mset.id)).scalars():
        ctx = drafters.get(stat.player_id)
        if ctx is not None:
            ctx.stats_rows.append({
                "format": stat.format, "wins": stat.wins, "losses": stat.losses,
                "trophies": stat.trophies, "events": stat.events,
            })
    for player_id, count in load_pod_draft_counts(session, seed).items():
        ctx = by_id.get(player_id)
        if ctx is not None:
            ctx.pod_drafts = count
    return [c for c in by_id.values() if c.events or c.pod_drafts]


def load_pod_draft_counts(session: Session, seed: SetSeed) -> dict[str, int]:
    """Pod drafts played per player inside the set window, counted by date and not by format code so
    a cube or Peasant pod run during the set still counts."""
    query = (
        select(PodDraftParticipant.player_id, func.count())
        .join(PodDraftEvent, PodDraftEvent.id == PodDraftParticipant.event_id)
        .where(
            PodDraftParticipant.player_id.is_not(None),
            PodDraftParticipant.record.is_not(None),
            PodDraftEvent.event_date >= seed.start_date,
        )
        .group_by(PodDraftParticipant.player_id)
    )
    if seed.end_date is not None:
        query = query.where(PodDraftEvent.event_date <= seed.end_date)
    return {player_id: count for player_id, count in session.execute(query)}


SPECIALIST_FIELD_SEP = ", vs field of"


def first_striker_detail(after_release: timedelta) -> str:
    return f"**{_fmt_delta(after_release)}** after set release"


def first_striker_ceremony(after_release: timedelta) -> str:
    return f"trophied {first_striker_detail(after_release)}"


def first_striker_gap(behind_leader: timedelta) -> str:
    return f"earned one **{_fmt_delta_coarse(behind_leader)}** later"


def seize_detail(trophies: int, when: datetime) -> str:
    local = when.astimezone(ET)
    return f"**{trophies} trophies** in 24h on {local:%b} {local.day}"


def seize_ceremony_detail(trophies: int, when: datetime) -> str:
    local = when.astimezone(ET)
    return f"**{trophies} trophies** on {local:%b} {local.day}"


def climber_detail(start_tier: str, days: int) -> str:
    return f"{start_tier} to Mythic in **{days} {'day' if days == 1 else 'days'}**"


def _field_suffix(field_wr: float) -> str:
    return f"{SPECIALIST_FIELD_SEP} {field_wr:.0%}"


def specialist_detail(win_rate: float, archetype: str, games: int, field_wr: float) -> str:
    return f"a **{win_rate:.0%}** win rate with **{archetype}** over {games} games{_field_suffix(field_wr)}"


def specialist_ceremony_detail(win_rate: float, archetype: str, games: int, field_wr: float) -> str:
    return f"**{win_rate:.0%}** on **{archetype}** over {games} games{_field_suffix(field_wr)}"


def revel_detail(boxes: int, events: int) -> str:
    return f"**{boxes}** boxes in {events} {'event' if events == 1 else 'events'}"


def mvp_detail(count: int) -> str:
    return f"**{count}** pod drafts"


def first_striker(ctxs: list[PlayerCtx], seed: SetSeed) -> list[AwardCandidate]:
    day_one_starts = [
        e.started_at for c in ctxs for e in c.events
        if e.started_at is not None and e.started_at.astimezone(ET).date() == seed.start_date
    ]
    t0 = min(day_one_starts) if day_one_starts else release_instant(seed.start_date)
    earliest: dict[str, tuple[datetime, PlayerCtx]] = {}
    for c in ctxs:
        for e in c.events:
            if "Sealed" in e.format:
                continue
            earned_at = e.finished_at or e.started_at
            if e.is_trophy and earned_at is not None:
                current = earliest.get(c.player.id)
                if current is None or earned_at < current[0]:
                    earliest[c.player.id] = (earned_at, c)
    ordered = sorted(earliest.values(), key=lambda t: (t[0], _neg(t[1].tiebreak)))
    leader_ts = ordered[0][0] if ordered else t0
    result = []
    for index, (ts, c) in enumerate(ordered):
        detail = first_striker_detail(ts - t0)
        ceremony = first_striker_ceremony(ts - t0) if index == 0 else first_striker_gap(ts - leader_ts)
        result.append(c.candidate(detail, ts, ceremony_detail=ceremony))
    return result


def seize_the_day(ctxs: list[PlayerCtx]) -> list[AwardCandidate]:
    scored = []
    for c in ctxs:
        times = sorted(e.finished_at for e in c.events if e.is_trophy and e.finished_at is not None)
        best, when = _max_within_24h(times)
        if best >= 2:
            scored.append((best, when, c))
    scored.sort(key=lambda t: (t[0], _neg(t[2].tiebreak)), reverse=True)
    result = []
    for n, when, c in scored:
        result.append(c.candidate(
            seize_detail(n, when),
            n,
            ceremony_detail=seize_ceremony_detail(n, when),
            when=when,
        ))
    return result


def _climb_score(floor_index: int, days: int) -> int:
    """A lower starting tier always outranks a higher one: CLIMB_TIER_WEIGHT exceeds any in-month day
    span, so a Bronze/Silver/Gold grind beats a Platinum or Diamond sprint and days only break ties
    within a tier."""
    return CLIMB_TIER_WEIGHT * (MYTHIC_INDEX - floor_index) - days


def climber(ctxs: list[PlayerCtx]) -> list[AwardCandidate]:
    scored = []
    for c in ctxs:
        best = _best_mythic_climb(c)
        if best is not None:
            days, tier_index, start_tier = best
            scored.append((days, tier_index, start_tier, c))
    scored.sort(key=lambda t: (-_climb_score(t[1], t[0]), t[0], t[1], _neg(t[3].tiebreak)))
    return [
        c.candidate(climber_detail(start_tier, days), (_climb_score(tier_index, days), days, tier_index))
        for days, tier_index, start_tier, c in scored
    ]


def specialist(ctxs: list[PlayerCtx]) -> list[AwardCandidate]:
    per_player: dict[tuple[str, str], list[int]] = defaultdict(lambda: [0, 0])
    community: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    by_id = {c.player.id: c for c in ctxs}
    for c in ctxs:
        for e in c.events:
            arch = _archetype(e.colors)
            if arch is None:
                continue
            games = e.wins + e.losses
            per_player[(c.player.id, arch)][0] += e.wins
            per_player[(c.player.id, arch)][1] += games
            community[arch][0] += e.wins
            community[arch][1] += games

    community_wr = {arch: (w / g if g else 0.0) for arch, (w, g) in community.items()}
    best_per_player: dict[str, tuple[float, str, float, int, float]] = {}
    for (pid, arch), (wins, games) in per_player.items():
        if games < MIN_ARCHETYPE_GAMES or community[arch][1] < MIN_COMMUNITY_GAMES:
            continue
        field_wr = community_wr[arch]
        player_wr = wins / games
        if not 0 < field_wr < 1:
            continue
        z = (player_wr - field_wr) / math.sqrt(field_wr * (1 - field_wr) / games)
        if pid not in best_per_player or z > best_per_player[pid][0]:
            best_per_player[pid] = (z, arch, player_wr, games, field_wr)

    ranked = sorted(best_per_player.items(), key=lambda kv: (kv[1][0], _neg(by_id[kv[0]].tiebreak)), reverse=True)
    return [
        by_id[pid].candidate(
            specialist_detail(wr, arch, games, fw),
            z,
            ceremony_detail=specialist_ceremony_detail(wr, arch, games, fw),
            archetype=arch,
        )
        for pid, (z, arch, wr, games, fw) in ranked
    ]


def revel_in_riches(ctxs: list[PlayerCtx], code: str) -> list[AwardCandidate]:
    scored = []
    for c in ctxs:
        sealed = [e for e in c.events if e.format == ARENA_DIRECT_SEALED_FORMAT]
        boxes = sum(boxes_for_event(code, e.wins, e.finished_at, e.is_trophy) for e in sealed)
        if boxes > 0:
            scored.append((boxes, len(sealed), c))
    scored.sort(key=lambda t: (t[0], _neg(t[2].tiebreak)), reverse=True)
    return [
        c.candidate(revel_detail(boxes, events), boxes)
        for boxes, events, c in scored
    ]


def mvp(ctxs: list[PlayerCtx]) -> list[AwardCandidate]:
    played = [c for c in ctxs if c.pod_drafts > 0]
    played.sort(key=lambda c: (c.pod_drafts, c.tiebreak), reverse=True)
    return [c.candidate(mvp_detail(c.pod_drafts), c.pod_drafts) for c in played]


def avatar_url(discord_id: str | None, avatar_hash: str | None) -> str:
    if discord_id and avatar_hash:
        return f"https://cdn.discordapp.com/avatars/{discord_id}/{avatar_hash}.png?size=128"
    index = (int(discord_id) >> 22) % 6 if discord_id and discord_id.isdigit() else 0
    return f"https://cdn.discordapp.com/embed/avatars/{index}.png"


def _neg(tiebreak: tuple[float, float, float]) -> tuple[float, float, float]:
    return (-tiebreak[0], -tiebreak[1], -tiebreak[2])


def _max_within_24h(times: list[datetime]) -> tuple[int, datetime | None]:
    best = 0
    best_start = None
    for i, start in enumerate(times):
        j = i
        while j < len(times) and times[j] - start <= timedelta(hours=24):
            j += 1
        if j - i > best:
            best = j - i
            best_start = start
    return best, best_start


def _best_mythic_climb(c: PlayerCtx) -> tuple[int, int, str] | None:
    by_month: dict[tuple[int | None, int, int], list[DraftEvent]] = defaultdict(list)
    for e in c.events:
        if e.started_at is not None and e.start_rank and e.end_rank:
            by_month[(e.account_id, e.started_at.year, e.started_at.month)].append(e)

    best: tuple[int, int, str] | None = None
    best_key: tuple[int, int, int] | None = None
    for events in by_month.values():
        events.sort(key=lambda e: e.started_at)
        mythic = [e for e in events if _rank_tier(e.end_rank) == "Mythic"]
        if not mythic:
            continue
        first_mythic = mythic[0]
        floor_index = 99
        floor_event = None
        for e in events:
            if e.started_at > first_mythic.started_at:
                continue
            tier = _rank_tier(e.start_rank)
            if tier is not None and RANK_TIERS.index(tier) < floor_index:
                floor_index = RANK_TIERS.index(tier)
                floor_event = e
        if floor_event is None or floor_index >= MYTHIC_INDEX:
            continue
        end_at = first_mythic.finished_at or first_mythic.started_at
        days = (end_at.date() - floor_event.started_at.date()).days
        key = (_climb_score(floor_index, days), -days, -floor_index)
        if best_key is None or key > best_key:
            best_key = key
            best = (days, floor_index, RANK_TIERS[floor_index])
    return best


def _delta_parts(td: timedelta) -> tuple[str, int, int, int]:
    total = int(td.total_seconds())
    sign = "-" if total < 0 else ""
    total = abs(total)
    days, rem = divmod(total, 86400)
    hours, rem = divmod(rem, 3600)
    return sign, days, hours, rem // 60


def _fmt_delta(td: timedelta) -> str:
    sign, days, hours, minutes = _delta_parts(td)
    if days:
        return f"{sign}{days}d {hours}h"
    if hours:
        return f"{sign}{hours}h {minutes}m"
    return f"{sign}{minutes}m"


def _fmt_delta_coarse(td: timedelta) -> str:
    sign, days, hours, minutes = _delta_parts(td)
    if days:
        return f"{sign}{days}d"
    if hours:
        return f"{sign}{hours}h"
    return f"{sign}{minutes}m"


def _rank_tier(rank: str | None) -> str | None:
    if not rank:
        return None
    tier = rank.split("-")[0].strip().capitalize()
    return tier if tier in RANK_TIERS else None


def _archetype(colors: str | None) -> str | None:
    if not colors:
        return None
    main = "".join(sorted([ch for ch in colors if ch.isupper()], key=lambda ch: "WUBRG".index(ch)))
    return main if 1 <= len(main) <= 5 else None
