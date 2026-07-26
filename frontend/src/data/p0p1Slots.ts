import type { Card, SlotDefinition } from "../types/p0p1";
import type { SetSummary } from "../types/leaderboard";

// --- Per-set config (the setup skill appends entries) ---

export const P0P1_CONTESTS: Record<
  string,
  { previewsOpen: string; votingDeadline?: string }
> = {
  MSH: { previewsOpen: "2026-06-09", votingDeadline: "2026-06-23T15:00:00Z" },
};

// --- Featured-contest resolution (Decision 3) ---

const DAY_MS = 86_400_000;

function releaseInstant(startDate: string): number {
  const [y, m, d] = startDate.split("-").map(Number);
  // noon ET ≈ 16:00 UTC (EDT); winter releases can specify votingDeadline explicitly
  return Date.UTC(y, m - 1, d, 16, 0, 0);
}

export interface FeaturedContest {
  code: string;
  name: string;
  release: Date;
  votingDeadline: Date;
  scoringDate: Date;
  revealEnd: Date;
  status: "voting" | "reveal" | "frozen";
  next?: { code: string; name: string };
}

interface ResolvedContest {
  code: string;
  name: string;
  release: number;
  previewsOpen: number;
  votingDeadline: number;
  revealEnd: number;
}

function resolveContests(sets: SetSummary[]): ResolvedContest[] {
  return Object.keys(P0P1_CONTESTS)
    .map((code) => {
      const set = sets.find((s) => s.code === code);
      if (!set) return null;
      const config = P0P1_CONTESTS[code];
      const release = releaseInstant(set.startDate);
      const previewsOpen = new Date(config.previewsOpen + "T00:00:00Z").getTime();
      const votingDeadline = config.votingDeadline
        ? new Date(config.votingDeadline).getTime()
        : release;
      const revealEnd = release + 28 * DAY_MS;
      return { code, name: set.name, release, previewsOpen, votingDeadline, revealEnd };
    })
    .filter((c): c is ResolvedContest => c !== null)
    .sort((a, b) => b.release - a.release);
}

export function resolveFeaturedContest(
  sets: SetSummary[],
  now: number,
): FeaturedContest | null {
  const contests = resolveContests(sets);
  if (contests.length === 0) return null;

  let featured: ResolvedContest | undefined;

  // 1. Voting window wins (newest release breaks ties — array is newest-first)
  featured = contests.find((c) => now >= c.previewsOpen && now < c.votingDeadline);

  // 2. Reveal window
  if (!featured) {
    featured = contests.find((c) => now >= c.release && now < c.revealEnd);
  }

  // 3. Most recently finished
  if (!featured) {
    featured = contests.find((c) => now >= c.revealEnd);
  }

  // 4. Fallback: nearest upcoming
  if (!featured) featured = contests[contests.length - 1];

  const status: FeaturedContest["status"] =
    now < featured.votingDeadline
      ? "voting"
      : now < featured.revealEnd
        ? "reveal"
        : "frozen";

  const laterContests = contests
    .filter((c) => c.release > featured!.release)
    .sort((a, b) => a.release - b.release);

  return {
    code: featured.code,
    name: featured.name,
    release: new Date(featured.release),
    votingDeadline: new Date(featured.votingDeadline),
    scoringDate: new Date(featured.votingDeadline + 28 * DAY_MS),
    revealEnd: new Date(featured.revealEnd),
    status,
    next: laterContests[0]
      ? { code: laterContests[0].code, name: laterContests[0].name }
      : undefined,
  };
}

export function resolveContestByCode(
  sets: SetSummary[],
  code: string,
  now: number,
): FeaturedContest | null {
  const contests = resolveContests(sets);
  const match = contests.find((c) => c.code === code.toUpperCase());
  if (!match) return null;

  const status: FeaturedContest["status"] =
    now < match.votingDeadline
      ? "voting"
      : now < match.revealEnd
        ? "reveal"
        : "frozen";

  const laterContests = contests
    .filter((c) => c.release > match.release)
    .sort((a, b) => a.release - b.release);

  return {
    code: match.code,
    name: match.name,
    release: new Date(match.release),
    votingDeadline: new Date(match.votingDeadline),
    scoringDate: new Date(match.votingDeadline + 28 * DAY_MS),
    revealEnd: new Date(match.revealEnd),
    status,
    next: laterContests[0]
      ? { code: laterContests[0].code, name: laterContests[0].name }
      : undefined,
  };
}

// --- Slot definitions (set-independent) ---

function isBasicLand(card: Card) {
  return card.typeLine.startsWith("Basic Land");
}

function monoColor(color: string) {
  return (card: Card, picked: Set<string>) =>
    card.rarity === "common" &&
    card.colors.length === 1 &&
    card.colors[0] === color &&
    !picked.has(card.name);
}

export const SLOTS: SlotDefinition[] = [
  { key: "white_common", label: "White Common", filter: monoColor("W") },
  { key: "blue_common", label: "Blue Common", filter: monoColor("U") },
  { key: "black_common", label: "Black Common", filter: monoColor("B") },
  { key: "red_common", label: "Red Common", filter: monoColor("R") },
  { key: "green_common", label: "Green Common", filter: monoColor("G") },
  {
    key: "multicolor_uncommon",
    label: "Multicolor Uncommon",
    filter: (card, picked) =>
      card.rarity === "uncommon" &&
      card.colors.length >= 2 &&
      !picked.has(card.name),
  },
  {
    key: "wildcard_common",
    label: "Wildcard Common",
    filter: (card, picked) =>
      card.rarity === "common" && !isBasicLand(card) && !picked.has(card.name),
  },
  {
    key: "wildcard_uncommon",
    label: "Wildcard Uncommon",
    filter: (card, picked) =>
      card.rarity === "uncommon" && !picked.has(card.name),
  },
];
