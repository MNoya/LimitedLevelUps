import { compareCollectorNumbers, type SetCard } from "./setCardPool";

const ARENA_DECK_LIMIT = 250;
const COPIES_PER_CARD = 4;
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
  rarity: string;
}

export interface CraftList {
  setCode: string;
  rarity: CraftRarity;
  group: string;
  part: number;
  parts: number;
  cards: CraftCard[];
}

export function craftListLabel(list: CraftList): string {
  return `${list.setCode} ${craftListTitle(list)}`;
}

export function craftListTitle(list: CraftList): string {
  const suffix = list.parts > 1 ? ` ${list.part}` : "";
  return `${list.group}${suffix}`;
}

export function craftListWildcards(list: CraftList): number {
  return list.cards.length * COPIES_PER_CARD;
}

export function craftListText(list: CraftList): string {
  const lines = ["About", `Name ${craftListLabel(list)}`, "", "Deck"];
  for (const card of list.cards) {
    lines.push(`${COPIES_PER_CARD} ${card.name} (${list.setCode}) ${card.collectorNumber}`);
  }
  return lines.join("\n");
}

export function buildCraftLists(setCode: string, pool: SetCard[]): CraftList[] {
  const cards = toCraftCards(pool);
  const lists: CraftList[] = [];
  for (const [rarity, group] of Object.entries(RARITY_GROUPS) as [CraftRarity, string][]) {
    lists.push(...splitLists(setCode, rarity, group, cards.filter((card) => card.rarity === rarity)));
  }
  return lists;
}

function toCraftCards(pool: SetCard[]): CraftCard[] {
  const cards: CraftCard[] = [];
  for (const card of [...pool].sort(compareCollectorNumbers)) {
    if (card.rarity in RARITY_GROUPS) {
      cards.push({ name: arenaName(card), collectorNumber: card.collectorNumber, rarity: card.rarity });
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

function splitLists(setCode: string, rarity: CraftRarity, group: string, cards: CraftCard[]): CraftList[] {
  if (cards.length === 0) {
    return [];
  }
  const perDeck = Math.floor(ARENA_DECK_LIMIT / COPIES_PER_CARD);
  const parts = Math.ceil(cards.length / perDeck);
  const size = Math.floor(cards.length / parts);
  const extra = cards.length % parts;
  const lists: CraftList[] = [];
  let start = 0;
  for (let index = 0; index < parts; index++) {
    const end = start + size + (index < extra ? 1 : 0);
    lists.push({ setCode, rarity, group, part: index + 1, parts, cards: cards.slice(start, end) });
    start = end;
  }
  return lists;
}
