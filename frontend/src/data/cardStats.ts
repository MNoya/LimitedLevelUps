import { THREE_COLOR_SETS } from "./constants";

export type DeckColors = string;

export interface PairStats {
  gihWr: number | null;
  gihGames: number;
}

export interface CardStats {
  mtgaId?: number;
  seen: number;
  picked: number;
  alsa: number | null;
  ata: number | null;
  gp: number;
  gpWr: number | null;
  ohWr: number | null;
  gdWr: number | null;
  gihGames: number;
  gihWr: number | null;
  gnsWr: number | null;
  iwd: number | null;
  pairs: Record<DeckColors, PairStats>;
}

export interface CardStatsFile {
  set: string;
  updatedAt: string;
  cards: Record<string, CardStats>;
}

export const cardDataUrl = (setCode: string) =>
  `https://www.17lands.com/card_data?expansion=${setCode}&format=PremierDraft`;

export const cardDetailsUrl = (setCode: string, mtgaId: number) => {
  const params = new URLSearchParams({
    card_id: String(mtgaId),
    expansion: setCode,
    format: "PremierDraft",
    time_period: "ALL_TIME",
  });
  return `https://www.17lands.com/card_data/details?${params}`;
};

export const formatWinRate = (value: number | null) => (value === null ? "–" : `${(value * 100).toFixed(1)}%`);

export const MIN_GAMES_FOR_INFERENCE = 100;
export const MIN_GAMES_FOR_GRADE = 500;

export async function fetchCardStatsFile(setCode: string, previous: CardStatsFile | null): Promise<CardStatsFile> {
  const overall = await fetchCardData(setCode, null);
  const cards: Record<string, CardStats> = {};
  for (const card of overall) {
    cards[card.name] = overallStats(card);
  }
  const updatedAt = new Date().toISOString();

  if (overall.length === 0) {
    return { set: setCode, updatedAt, cards };
  }
  if (previous && sameGameCounts(previous, cards)) {
    return { ...previous, updatedAt };
  }

  const colorPairs = ["WU", "UB", "BR", "RG", "WG", "WB", "UR", "BG", "WR", "UG"];
  const colorTrios = ["WUB", "WUR", "WUG", "WBR", "WBG", "WRG", "UBR", "UBG", "URG", "BRG"];
  const decks = THREE_COLOR_SETS.includes(setCode) ? [...colorPairs, ...colorTrios] : colorPairs;
  const secondsBetweenCalls = 7;
  for (const pair of decks) {
    await pause(secondsBetweenCalls);
    for (const card of await fetchCardData(setCode, pair)) {
      const stats = cards[card.name];
      if (stats && card.ever_drawn_game_count > 0) {
        stats.pairs[pair] = { gihWr: rounded(card.ever_drawn_win_rate, 4), gihGames: card.ever_drawn_game_count };
      }
    }
  }
  return { set: setCode, updatedAt, cards };
}

export type Grade = string;

export interface CardGrades {
  all: Grade | null;
  pairs: Record<DeckColors, Grade>;
}

export function gradeCardStats(file: CardStatsFile): Map<string, CardGrades> {
  const grades = new Map<string, CardGrades>();
  for (const name of Object.keys(file.cards)) {
    grades.set(name, { all: null, pairs: {} });
  }

  const overallSamples = Object.entries(file.cards).map(([name, s]) => ({ name, wr: s.gihWr, games: s.gihGames }));
  for (const [name, grade] of percentileGrades(overallSamples)) {
    grades.get(name)!.all = grade;
  }
  const deckKeys = new Set<DeckColors>();
  for (const stats of Object.values(file.cards)) {
    for (const deck of Object.keys(stats.pairs)) {
      deckKeys.add(deck);
    }
  }
  for (const pair of deckKeys) {
    const samples = Object.entries(file.cards).map(([name, s]) => ({
      name,
      wr: s.pairs[pair]?.gihWr ?? null,
      games: s.pairs[pair]?.gihGames ?? 0,
    }));
    for (const [name, grade] of percentileGrades(samples)) {
      grades.get(name)!.pairs[pair] = grade;
    }
  }
  return grades;
}

