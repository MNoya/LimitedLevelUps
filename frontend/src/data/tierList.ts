import { useEffect, useState } from "react";
import { useQueries } from "@tanstack/react-query";
import {
  TIER_LIST_DATA_BASE,
  TIER_LIST_DATA_BASE_OVERRIDES,
  TIER_LIST_GRADERS,
  TIER_LIST_PREVIEW_SETS,
  TIER_LIST_UIDS,
} from "./constants";
import type { SetSummary } from "../types/leaderboard";

// A set has a tier list if it has a consensus list of its own or grader lists to compare.
export function hasTierList(code: string): boolean {
  return Boolean(TIER_LIST_UIDS[code]) || (TIER_LIST_GRADERS[code]?.length ?? 0) > 0;
}

export interface ResolvedTierList {
  uid: string | undefined;
  graders: Grader[];
  comparison: boolean;
  effectiveUid: string | undefined;
}

// Resolves a set code to the list that should drive grid placement. With no consensus list
// the first grader stands in, and comparison mode shows every grader's grade side by side.
export function resolveTierList(code: string): ResolvedTierList {
  const uid = TIER_LIST_UIDS[code];
  const graders = TIER_LIST_GRADERS[code] ?? [];
  return { uid, graders, comparison: !uid && graders.length > 0, effectiveUid: uid || graders[0]?.uid };
}

// Sets that have a tier list (live feed or preview snapshot), newest first.
// The first entry is the latest available tier list.
export function buildTierListSets(sets: SetSummary[] | undefined): SetSummary[] {
  const live = (sets ?? []).filter((s) => hasTierList(s.code));
  const liveCodes = new Set(live.map((s) => s.code));
  const previews = Object.entries(TIER_LIST_PREVIEW_SETS)
    .filter(([code]) => hasTierList(code) && !liveCodes.has(code))
    .map(
      ([code, info]): SetSummary => ({
        code,
        name: info.name,
        startDate: info.startDate,
        endDate: "",
        isActive: false,
      }),
    );
  return [...previews, ...live].sort((a, b) => b.startDate.localeCompare(a.startDate));
}

export interface GraderGrade {
  name: string;
  tier: string;
}

export interface Grader {
  name: string;
  uid: string;
}

export const TIER_ORDER = [
  "A+",
  "A",
  "A-",
  "B+",
  "B",
  "B-",
  "C+",
  "C",
  "C-",
  "D+",
  "D",
  "D-",
  "F",
  "SB",
  "TBD",
];
// Green (top) → red (bottom) accent down the grade column; SB/TBD and unknowns stay neutral.
const MAIN_TIERS = TIER_ORDER.filter((t) => t !== "SB" && t !== "TBD");
export function tierColor(tier: string): string {
  const i = MAIN_TIERS.indexOf(tier);
  if (i === -1) {
    return "#4a5260";
  }
  const hue = Math.round(130 - (130 * i) / (MAIN_TIERS.length - 1));
  return `hsl(${hue}, 62%, 47%)`;
}

export interface TierDescription {
  title: string;
  body?: string;
}

// Alex and Marc's definitions from the set review: the opening clause becomes the title,
// the rest reads as the explanation.
export const TIER_DESCRIPTIONS: Record<string, TierDescription> = {
  "A+": {
    title: "The Best Cards in the set",
    body: "Game winning when cast or hugely catch you up from behind",
  },
  A: {
    title: "Game Warping Card",
    body: "Often generates value or is difficult to deal with",
  },
  "A-": {
    title: "Very strong card",
    body: "Game winning if it sticks, usually a bit easier to deal with than A or A+ cards.\nHyper efficient cards like Lightning Bolt also often get an A- grade",
  },
  "B+": {
    title: "Cards you're excited to first pick",
    body: "Not quite bomb tier but will be one of the best cards in your deck",
  },
  B: {
    title: "Good early picks",
    body: "Cards you might consider pivoting for",
  },
  "B-": {
    title: "Some of the better cards in your deck",
    body: "Often the top commons live here",
  },
  "C+": {
    title: "Cards that are close to uncuttable",
    body: "Cards you're happy to take if they're in your color, not quite good enough to pivot for",
  },
  C: { title: "Good Filler/Pillars of certain archetypes" },
  "C-": { title: "Solid Filler" },
  "D+": { title: "Medium Filler/Not fully supported Synergy Cards" },
  D: { title: "Bad Filler" },
  "D-": { title: "Try to avoid" },
  F: {
    title: "Actual Limited unplayable",
    body: "Cards that will always make your deck worse",
  },
  SB: {
    title: "Sideboard card",
    body: "Not maindeckable, but worth bringing in against the right deck",
  },
};

