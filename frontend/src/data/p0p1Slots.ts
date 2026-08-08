import contestsConfig from "../../../p0p1_contests.json";
import type { Card, ContestConfig, SlotDefinition } from "../types/p0p1";

// The same file bot/scripts writes and a future bot task reads, alongside scoring_buckets.json
export const P0P1_CONTESTS: Record<string, ContestConfig> = contestsConfig;

// --- Featured-contest resolution (Decision 3) ---

const DAY_MS = 86_400_000;
const SCORING_WINDOW_MS = 28 * DAY_MS;

export interface FeaturedContest {
  code: string;
  name: string;
  release: Date;
  votingDeadline: Date;
  scoringDate: Date;
  status: "pre" | "voting" | "reveal" | "frozen";
  next?: { code: string; name: string; previewsOpen: Date };
}

interface ResolvedContest {
  code: string;
  name: string;
  release: number;
  previewsOpen: number;
  votingDeadline: number;
  scoringDate: number;
}

function resolveContests(): ResolvedContest[] {
  return Object.entries(P0P1_CONTESTS)
    .map(([code, config]) => {
      const release = new Date(config.release).getTime();
      const scoringDate = config.scoringDate
        ? new Date(config.scoringDate).getTime()
        : release + SCORING_WINDOW_MS;
      return {
        code,
        name: config.name,
        release,
        previewsOpen: new Date(config.previewsOpen).getTime(),
        votingDeadline: config.votingDeadline ? new Date(config.votingDeadline).getTime() : release,
        scoringDate,
      };
    })
    .sort((a, b) => b.release - a.release);
}

export function resolveFeaturedContest(now: number): FeaturedContest | null {
  const contests = resolveContests();
  if (contests.length === 0) return null;

  // 1. Voting window wins (newest release breaks ties — array is newest-first)
  let featured = contests.find((c) => now >= c.previewsOpen && now < c.votingDeadline);

  // 2. Results window, which opens the instant voting closes. Anchoring it to `release` instead
  // would un-feature a contest for the whole gap between an early deadline and the Arena drop,
  // sending fresh voters back to the previous set's archive.
  if (!featured) {
    featured = contests.find((c) => now >= c.votingDeadline && now < c.scoringDate);
  }

  // 3. Most recently finished
  if (!featured) {
    featured = contests.find((c) => now >= c.scoringDate);
  }

  // 4. Nothing has opened yet: the earliest contest, which describeContest reports as "pre"
  if (!featured) featured = contests[contests.length - 1];

  return describeContest(featured, contests, now);
}

/** A contest addressed by its own URL is the historic viewer, so it carries no `next` — a frozen
 * archive page should not advertise a later contest the way the featured page does. */
export function resolveContestByCode(code: string, now: number): FeaturedContest | null {
  const contests = resolveContests();
  const match = contests.find((c) => c.code === code.toUpperCase());
  if (!match) return null;
  return describeContest(match, [], now);
}

function describeContest(
  contest: ResolvedContest,
  contests: ResolvedContest[],
  now: number,
): FeaturedContest {
  let status: FeaturedContest["status"] = "frozen";
  if (now < contest.previewsOpen) {
    status = "pre";
  } else if (now < contest.votingDeadline) {
    status = "voting";
  } else if (now < contest.scoringDate) {
    status = "reveal";
  }

  const laterContests = contests
    .filter((c) => c.release > contest.release)
    .sort((a, b) => a.release - b.release);
  const next = laterContests[0];

  return {
    code: contest.code,
    name: contest.name,
    release: new Date(contest.release),
    votingDeadline: new Date(contest.votingDeadline),
    scoringDate: new Date(contest.scoringDate),
    status,
    next: next
      ? { code: next.code, name: next.name, previewsOpen: new Date(next.previewsOpen) }
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
