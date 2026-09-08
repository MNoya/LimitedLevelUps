// Reads public_pod_card_stats (one raw-sum row per season+card); each rate is a ratio of sums, All = no filter
export interface PodCardStatRow {
  set_code: string;
  season: string;
  card_name: string;
  card_set: string | null;
  colors: string | null;
  rarity: string | null;
  cmc: number | null;
  type_line: string | null;
  seen_count: number;
  last_seen_sum: number;
  saw_count: number;
  pick_count: number;
  pick_sum: number;
  maindeck_count: number;
  drafts: number;
  game_count: number;
  game_wins: number;
}

export interface PodCard {
  name: string;
  set: string | null;
  colors: string;
  rarity: string | null;
  cmc: number | null;
  typeLine: string | null;
  seen: number;
  alsa: number | null;
  picked: number;
  ata: number | null;
  pool: number;
  drafts: number;
  maindecked: number;
  playRate: number | null;
  gamesPlayed: number;
  winRate: number | null;
}

interface CardSums {
  card_set: string | null;
  colors: string | null;
  rarity: string | null;
  cmc: number | null;
  type_line: string | null;
  seen: number;
  lastSeenSum: number;
  sawCount: number;
  picked: number;
  pickSum: number;
  maindecked: number;
  drafts: number;
  games: number;
  gameWins: number;
}

// Fold the in-scope raw-sum rows into one PodCard per card, computing each rate from the summed components
export function aggregatePodCards(rows: PodCardStatRow[]): PodCard[] {
  const byCard = new Map<string, CardSums>();
  for (const row of rows) {
    const acc = byCard.get(row.card_name) ?? {
      card_set: row.card_set, colors: row.colors, rarity: row.rarity, cmc: row.cmc, type_line: row.type_line,
      seen: 0, lastSeenSum: 0, sawCount: 0, picked: 0, pickSum: 0, maindecked: 0, drafts: 0, games: 0, gameWins: 0,
    };
    acc.seen += row.seen_count;
    acc.lastSeenSum += row.last_seen_sum;
    acc.sawCount += row.saw_count;
    acc.picked += row.pick_count;
    acc.pickSum += row.pick_sum;
    acc.maindecked += row.maindeck_count;
    acc.drafts += row.drafts;
    acc.games += row.game_count;
    acc.gameWins += row.game_wins;
    byCard.set(row.card_name, acc);
  }
  const ratio = (num: number, den: number) => (den > 0 ? num / den : null);
  const cards: PodCard[] = [];
  for (const [name, s] of byCard) {
    cards.push({
      name,
      set: s.card_set,
      colors: s.colors ?? "",
      rarity: s.rarity,
      cmc: s.cmc,
      typeLine: s.type_line,
      seen: s.seen,
      alsa: ratio(s.lastSeenSum, s.sawCount),
      picked: s.picked,
      ata: ratio(s.pickSum, s.picked),
      pool: s.picked,
      drafts: s.drafts,
      maindecked: s.maindecked,
      playRate: ratio(s.maindecked, s.picked),
      gamesPlayed: s.games,
      winRate: ratio(s.gameWins, s.games),
    });
  }
  return cards;
}

const CUBE_LABELS: Record<string, string> = {
  PEASANT: "Peasant",
};

export function cardDataLabel(code: string): string {
  return CUBE_LABELS[code] ?? code;
}

export function hasCardData(code: string): boolean {
  return code === "PEASANT";
}

export type ColumnTier = "count" | "stat" | "payoff";

export interface PodCardColumn {
  key: keyof PodCard;
  label: string;
  shortLabel?: string;
  title: string;
  format: (card: PodCard) => string;
  tier: ColumnTier;
}

const int = (n: number | null) => (n == null || n === 0 ? "—" : String(n));
const dec = (n: number | null, digits = 2) => (n == null ? "—" : n.toFixed(digits));
const pct = (n: number | null) => (n == null ? "—" : `${(n * 100).toFixed(1)}%`);

export const POD_CARD_COLUMNS: PodCardColumn[] = [
  { key: "seen", label: "# Seen", title: "Times Seen", format: (c) => int(c.seen), tier: "count" },
  { key: "picked", label: "# Picked", shortLabel: "# Pick", title: "Times Picked", format: (c) => int(c.picked), tier: "count" },
  { key: "alsa", label: "ALSA", title: "Average Last Seen At", format: (c) => dec(c.alsa), tier: "stat" },
  { key: "ata", label: "ATA", title: "Average Taken At", format: (c) => dec(c.ata), tier: "stat" },
  { key: "gamesPlayed", label: "# GP", title: "Games Played in Maindeck", format: (c) => int(c.gamesPlayed), tier: "count" },
  { key: "playRate", label: "% GP", title: "% Main-decked", format: (c) => pct(c.playRate), tier: "payoff" },
  { key: "winRate", label: "GP WR", title: "Maindeck Win Rate", format: (c) => pct(c.winRate), tier: "payoff" },
];

export type SortDir = "asc" | "desc";