// Grade blocks as they were written, one letter family per block; the guide rules between them.
export const TIER_GUIDE_BLOCKS: string[][] = [
  ["A+", "A", "A-"],
  ["B+", "B", "B-"],
  ["C+", "C", "C-"],
  ["D+", "D", "D-"],
  ["F"],
  ["SB"],
];

// Grid columns and the color filter share one axis: lands fold into the colorless column
export const COLUMN_CODES = ["W", "U", "B", "R", "G", "M", "C"];
export const COLUMN_NAMES: Record<string, string> = {
  W: "White",
  U: "Blue",
  B: "Black",
  R: "Red",
  G: "Green",
  M: "Multicolor",
  C: "Colorless",
};

export const columnOf = (color: string) => (color === "L" ? "C" : color);

export interface TierCard {
  card_id: number;
  name: string;
  url: string;
  url_back?: string | null;
  rarity: string;
  color: string;
  tier: string;
  sort_key: number | null;
  collector_number?: string | null;
  comment: string;
  types: string[];
  cmc: number;
  expansion: string;
  inclusion_type: string;
  flags: { buildaround: boolean; synergy: boolean; sideboard?: boolean };
  trend?: "up" | "down" | null;
  trend_from?: string | null;
  graders?: GraderGrade[];
}

export interface CardFlag {
  key: "synergy" | "buildaround";
  glyph: string;
  label: string;
}

export const CARD_FLAGS: CardFlag[] = [
  { key: "synergy", glyph: "🤝", label: "Synergy" },
  { key: "buildaround", glyph: "🛠️", label: "Build-Around" },
];

export function cardFlags(card: TierCard): CardFlag[] {
  return CARD_FLAGS.filter((flag) => card.flags[flag.key]);
}

export const TREND_COLOR: Record<"up" | "down", string> = {
  up: "#4ade80",
  down: "#f87171",
};
export const TREND_GLYPH: Record<"up" | "down", string> = { up: "▲", down: "▼" };
export const TREND_LABEL: Record<"up" | "down", string> = {
  up: "Up since the set review",
  down: "Down since the set review",
};

export function trendSteps(card: TierCard): number {
  if (!card.trend) return 0;
  const from = TIER_ORDER.indexOf(card.trend_from ?? "");
  const to = TIER_ORDER.indexOf(card.tier);
  if (from === -1 || to === -1) return 1;
  return Math.max(1, Math.abs(to - from));
}

// One glyph per grade step moved since the set review, capped at 3.
export function trendGlyphStack(card: TierCard): string[] {
  if (!card.trend) {
    return [];
  }
  const char = TREND_GLYPH[card.trend];
  return Array.from({ length: Math.min(trendSteps(card), 3) }, () => char);
}

// Filterable type groups — some card types collapse into one toggle (subtypes are ignored)
export const TYPE_GROUPS: Array<{
  key: string;
  label: string;
  ms: string;
  types: string[];
}> = [
  { key: "creature", label: "Creature", ms: "creature", types: ["creature"] },
  {
    key: "spell",
    label: "Instant / Sorcery",
    ms: "instant",
    types: ["instant", "sorcery"],
  },
  {
    key: "permanent",
    label: "Artifact / Enchantment / Planeswalker",
    ms: "enchantment",
    types: ["artifact", "enchantment", "planeswalker"],
  },
  { key: "battle", label: "Battle", ms: "battle", types: ["battle"] },
  { key: "land", label: "Land", ms: "land", types: ["land"] },
];
const TYPE_GROUP_BY_KEY: Record<string, { types: string[] }> =
  Object.fromEntries(TYPE_GROUPS.map((g) => [g.key, g]));

export const MANA_VALUE_BUCKETS = ["1", "2", "3", "4", "5", "6+"];

export function manaValueBucket(cmc: number): string {
  const n = Math.floor(cmc);
  return n >= 6 ? "6+" : String(n);
}

// Each group is an OR within itself and AND across groups; empty group = no constraint
export interface TierFilters {
  sets: string[];
  colors: string[];
  manaValues: string[];
  rarities: string[];
  cardTypes: string[];
  trends: string[];
}

export const EMPTY_FILTERS: TierFilters = {
  sets: [],
  colors: [],
  manaValues: [],
  rarities: [],
  cardTypes: [],
  trends: [],
};

export function activeFilterCount(f: TierFilters): number {
  return (
    f.sets.length +
    f.colors.length +
    f.manaValues.length +
    f.rarities.length +
    f.cardTypes.length +
    f.trends.length
  );
}

