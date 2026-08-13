import { BUCKET_DEFS, type BucketDef } from "../data/format-buckets";
import { aggregate, groupTotalsFromBreakdown } from "../data/scoring";
import type { PlayerFormatBreakdown } from "../types/leaderboard";

export interface BreakdownRow {
  label: string;
  played: boolean;
  events: number;
  wins: number;
  losses: number;
  count: number;
  points: number;
  rate: number;
  isLcq: boolean;
  isPod: boolean;
  twoWins: number;
  oneWins: number;
  score: number;
}

export interface BreakdownResult {
  rows: BreakdownRow[];
  confidence: number;
}

export function pct(n: number): string {
  return `${Math.round(n * 100)}%`;
}

const FULL_FORMAT_NAMES: Record<string, string> = {
  Premier: "Premier Draft",
  Trad: "Traditional Draft",
  Sealed: "Sealed",
  Quick: "Quick Draft",
  "LCQ Draft 1": "LCQ Draft 1",
  "LCQ Draft 2": "LCQ Draft 2",
  Pod: "Pod Draft",
};

export function fullFormatName(label: string): string {
  return FULL_FORMAT_NAMES[label] ?? label;
}

function rowFor(
  def: BucketDef,
  breakdown: PlayerFormatBreakdown[],
  contributionByLabel: Map<string, number>,
): BreakdownRow {
  const r = breakdown.find((b) => b.formatLabel === def.label);
  const events = r?.events ?? 0;
  const wins = r?.wins ?? 0;
  const losses = r?.losses ?? 0;
  const trophies = r?.trophies ?? 0;
  const score = contributionByLabel.get(def.label) ?? 0;

  if (def.rule === "lcq_draft_2") {
    const games = wins + losses;
    const winrate = games > 0 ? wins / games : 0;
    return {
      label: def.label,
      played: games > 0,
      events,
      wins,
      losses,
      count: wins,
      points: def.points,
      rate: winrate,
      isLcq: true,
      isPod: false,
      twoWins: 0,
    oneWins: 0,
      score,
    };
  }

  const trophyRate = events > 0 ? trophies / events : 0;
  return {
    label: def.label,
    played: events > 0,
    events,
    wins,
    losses,
    count: trophies,
    points: def.points,
    rate: trophyRate,
    isLcq: false,
    isPod: false,
    twoWins: 0,
    oneWins: 0,
    score,
  };
}

function podRow(pod: PlayerFormatBreakdown): BreakdownRow {
  return {
    label: pod.formatLabel,
    played: true,
    events: pod.events,
    wins: pod.wins,
    losses: pod.losses,
    count: pod.trophies,
    points: 0,
    rate: 0,
    isLcq: false,
    isPod: true,
    twoWins: pod.twoWins ?? 0,
    oneWins: pod.oneWins ?? 0,
    score: pod.scoreContribution,
  };
}

export function computeRows(
  breakdown: PlayerFormatBreakdown[],
  confidenceOverride?: number,
): BreakdownResult {
  const queues = breakdown.filter((b) => b.formatLabel !== "Pod");
  const agg = aggregate(groupTotalsFromBreakdown(queues));
  const confidence = confidenceOverride ?? agg.confidence;
  // A format-filtered subset would otherwise shrink confidence to its own trophies; rescale the
  // confidence-weighted contributions to the player-wide factor. LCQ Draft 2 carries no confidence.
  const scale = confidenceOverride != null && agg.confidence > 0 ? confidenceOverride / agg.confidence : 1;
  const rows = BUCKET_DEFS.map((def) => {
    const row = rowFor(def, queues, agg.contributionByLabel);
    if (scale !== 1 && !row.isLcq) row.score *= scale;
    return row;
  }).filter((r) => r.played);
  const pod = breakdown.find((b) => b.formatLabel === "Pod");
  if (pod) rows.push(podRow(pod));
  return { rows, confidence };
}
