// Completion projections carried over verbatim from the tracker spreadsheet's top block, so the
// numbers here match the tab they replace. Every constant below is the sheet's, not a new estimate.
//
//   Rare after   = (owned + (packs + futureRewards) * 0.77 + max(golden * 4.167, 0)) / (rares * 4)
//   Mythic after = (owned + (packs + futureRewards) * (1/5.8 - 1/15)
//                   + golden * 0.63) / (mythics * 4)
//   Drafts to rare-complete, cell H5 = MAX(ROUNDUP(
//                   ((rares*4) - owned - (packs + futureRewards)*0.8 - golden*5*7/8)
//                   / (avgRares + avgPacksWon*0.8)), 0)
//
// H5 carries its own pack constants, 0.8 and 5*7/8, which disagree with the 0.77 and 4.167 the
// percentage above uses. Both are reproduced as the sheet has them rather than reconciled.

import type { SetEconomy } from "./trackerApi";

const RARES_PER_PACK = 0.77;
const RARES_PER_GOLDEN_PACK = 4.167;
const MYTHICS_PER_PACK = 1 / 5.8 - 1 / 15;
const MYTHICS_PER_GOLDEN_PACK = 0.63;

const H5_RARES_PER_PACK = 0.8;
const H5_RARES_PER_GOLDEN_PACK = (5 * 7) / 8;
const H5_FALLBACK_AVG_RARES = 3;
const H5_FALLBACK_AVG_PACKS = 2.5;

export interface MasteryTrack {
  totalPacks: number;
  levelsCap: number;
  bonuses: Array<{ atLevel: number; packs: number }>;
}

// Read off each set tab's H9, except HOB, whose tab holds a miscopied track
const MASTERY_TRACKS: Record<string, MasteryTrack> = {
  HOB: { totalPacks: 26, levelsCap: 22, bonuses: [{ atLevel: 21, packs: 4 }] },
  MSH: { totalPacks: 25, levelsCap: 21, bonuses: [{ atLevel: 8, packs: 2 }, { atLevel: 24, packs: 2 }] },
  SOS: {
    totalPacks: 31,
    levelsCap: 27,
    bonuses: [{ atLevel: 3, packs: 1 }, { atLevel: 17, packs: 1 },
              { atLevel: 35, packs: 1 }, { atLevel: 47, packs: 1 }],
  },
  TMT: { totalPacks: 26, levelsCap: 22, bonuses: [{ atLevel: 6, packs: 2 }, { atLevel: 30, packs: 2 }] },
  ECL: { totalPacks: 23, levelsCap: 18, bonuses: [{ atLevel: 4, packs: 3 }, { atLevel: 26, packs: 2 }] },
};

export function masteryTrackFor(setCode: string): MasteryTrack {
  return MASTERY_TRACKS[setCode] ?? MASTERY_TRACKS.HOB;
}

/** Packs still to come on a set's mastery track at the level given */
export function remainingMasteryPacks(masteryLevel: number, track: MasteryTrack): number {
  const level = Math.max(0, masteryLevel);
  let earned = Math.min(Math.trunc(level / 2), track.levelsCap);
  for (const bonus of track.bonuses) {
    if (level >= bonus.atLevel) {
      earned += bonus.packs;
    }
  }
  return Math.max(0, track.totalPacks - earned);
}

export interface Projection {
  futureRewardPacks: number;
  rarePct: number;
  mythicPct: number;
}

/** Drafts still needed for a full rare set once every owned and future pack has been opened */
export function draftsToRareComplete(
  economy: SetEconomy,
  rares: { owned: number; cards: number },
  perDraft: { avgRares: number | null; avgPacksWon: number | null },
  track: MasteryTrack,
): number {
  const futureRewardPacks = remainingMasteryPacks(economy.masteryLevel, track) + economy.rankedSeasonPacks;
  const avgRares = perDraft.avgRares ?? H5_FALLBACK_AVG_RARES;
  const avgPacksWon = perDraft.avgPacksWon ?? H5_FALLBACK_AVG_PACKS;

  const shortfall =
    rares.cards * 4
    - rares.owned
    - (economy.packsOwned + futureRewardPacks) * H5_RARES_PER_PACK
    - economy.goldenPacks * H5_RARES_PER_GOLDEN_PACK;
  const raresPerDraft = avgRares + avgPacksWon * H5_RARES_PER_PACK;
  if (raresPerDraft <= 0) {
    return 0;
  }

  return Math.max(Math.ceil(shortfall / raresPerDraft), 0);
}

/** Extra packs to accrue for a full rare playset, past every pack already owned or promised */
export function packsToRareComplete(
  economy: SetEconomy,
  rares: { owned: number; cards: number },
  track: MasteryTrack,
): number {
  const futureRewardPacks = remainingMasteryPacks(economy.masteryLevel, track) + economy.rankedSeasonPacks;
  const packs = economy.packsOwned + futureRewardPacks;
  const projected =
    rares.owned + packs * RARES_PER_PACK + Math.max(economy.goldenPacks * RARES_PER_GOLDEN_PACK, 0);
  const shortfall = rares.cards * 4 - projected;
  return Math.max(Math.ceil(shortfall / RARES_PER_PACK), 0);
}

export function projectCompletion(
  economy: SetEconomy,
  rares: { owned: number; cards: number },
  mythics: { owned: number; cards: number },
  track: MasteryTrack,
): Projection {
  const futureRewardPacks = remainingMasteryPacks(economy.masteryLevel, track) + economy.rankedSeasonPacks;
  const packs = economy.packsOwned + futureRewardPacks;

  const rareTotal = rares.cards * 4;
  const mythicTotal = mythics.cards * 4;
  const projectedRares =
    rares.owned + packs * RARES_PER_PACK + Math.max(economy.goldenPacks * RARES_PER_GOLDEN_PACK, 0);
  const projectedMythics =
    mythics.owned + packs * MYTHICS_PER_PACK + economy.goldenPacks * MYTHICS_PER_GOLDEN_PACK;

  return {
    futureRewardPacks,
    rarePct: rareTotal ? Math.round((projectedRares / rareTotal) * 100) : 0,
    mythicPct: mythicTotal ? Math.round((projectedMythics / mythicTotal) * 100) : 0,
  };
}
