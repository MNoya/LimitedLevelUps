const SCRYFALL_SEARCH = "https://api.scryfall.com/cards/search";
const NO_MATCHES_STATUS = 404;
const PAGE_DELAY_MS = 500;
const ARENA_DECK_LIMIT = 250;
const COPIES_PER_CARD = 4;
export type CraftRarity = "common" | "uncommon" | "rare" | "mythic";

const RARITY_GROUPS: Record<CraftRarity, string> = {
  common: "Commons",
  uncommon: "Uncommons",
  rare: "Rares",
  mythic: "Mythics",
};

interface ScryfallPrinting {
  name: string;
  collector_number: string;
  rarity: string;
  layout: string;
  type_line?: string;
}

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

export function isCraftSetCode(setCode: string): boolean {
  return /^[A-Z0-9]{2,5}$/.test(setCode);
}

export async function fetchCraftLists(setCode: string): Promise<CraftList[]> {
  const printings = await scryfallSearch(`game:arena set:${setCode.toLowerCase()}`);
  return buildCraftLists(setCode.toUpperCase(), printings);
}

function buildCraftLists(setCode: string, printings: ScryfallPrinting[]): CraftList[] {
  const cards = firstPrintingPerName(draftable(printings));
  const lists: CraftList[] = [];
  for (const [rarity, group] of Object.entries(RARITY_GROUPS) as [CraftRarity, string][]) {
    lists.push(...splitLists(setCode, rarity, group, cards.filter((card) => card.rarity === rarity)));
  }
  return lists;
}

function draftable(printings: ScryfallPrinting[]): ScryfallPrinting[] {
  let firstBasic = Infinity;
  for (const printing of printings) {
    if (isBasicLand(printing)) {
      firstBasic = Math.min(firstBasic, collectorNumber(printing.collector_number));
    }
  }
  return printings.filter(
    (printing) => !isBasicLand(printing) && collectorNumber(printing.collector_number) < firstBasic,
  );
}

function isBasicLand(printing: ScryfallPrinting): boolean {
  const supertypes = (printing.type_line ?? "").split("—")[0];
  return supertypes.includes("Basic") && supertypes.includes("Land");
}

function firstPrintingPerName(printings: ScryfallPrinting[]): CraftCard[] {
  const first = new Map<string, CraftCard>();
  for (const printing of printings) {
    if (!(printing.rarity in RARITY_GROUPS)) {
      continue;
    }
    const card = { name: arenaName(printing), collectorNumber: printing.collector_number, rarity: printing.rarity };
    const current = first.get(card.name);
    if (!current || compareCollectorNumbers(card, current) < 0) {
      first.set(card.name, card);
    }
  }
  return [...first.values()].sort(compareCollectorNumbers);
}

function arenaName(printing: ScryfallPrinting): string {
  if (printing.layout === "split") {
    return printing.name;
  }
  return printing.name.split(" // ")[0];
}

function compareCollectorNumbers(a: CraftCard, b: CraftCard): number {
  const byNumber = collectorNumber(a.collectorNumber) - collectorNumber(b.collectorNumber);
  if (byNumber !== 0) {
    return byNumber;
  }
  return a.collectorNumber.localeCompare(b.collectorNumber);
}

function collectorNumber(value: string): number {
  const digits = value.match(/^\d+/);
  return digits ? Number(digits[0]) : Infinity;
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

async function scryfallSearch(query: string): Promise<ScryfallPrinting[]> {
  const params = new URLSearchParams({ q: query, unique: "prints", order: "set" });
  let url: string | null = `${SCRYFALL_SEARCH}?${params}`;
  const printings: ScryfallPrinting[] = [];
  while (url) {
    const response = await fetch(url, { headers: { accept: "application/json", "user-agent": "LimitedLevelUps/1.0" } });
    if (response.status === NO_MATCHES_STATUS) {
      return printings;
    }
    if (!response.ok) {
      throw new Error(`Scryfall search failed with ${response.status}`);
    }
    const page: { data: ScryfallPrinting[]; next_page?: string } = await response.json();
    printings.push(...page.data);
    url = page.next_page ?? null;
    if (url) {
      await new Promise((resolve) => setTimeout(resolve, PAGE_DELAY_MS));
    }
  }
  return printings;
}
