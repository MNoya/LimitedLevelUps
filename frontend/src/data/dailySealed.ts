import { TYPE_GROUPS } from "./tierList";
import { DAILY_TURNOVER_HOUR_ET } from "../lib/daily-turnover";

export type Color = "W" | "U" | "B" | "R" | "G";
export type Basics = Record<Color, number>;
export type Zone = "deck" | "side" | "hidden";

export interface PoolCard {
  name: string;
  cmc: number;
  identity: string;
  cost: string;
  image: string;
  back: string | null;
  rarity: string;
  types: string[];
}

export interface DailySealedPool {
  day: string;
  setCode: string;
  poolNumber: number;
  format: string;
  cards: PoolCard[];
  originalMain: number[];
  originalBasics: Basics | null;
  colors: string | null;
  wins: number;
  losses: number;
  buildCount: number;
}

export interface DailySealedBuild {
  buildKey: string;
  main: number[];
  basics: Basics;
  colors: string;
}

export interface PoolEntry {
  index: number;
  card: PoolCard;
  copies?: number;
}

export interface CardGroup {
  key: string;
  label: string;
  entries: PoolEntry[];
}

interface PairUsage {
  colors: string;
  decks: number;
  splashed: number;
}

export interface CardUsage {
  card: PoolCard;
  indexes: number[];
  decks: number;
  share: number;
  mostCopies: number;
  yours: "deck" | "out" | null;
}

export interface Breakdown {
  builds: number;
  pairs: PairUsage[];
  cards: CardUsage[];
}

export const COLORS: Color[] = ["W", "U", "B", "R", "G"];
export const BASIC_NAMES: Record<Color, string> = {
  W: "Plains",
  U: "Island",
  B: "Swamp",
  R: "Mountain",
  G: "Forest",
};

const BASIC_SLOT = 100;

export const isBasicIndex = (index: number) => index < 0;

export const basicColorOf = (index: number): Color => COLORS[Math.floor((-1 - index) / BASIC_SLOT)];

export const basicEntries = (basics: Basics, images: Map<string, string>, setCode: string): PoolEntry[] =>
  COLORS.filter((color) => basics[color] > 0).map((color) => ({
    index: -1 - COLORS.indexOf(color) * BASIC_SLOT,
    copies: basics[color],
    card: {
      name: BASIC_NAMES[color],
      cmc: 0,
      identity: "",
      cost: "",
      image: images.get(`${setCode.toLowerCase()}|${BASIC_NAMES[color].toLowerCase()}`) ?? "",
      back: null,
      rarity: "common",
      types: [`Basic Land - ${BASIC_NAMES[color]}`],
    },
  }));

export const entryCount = (entries: PoolEntry[]) => entries.reduce((total, entry) => total + (entry.copies ?? 1), 0);
export const DAILY_SEALED_BLURB = "Build from the same Sealed pool and see what the community picked each day";
export const DECK_SIZE = 40;
export const LAND_TARGET = 17;
export const EMPTY_BASICS: Basics = { W: 0, U: 0, B: 0, R: 0, G: 0 };

const SPLASH_MAX_CARDS = 2;
const MANA_VALUE_COLUMNS = [1, 2, 3, 4, 5, 6];

export const typeLine = (card: PoolCard) => card.types.join(" ");
export const isLand = (card: PoolCard) => typeLine(card).includes("Land");
export const isCreature = (card: PoolCard) => typeLine(card).includes("Creature");
export const basicCount = (basics: Basics) => COLORS.reduce((sum, color) => sum + basics[color], 0);

export const servingDay = (now: Date = new Date()): string => {
  const eastern = new Date(now.toLocaleString("en-US", { timeZone: "America/New_York" }));
  eastern.setHours(eastern.getHours() - DAILY_TURNOVER_HOUR_ET);
  const month = String(eastern.getMonth() + 1).padStart(2, "0");
  const day = String(eastern.getDate()).padStart(2, "0");
  return `${eastern.getFullYear()}-${month}-${day}`;
};

export const nextTurnover = (now: Date = new Date()): Date => {
  const [year, month, day] = servingDay(now).split("-").map(Number);
  const easternNoonUtc = Date.UTC(year, month - 1, day + 1, 12);
  const offsetHours = easternOffsetHours(new Date(easternNoonUtc));
  return new Date(Date.UTC(year, month - 1, day + 1, DAILY_TURNOVER_HOUR_ET + offsetHours));
};

const easternOffsetHours = (at: Date): number => {
  const eastern = new Date(at.toLocaleString("en-US", { timeZone: "America/New_York" }));
  const utc = new Date(at.toLocaleString("en-US", { timeZone: "UTC" }));
  return Math.round((utc.getTime() - eastern.getTime()) / 3_600_000);
};

