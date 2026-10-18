import type { PodEventSummary } from "../types/leaderboard";

// Folds deck colors into the main color pair, mono and 3+ into "Other"
export interface PodArchetypeRow {
  set_code: string;
  season: string;
  event_id: string;
  deck_colors: string;
  decks: number;
  game_wins: number;
  games: number;
}

export interface ArchetypeTally {
  deckColors: string;
  decks: number;
  wins: number;
  games: number;
}

export interface Archetype {
  key: string;
  colors: string;
  decks: number;
  wins: number;
  games: number;
  playRate: number;
  winRate: number | null;
}

export const OTHER_KEY = "OTHER";

const WUBRG = "WUBRG";

export function mainPair(deckColors: string): string {
  const main = [...deckColors].filter((c) => WUBRG.includes(c));
  main.sort((a, b) => WUBRG.indexOf(a) - WUBRG.indexOf(b));
  return main.length === 2 ? main.join("") : OTHER_KEY;
}

export function gameTally(row: PodArchetypeRow): ArchetypeTally {
  return { deckColors: row.deck_colors, decks: row.decks, wins: row.game_wins, games: row.games };
}

export function aggregateArchetypes(tallies: ArchetypeTally[]): Archetype[] {
  const byKey = new Map<string, { decks: number; wins: number; games: number }>();
  let totalDecks = 0;
  for (const tally of tallies) {
    const key = mainPair(tally.deckColors);
    const acc = byKey.get(key) ?? { decks: 0, wins: 0, games: 0 };
    acc.decks += tally.decks;
    acc.wins += tally.wins;
    acc.games += tally.games;
    byKey.set(key, acc);
    totalDecks += tally.decks;
  }
  const archetypes: Archetype[] = [];
  for (const [key, acc] of byKey) {
    archetypes.push({
      key,
      colors: key === OTHER_KEY ? "" : key,
      decks: acc.decks,
      wins: acc.wins,
      games: acc.games,
      playRate: totalDecks > 0 ? acc.decks / totalDecks : 0,
      winRate: acc.games > 0 ? acc.wins / acc.games : null,
    });
  }
  return archetypes;
}

export function championPairCounts(events: PodEventSummary[]): Map<string, number> {
  const counts = new Map<string, number>();
  for (const e of events) {
    if (e.kind === "mock" || !e.isFinalized || !e.championDeckColors) {
      continue;
    }
    const key = mainPair(e.championDeckColors);
    counts.set(key, (counts.get(key) ?? 0) + 1);
  }
  return counts;
}
