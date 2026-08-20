import type { PodLeaderboardRow, PodSeasonResultRow, SetSummary } from "../types/leaderboard";
import { POD_TROPHY_WINS, podPoints } from "./scoring";
import { isCubeCode } from "./utils";

// A pod season is a set's Arena rotation window, holding every pod played inside it whatever it drafted
const POD_SEASON_START = "2026-04-21";

export function podSeasons(sets: SetSummary[] | undefined): SetSummary[] {
  if (!sets) return [];
  return sets
    .filter((s) => s.startDate >= POD_SEASON_START && s.endDate)
    .slice()
    .sort((a, b) => (a.startDate < b.startDate ? 1 : a.startDate > b.startDate ? -1 : 0));
}

export function seasonForDate(sets: SetSummary[] | undefined, date: string): SetSummary | undefined {
  for (const season of podSeasons(sets)) {
    if (date >= season.startDate && date <= season.endDate) {
      return season;
    }
  }
  return undefined;
}

export function currentSeason(sets: SetSummary[] | undefined): SetSummary | undefined {
  return seasonForDate(sets, todayIso());
}

export function inSeasonWindow(season: SetSummary, date: string): boolean {
  return date >= season.startDate && date <= season.endDate;
}

// Trophy and finish counts mirror public_pod_scoring, so the points match the board's own term
export function aggregatePodStandings(
  results: PodSeasonResultRow[] | undefined,
): PodLeaderboardRow[] | undefined {
  if (!results) return undefined;
  const byPlayer = new Map<string, PodLeaderboardRow>();
  const finishes = new Map<string, { twoWins: number; oneWins: number }>();
  for (const r of results) {
    let row = byPlayer.get(r.slug);
    if (!row) {
      row = {
        setCode: r.setCode,
        rank: 0,
        slug: r.slug,
        displayName: r.displayName,
        avatarUrl: r.avatarUrl,
        events: 0,
        wins: 0,
        losses: 0,
        trophies: 0,
        points: 0,
        lastFinishedAt: null,
      };
      byPlayer.set(r.slug, row);
      finishes.set(r.slug, { twoWins: 0, oneWins: 0 });
    }
    const finish = finishes.get(r.slug)!;
    row.events += 1;
    row.wins += r.wins;
    row.losses += r.losses;
    if (r.wins >= POD_TROPHY_WINS) {
      row.trophies += 1;
    } else if (r.wins === 2) {
      finish.twoWins += 1;
    } else if (r.wins === 1) {
      finish.oneWins += 1;
    }
    if (!row.lastFinishedAt || r.eventTime > row.lastFinishedAt) {
      row.lastFinishedAt = r.eventTime;
    }
  }
  for (const row of byPlayer.values()) {
    const finish = finishes.get(row.slug)!;
    row.points = podPoints(row.trophies, finish.twoWins, finish.oneWins);
  }
  return Array.from(byPlayer.values())
    .sort((a, b) => {
      if ((b.points ?? 0) !== (a.points ?? 0)) return (b.points ?? 0) - (a.points ?? 0);
      if (b.trophies !== a.trophies) return b.trophies - a.trophies;
      return b.wins - a.wins;
    })
    .map((r, i) => ({ ...r, rank: i + 1 }));
}

export type PodFormatBucket = "set" | "flashback" | "cube" | "mock";

interface BucketableEvent {
  setCode: string;
  formatLabel: string | null;
  kind: string;
}

export function bucketOf(event: BucketableEvent, seasonCode: string): PodFormatBucket {
  if (event.kind === "mock") return "mock";
  if (event.formatLabel || isCubeCode(event.setCode)) return "cube";
  return event.setCode === seasonCode ? "set" : "flashback";
}

// Buckets each event against the season it was played in, for a board spanning every season
export function lifetimeBucketOf(
  event: BucketableEvent & { eventDate: string },
  sets: SetSummary[] | undefined,
): PodFormatBucket {
  return bucketOf(event, seasonForDate(sets, event.eventDate)?.code ?? "");
}

// The seasons a board actually played in, newest first, for a board sliced by season
export function seasonsPlayed(
  events: { eventDate: string; kind: string }[] | undefined,
  sets: SetSummary[] | undefined,
): { season: SetSummary; count: number }[] {
  const counts = new Map<string, number>();
  for (const e of events ?? []) {
    if (e.kind === "mock") continue;
    const season = seasonForDate(sets, e.eventDate);
    if (season) counts.set(season.code, (counts.get(season.code) ?? 0) + 1);
  }
  const played: { season: SetSummary; count: number }[] = [];
  for (const season of podSeasons(sets)) {
    const count = counts.get(season.code);
    if (count) played.push({ season, count });
  }
  return played;
}

// The format buckets a board offers, in a fixed order, dropping the ones it never played
export function podFormatBuckets<E>(
  events: E[] | undefined,
  bucketFor: (event: E) => PodFormatBucket,
): { key: PodFormatBucket; count: number }[] {
  const counts = new Map<PodFormatBucket, number>();
  for (const e of events ?? []) {
    const bucket = bucketFor(e);
    counts.set(bucket, (counts.get(bucket) ?? 0) + 1);
  }
  const order: PodFormatBucket[] = ["set", "flashback", "cube", "mock"];
  return order
    .filter((key) => (counts.get(key) ?? 0) > 0)
    .map((key) => ({ key, count: counts.get(key)! }));
}

function todayIso(): string {
  const now = new Date();
  const month = String(now.getMonth() + 1).padStart(2, "0");
  const day = String(now.getDate()).padStart(2, "0");
  return `${now.getFullYear()}-${month}-${day}`;
}
