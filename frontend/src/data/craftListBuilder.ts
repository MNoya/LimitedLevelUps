import { compareCollectorNumbers, type SetCard, type SetCardPool } from "./setCardPool";

const ARENA_DECK_LIMIT = 250;
export type CraftCopies = 1 | 4;
export type CraftRarity = "common" | "uncommon" | "rare" | "mythic";

const RARITY_GROUPS: Record<CraftRarity, string> = {
  common: "Commons",
  uncommon: "Uncommons",
  rare: "Rares",
  mythic: "Mythics",
};

interface CraftCard {
  name: string;
  collectorNumber: string;
  rarity: CraftRarity;
}

export interface CraftList {
  setCode: string;
  rarity: CraftRarity;
  group: string;
  part: number;
  parts: number;
  copies: CraftCopies;
  cards: CraftCard[];
}

export function craftListLabel(list: CraftList): string {
  return `${list.setCode} ${craftListTitle(list)}`;
}

export function craftListTitle(list: CraftList): string {
  const suffix = list.parts > 1 ? ` ${list.part}` : "";
  return `${list.group}${suffix}`;
}

export function craftListWildcards(list: CraftList): Array<{ rarity: CraftRarity; count: number }> {
  const wildcards: Array<{ rarity: CraftRarity; count: number }> = [];
  for (const rarity of Object.keys(RARITY_GROUPS) as CraftRarity[]) {
    const cards = list.cards.filter((card) => card.rarity === rarity);
    if (cards.length > 0) {
      wildcards.push({ rarity, count: cards.length * list.copies });
    }
  }
  return wildcards;
}

export function craftListText(list: CraftList): string {
  const lines = ["About", `Name ${craftListLabel(list)}`, "", "Deck"];
  for (const card of list.cards) {
    lines.push(`${list.copies} ${card.name} (${list.setCode}) ${card.collectorNumber}`);
  }
  return lines.join("\n");
}

export function buildCraftLists(setCode: string, pool: SetCardPool, copies: CraftCopies): CraftList[] {
  const cards = toCraftCards(pool.cards);
  const lists: CraftList[] = [];
  for (const [rarity, group] of Object.entries(RARITY_GROUPS) as [CraftRarity, string][]) {
    const rarityCards = cards.filter((card) => card.rarity === rarity);
    lists.push(...splitLists({ setCode, rarity, group, copies }, rarityCards));
  }
  if (pool.bonusSheet) {
    const bonusCards = toCraftCards(pool.bonusSheet.cards);
    const { setCode: bonusCode, label } = pool.bonusSheet;
    const bonusHeader = { setCode: bonusCode, rarity: highestRarity(bonusCards), group: label, copies };
    lists.push(...splitLists(bonusHeader, bonusCards));
  }
  return lists;
}

function highestRarity(cards: CraftCard[]): CraftRarity {
  const rarities = Object.keys(RARITY_GROUPS) as CraftRarity[];
  let highest = 0;
  for (const card of cards) {
    highest = Math.max(highest, rarities.indexOf(card.rarity));
  }
  return rarities[highest];
}

function toCraftCards(pool: SetCard[]): CraftCard[] {
  const cards: CraftCard[] = [];
  for (const card of [...pool].sort(compareCollectorNumbers)) {
    if (card.rarity in RARITY_GROUPS) {
      const rarity = card.rarity as CraftRarity;
      cards.push({ name: arenaName(card), collectorNumber: card.collectorNumber, rarity });
    }
  }
  return cards;
}

function arenaName(card: SetCard): string {
  if (card.layout === "split") {
    return card.name;
  }
  return card.name.split(" // ")[0];
}

type CraftListHeader = Pick<CraftList, "setCode" | "rarity" | "group" | "copies">;

function splitLists(header: CraftListHeader, cards: CraftCard[]): CraftList[] {
  if (cards.length === 0) {
    return [];
  }
  const perDeck = Math.floor(ARENA_DECK_LIMIT / header.copies);
  const parts = Math.ceil(cards.length / perDeck);
  const size = Math.floor(cards.length / parts);
  const extra = cards.length % parts;
  const lists: CraftList[] = [];
  let start = 0;
  for (let index = 0; index < parts; index++) {
    const end = start + size + (index < extra ? 1 : 0);
    lists.push({ ...header, part: index + 1, parts, cards: cards.slice(start, end) });
    start = end;
  }
  return lists;
}
