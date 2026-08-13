"""Format groups and scoring formula for player rating.

    raw_group   = weighted_trophies × group_points × trophy_rate
    confidence  = T / (T + 2)        # T = total trophies across all groups
    total       = (Σ raw_group) × confidence

with a special case for LCQ Draft 2 (counts wins instead of trophies, uses
winrate, and is exempt from the confidence multiplier).

Confidence is an aggregate: it shrinks the whole resume by one factor built
from total trophy count, rather than penalising each queue group on its own
small sample. Pod-draft points are a separate flat term (see ``pod_points``),
added to the leaderboard total outside this module.

``weighted_trophies`` counts a trophy by what the player's rank was worth at
the end of the event, so a group carrying ``rank_points`` pays more for a
trophy taken at a high rank. Only the numerator is weighted: trophy_rate and
the confidence total stay on raw counts, so a rank weight moves the multiplier
and never the rate. Groups without ``rank_points`` weight every trophy at 1.0,
which leaves ``weighted_trophies`` equal to ``trophies``. A row carrying trophies
but no weighted count scores unweighted, so a writer that predates the column
degrades to the old formula instead of to zero.

A ``QueueGroup`` collects raw 17lands ``format`` strings under a single label
that shares a points weight. The ``Sealed`` group rolls best-of-1 and
best-of-3 sealed under one entry — sealed is sealed for scoring purposes. LCQ
groups sit dormant until WOTC actually runs LCQ events for the season.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Iterable, Mapping, Sequence

from bot.sets import (
    SIX_WIN_COLLECTOR_DIRECT_SETS,
    SIX_WIN_PLAY_DIRECT_SETS,
    is_collector_booster_window,
)


@dataclass(frozen=True)
class QueueGroup:
    label: str
    points: int
    formats: tuple[str, ...]
    # None = standard formula; "lcq_draft_2" = wins-not-trophies × winrate × points
    rule: str | None = None
    # Arena rank tier -> what a trophy taken at that tier is worth, in the same points unit
    rank_points: Mapping[str, int] = field(default_factory=dict)

    def trophy_weight(self, end_rank: str | None) -> float:
        """Multiplier for one trophy, keyed on the tier of a ``Platinum-3``-shaped rank string."""
        if not end_rank or not self.rank_points:
            return 1.0
        tier = end_rank.split("-")[0]
        return self.rank_points.get(tier, self.points) / self.points


BUCKETS_JSON = Path(__file__).resolve().parents[1] / "scoring_buckets.json"
_BUCKETS = json.loads(BUCKETS_JSON.read_text())

DEFAULT_QUEUE_GROUPS: tuple[QueueGroup, ...] = tuple(
    QueueGroup(
        label=g["label"],
        points=int(g["points"]),
        formats=tuple(g["formats"]),
        rule=g.get("rule"),
        rank_points={tier: int(pts) for tier, pts in g.get("rank_points", {}).items()},
    )
    for g in _BUCKETS["groups"]
)

POD_TROPHY_POINTS = float(_BUCKETS.get("pod", {}).get("trophy_points", 5))
POD_TWO_WIN_POINTS = float(_BUCKETS.get("pod", {}).get("two_win_points", 2))
POD_ONE_WIN_POINTS = float(_BUCKETS.get("pod", {}).get("one_win_points", 0.5))

ARENA_DIRECT_SEALED_FORMAT = "ArenaDirect_Sealed"


def pod_points(trophies: int, two_win_finishes: int, one_win_finishes: int) -> int:
    """Flat pod-draft contribution, floored so fractional finishes bank across pods.

    Paid on match wins, not on the record string: a trophy is a 3-0 or a pod win, and two wins pay the
    same whether the third match was lost or forfeited by a drop. Added to the leaderboard total
    alongside ``compute_score`` — pods are not a 17lands queue group and are exempt from
    trophy_rate / confidence.
    """
    total = (
        trophies * POD_TROPHY_POINTS
        + two_win_finishes * POD_TWO_WIN_POINTS
        + one_win_finishes * POD_ONE_WIN_POINTS
    )
    return int(total)


def supported_formats(groups: Iterable[QueueGroup] = DEFAULT_QUEUE_GROUPS) -> tuple[str, ...]:
    return tuple(fmt for g in groups for fmt in g.formats)


def group_label_for_format(fmt: str | None, groups: Iterable[QueueGroup] = DEFAULT_QUEUE_GROUPS) -> str | None:
    if fmt is None:
        return None
    for group in groups:
        if fmt in group.formats:
            return group.label
    return None


def confidence_factor(total_trophies: int) -> float:
    """Aggregate shrinkage prior: T/(T+2) over the player's whole trophy count."""
    return total_trophies / (total_trophies + 2) if total_trophies > 0 else 0.0


