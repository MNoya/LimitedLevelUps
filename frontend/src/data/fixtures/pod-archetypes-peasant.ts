import type { PodArchetypeRow } from "../podArchetypes";

// Stand-in archetype rows per (season, deck_colors) until real pod decks accumulate. The client folds
// deck_colors into color pairs and sums the rows in scope, so All is every row and a season is a filter.
const mk = (season: string, colors: string, decks: number, wins: number, games: number): PodArchetypeRow => ({
  set_code: "PEASANT",
  season,
  deck_colors: colors,
  decks,
  game_wins: wins,
  games,
});

export const peasantArchetypesFixture: PodArchetypeRow[] = [
  mk("SOS", "WU", 34, 118, 210),
  mk("MSH", "WUb", 6, 22, 40),
  mk("SOS", "UB", 41, 150, 262),
  mk("SOS", "BR", 38, 132, 240),
  mk("MSH", "RG", 29, 96, 188),
  mk("MSH", "GW", 27, 84, 176),
  mk("HOB", "WB", 22, 71, 140),
  mk("HOB", "UR", 25, 79, 158),
  mk("HOB", "BG", 19, 58, 120),
  mk("SOS", "WR", 16, 44, 100),
  mk("MSH", "UG", 14, 40, 92),
  mk("HOB", "WUB", 7, 20, 48),
  mk("SOS", "R", 4, 9, 22),
];
