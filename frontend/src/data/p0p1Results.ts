// Pure scoring and comparison functions for the P0P1 results phases.
// All computation happens client-side from the ratings JSON + pick stats/ballots.

import type { Card, P0P1BallotRow, P0P1PickStat, SlotKey } from "../types/p0p1";
import type { SlotDefinition } from "../types/p0p1";
import type { P0P1DevSelfPlacement } from "./p0p1DevState";

export type P0P1Phase = "voting" | "postVoting" | "midway" | "finalizing" | "final";

export interface CardRating {
  card_name: string;
  // null means 17lands had no data for this card
  gihwr: number | null;
  gih: number;
}

export interface RatingsSnapshot {
  setCode: string;
  phase: "midway" | "final" | null;
  dateRange: { start: string; end: string } | null;
  cards: CardRating[];
}

export interface TeamPick {
  slot: SlotKey;
  cardName: string;
  gihwr: number;
}

export interface TeamResult {
  picks: TeamPick[];
  score: number;
}

// Cards with fewer than this many GIH games are excluded from scoring and team-building
export const GIH_SAMPLE_FLOOR = 500;

export interface GihwrBounds {
  min: number;
  max: number;
}

export function gihwrBounds(
  pickStats: P0P1PickStat[],
  ratingsByName: Map<string, CardRating>,
): GihwrBounds {
  let min = Infinity;
  let max = -Infinity;
  for (const stat of pickStats) {
    const r = ratingsByName.get(normalizeCardName(stat.cardName));
    if (!r || r.gih < GIH_SAMPLE_FLOOR || r.gihwr === null) continue;
    if (r.gihwr < min) min = r.gihwr;
    if (r.gihwr > max) max = r.gihwr;
  }
  return { min: min === Infinity ? 0 : min, max: max === -Infinity ? 0 : max };
}

export function normalizeCardName(name: string): string {
  return name.split(" // ")[0].trim();
}

export function buildRatingsByName(snapshot: RatingsSnapshot): Map<string, CardRating> {
  return new Map(snapshot.cards.map((c) => [normalizeCardName(c.card_name), c]));
}

// Sum GIHWR for a ballot. Cards absent from ratings, below the GIH floor,
// or with null gihwr contribute 0 (missing slots already contribute 0 via omission).
export function scoreBallot(
  picks: Map<SlotKey, string>,
  ratingsByName: Map<string, CardRating>,
): number {
  let total = 0;
  for (const cardName of picks.values()) {
    const rating = ratingsByName.get(normalizeCardName(cardName));
    if (!rating || rating.gih < GIH_SAMPLE_FLOOR || rating.gihwr === null) continue;
    total += rating.gihwr * 100;
  }
  return total;
}

// Best-possible legal team: max-weight assignment of cards to slots under the
// uniqueness constraint. Uses most-constrained-first greedy, which is optimal
// for the MSH slot structure because the 5 color-common slots have disjoint
// card pools and the wildcard slots are naturally last.
export function bestPossibleTeam(
  cards: Card[],
  slots: SlotDefinition[],
  ratingsByName: Map<string, CardRating>,
): TeamResult {
  const empty = new Set<string>();

  // For each slot, collect above-floor eligible cards sorted by GIHWR desc
  const slotCandidates: Array<Array<{ name: string; gihwr: number }>> = slots.map((slot) =>
    cards
      .filter((c) => slot.filter(c, empty))
      .flatMap((c) => {
        const r = ratingsByName.get(normalizeCardName(c.name));
        if (!r || r.gih < GIH_SAMPLE_FLOOR || r.gihwr === null) return [];
        return [{ name: c.name, gihwr: r.gihwr }];
      })
      .sort((a, b) => b.gihwr - a.gihwr),
  );

  // Process most-constrained slots first (fewest eligible cards)
  const slotOrder = slots
    .map((_, i) => i)
    .sort((a, b) => slotCandidates[a].length - slotCandidates[b].length);

  const assigned = new Map<number, { name: string; gihwr: number }>();
  const usedCards = new Set<string>();

  for (const idx of slotOrder) {
    for (const card of slotCandidates[idx]) {
      if (!usedCards.has(card.name)) {
        assigned.set(idx, card);
        usedCards.add(card.name);
        break;
      }
    }
  }

  const picks: TeamPick[] = slots.map((slot, i) => {
    const card = assigned.get(i);
    return { slot: slot.key, cardName: card?.name ?? "", gihwr: card?.gihwr ?? 0 };
  });

  return { picks, score: picks.reduce((sum, p) => sum + p.gihwr * 100, 0) };
}

