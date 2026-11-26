import { COLORS, isCreature, isLand, type PoolCard } from "./dailySealed";

export type SortKey = "mana" | "color" | "rarity";
export type PileZone = "side" | "deck";

export interface Pile {
  key: string;
  label: string | null;
  cards: number[];
}

export type Row = Pile[];

export interface Layout {
  side: Row[];
  deck: Row[];
  hidden: number[];
  basicsSlot?: BasicsSlot;
}

export interface BasicsSlot {
  row: number;
  pile: number;
}

type DropZone = PileZone | "hidden";

export interface PileTarget {
  zone: DropZone;
  row: number;
  pile: number;
  position: number;
}

export const BASICS_PILE_KEY: Record<SortKey, string> = { mana: "land", color: "C", rarity: "basic" };

const MANA_SLOTS = [0, 1, 2, 3, 4, 5, 6];
const RARITY_ORDER = ["mythic", "rare", "uncommon", "common"];
const COLOR_SLOTS = [...COLORS, "M", "C"];

const sortKeyOf = (card: PoolCard, key: SortKey): string => {
  if (key === "mana") {
    return isLand(card) ? "land" : `mv${Math.min(card.cmc, 6)}`;
  }
  if (key === "rarity") {
    return card.rarity;
  }
  if (isLand(card) || card.identity.length === 0) {
    return "C";
  }
  return card.identity.length > 1 ? "M" : card.identity;
};

export const cardsFitPileKey = (key: string, pileCards: PoolCard[]): boolean => {
  const sort = sortForKey(key);
  return sort !== null && pileCards.every((card) => sortKeyOf(card, sort) === key);
};

const sortForKey = (key: string): SortKey | null => {
  if (key === "land" || /^mv\d$/.test(key)) {
    return "mana";
  }
  if (RARITY_ORDER.includes(key)) {
    return "rarity";
  }
  return COLOR_SLOTS.includes(key) ? "color" : null;
};

const slotsFor = (key: SortKey): { key: string; label: string | null }[] => {
  if (key === "mana") {
    return [{ key: "land", label: "land" }, ...MANA_SLOTS.map((mv) => ({ key: `mv${mv}`, label: String(mv) }))];
  }
  if (key === "rarity") {
    return RARITY_ORDER.map((rarity) => ({ key: rarity, label: null }));
  }
  return COLOR_SLOTS.map((color) => ({ key: color, label: null }));
};

const byValue = (cards: PoolCard[]) => (a: number, b: number) =>
  cards[a].cmc - cards[b].cmc || cards[a].name.localeCompare(cards[b].name);

const sortRow = (cards: PoolCard[], indexes: number[], key: SortKey): Row => {
  const piles = slotsFor(key).map((slot) => ({ ...slot, cards: [] as number[] }));
  for (const index of [...indexes].sort(byValue(cards))) {
    const slot = piles.find((pile) => pile.key === sortKeyOf(cards[index], key));
    slot?.cards.push(index);
  }
  return piles.filter((pile) => pile.cards.length > 0);
};

export const sortZone = (cards: PoolCard[], indexes: number[], key: SortKey, split: boolean): Row[] => {
  if (!split) {
    return [sortRow(cards, indexes, key)];
  }
  const creatures = indexes.filter((index) => isCreature(cards[index]));
  const others = indexes.filter((index) => !isCreature(cards[index]));
  return [sortRow(cards, creatures, key), sortRow(cards, others, key)];
};

export const zoneCards = (rows: Row[]) => rows.flatMap((row) => row.flatMap((pile) => pile.cards));

const withoutCards = (layout: Layout, indexes: number[]): Layout => {
  const moving = new Set(indexes);
  const strip = (rows: Row[]) =>
    rows.map((row) => row.map((pile) => ({ ...pile, cards: pile.cards.filter((index) => !moving.has(index)) })));
  return {
    side: strip(layout.side),
    deck: strip(layout.deck),
    hidden: layout.hidden.filter((index) => !moving.has(index)),
  };
};

