// Formula port of bot/scoring.py — must stay in sync. Buckets, weights, and pod
// point values come from the shared scoring_buckets.json (same file Python loads).
//
//   raw_group  = weighted_trophies × weight × trophy_rate
//   confidence = T / (T + 2)        // T = total trophies across all groups
//   total      = (Σ raw_group) × confidence
//
// Confidence is aggregate (one factor over total trophies), and LCQ Draft 2 keeps
// its wins×winrate×weight rule, exempt from confidence. Pod points are a separate
// flat term added by callers via podPoints().
//
// weightedTrophies counts a trophy by what the end-of-event rank was worth, and the
// database supplies it. Only the numerator is weighted: trophy rate and the confidence
// total stay on raw counts. It falls back to trophies where a caller has no rank data.
import {
  BUCKET_DEFS,
  formatsForBucket,
  POD_TROPHY_POINTS,
  POD_WIN_2_1_POINTS,
} from "./format-buckets";

interface QueueGroup {
  label: string;
  points: number;
  formats: readonly string[];
  rule?: "lcq_draft_2";
}

const DEFAULT_QUEUE_GROUPS: readonly QueueGroup[] = BUCKET_DEFS.map((d) => ({
  ...d,
  formats: formatsForBucket(d.label),
}));

export interface ScoringStatRow {
  format: string;
  wins: number;
  losses: number;
  trophies: number;
  weightedTrophies?: number;
  events: number;
}

export interface GroupTotals {
  label: string;
  events: number;
  wins: number;
  losses: number;
  trophies: number;
  weightedTrophies?: number;
}

export interface Aggregate {
  total: number;
  confidence: number;
  contributionByLabel: Map<string, number>;
}

export function podPoints(trophies: number, wins21: number): number {
  return trophies * POD_TROPHY_POINTS + wins21 * POD_WIN_2_1_POINTS;
}

export function confidenceFactor(totalTrophies: number): number {
  return totalTrophies > 0 ? totalTrophies / (totalTrophies + 2) : 0;
}

function defFor(label: string): QueueGroup | undefined {
  return DEFAULT_QUEUE_GROUPS.find((g) => g.label === label);
}

// Per-group contribution (already × aggregate confidence) + the confidence factor.
// Input is per-group totals; rows for the same label are summed first.
export function aggregate(groups: GroupTotals[]): Aggregate {
  const byLabel = new Map<string, GroupTotals>();
  for (const g of groups) {
    if (!defFor(g.label)) continue;
    const cur = byLabel.get(g.label);
    if (cur) {
      cur.events += g.events;
      cur.wins += g.wins;
      cur.losses += g.losses;
      cur.trophies += g.trophies;
      cur.weightedTrophies = (cur.weightedTrophies ?? 0) + (g.weightedTrophies || g.trophies);
    } else {
      byLabel.set(g.label, { ...g, weightedTrophies: g.weightedTrophies || g.trophies });
    }
  }

  const rawByLabel = new Map<string, number>();
  const lcqByLabel = new Map<string, number>();
  let totalTrophies = 0;
  for (const def of DEFAULT_QUEUE_GROUPS) {
    const g = byLabel.get(def.label);
    if (!g) continue;
    if (def.rule === "lcq_draft_2") {
      const games = g.wins + g.losses;
      if (games > 0 && g.wins > 0) {
        lcqByLabel.set(def.label, g.wins * (g.wins / games) * def.points);
      }
      continue;
    }
    if (g.trophies === 0 || g.events === 0) continue;
    const weighted = g.weightedTrophies || g.trophies;
    rawByLabel.set(def.label, weighted * def.points * (g.trophies / g.events));
    totalTrophies += g.trophies;
  }

  const confidence = confidenceFactor(totalTrophies);
  const contributionByLabel = new Map<string, number>();
  for (const [label, raw] of rawByLabel) contributionByLabel.set(label, raw * confidence);
  for (const [label, score] of lcqByLabel) contributionByLabel.set(label, score);

  let total = 0;
  for (const v of contributionByLabel.values()) total += v;
  return { total, confidence, contributionByLabel };
}