interface ApiCard {
  name: string;
  mtga_id: number;
  seen_count: number;
  pick_count: number;
  avg_seen: number | null;
  avg_pick: number | null;
  game_count: number;
  win_rate: number | null;
  opening_hand_win_rate: number | null;
  drawn_win_rate: number | null;
  ever_drawn_game_count: number;
  ever_drawn_win_rate: number | null;
  never_drawn_win_rate: number | null;
  drawn_improvement_win_rate: number | null;
}

async function fetchCardData(setCode: string, pair: DeckColors | null): Promise<ApiCard[]> {
  const params = new URLSearchParams({ expansion: setCode, event_type: "PremierDraft", time_period: "ALL_TIME" });
  if (pair) {
    params.set("colors", pair);
  }
  const resp = await fetch(`https://www.17lands.com/api/card_data?${params}`, {
    headers: { accept: "application/json", referer: "https://www.17lands.com/card_data" },
  });
  if (!resp.ok) {
    throw new Error(`17lands card_data ${setCode} ${pair ?? "all"} failed with ${resp.status}`);
  }
  const body = (await resp.json()) as { data: ApiCard[] };
  return body.data;
}

function overallStats(card: ApiCard): CardStats {
  return {
    mtgaId: card.mtga_id,
    seen: card.seen_count,
    picked: card.pick_count,
    alsa: rounded(card.avg_seen, 2),
    ata: rounded(card.avg_pick, 2),
    gp: card.game_count,
    gpWr: rounded(card.win_rate, 4),
    ohWr: rounded(card.opening_hand_win_rate, 4),
    gdWr: rounded(card.drawn_win_rate, 4),
    gihGames: card.ever_drawn_game_count,
    gihWr: rounded(card.ever_drawn_win_rate, 4),
    gnsWr: rounded(card.never_drawn_win_rate, 4),
    iwd: rounded(card.drawn_improvement_win_rate, 4),
    pairs: {},
  };
}

function sameGameCounts(previous: CardStatsFile, cards: Record<string, CardStats>): boolean {
  for (const [name, stats] of Object.entries(cards)) {
    if (previous.cards[name]?.gp !== stats.gp) {
      return false;
    }
  }
  return true;
}

const pause = (seconds: number) => new Promise((resolve) => setTimeout(resolve, seconds * 1000));

function rounded(value: number | null, digits: number): number | null {
  if (value === null) {
    return null;
  }
  const factor = 10 ** digits;
  return Math.round(value * factor) / factor;
}

const GRADE_THRESHOLDS: [Grade, number][] = [
  ["A+", 99],
  ["A", 95],
  ["A-", 90],
  ["B+", 85],
  ["B", 76],
  ["B-", 68],
  ["C+", 57],
  ["C", 45],
  ["C-", 36],
  ["D+", 27],
  ["D", 17],
  ["D-", 5],
  ["F", 0],
];

function percentileGrades(samples: { name: string; wr: number | null; games: number }[]): Map<string, Grade> {
  const inferable = samples.filter((s) => s.wr !== null && s.games >= MIN_GAMES_FOR_INFERENCE);
  const grades = new Map<string, Grade>();
  if (inferable.length <= 1) {
    return grades;
  }
  const winRates = inferable.map((s) => s.wr!);
  const mean = winRates.reduce((sum, wr) => sum + wr, 0) / winRates.length;
  const variance = winRates.reduce((sum, wr) => sum + (wr - mean) ** 2, 0) / (winRates.length - 1);
  const std = Math.sqrt(variance);

  for (const sample of inferable) {
    if (sample.games <= MIN_GAMES_FOR_GRADE) {
      continue;
    }
    const score = normalCdf((sample.wr! - mean) / std) * 100;
    for (const [grade, threshold] of GRADE_THRESHOLDS) {
      if (score >= threshold) {
        grades.set(sample.name, grade);
        break;
      }
    }
  }
  return grades;
}

function normalCdf(z: number): number {
  const t = 1 / (1 + 0.3275911 * (Math.abs(z) / Math.SQRT2));
  const poly = t * (0.254829592 + t * (-0.284496736 + t * (1.421413741 + t * (-1.453152027 + t * 1.061405429))));
  const erf = 1 - poly * Math.exp(-(z * z) / 2);
  return z >= 0 ? (1 + erf) / 2 : (1 - erf) / 2;
}