export function hasActiveFilters(f: TierFilters): boolean {
  return activeFilterCount(f) > 0;
}

function cardMatchesFilters(card: TierCard, f: TierFilters): boolean {
  if (f.trends.length > 0 && (!card.trend || !f.trends.includes(card.trend))) return false;
  if (f.sets.length > 0 && !f.sets.includes(card.expansion)) return false;
  if (f.colors.length > 0 && !f.colors.includes(columnOf(card.color))) return false;
  if (
    f.manaValues.length > 0 &&
    !f.manaValues.includes(manaValueBucket(card.cmc))
  )
    return false;
  if (f.rarities.length > 0 && !f.rarities.includes(card.rarity)) return false;
  if (f.cardTypes.length > 0) {
    const present = new Set(card.types.map((t) => t.toLowerCase()));
    const inSelectedGroup = f.cardTypes.some((key) =>
      TYPE_GROUP_BY_KEY[key]?.types.some((t) => present.has(t)),
    );
    if (!inSelectedGroup) return false;
  }
  return true;
}

export function isCardFilteredOut(card: TierCard, f: TierFilters): boolean {
  if (!hasActiveFilters(f)) return false;
  return !cardMatchesFilters(card, f);
}

export interface TierCardMatch {
  card: TierCard;
  start: number;
  end: number;
}

const SEARCH_LIMIT = 12;

const foldName = (name: string) => name.normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase();

// Word-start name matches, whole-name matches first; start/end index the raw name
export function searchTierCards(cards: TierCard[], query: string, limit = SEARCH_LIMIT): TierCardMatch[] {
  const needle = foldName(query.trim());
  if (!needle) {
    return [];
  }
  const ranked: Array<TierCardMatch & { rank: number }> = [];
  for (const card of cards) {
    const at = wordStartIndexOf(foldName(card.name), needle);
    if (at === -1) {
      continue;
    }
    ranked.push({ card, start: at, end: at + needle.length, rank: at === 0 ? 0 : 1 });
  }
  ranked.sort((a, b) => a.rank - b.rank || a.card.name.localeCompare(b.card.name));
  return ranked.slice(0, limit).map(({ card, start, end }) => ({ card, start, end }));
}