// Most-popular legal team: same uniqueness constraint, greedy from most-voted
// card per slot. SLOTS order (color slots before wildcards) is intentional so
// the specific slots claim their top card before wildcards pick remainders.
export function mostPopularTeam(
  pickStats: P0P1PickStat[],
  slots: SlotDefinition[],
  ratingsByName: Map<string, CardRating>,
): TeamResult {
  const statsBySlot = new Map<SlotKey, P0P1PickStat[]>();
  for (const stat of pickStats) {
    const arr = statsBySlot.get(stat.slot) ?? [];
    arr.push(stat);
    statsBySlot.set(stat.slot, arr);
  }

  const usedCards = new Set<string>();
  const picks: TeamPick[] = [];

  for (const slot of slots) {
    const candidates = (statsBySlot.get(slot.key) ?? []).sort(
      (a, b) => b.pickCount - a.pickCount,
    );
    let picked: TeamPick = { slot: slot.key, cardName: "", gihwr: 0 };
    for (const stat of candidates) {
      if (!usedCards.has(stat.cardName)) {
        usedCards.add(stat.cardName);
        const r = ratingsByName.get(normalizeCardName(stat.cardName));
        picked = {
          slot: slot.key,
          cardName: stat.cardName,
          gihwr: r && r.gih >= GIH_SAMPLE_FLOOR && r.gihwr !== null ? r.gihwr : 0,
        };
        break;
      }
    }
    picks.push(picked);
  }

  return { picks, score: picks.reduce((sum, p) => sum + p.gihwr * 100, 0) };
}

// ── Midway versus card ──────────────────────────────────────────────────────

export interface MidwayVersusSide {
  name: string;
  imageUrl: string;
  // null when below the GIH floor or absent from ratings
  gihwr: number | null;
  gih: number;
}

export interface MidwaySlotVersus {
  slotKey: SlotKey;
  slotLabel: string;
  // null when logged-out or user left this slot empty
  yours: MidwayVersusSide | null;
  crowd: MidwayVersusSide;
  best: MidwayVersusSide;
}

function makeSide(
  cardName: string,
  ratingsByName: Map<string, CardRating>,
  cardsByName: Map<string, Card>,
): MidwayVersusSide {
  const r = ratingsByName.get(normalizeCardName(cardName));
  const gihwr = r && r.gih >= GIH_SAMPLE_FLOOR && r.gihwr !== null ? r.gihwr : null;
  return {
    name: cardName,
    imageUrl: cardsByName.get(cardName)?.imageNormal ?? "",
    gihwr,
    gih: r?.gih ?? 0,
  };
}

export function buildMidwaySlotVersus(
  slots: SlotDefinition[],
  picksBySlot: Map<string, string>,
  crowdTeam: TeamResult,
  bestTeam: TeamResult,
  ratingsByName: Map<string, CardRating>,
  cardsByName: Map<string, Card>,
  includeYours: boolean,
): MidwaySlotVersus[] {
  const crowdBySlot = new Map(crowdTeam.picks.map((p) => [p.slot, p]));
  const bestBySlot = new Map(bestTeam.picks.map((p) => [p.slot, p]));

  return slots.map((slot) => {
    const yourCardName = includeYours ? picksBySlot.get(slot.key) : undefined;
    const crowdCardName = crowdBySlot.get(slot.key)?.cardName ?? "";
    const bestCardName = bestBySlot.get(slot.key)?.cardName ?? "";

    return {
      slotKey: slot.key,
      slotLabel: slot.label,
      yours: yourCardName ? makeSide(yourCardName, ratingsByName, cardsByName) : null,
      crowd: makeSide(crowdCardName, ratingsByName, cardsByName),
      best: makeSide(bestCardName, ratingsByName, cardsByName),
    };
  });
}