export const colorPips = (card: PoolCard, color: Color): number =>
  (card.cost.match(new RegExp(`\\{[^}]*${color}[^}]*\\}`, "g")) ?? []).length;

export const deckColors = (cards: PoolCard[]): string => {
  const cardsPerColor = new Map<Color, number>();
  for (const card of cards) {
    if (isLand(card)) {
      continue;
    }
    for (const color of COLORS) {
      if (colorPips(card, color) > 0) {
        cardsPerColor.set(color, (cardsPerColor.get(color) ?? 0) + 1);
      }
    }
  }
  let main = "";
  let splash = "";
  for (const color of COLORS) {
    const count = cardsPerColor.get(color) ?? 0;
    if (count > SPLASH_MAX_CARDS) {
      main += color;
    } else if (count > 0) {
      splash += color.toLowerCase();
    }
  }
  return main + splash;
};

export const mainColors = (colors: string): string => {
  const present = new Set(colors.split("").filter((letter) => letter === letter.toUpperCase()));
  const ordered = COLORS.filter((color) => present.has(color)).join("");
  return ordered || "C";
};

export const fillLands = (cards: PoolCard[], basics: Basics): Basics => {
  const open = LAND_TARGET - cards.filter(isLand).length;
  const pips: Record<Color, number> = { ...EMPTY_BASICS };
  let totalPips = 0;
  for (const card of cards) {
    if (isLand(card)) {
      continue;
    }
    for (const color of COLORS) {
      const count = colorPips(card, color);
      pips[color] += count;
      totalPips += count;
    }
  }
  if (totalPips === 0) {
    return basics;
  }
  const next = { ...EMPTY_BASICS };
  if (open <= 0) {
    return next;
  }
  const shares = COLORS.map((color) => ({ color, exact: (open * pips[color]) / totalPips }));
  let placed = 0;
  for (const share of shares) {
    const whole = Math.floor(share.exact);
    next[share.color] += whole;
    placed += whole;
  }
  const byRemainder = [...shares].sort((a, b) => (b.exact % 1) - (a.exact % 1));
  for (let i = 0; i < open - placed; i += 1) {
    next[byRemainder[i].color] += 1;
  }
  return next;
};

export const arenaExport = (deck: PoolCard[], sideboard: PoolCard[], basics: Basics): string => {
  const lines = ["Deck", ...countedLines(deck)];
  for (const color of COLORS) {
    if (basics[color] > 0) {
      lines.push(`${basics[color]} ${BASIC_NAMES[color]}`);
    }
  }
  lines.push("", "Sideboard", ...countedLines(sideboard));
  return lines.join("\n");
};

const countedLines = (cards: PoolCard[]): string[] => {
  const counts = new Map<string, number>();
  for (const card of cards) {
    counts.set(card.name, (counts.get(card.name) ?? 0) + 1);
  }
  return [...counts].map(([name, count]) => `${count} ${name}`);
};

export const breakdown = (
  pool: DailySealedPool,
  builds: DailySealedBuild[],
  pairFilter: string | null,
  yourMain: number[] | null,
): Breakdown => {
  const pairs = new Map<string, PairUsage>();
  for (const build of builds) {
    const colors = mainColors(build.colors);
    const pair = pairs.get(colors) ?? { colors, decks: 0, splashed: 0 };
    pair.decks += 1;
    pair.splashed += build.colors !== build.colors.toUpperCase() ? 1 : 0;
    pairs.set(colors, pair);
  }
  const counted = pairFilter ? builds.filter((build) => mainColors(build.colors) === pairFilter) : builds;
  const yours = yourMain ? new Set(yourMain) : null;
  const byName = new Map<string, CardUsage>();
  for (const [index, card] of pool.cards.entries()) {
    const usage = byName.get(card.name) ?? { card, indexes: [], decks: 0, share: 0, mostCopies: 0, yours: null };
    usage.indexes.push(index);
    byName.set(card.name, usage);
  }
  for (const usage of byName.values()) {
    const indexes = new Set(usage.indexes);
    for (const build of counted) {
      const copies = build.main.filter((index) => indexes.has(index)).length;
      if (copies > 0) {
        usage.decks += 1;
        usage.mostCopies = Math.max(usage.mostCopies, copies);
      }
    }
    usage.share = counted.length === 0 ? 0 : usage.decks / counted.length;
    if (yours) {
      usage.yours = usage.indexes.some((index) => yours.has(index)) ? "deck" : "out";
    }
  }
  const cards = [...byName.values()].sort(
    (a, b) => b.decks - a.decks || a.card.cmc - b.card.cmc || a.card.name.localeCompare(b.card.name),
  );
  return { builds: counted.length, pairs: [...pairs.values()].sort((a, b) => b.decks - a.decks), cards };
};

export const usageColumn = (card: PoolCard): string => {
  if (isLand(card) || card.identity.length === 0) {
    return "C";
  }
  return card.identity.length > 1 ? "M" : card.identity;
};