const WORD_CHAR = /[\p{L}\p{N}']/u;

function wordStartIndexOf(haystack: string, needle: string): number {
  let at = haystack.indexOf(needle);
  while (at > 0 && WORD_CHAR.test(haystack[at - 1])) {
    at = haystack.indexOf(needle, at + 1);
  }
  return at;
}

export const RARITY_ORDER = ["C", "U", "R", "M"];
export const RARITY_NAMES: Record<string, string> = {
  C: "Common",
  U: "Uncommon",
  R: "Rare",
  M: "Mythic",
};

export const INCLUSION_ORDER = ["Main Set", "Bonus Sheet", "Special Guests", "Source Material"];

export function inclusionRank(type: string): number {
  const i = INCLUSION_ORDER.indexOf(type);
  return i === -1 ? INCLUSION_ORDER.length : i;
}

export interface TierFilterOptions {
  sets: Array<{ value: string; label: string; count: number }>;
  colors: Array<{ value: string; name: string; count: number }>;
  rarities: Array<{ value: string; name: string; count: number }>;
  types: Array<{ value: string; label: string; ms: string; count: number }>;
  trends: { up: number; down: number };
}

export function tierFilterOptions(cards: TierCard[]): TierFilterOptions {
  const setInfo = new Map<string, { label: string; count: number }>();
  const colorCounts = new Map<string, number>();
  const rarityCounts = new Map<string, number>();
  const groupCounts = new Map<string, number>();
  const trendCounts = { up: 0, down: 0 };
  for (const card of cards) {
    if (card.trend) {
      trendCounts[card.trend] += 1;
    }
    const set = setInfo.get(card.expansion);
    if (set) {
      set.count += 1;
    } else {
      setInfo.set(card.expansion, { label: card.inclusion_type, count: 1 });
    }
    const column = columnOf(card.color);
    colorCounts.set(column, (colorCounts.get(column) ?? 0) + 1);
    rarityCounts.set(card.rarity, (rarityCounts.get(card.rarity) ?? 0) + 1);
    const present = new Set(card.types.map((t) => t.toLowerCase()));
    for (const group of TYPE_GROUPS) {
      if (group.types.some((t) => present.has(t))) {
        groupCounts.set(group.key, (groupCounts.get(group.key) ?? 0) + 1);
      }
    }
  }
  const sets = [...setInfo.entries()]
    .map(([value, { label, count }]) => ({ value, label, count }))
    .sort((a, b) => {
      const ra = INCLUSION_ORDER.indexOf(a.label);
      const rb = INCLUSION_ORDER.indexOf(b.label);
      return (
        (ra === -1 ? INCLUSION_ORDER.length : ra) -
        (rb === -1 ? INCLUSION_ORDER.length : rb)
      );
    });
  return {
    sets,
    colors: COLUMN_CODES.filter((c) => colorCounts.has(c)).map((c) => ({
      value: c,
      name: COLUMN_NAMES[c],
      count: colorCounts.get(c)!,
    })),
    rarities: RARITY_ORDER.filter((r) => rarityCounts.has(r)).map((r) => ({
      value: r,
      name: RARITY_NAMES[r],
      count: rarityCounts.get(r)!,
    })),
    types: TYPE_GROUPS.filter((g) => groupCounts.has(g.key)).map((g) => ({
      value: g.key,
      label: g.label,
      ms: g.ms,
      count: groupCounts.get(g.key)!,
    })),
    trends: trendCounts,
  };
}

const HIDE_ART_STORAGE_KEY = "tierListHideArt";

export function useHideArt(): [boolean, (value: boolean) => void] {
  const [hideArt, setHideArt] = useState(() => {
    if (typeof window === "undefined") return false;
    return window.localStorage.getItem(HIDE_ART_STORAGE_KEY) === "1";
  });
  useEffect(() => {
    window.localStorage.setItem(HIDE_ART_STORAGE_KEY, hideArt ? "1" : "0");
  }, [hideArt]);
  return [hideArt, setHideArt];
}

const ONE_HOUR = 60 * 60 * 1000;

const normalizeName = (name: string) => name.trim().toLowerCase();

interface TierListPayload {
  cards: TierCard[];
  lastUpdated: string | null;
}

// 17Lands ships trend as a signed step count; the renderer keys off "up"/"down"
function normalizeTrend(raw: unknown): "up" | "down" | null {
  if (typeof raw === "number") {
    if (raw > 0) return "up";
    if (raw < 0) return "down";
    return null;
  }
  return raw === "up" || raw === "down" ? raw : null;
}

const normalizeCards = (cards: TierCard[]): TierCard[] =>
  cards.map((card) => ({ ...card, trend: normalizeTrend(card.trend) }));

// Bare-array responses are card ratings only; the dict shape adds list metadata
// including `last_updated` (UTC, space-separated).
async function fetchTierList(uid: string): Promise<TierListPayload> {
  const override = TIER_LIST_DATA_BASE_OVERRIDES[uid];
  const res = await fetch(override ?? `${TIER_LIST_DATA_BASE}/${uid}`);
  if (!res.ok) {
    throw new Error(`Tier list fetch failed: ${res.status}`);
  }
  const json = await res.json();
  if (Array.isArray(json)) {
    return { cards: normalizeCards(json), lastUpdated: null };
  }
  const lastUpdated = json?.last_updated
    ? `${String(json.last_updated).replace(" ", "T")}Z`
    : null;
  return { cards: normalizeCards(json?.ratings ?? []), lastUpdated };
}

// The consensus list updates every few days; grader review lists are locked and never change,
// so they cache forever and the join attaches each grader's grade onto its card by name.
export function useTierList(uid: string | undefined, graders: Grader[] = []) {
  const results = useQueries({
    queries: [
      {
        queryKey: ["tier-list", uid],
        queryFn: () => fetchTierList(uid!),
        enabled: !!uid,
        staleTime: ONE_HOUR,
      },
      ...graders.map((grader) => ({
        queryKey: ["tier-list", grader.uid],
        queryFn: () => fetchTierList(grader.uid),
        staleTime: Infinity,
        gcTime: Infinity,
      })),
    ],
  });

  const [consensus, ...graderResults] = results;
  let data = consensus.data?.cards;
  if (data && graders.length > 0) {
    const gradesByName = graderResults.map((result) => {
      const byName = new Map<string, string>();
      for (const card of result.data?.cards ?? []) {
        byName.set(normalizeName(card.name), card.tier);
      }
      return byName;
    });
    data = data.map((card) => ({
      ...card,
      graders: graders
        .map((grader, i) => ({
          name: grader.name,
          tier: gradesByName[i].get(normalizeName(card.name)),
        }))
        .filter((grade): grade is GraderGrade => Boolean(grade.tier)),
    }));
  }

  return {
    data,
    lastUpdated: consensus.data?.lastUpdated ?? null,
    isLoading: consensus.isLoading,
    isError: consensus.isError,
  };
}