// Fold flat ballot rows (one per slot) into the grouped shape rankBallots expects.
export function groupBallotRows(
  rows: P0P1BallotRow[],
): Array<{ ballotId: number; name: string; avatarUrl: string | null; picks: Map<SlotKey, string> }> {
  const byId = new Map<number, { ballotId: number; name: string; avatarUrl: string | null; picks: Map<SlotKey, string> }>();
  for (const row of rows) {
    let ballot = byId.get(row.ballotId);
    if (!ballot) {
      ballot = { ballotId: row.ballotId, name: row.name, avatarUrl: row.avatarUrl, picks: new Map() };
      byId.set(row.ballotId, ballot);
    }
    ballot.picks.set(row.slot, row.cardName);
  }
  return Array.from(byId.values());
}

// Rank all ballots by summed GIHWR (descending). Partial ballots sink naturally.
// Returns the same ballots array with rank attached.
export interface RankedBallot {
  ballotId: number;
  name: string;
  avatarUrl: string | null;
  picks: Map<SlotKey, string>;
  score: number;
  rank: number;
}

export function rankBallots(
  ballots: Array<{ ballotId: number; name: string; avatarUrl: string | null; picks: Map<SlotKey, string> }>,
  ratingsByName: Map<string, CardRating>,
): RankedBallot[] {
  const scored = ballots.map((b) => ({
    ...b,
    score: scoreBallot(b.picks, ratingsByName),
    rank: 0,
  }));
  scored.sort((a, b) => b.score - a.score);
  for (let i = 0; i < scored.length; i++) {
    scored[i].rank = i + 1;
  }
  return scored;
}

// Dev-only: rewrite the viewer's ballot score so it lands at a chosen standings
// position, then re-rank. Lets the best-possible badge and medal rows be
// previewed without waiting for a real submission to earn them.
export function applyDevSelfPlacement(
  ranked: RankedBallot[],
  selfBallotId: number,
  bestTeam: TeamResult,
  placement: P0P1DevSelfPlacement,
): RankedBallot[] {
  if (placement === "auto") return ranked;

  const self = ranked.find((b) => b.ballotId === selfBallotId);
  if (!self) return ranked;
  const others = ranked.filter((b) => b.ballotId !== selfBallotId);

  let targetScore: number;
  if (placement === "best") {
    targetScore = bestTeam.score;
  } else if (placement === "first") {
    targetScore = (others[0]?.score ?? 0) + 1;
  } else if (placement === "second") {
    targetScore = others.length >= 2 ? (others[0].score + others[1].score) / 2 : (others[0]?.score ?? 0) - 1;
  } else {
    targetScore =
      others.length >= 3
        ? (others[1].score + others[2].score) / 2
        : (others[others.length - 1]?.score ?? 0) - 1;
  }

  const rescored = [...others, { ...self, score: targetScore }];
  rescored.sort((a, b) => b.score - a.score);
  return rescored.map((b, i) => ({ ...b, rank: i + 1 }));
}

// Ghost rows for the reference teams, inserted into the standings at their
// score position. The Best row is hidden when a real ballot ties its score —
// that ballot earns the badge instead (see bestAchieverIds).
const BEST_SCORE_EPSILON = 1e-6;

export interface SyntheticStanding {
  kind: "best" | "crowd";
  team: TeamResult;
}

export type StandingsEntry =
  | { kind: "ballot"; ballot: RankedBallot }
  | { kind: "synthetic"; standing: SyntheticStanding };

export interface StandingsList {
  entries: StandingsEntry[];
  bestAchieverIds: Set<number>;
}