export const placeInSlot = (
  layout: Layout,
  cards: PoolCard[],
  indexes: number[],
  zone: PileZone,
  key: SortKey,
  split: boolean,
): Layout => {
  const next = withoutCards(layout, indexes);
  const rows = next[zone].map((row) => row.map((pile) => ({ ...pile, cards: [...pile.cards] })));
  if (rows.length === 0) {
    rows.push([]);
  }
  for (const index of indexes) {
    const card = cards[index];
    const rowIndex = split && rows.length > 1 && !isCreature(card) ? 1 : 0;
    const row = rows[rowIndex];
    const slotKey = sortKeyOf(card, key);
    let pile = row.find((candidate) => candidate.key === slotKey);
    if (!pile) {
      pile = insertSlotPile(row, slotKey, key);
    }
    pile.cards.push(index);
  }
  return { ...next, [zone]: rows };
};

const insertSlotPile = (row: Row, slotKey: string, key: SortKey): Pile => {
  const order = slotsFor(key).map((slot) => slot.key);
  const rank = order.indexOf(slotKey);
  const pile = emptySlotPile(slotKey, key);
  let at = row.length;
  for (const [position, existing] of row.entries()) {
    if (order.indexOf(existing.key) > rank) {
      at = position;
      break;
    }
  }
  row.splice(at, 0, pile);
  return pile;
};

export const placeAt = (layout: Layout, indexes: number[], target: PileTarget): Layout => {
  const next = withoutCards(layout, indexes);
  if (target.zone === "hidden") {
    const hidden = [...next.hidden];
    hidden.splice(Math.min(target.position, hidden.length), 0, ...indexes);
    return { ...next, hidden };
  }
  const rows = next[target.zone].map((row) => row.map((pile) => ({ ...pile, cards: [...pile.cards] })));
  while (rows.length <= target.row) {
    rows.push([]);
  }
  const row = rows[target.row];
  while (row.length < target.pile) {
    row.push({ key: `gap-${row.length}-${indexes[0]}`, label: null, cards: [] });
  }
  if (target.pile >= row.length) {
    row.push({ key: `free-${indexes[0]}`, label: null, cards: [] });
  }
  const pile = row[Math.min(target.pile, row.length - 1)];
  pile.cards.splice(Math.min(target.position, pile.cards.length), 0, ...indexes);
  return { ...next, [target.zone]: rows };
};

const emptySlotPile = (slotKey: string, sort: SortKey): Pile => ({
  key: slotKey,
  label: slotsFor(sort).find((slot) => slot.key === slotKey)?.label ?? null,
  cards: [],
});

export const basicsRow = (layout: Layout) => Math.min(layout.basicsSlot?.row ?? Infinity, layout.deck.length - 1);

export const withLandsPile = (layout: Layout, sort: SortKey): Layout => {
  const key = BASICS_PILE_KEY[sort];
  const rowIndex = basicsRow(layout);
  const row = layout.deck[rowIndex];
  if (!row || row.some((pile) => pile.key === key)) {
    return layout;
  }
  const leading = sort === "mana" ? 0 : row.length;
  const at = Math.min(layout.basicsSlot?.pile ?? leading, row.length);
  const pile = emptySlotPile(key, sort);
  const deck = layout.deck.map((each, index) => (index === rowIndex ? [...each.slice(0, at), pile, ...each.slice(at)] : each));
  return { ...layout, deck };
};

export const moveDeckPile = (layout: Layout, from: BasicsSlot, to: BasicsSlot): Layout => {
  const deck = layout.deck.map((row) => [...row]);
  const landing = deck[to.row];
  const pile = deck[from.row]?.[from.pile];
  if (!landing || !pile) {
    return layout;
  }
  deck[from.row].splice(from.pile, 1);
  const at = Math.min(to.pile, landing.length);
  if (from.row === to.row && at === from.pile) {
    return layout;
  }
  landing.splice(at, 0, pile);
  return { ...layout, deck, basicsSlot: { row: to.row, pile: at } };
};

export const hideCards = (layout: Layout, indexes: number[]): Layout => {
  const next = withoutCards(layout, indexes);
  return { ...next, hidden: [...next.hidden, ...indexes] };
};

export const pruneEmptyPiles = (layout: Layout): Layout => {
  const prune = (rows: Row[]) => rows.map(withoutTrailingEmpties);
  return { ...layout, side: prune(layout.side), deck: prune(layout.deck) };
};

const withoutTrailingEmpties = (row: Row): Row => {
  let end = row.length;
  while (end > 0 && row[end - 1].cards.length === 0) {
    end -= 1;
  }
  return row.slice(0, end);
};
