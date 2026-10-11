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
const FALLBACK_AVG_MYTHICS = 0.5;
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
  rarePct: number;
  mythicPct: number;
  mythicMath: MythicCompletionMath;
}

export interface MythicCompletionMath {
  owned: number;
  playsetTotal: number;
  packsToOpen: number;
  mythicsPerPack: number;
  goldenPacks: number;
  mythicsPerGoldenPack: number;
  remainingIcrs: number;
  projected: number;
}

export function projectCompletion(
  economy: SetEconomy,
  rares: { owned: number; cards: number },
  mythics: { owned: number; cards: number },
  rules: SetPackRules,
): Projection {
  const rareTotal = rares.cards * 4;
  const mythicMath = mythicCompletionMath(economy, mythics, rules);

  return {
    rarePct: rareTotal ? Math.round((projectedRares(economy, rares.owned, rules) / rareTotal) * 100) : 0,
    mythicPct: mythicMath.playsetTotal ? Math.round((mythicMath.projected / mythicMath.playsetTotal) * 100) : 0,
    mythicMath,
  };
}

export interface RareCompletionMath {
  owned: number;
  playsetTotal: number;
  packsToOpen: number;
  raresPerPack: number;
  goldenPacks: number;
  raresPerGoldenPack: number;
  projected: number;
  packsNeeded: number;
}

/** Extra packs to accrue for a full rare playset, past every pack already owned or promised */
export function packsToRareComplete(
  economy: SetEconomy,
  rares: { owned: number; cards: number },
  rules: SetPackRules,
): RareCompletionMath {
  const raresPerPack = packYield(rules).rares;
  const playsetTotal = rares.cards * 4;
  const projected = projectedRares(economy, rares.owned, rules);
  const shortfall = Math.max(playsetTotal - projected, 0);
  return {
    owned: rares.owned,
    playsetTotal,
    packsToOpen: packsToOpen(economy, rules),
    raresPerPack,
    goldenPacks: economy.goldenPacks,
    raresPerGoldenPack: GOLDEN_PACK_YIELD.rares,
    projected,
    packsNeeded: Math.ceil(shortfall / raresPerPack),
  };
}

export interface DraftRates {
  avgRares: number | null;
  avgMythics: number | null;
  avgPacksWon: number | null;
}

/** Drafts still needed for a full rare set once every owned and future pack has been opened */
export function draftsToRareComplete(
  economy: SetEconomy,
  rares: { owned: number; cards: number },
  perDraft: DraftRates,
  rules: SetPackRules,
): number {
  const shortfall = rares.cards * 4 - projectedRares(economy, rares.owned, rules);
  const raresPerDraft = draftYield(perDraft.avgRares ?? FALLBACK_AVG_RARES, perDraft, packYield(rules).rares);
  return unitsToCover(shortfall, raresPerDraft);
}

/** Drafts still needed for a full mythic set once every owned and future pack and ICR has been claimed */
export function draftsToMythicComplete(
  economy: SetEconomy,
  mythics: { owned: number; cards: number },
  perDraft: DraftRates,
  rules: SetPackRules,
): number {
  const math = mythicCompletionMath(economy, mythics, rules);
  const mythicsPerDraft = draftYield(perDraft.avgMythics ?? FALLBACK_AVG_MYTHICS, perDraft, packYield(rules).mythics);
  return unitsToCover(math.playsetTotal - math.projected, mythicsPerDraft);
}

/** Mythics still missing once every owned and future pack and ICR has been claimed */
export function mythicsToComplete(
  economy: SetEconomy,
  mythics: { owned: number; cards: number },
  rules: SetPackRules,
): number {
  const math = mythicCompletionMath(economy, mythics, rules);
  return Math.max(Math.ceil(math.playsetTotal - math.projected), 0);
}

function draftYield(pickedPerDraft: number, perDraft: DraftRates, perPack: number): number {
  return pickedPerDraft + (perDraft.avgPacksWon ?? FALLBACK_AVG_PACKS) * perPack;
}

function unitsToCover(shortfall: number, perUnit: number): number {
  if (perUnit <= 0) {
    return 0;
  }
  return Math.max(Math.ceil(shortfall / perUnit), 0);
}

function projectedRares(economy: SetEconomy, owned: number, rules: SetPackRules): number {
  return owned + packsToOpen(economy, rules) * packYield(rules).rares + economy.goldenPacks * GOLDEN_PACK_YIELD.rares;
}

function packsToOpen(economy: SetEconomy, rules: SetPackRules): number {
  return economy.packsOwned + remainingMasteryPacks(economy.masteryLevel, rules.track) + economy.rankedSeasonPacks;
}

function mythicCompletionMath(
  economy: SetEconomy,
  mythics: { owned: number; cards: number },
  rules: SetPackRules,
): MythicCompletionMath {
  const toOpen = packsToOpen(economy, rules);
  const mythicsPerPack = packYield(rules).mythics;
  const remainingIcrs = remainingMythicIcrs(economy.masteryLevel, rules.track);
  return {
    owned: mythics.owned,
    playsetTotal: mythics.cards * 4,
    packsToOpen: toOpen,
    mythicsPerPack,
    goldenPacks: economy.goldenPacks,
    mythicsPerGoldenPack: GOLDEN_PACK_YIELD.mythics,
    remainingIcrs,
    projected:
      mythics.owned + toOpen * mythicsPerPack + economy.goldenPacks * GOLDEN_PACK_YIELD.mythics + remainingIcrs,
  };
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