export function buildStandingsList(
  rankedBallots: RankedBallot[],
  bestTeam: TeamResult,
  crowdTeam: TeamResult,
): StandingsList {
  const bestAchieverIds = new Set(
    rankedBallots
      .filter((b) => Math.abs(b.score - bestTeam.score) < BEST_SCORE_EPSILON)
      .map((b) => b.ballotId),
  );

  const entries: StandingsEntry[] = [];
  let crowdInserted = false;
  for (const ballot of rankedBallots) {
    if (!crowdInserted && ballot.score < crowdTeam.score) {
      entries.push({ kind: "synthetic", standing: { kind: "crowd", team: crowdTeam } });
      crowdInserted = true;
    }
    entries.push({ kind: "ballot", ballot });
  }
  if (!crowdInserted) {
    entries.push({ kind: "synthetic", standing: { kind: "crowd", team: crowdTeam } });
  }
  if (bestAchieverIds.size === 0) {
    entries.unshift({ kind: "synthetic", standing: { kind: "best", team: bestTeam } });
  }

  return { entries, bestAchieverIds };
}

// Locate the viewer's ballot by exact slot→card match (public rows carry no user id).
// The signed-in viewer's Discord id is embedded in their ballot's avatar_url
// (cdn.discordapp.com/avatars/<id>/…), so it identifies their row uniquely even
// when several players submitted the same team. Pick-matching is only a fallback
// for default-avatar accounts whose url carries no id.
export function findUserBallot(
  rankedBallots: RankedBallot[],
  picksBySlot: Map<string, string>,
  discordId?: string | null,
): RankedBallot | null {
  if (discordId) {
    const needle = `/avatars/${discordId}/`;
    for (const ballot of rankedBallots) {
      if (ballot.avatarUrl?.includes(needle)) return ballot;
    }
  }
  if (picksBySlot.size === 0) return null;
  for (const ballot of rankedBallots) {
    if (ballot.picks.size !== picksBySlot.size) continue;
    let match = true;
    for (const [slot, cardName] of picksBySlot) {
      if (ballot.picks.get(slot as SlotKey) !== cardName) { match = false; break; }
    }
    if (match) return ballot;
  }
  return null;
}

// ── Highlights feed ─────────────────────────────────────────────────────────
// Trap / Sleeper awards selected by GIHWR effect size; see
// spec/p0p1-results.md → Highlights. Sleeper popularity uses team share
// (fraction of all ballots playing the card in any slot — wildcard slots
// overlap the color slots); the Trap keeps within-slot share, its cost is slot-local.

const TRAP_SHORTFALL_FLOOR = 0.02;
const SLEEPER_TEAM_SHARE_CEIL = 0.05;

export interface HighlightVoter {
  name: string;
  avatarUrl: string | null;
}

interface HighlightBase {
  slot: SlotKey;
  slotLabel: string;
  cardName: string;
  gihwr: number;
  // within-category normalized drama, (0, 1]; the feed is ordered by this
  drama: number;
}

export interface TrapHighlight extends HighlightBase {
  kind: "trap";
  pickCount: number;
  pickShare: number;
  slotBestName: string;
  slotBestGihwr: number;
}

export interface SleeperHighlight extends HighlightBase {
  kind: "sleeper";
  teamCount: number;
  teamShare: number;
  crowdFavName: string;
  crowdFavGihwr: number;
  voters: HighlightVoter[];
}

export type Highlight = TrapHighlight | SleeperHighlight;

