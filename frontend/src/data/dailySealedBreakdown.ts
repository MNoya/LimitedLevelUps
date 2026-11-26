import {
  COLORS,
  isLand,
  mainColors,
  type DailySealedBuild,
  type DailySealedPool,
  type PoolCard,
} from "./dailySealed";

export const SMALL_SAMPLE = 10;

export const EVENT_NAMES: Record<string, string> = {
  Sealed: "Sealed",
  TradSealed: "Traditional Sealed",
  ArenaDirect_Sealed: "Arena Direct",
  QualifierPlayInSealed: "Qualifier Play-In",
  QualifierPlayInTradSealed: "Qualifier Play-In Bo3",
  Qualifier_D1_Sealed: "Qualifier Weekend Day 1",
  Qualifier_D2_Sealed: "Qualifier Weekend Day 2",
};

export interface CardRate {
  played: number;
  decks: number;
}

export interface PairRow {
  pair: string;
  decks: number;
  splashed: number;
}

export type RateBasis = "oncolor" | "overall";

export const cardRates = (
  pool: DailySealedPool,
  builds: DailySealedBuild[],
  basis: RateBasis = "oncolor",
): Map<string, CardRate> => {
  const indexesByName = new Map<string, Set<number>>();
  for (const [index, card] of pool.cards.entries()) {
    const indexes = indexesByName.get(card.name) ?? new Set<number>();
    indexes.add(index);
    indexesByName.set(card.name, indexes);
  }
  const rates = new Map<string, CardRate>();
  for (const [name, indexes] of indexesByName) {
    const card = pool.cards[[...indexes][0]];
    const rate: CardRate = { played: 0, decks: 0 };
    for (const build of builds) {
      const runs = build.main.some((index) => indexes.has(index));
      if (runs || basis === "overall" || fitsColors(card, mainColors(build.colors))) {
        rate.decks += 1;
        rate.played += runs ? 1 : 0;
      }
    }
    rates.set(name, rate);
  }
  return rates;
};

export const rateText = (rate: CardRate) =>
  rate.decks < SMALL_SAMPLE ? `${rate.played}/${rate.decks}` : `${Math.round((100 * rate.played) / rate.decks)}%`;

export const pairRows = (builds: DailySealedBuild[]): PairRow[] => {
  const rows = new Map<string, PairRow>();
  for (const build of builds) {
    const pair = mainColors(build.colors);
    const row = rows.get(pair) ?? { pair, decks: 0, splashed: 0 };
    row.decks += 1;
    row.splashed += isSplashed(build) ? 1 : 0;
    rows.set(pair, row);
  }
  return [...rows.values()].sort((a, b) => b.decks - a.decks);
};

export const RATE_BANDS = [
  { key: "always", label: "ALWAYS", fits: (rate: CardRate) => rate.decks > 0 && rate.played === rate.decks },
  { key: "sometimes", label: "SOMETIMES", fits: (rate: CardRate) => rate.played > 0 && rate.played < rate.decks },
  { key: "never", label: "NEVER", fits: (rate: CardRate) => rate.played === 0 },
];

export const rateShare = (rate: CardRate) => (rate.decks === 0 ? 0 : rate.played / rate.decks);

export const isSplit = (rate: CardRate) => rate.played > 0 && rate.played < rate.decks;

export const bandOf = (rate: CardRate) => {
  for (const band of RATE_BANDS) {
    if (band.fits(rate)) {
      return band.key;
    }
  }
  return "never";
};

export const splashCounts = (pool: DailySealedPool, builds: DailySealedBuild[]): Map<string, number> => {
  const counts = new Map<string, number>();
  for (const build of builds) {
    if (!isSplashed(build)) {
      continue;
    }
    const main = mainColors(build.colors);
    const named = new Set<string>();
    for (const index of build.main) {
      const card = pool.cards[index];
      if (card && !isLand(card) && !fitsColors(card, main)) {
        named.add(card.name);
      }
    }
    for (const name of named) {
      counts.set(name, (counts.get(name) ?? 0) + 1);
    }
  }
  return counts;
};

export const colorSplashRows = (builds: DailySealedBuild[]) =>
  COLORS.map((color) => {
    let main = 0;
    let splash = 0;
    for (const build of builds) {
      if (build.colors.includes(color)) {
        main += 1;
      } else if (build.colors.includes(color.toLowerCase())) {
        splash += 1;
      }
    }
    return { color, main, splash };
  }).filter((row) => row.main + row.splash > 0);

export const comparisonWithPeers = (pool: DailySealedPool, builds: DailySealedBuild[], yours: DailySealedBuild) => {
  const pair = mainColors(yours.colors);
  const yourKey = [...yours.main].sort((a, b) => a - b).join(",");
  const peers = builds.filter(
    (build) => mainColors(build.colors) === pair && [...build.main].sort((a, b) => a - b).join(",") !== yourKey,
  );
  const rates = cardRates(pool, peers);
  const yourNames = new Set(yours.main.map((index) => pool.cards[index]?.name));
  const yourPicks: string[] = [];
  const theirPicks: string[] = [];
  for (const [name, rate] of rates) {
    const card = pool.cards.find((candidate) => candidate.name === name);
    if (!card || isLand(card) || !fitsColors(card, pair) || rate.decks === 0) {
      continue;
    }
    if (yourNames.has(name) && rateShare(rate) < 0.5) {
      yourPicks.push(name);
    } else if (!yourNames.has(name) && rateShare(rate) >= 0.5) {
      theirPicks.push(name);
    }
  }
  return { pair, peers: peers.length, rates, yourPicks, theirPicks };
};

export const mostContested = (rates: Map<string, CardRate>): string | null => {
  let best: string | null = null;
  let bestRate: CardRate | null = null;
  for (const [name, rate] of rates) {
    if (!isSplit(rate)) {
      continue;
    }
    const distance = Math.abs(rateShare(rate) - 0.5);
    const bestDistance = bestRate ? Math.abs(rateShare(bestRate) - 0.5) : Infinity;
    if (distance < bestDistance || (distance === bestDistance && bestRate && rate.decks > bestRate.decks)) {
      best = name;
      bestRate = rate;
    }
  }
  return best;
};

export const topGihBuild = (
  pool: DailySealedPool,
  builds: DailySealedBuild[],
  gihWrOf: (name: string) => number | null,
): { build: DailySealedBuild; average: number } | null => {
  let top: { build: DailySealedBuild; average: number } | null = null;
  for (const build of builds) {
    let total = 0;
    let rated = 0;
    for (const index of build.main) {
      const card = pool.cards[index];
      const gih = card && !isLand(card) ? gihWrOf(card.name) : null;
      if (gih !== null) {
        total += gih;
        rated += 1;
      }
    }
    if (rated > 0 && (!top || total / rated > top.average)) {
      top = { build, average: total / rated };
    }
  }
  return top;
};

const isSplashed = (build: DailySealedBuild) => build.colors !== build.colors.toUpperCase();

const fitsColors = (card: PoolCard, colors: string) =>
  COLORS.every((color) => !card.identity.includes(color) || colors.includes(color));
