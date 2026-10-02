import type { SetEconomy } from "./trackerApi";

export interface MasteryTrack {
  totalPacks: number;
  levelsCap: number;
  bonuses: Array<{ atLevel: number; packs: number }>;
  mythicIcrs: Array<{ atLevel: number; cards: number }>;
}

export interface SetPackRules {
  track: MasteryTrack;
  mythicUpgrade: number;
  bonusSlot?: { rareChance: number; mythicUpgrade: number };
}

export interface PackYield {
  rares: number;
  mythics: number;
}

const SET_PACK_RULES: Record<string, SetPackRules> = {
  FRA: {
    track: {
      totalPacks: 23,
      levelsCap: 18,
      bonuses: [{ atLevel: 23, packs: 5 }],
      mythicIcrs: [{ atLevel: 4, cards: 3 }, { atLevel: 21, cards: 3 }, { atLevel: 29, cards: 4 }],
    },
    mythicUpgrade: 7,
    bonusSlot: { rareChance: 1 / 10, mythicUpgrade: 5.7 },
  },
  HOB: {
    track: { totalPacks: 26, levelsCap: 22, bonuses: [{ atLevel: 21, packs: 4 }], mythicIcrs: [] },
    mythicUpgrade: 8.1,
  },
  MSH: {
    track: {
      totalPacks: 25, levelsCap: 21, bonuses: [{ atLevel: 8, packs: 2 }, { atLevel: 24, packs: 2 }], mythicIcrs: [],
    },
    mythicUpgrade: 5.8,
  },
  SOS: {
    track: {
      totalPacks: 31,
      levelsCap: 27,
      bonuses: [{ atLevel: 3, packs: 1 }, { atLevel: 17, packs: 1 },
                { atLevel: 35, packs: 1 }, { atLevel: 47, packs: 1 }],
      mythicIcrs: [],
    },
    mythicUpgrade: 7,
  },
  TMT: {
    track: {
      totalPacks: 26, levelsCap: 22, bonuses: [{ atLevel: 6, packs: 2 }, { atLevel: 30, packs: 2 }], mythicIcrs: [],
    },
    mythicUpgrade: 8.1,
  },
  ECL: {
    track: {
      totalPacks: 23, levelsCap: 18, bonuses: [{ atLevel: 4, packs: 3 }, { atLevel: 26, packs: 2 }], mythicIcrs: [],
    },
    mythicUpgrade: 7,
  },
};

const WILDCARD_RATE = 1 / 30;
const GOLDEN_RARE_SLOTS = 5;
const GOLDEN_MYTHIC_UPGRADE = 7.1;
const GOLDEN_PACK_YIELD: PackYield = {
  rares: GOLDEN_RARE_SLOTS * (1 - 1 / GOLDEN_MYTHIC_UPGRADE),
  mythics: 1 + GOLDEN_RARE_SLOTS / GOLDEN_MYTHIC_UPGRADE,
};

const FALLBACK_AVG_RARES = 3;
const FALLBACK_AVG_PACKS = 2.5;

/** Null for a set with no researched rules, so callers show a blank instead of another set's numbers */
export function setPackRulesFor(setCode: string): SetPackRules | null {
  return SET_PACK_RULES[setCode] ?? null;
}

/** Set rares and mythics per opened pack, net of the rare-slot wildcards that are not spent on this set */
export function packYield(rules: SetPackRules): PackYield {
  const mythicShare = 1 / rules.mythicUpgrade;
  let rares = 1 - mythicShare - WILDCARD_RATE;
  let mythics = mythicShare - WILDCARD_RATE;
  if (rules.bonusSlot) {
    const { rareChance, mythicUpgrade } = rules.bonusSlot;
    rares += rareChance * (1 - 1 / mythicUpgrade);
    mythics += rareChance / mythicUpgrade;
  }
  return { rares, mythics };
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

export function projectCompletion(
  economy: SetEconomy,
  rares: { owned: number; cards: number },
  mythics: { owned: number; cards: number },
  rules: SetPackRules,
): Projection {
  const futureRewardPacks = remainingMasteryPacks(economy.masteryLevel, rules.track) + economy.rankedSeasonPacks;
  const rareTotal = rares.cards * 4;
  const mythicTotal = mythics.cards * 4;
  const projectedMythics =
    mythics.owned
    + (economy.packsOwned + futureRewardPacks) * packYield(rules).mythics
    + economy.goldenPacks * GOLDEN_PACK_YIELD.mythics
    + remainingMythicIcrs(economy.masteryLevel, rules.track);

  return {
    futureRewardPacks,
    rarePct: rareTotal ? Math.round((projectedRares(economy, rares.owned, rules) / rareTotal) * 100) : 0,
    mythicPct: mythicTotal ? Math.round((projectedMythics / mythicTotal) * 100) : 0,
  };
}

/** Extra packs to accrue for a full rare playset, past every pack already owned or promised */
export function packsToRareComplete(
  economy: SetEconomy,
  rares: { owned: number; cards: number },
  rules: SetPackRules,
): number {
  const shortfall = rares.cards * 4 - projectedRares(economy, rares.owned, rules);
  return Math.max(Math.ceil(shortfall / packYield(rules).rares), 0);
}

/** Drafts still needed for a full rare set once every owned and future pack has been opened */
export function draftsToRareComplete(
  economy: SetEconomy,
  rares: { owned: number; cards: number },
  perDraft: { avgRares: number | null; avgPacksWon: number | null },
  rules: SetPackRules,
): number {
  const avgRares = perDraft.avgRares ?? FALLBACK_AVG_RARES;
  const avgPacksWon = perDraft.avgPacksWon ?? FALLBACK_AVG_PACKS;
  const raresPerDraft = avgRares + avgPacksWon * packYield(rules).rares;
  if (raresPerDraft <= 0) {
    return 0;
  }

  const shortfall = rares.cards * 4 - projectedRares(economy, rares.owned, rules);
  return Math.max(Math.ceil(shortfall / raresPerDraft), 0);
}

function projectedRares(economy: SetEconomy, owned: number, rules: SetPackRules): number {
  const packsToOpen =
    economy.packsOwned + remainingMasteryPacks(economy.masteryLevel, rules.track) + economy.rankedSeasonPacks;
  return owned + packsToOpen * packYield(rules).rares + economy.goldenPacks * GOLDEN_PACK_YIELD.rares;
}

function remainingMythicIcrs(masteryLevel: number, track: MasteryTrack): number {
  let remaining = 0;
  for (const icr of track.mythicIcrs) {
    if (masteryLevel < icr.atLevel) {
      remaining += icr.cards;
    }
  }
  return remaining;
}