// Top highlights across all slots: the best Trap and Sleeper are guaranteed
// a slot (quota), the rest fill by drama normalized within category.
export function highlightsFeed(
  pickStats: P0P1PickStat[],
  ballots: P0P1BallotRow[],
  cards: Card[],
  slots: SlotDefinition[],
  ratingsByName: Map<string, CardRating>,
  feedSize = 5,
): Highlight[] {
  const rated = (name: string): number | null => {
    const r = ratingsByName.get(normalizeCardName(name));
    return r && r.gih >= GIH_SAMPLE_FLOOR && r.gihwr !== null ? r.gihwr : null;
  };

  const voterIds = new Set(ballots.map((b) => b.ballotId));
  const voterCount = voterIds.size;
  if (voterCount === 0) return [];
  const teamCount = new Map<string, number>();
  const teamVoters = new Map<string, HighlightVoter[]>();
  for (const b of ballots) {
    teamCount.set(b.cardName, (teamCount.get(b.cardName) ?? 0) + 1);
    const arr = teamVoters.get(b.cardName) ?? [];
    arr.push({ name: b.name, avatarUrl: b.avatarUrl });
    teamVoters.set(b.cardName, arr);
  }
  const teamShare = (name: string) => (teamCount.get(name) ?? 0) / voterCount;

  const statsBySlot = new Map<SlotKey, P0P1PickStat[]>();
  for (const stat of pickStats) {
    const arr = statsBySlot.get(stat.slot) ?? [];
    arr.push(stat);
    statsBySlot.set(stat.slot, arr);
  }

  const emptyPicked = new Set<string>();
  const traps: TrapHighlight[] = [];
  const sleepers: SleeperHighlight[] = [];

  for (const slot of slots) {
    const pool = cards
      .filter((c) => slot.filter(c, emptyPicked))
      .flatMap((c) => {
        const gihwr = rated(c.name);
        return gihwr === null ? [] : [{ name: c.name, gihwr }];
      });
    if (pool.length === 0) continue;
    const best = pool.reduce((a, b) => (b.gihwr > a.gihwr ? b : a));

    const stats = statsBySlot.get(slot.key) ?? [];
    const slotVotes = stats.reduce((sum, s) => sum + s.pickCount, 0);

    for (const stat of stats) {
      const gihwr = rated(stat.cardName);
      if (gihwr === null || slotVotes === 0) continue;
      if (best.gihwr - gihwr < TRAP_SHORTFALL_FLOOR) continue;
      const pickShare = stat.pickCount / slotVotes;
      traps.push({
        kind: "trap",
        slot: slot.key,
        slotLabel: slot.label,
        cardName: stat.cardName,
        gihwr,
        drama: pickShare * (best.gihwr - gihwr),
        pickCount: stat.pickCount,
        pickShare,
        slotBestName: best.name,
        slotBestGihwr: best.gihwr,
      });
    }

    const crowdFavStat = stats.reduce(
      (a, b) => (b.pickCount > (a?.pickCount ?? 0) ? b : a),
      null as P0P1PickStat | null,
    );
    const crowdFavGihwr = crowdFavStat ? rated(crowdFavStat.cardName) : null;
    if (crowdFavStat && crowdFavGihwr !== null) {
      for (const c of pool) {
        if (teamShare(c.name) > SLEEPER_TEAM_SHARE_CEIL) continue;
        if (c.gihwr <= crowdFavGihwr) continue;
        sleepers.push({
          kind: "sleeper",
          slot: slot.key,
          slotLabel: slot.label,
          cardName: c.name,
          gihwr: c.gihwr,
          drama: c.gihwr - crowdFavGihwr,
          teamCount: teamCount.get(c.name) ?? 0,
          teamShare: teamShare(c.name),
          crowdFavName: crowdFavStat.cardName,
          crowdFavGihwr,
          voters: teamVoters.get(c.name) ?? [],
        });
      }
    }
  }

  // A card qualifying in multiple slots (wildcard overlap) keeps its strongest instance
  const dedupe = <T extends Highlight>(entries: T[]): T[] => {
    const byCard = new Map<string, T>();
    for (const e of entries) {
      const cur = byCard.get(e.cardName);
      if (!cur || e.drama > cur.drama) byCard.set(e.cardName, e);
    }
    return Array.from(byCard.values()).sort((a, b) => b.drama - a.drama);
  };

  const categories: Highlight[][] = [dedupe(traps), dedupe(sleepers)];
  for (const entries of categories) {
    const max = entries[0]?.drama ?? 1;
    for (const e of entries) e.drama = e.drama / max;
  }

  const feed: Highlight[] = categories.flatMap((entries) => entries.slice(0, 1));
  const rest = categories
    .flatMap((entries) => entries.slice(1))
    .sort((a, b) => b.drama - a.drama);
  for (const e of rest) {
    if (feed.length >= feedSize) break;
    feed.push(e);
  }

  return feed.sort((a, b) => b.drama - a.drama).slice(0, feedSize);
}