export function sortPodCards(cards: PodCard[], key: keyof PodCard, dir: SortDir): PodCard[] {
  const factor = dir === "asc" ? 1 : -1;
  return [...cards].sort((a, b) => {
    const av = a[key];
    const bv = b[key];
    if (av == null && bv == null) {
      return a.name.localeCompare(b.name);
    }
    if (av == null) {
      return 1;
    }
    if (bv == null) {
      return -1;
    }
    if (typeof av === "number" && typeof bv === "number") {
      return (av - bv) * factor || a.name.localeCompare(b.name);
    }
    return String(av).localeCompare(String(bv)) * factor;
  });
}

export const COLOR_COLUMNS = ["W", "U", "B", "R", "G", "M", "C"] as const;
export const COLOR_NAMES: Record<string, string> = {
  W: "White", U: "Blue", B: "Black", R: "Red", G: "Green", M: "Multicolor", C: "Colorless",
};

export function colorColumn(colors: string): string {
  if (colors.length === 0) {
    return "C";
  }
  if (colors.length > 1) {
    return "M";
  }
  return colors.toUpperCase();
}

export const TYPE_GROUPS: Array<{ key: string; label: string; ms: string; types: string[] }> = [
  { key: "creature", label: "Creature", ms: "creature", types: ["creature"] },
  { key: "instant", label: "Instant", ms: "instant", types: ["instant"] },
  { key: "sorcery", label: "Sorcery", ms: "sorcery", types: ["sorcery"] },
  { key: "artifact", label: "Artifact", ms: "artifact", types: ["artifact"] },
  { key: "enchantment", label: "Enchantment", ms: "enchantment", types: ["enchantment"] },
  { key: "planeswalker", label: "Planeswalker", ms: "planeswalker", types: ["planeswalker"] },
  { key: "land", label: "Land", ms: "land", types: ["land"] },
  { key: "battle", label: "Battle", ms: "battle", types: ["battle"] },
];

export const MANA_VALUE_BUCKETS = ["1", "2", "3", "4", "5", "6+"];

export function manaValueBucket(cmc: number | null): string | null {
  if (cmc == null) {
    return null;
  }
  const n = Math.floor(cmc);
  return n >= 6 ? "6+" : String(n);
}

export interface PodCardFilters {
  colors: string[];
  types: string[];
  manaValues: string[];
  sets: string[];
}

export const EMPTY_POD_CARD_FILTERS: PodCardFilters = { colors: [], types: [], manaValues: [], sets: [] };

export function activePodCardFilterCount(f: PodCardFilters): number {
  return f.colors.length + f.types.length + f.manaValues.length + f.sets.length;
}

const TYPE_GROUP_BY_KEY = Object.fromEntries(TYPE_GROUPS.map((g) => [g.key, g]));

export function cardMatchesFilters(card: PodCard, f: PodCardFilters): boolean {
  if (f.colors.length > 0 && !f.colors.includes(colorColumn(card.colors))) {
    return false;
  }
  if (f.sets.length > 0 && (!card.set || !f.sets.includes(card.set))) {
    return false;
  }
  const bucket = manaValueBucket(card.cmc);
  if (f.manaValues.length > 0 && (bucket == null || !f.manaValues.includes(bucket))) {
    return false;
  }
  if (f.types.length > 0) {
    const line = (card.typeLine ?? "").toLowerCase();
    const inGroup = f.types.some((key) => TYPE_GROUP_BY_KEY[key]?.types.some((t) => line.includes(t)));
    if (!inGroup) {
      return false;
    }
  }
  return true;
}

export interface PodCardFilterOptions {
  colors: Array<{ value: string; name: string; count: number }>;
  types: Array<{ value: string; label: string; ms: string; count: number }>;
  manaValues: Array<{ value: string; count: number }>;
  sets: Array<{ value: string; count: number }>;
}

export function podCardFilterOptions(cards: PodCard[]): PodCardFilterOptions {
  const colorCounts = new Map<string, number>();
  const typeCounts = new Map<string, number>();
  const manaCounts = new Map<string, number>();
  const setCounts = new Map<string, number>();
  for (const card of cards) {
    bump(colorCounts, colorColumn(card.colors));
    const bucket = manaValueBucket(card.cmc);
    if (bucket) {
      bump(manaCounts, bucket);
    }
    if (card.set) {
      bump(setCounts, card.set);
    }
    const line = (card.typeLine ?? "").toLowerCase();
    for (const group of TYPE_GROUPS) {
      if (group.types.some((t) => line.includes(t))) {
        bump(typeCounts, group.key);
      }
    }
  }
  return {
    colors: COLOR_COLUMNS.map((c) => ({ value: c, name: COLOR_NAMES[c], count: colorCounts.get(c) ?? 0 })),
    types: TYPE_GROUPS.map((g) => ({ value: g.key, label: g.label, ms: g.ms, count: typeCounts.get(g.key) ?? 0 })),
    manaValues: MANA_VALUE_BUCKETS.map((m) => ({ value: m, count: manaCounts.get(m) ?? 0 })),
    sets: [...setCounts.entries()].sort((a, b) => a[0].localeCompare(b[0])).map(([value, count]) => ({ value, count })),
  };
}

function bump(counts: Map<string, number>, key: string): void {
  counts.set(key, (counts.get(key) ?? 0) + 1);
}
