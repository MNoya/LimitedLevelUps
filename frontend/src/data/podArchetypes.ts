// Reads public_pod_archetype_stats (one row per deck_colors); folds into the main color pair, mono and 3+ into "Other"
export interface PodArchetypeRow {
  set_code: string;
  season: string;
  deck_colors: string;
  decks: number;
  game_wins: number;
  games: number;
}

export interface Archetype {
  key: string;
  colors: string;
  decks: number;
  gameWins: number;
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

export function aggregateArchetypes(rows: PodArchetypeRow[]): Archetype[] {
  const byKey = new Map<string, { decks: number; gameWins: number; games: number }>();
  let totalDecks = 0;
  for (const row of rows) {
    const key = mainPair(row.deck_colors);
    const acc = byKey.get(key) ?? { decks: 0, gameWins: 0, games: 0 };
    acc.decks += row.decks;
    acc.gameWins += row.game_wins;
    acc.games += row.games;
    byKey.set(key, acc);
    totalDecks += row.decks;
  }
  const archetypes: Archetype[] = [];
  for (const [key, acc] of byKey) {
    archetypes.push({
      key,
      colors: key === OTHER_KEY ? "" : key,
      decks: acc.decks,
      gameWins: acc.gameWins,
      games: acc.games,
      playRate: totalDecks > 0 ? acc.decks / totalDecks : 0,
      winRate: acc.games > 0 ? acc.gameWins / acc.games : null,
    });
  }
  return archetypes;
}

export function sortArchetypes(archetypes: Archetype[]): Archetype[] {
  return [...archetypes].sort((a, b) => {
    if (a.key === OTHER_KEY && b.key !== OTHER_KEY) {
      return 1;
    }
    if (b.key === OTHER_KEY && a.key !== OTHER_KEY) {
      return -1;
    }
    const aw = a.winRate ?? -1;
    const bw = b.winRate ?? -1;
    return bw - aw || b.decks - a.decks;
  });
}