def _aggregate(
    stats_rows: Sequence[dict],
    groups: Iterable[QueueGroup],
) -> tuple[dict[str, float], float]:
    """Per-group score contribution (by label) and the aggregate confidence factor.

    Non-LCQ groups contribute ``raw_group × confidence`` where confidence is built
    from total trophies across all non-LCQ groups, so the parts sum to the total.
    LCQ Draft 2 keeps its wins×winrate×points rule and is exempt from confidence.
    """
    groups = list(groups)
    grouped: dict[str, list[dict]] = {}
    for row in stats_rows:
        g = _group_for_format(groups, row["format"])
        if g is not None:
            grouped.setdefault(g.label, []).append(row)

    raw_by_label: dict[str, float] = {}
    lcq_by_label: dict[str, float] = {}
    total_trophies = 0
    for g in groups:
        rows = grouped.get(g.label)
        if not rows:
            continue
        if g.rule == "lcq_draft_2":
            wins = sum(r.get("wins", 0) for r in rows)
            losses = sum(r.get("losses", 0) for r in rows)
            games = wins + losses
            if games and wins:
                lcq_by_label[g.label] = wins * (wins / games) * g.points
            continue
        trophies = sum(r.get("trophies", 0) for r in rows)
        events = sum(r.get("events", 0) for r in rows)
        if trophies == 0 or events == 0:
            continue
        weighted = sum(r.get("weighted_trophies") or r.get("trophies", 0) for r in rows)
        raw_by_label[g.label] = weighted * g.points * (trophies / events)
        total_trophies += trophies

    confidence = confidence_factor(total_trophies)
    contrib = {label: raw * confidence for label, raw in raw_by_label.items()}
    contrib.update(lcq_by_label)
    return contrib, confidence


def compute_score_breakdown(
    stats_rows: Sequence[dict],
    groups: Iterable[QueueGroup] = DEFAULT_QUEUE_GROUPS,
) -> list[dict]:
    """Per-group totals + score contribution, derived from the aggregate so the
    contributions sum to ``compute_score``. Skips groups with no matching rows.
    """
    groups_list = list(groups)
    grouped: dict[str, list[dict]] = {}
    for row in stats_rows:
        g = _group_for_format(groups_list, row["format"])
        if g is not None:
            grouped.setdefault(g.label, []).append(row)

    contrib, _ = _aggregate(stats_rows, groups_list)
    breakdown: list[dict] = []
    for g in groups_list:
        rows = grouped.get(g.label)
        if not rows:
            continue
        breakdown.append({
            "label": g.label,
            "events": sum(r.get("events", 0) for r in rows),
            "wins": sum(r.get("wins", 0) for r in rows),
            "losses": sum(r.get("losses", 0) for r in rows),
            "trophies": sum(r.get("trophies", 0) for r in rows),
            "score": round(contrib.get(g.label, 0.0), 2),
        })
    return breakdown


def compute_score(
    stats_rows: Sequence[dict],
    groups: Iterable[QueueGroup] = DEFAULT_QUEUE_GROUPS,
) -> float:
    """Total 17lands score for one player across all their group-rolled stats.

    ``stats_rows`` items are dicts with keys: format, wins, losses, trophies, events,
    and optionally weighted_trophies, which falls back to trophies when absent.
    Rows whose format isn't in any group are ignored. Pod points are added by the
    caller via ``pod_points``.
    """
    contrib, _ = _aggregate(stats_rows, groups)
    return round(sum(contrib.values()), 2)


def boxes_for_event(set_code: str, wins: int, finished_at: datetime | None, is_trophy: bool) -> int:
    """Boxes awarded for a single Arena Direct Sealed event, per the era rules in bot.sets.

    A collector premiere always pays one box for winning the event, and a 2024 play set
    pays two — both keyed on ``is_trophy`` so the per-era win cap (6 vs 7, including the
    mid-TDM rollout) comes straight from 17lands rather than a hardcoded threshold. Only
    the default 7-win play ladder needs raw wins, for its 1-box consolation at six.
    """
    if set_code in SIX_WIN_PLAY_DIRECT_SETS:
        return 2 if is_trophy else 0
    if set_code in SIX_WIN_COLLECTOR_DIRECT_SETS:
        return 1 if is_trophy else 0
    if finished_at is not None and is_collector_booster_window(set_code, finished_at.date()):
        return 1 if is_trophy else 0
    return 2 if wins >= 7 else (1 if wins == 6 else 0)


def _group_for_format(groups: Iterable[QueueGroup], fmt: str) -> QueueGroup | None:
    for g in groups:
        if fmt in g.formats:
            return g
    return None