const sortByValue = (entries: PoolEntry[]) =>
  [...entries].sort((a, b) => a.card.cmc - b.card.cmc || a.card.name.localeCompare(b.card.name));

export const groupByColor = (entries: PoolEntry[]): CardGroup[] => {
  const groups: CardGroup[] = COLORS.map((color) => ({ key: color, label: color, entries: [] }));
  const multi: CardGroup = { key: "M", label: "M", entries: [] };
  const colorless: CardGroup = { key: "C", label: "C", entries: [] };
  for (const entry of sortByValue(entries)) {
    const identity = entry.card.identity;
    if (isLand(entry.card) || identity.length === 0) {
      colorless.entries.push(entry);
    } else if (identity.length > 1) {
      multi.entries.push(entry);
    } else {
      groups[COLORS.indexOf(identity as Color)].entries.push(entry);
    }
  }
  return [...groups, multi, colorless].filter((group) => group.entries.length > 0);
};

export const groupByManaValue = (entries: PoolEntry[], withLands = true): CardGroup[] => {
  const groups: CardGroup[] = MANA_VALUE_COLUMNS.map((mv) => ({
    key: String(mv),
    label: mv === 6 ? "6+" : String(mv),
    entries: [],
  }));
  const lands: CardGroup = { key: "L", label: "Land", entries: [] };
  for (const entry of sortByValue(entries)) {
    if (isLand(entry.card)) {
      lands.entries.push(entry);
    } else {
      groups[Math.min(Math.max(entry.card.cmc, 1), 6) - 1].entries.push(entry);
    }
  }
  return withLands ? [lands, ...groups] : groups;
};

export const RARITY_ORDER = ["common", "uncommon", "rare", "mythic"] as const;
type PoolRarity = (typeof RARITY_ORDER)[number];

export interface PoolFilters {
  colors: Color[];
  rarities: PoolRarity[];
  colorless: boolean;
  types: string[];
  search: string;
}

export const NO_FILTERS: PoolFilters = {
  colors: [],
  rarities: [],
  colorless: false,
  types: [],
  search: "",
};

const SPLIT_TYPE_GROUPS: Record<string, { key: string; label: string; ms: string; types: string[]; onlyWhenPresent?: boolean }[]> = {
  spell: [
    { key: "instant", label: "Instant", ms: "instant", types: ["instant"] },
    { key: "sorcery", label: "Sorcery", ms: "sorcery", types: ["sorcery"] },
  ],
  permanent: [
    { key: "artifact", label: "Artifact", ms: "artifact", types: ["artifact"] },
    { key: "enchantment", label: "Enchantment", ms: "enchantment", types: ["enchantment"] },
    { key: "planeswalker", label: "Planeswalker", ms: "planeswalker", types: ["planeswalker"], onlyWhenPresent: true },
  ],
};

const POOL_TYPE_GROUPS = TYPE_GROUPS.flatMap((group) => SPLIT_TYPE_GROUPS[group.key] ?? [group]);

export const typeGroupsIn = (cards: PoolCard[]) =>
  POOL_TYPE_GROUPS.filter(
    (group) => !group.onlyWhenPresent || cards.some((card) => inTypeGroup(card, group.key)),
  );

const inTypeGroup = (card: PoolCard, key: string) => {
  const words = new Set(cardTypeWords(card));
  const group = POOL_TYPE_GROUPS.find((candidate) => candidate.key === key);
  return group?.types.some((type) => words.has(type)) ?? false;
};

const cardTypeWords = (card: PoolCard) =>
  card.types.flatMap((line) => line.split(/\s[-\u2014]\s/)[0].toLowerCase().split(/\s+/));

export const filtersActive = (filters: PoolFilters) =>
  filters.colors.length > 0 || filters.rarities.length > 0 || filters.colorless || filters.types.length > 0 || filters.search.trim() !== "";

export const filterEntries = (entries: PoolEntry[], filters: PoolFilters): PoolEntry[] => {
  const search = filters.search.trim().toLowerCase();
  const selected = new Set<string>(filters.colors);
  return entries.filter(({ card }) => {
    const identity = card.identity.split("");
    const colorFilterOn = selected.size > 0 || filters.colorless;
    const colorMatch = identity.length === 0 ? filters.colorless : identity.some((color) => selected.has(color));
    if (colorFilterOn && !colorMatch) {
      return false;
    }
    if (filters.rarities.length > 0 && !filters.rarities.includes(card.rarity as PoolRarity)) {
      return false;
    }
    if (filters.types.length > 0 && !filters.types.some((key) => inTypeGroup(card, key))) {
      return false;
    }
    if (search && !card.name.toLowerCase().includes(search) && !typeLine(card).toLowerCase().includes(search)) {
      return false;
    }
    return true;
  });
};