export function groupTotalsFromRows(rows: ScoringStatRow[]): GroupTotals[] {
  const byLabel = new Map<string, GroupTotals>();
  for (const row of rows) {
    const def = DEFAULT_QUEUE_GROUPS.find((g) => g.formats.includes(row.format));
    if (!def) continue;
    const cur =
      byLabel.get(def.label) ??
      { label: def.label, events: 0, wins: 0, losses: 0, trophies: 0, weightedTrophies: 0 };
    cur.events += row.events;
    cur.wins += row.wins;
    cur.losses += row.losses;
    cur.trophies += row.trophies;
    cur.weightedTrophies = (cur.weightedTrophies ?? 0) + (row.weightedTrophies || row.trophies);
    byLabel.set(def.label, cur);
  }
  return [...byLabel.values()];
}

// A public_*_breakdown row already carries its group label, so it becomes GroupTotals directly.
export function groupTotalsFromBreakdown(
  rows: readonly {
    formatLabel: string;
    events: number;
    wins: number;
    losses: number;
    trophies: number;
    weightedTrophies?: number;
  }[],
): GroupTotals[] {
  return rows.map((r) => ({
    label: r.formatLabel,
    events: r.events,
    wins: r.wins,
    losses: r.losses,
    trophies: r.trophies,
    weightedTrophies: r.weightedTrophies,
  }));
}

export function computeScore(rows: ScoringStatRow[]): number {
  return Math.round(aggregate(groupTotalsFromRows(rows)).total * 100) / 100;
}

export function scoreFromGroups(groups: GroupTotals[]): number {
  return Math.round(aggregate(groups).total * 100) / 100;
}

// Arena Direct box payouts — port of bot/scoring.py boxes_for_event and the era
// constants in bot/sets.py. Must stay in sync.
const SIX_WIN_PLAY_DIRECT_SETS = new Set(["OTJ", "FDN", "BLB", "DSK"]);
const SIX_WIN_COLLECTOR_DIRECT_SETS = new Set(["DFT"]);

const COLLECTOR_BOOSTER_WINDOWS: ReadonlyArray<{ setCode: string; startDate: string; endDate: string }> = [
  { setCode: "TDM", startDate: "2025-04-18", endDate: "2025-04-20" },
  { setCode: "FIN", startDate: "2025-06-20", endDate: "2025-06-22" },
  { setCode: "EOE", startDate: "2025-08-08", endDate: "2025-08-11" },
  { setCode: "TLA", startDate: "2025-11-28", endDate: "2025-11-30" },
  { setCode: "ECL", startDate: "2026-01-30", endDate: "2026-02-01" },
  { setCode: "TMT", startDate: "2026-03-13", endDate: "2026-03-15" },
  { setCode: "SOS", startDate: "2026-04-30", endDate: "2026-05-04" },
  { setCode: "MSH", startDate: "2026-06-30", endDate: "2026-07-06" },
  { setCode: "HOB", startDate: "2026-08-14", endDate: "2026-08-23" },
];

const COLLECTOR_WINDOW_SLACK_DAYS = 1;

function shiftDays(isoDate: string, days: number): string {
  const d = new Date(`${isoDate}T00:00:00Z`);
  d.setUTCDate(d.getUTCDate() + days);
  return d.toISOString().slice(0, 10);
}

function isCollectorBoosterWindow(setCode: string, finishedAt: string): boolean {
  const day = finishedAt.slice(0, 10);
  for (const w of COLLECTOR_BOOSTER_WINDOWS) {
    if (w.setCode !== setCode) continue;
    const start = shiftDays(w.startDate, -COLLECTOR_WINDOW_SLACK_DAYS);
    const end = shiftDays(w.endDate, COLLECTOR_WINDOW_SLACK_DAYS);
    if (start <= day && day <= end) return true;
  }
  return false;
}

export function boxesForEvent(
  setCode: string,
  wins: number,
  finishedAt: string | null,
  isTrophy: boolean,
): number {
  if (SIX_WIN_PLAY_DIRECT_SETS.has(setCode)) return isTrophy ? 2 : 0;
  if (SIX_WIN_COLLECTOR_DIRECT_SETS.has(setCode)) return isTrophy ? 1 : 0;
  if (finishedAt && isCollectorBoosterWindow(setCode, finishedAt)) return isTrophy ? 1 : 0;
  return wins >= 7 ? 2 : wins === 6 ? 1 : 0;
}

// LCQ Draft 2 cash payouts per event: a 6-win run pays $2k, a 5-win run $1k.
export function lcqDraft2Earnings(wins: number): number {
  return wins >= 6 ? 2000 : wins === 5 ? 1000 : 0;
}
