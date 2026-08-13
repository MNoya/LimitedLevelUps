import { BUCKET_DEFS, FORMAT_BUCKETS, type BucketDef } from "../data/format-buckets";
import { aggregate, groupTotalsFromBreakdown } from "../data/scoring";
import type { PlayerDraftEvent, PlayerFormatBreakdown } from "../types/leaderboard";

// Trophies of one Arena rank tier, divisions collapsed. tier is null for a trophy with no rank on
// record, which weighs the same as the lowest tiers
export interface RankTerm {
  tier: string | null;
  points: number;
  count: number;
}

export interface BreakdownRow {
  label: string;
  played: boolean;
  events: number;
  wins: number;
  losses: number;
  count: number;
  points: number;
  // Every trophy priced at the rank it was taken at. Equals count × points for a group paying no
  // rank bonus, and comes from the same weighted count the score itself used
  weightedPoints: number;
  rate: number;
  isLcq: boolean;
  isPod: boolean;
  // The group pays a rank bonus, so weightedPoints carries the points and `points` alone would lie
  rankWeighted: boolean;
  twoWins: number;
  oneWins: number;
  // Empty when no rank is on record for any of the trophies
  rankTerms: RankTerm[];
  score: number;
}

export const RANK_TIERS = ["Mythic", "Diamond", "Platinum", "Gold", "Silver", "Bronze"] as const;

export type TrophyTierCounts = Map<string, Map<string, number>>;

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
  tierCounts?: Map<string, number>,
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
      weightedPoints: wins * def.points,
      rate: winrate,
      isLcq: true,
      isPod: false,
      rankWeighted: false,
      twoWins: 0,
      oneWins: 0,
      rankTerms: [],
      score,
    };
  }

  const weightedTrophies = r?.weightedTrophies || trophies;
  const trophyRate = events > 0 ? trophies / events : 0;
  return {
    label: def.label,
    played: events > 0,
    events,
    wins,
    losses,
    count: trophies,
    points: def.points,
    weightedPoints: Math.round(weightedTrophies * def.points * 100) / 100,
    rate: trophyRate,
    isLcq: false,
    isPod: false,
    rankWeighted: def.rankPoints != null,
    twoWins: 0,
    oneWins: 0,
    rankTerms: rankTerms(def, trophies, tierCounts),
    score,
  };
}

// Best rank first, trophies with no rank on record last
function rankTerms(def: BucketDef, trophies: number, tierCounts?: Map<string, number>): RankTerm[] {
  if (!def.rankPoints || trophies === 0 || !tierCounts) {
    return [];
  }
  const terms: RankTerm[] = [];
  let ranked = 0;
  for (const tier of RANK_TIERS) {
    const count = tierCounts.get(tier) ?? 0;
    if (count > 0) {
      terms.push({ tier, points: def.rankPoints[tier] ?? def.points, count });
      ranked += count;
    }
  }
  if (terms.length === 0) {
    return [];
  }
  const unranked = trophies - ranked;
  if (unranked > 0) {
    terms.push({ tier: null, points: def.points, count: unranked });
  }
  return terms;
}

// Trophy counts per group label per rank tier. A junk or missing end_rank is left uncounted, so it
// lands in the unranked remainder rankTerms derives from the group's trophy total
export function trophyTierCounts(events: readonly PlayerDraftEvent[]): TrophyTierCounts {
  const byLabel: TrophyTierCounts = new Map();
  for (const e of events) {
    const tier = RANK_TIERS.find((t) => t === e.endRank?.split("-")[0]);
    const label = FORMAT_BUCKETS[e.format];
    if (!e.isTrophy || !tier || !label) {
      continue;
    }
    const tiers = byLabel.get(label) ?? new Map<string, number>();
    tiers.set(tier, (tiers.get(tier) ?? 0) + 1);
    byLabel.set(label, tiers);
  }
  return byLabel;
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
    weightedPoints: 0,
    rate: 0,
    isLcq: false,
    isPod: true,
    rankWeighted: false,
    twoWins: pod.twoWins ?? 0,
    oneWins: pod.oneWins ?? 0,
    rankTerms: [],
    score: pod.scoreContribution,
  };
}

export function computeRows(
  breakdown: PlayerFormatBreakdown[],
  confidenceOverride?: number,
  tierCounts?: TrophyTierCounts,
): BreakdownResult {
  const queues = breakdown.filter((b) => b.formatLabel !== "Pod");
  const agg = aggregate(groupTotalsFromBreakdown(queues));
  const confidence = confidenceOverride ?? agg.confidence;
  // A format-filtered subset would otherwise shrink confidence to its own trophies; rescale the
  // confidence-weighted contributions to the player-wide factor. LCQ Draft 2 carries no confidence.
  const scale = confidenceOverride != null && agg.confidence > 0 ? confidenceOverride / agg.confidence : 1;
  const rows = BUCKET_DEFS.map((def) => {
    const row = rowFor(def, queues, agg.contributionByLabel, tierCounts?.get(def.label));
    if (scale !== 1 && !row.isLcq) row.score *= scale;
    return row;
  }).filter((r) => r.played);
  const pod = breakdown.find((b) => b.formatLabel === "Pod");
  if (pod) rows.push(podRow(pod));
  return { rows, confidence };
}
