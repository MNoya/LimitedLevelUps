import { fullName, type FieldPlayer } from "./fantasyMock";

export type BracketMatchKey = "qf1" | "qf2" | "qf3" | "qf4" | "sf1" | "sf2" | "final";

export type GameScore = "3-0" | "3-1" | "3-2";

export type BracketPick = { winner: string; games?: GameScore };

export type BracketPicks = Partial<Record<BracketMatchKey, BracketPick>>;

export type MatchResult = { winner: FieldPlayer; loser: FieldPlayer; games: GameScore };

export type BracketResults = Partial<Record<BracketMatchKey, MatchResult>>;

export type BracketStage = "quarterfinal" | "semifinal" | "final";

export type BracketMatch = {
  key: BracketMatchKey;
  stage: BracketStage;
  feeders: [BracketMatchKey, BracketMatchKey] | null;
  seeds: [number, number] | null;
};

export const GAME_SCORES: GameScore[] = ["3-0", "3-1", "3-2"];

export const BRACKET_MATCHES: BracketMatch[] = [
  { key: "qf1", stage: "quarterfinal", feeders: null, seeds: [1, 8] },
  { key: "qf2", stage: "quarterfinal", feeders: null, seeds: [2, 7] },
  { key: "qf3", stage: "quarterfinal", feeders: null, seeds: [4, 5] },
  { key: "qf4", stage: "quarterfinal", feeders: null, seeds: [3, 6] },
  { key: "sf1", stage: "semifinal", feeders: ["qf1", "qf3"], seeds: null },
  { key: "sf2", stage: "semifinal", feeders: ["qf2", "qf4"], seeds: null },
  { key: "final", stage: "final", feeders: ["sf1", "sf2"], seeds: null },
];

export const BRACKET_KEY: Record<string, BracketMatchKey> = {
  QF1: "qf1",
  QF2: "qf2",
  QF3: "qf3",
  QF4: "qf4",
  SF1: "sf1",
  SF2: "sf2",
  F: "final",
};

export const STAGE_LABEL: Record<BracketStage, string> = {
  quarterfinal: "Quarterfinals",
  semifinal: "Semifinals",
  final: "Final",
};

export const BRACKET_WINNER_POINTS: Record<BracketStage, number> = { quarterfinal: 2, semifinal: 4, final: 8 };
export const BRACKET_EXACT_GAMES_BONUS = 1;
export const TOP8_REACHED_BONUS = 4;
export const TOP8_MATCH_WIN_BONUS = 4;
export const TOP8_FINAL_WIN_BONUS = 8;

export function bracketMatch(key: BracketMatchKey): BracketMatch {
  const match = BRACKET_MATCHES.find((entry) => entry.key === key);
  if (!match) {
    throw new Error(`Unknown bracket match ${key}`);
  }
  return match;
}

export function entrants(
  match: BracketMatch,
  seeded: FieldPlayer[],
  winnerOf: (key: BracketMatchKey) => FieldPlayer | undefined,
): [FieldPlayer | undefined, FieldPlayer | undefined] {
  if (match.seeds) {
    return [seeded[match.seeds[0] - 1], seeded[match.seeds[1] - 1]];
  }
  const [first, second] = match.feeders as [BracketMatchKey, BracketMatchKey];
  return [winnerOf(first), winnerOf(second)];
}

export function bySeed(players: [FieldPlayer, FieldPlayer], seeded: FieldPlayer[]): [FieldPlayer, FieldPlayer] {
  const [first, second] = players;
  const seedOf = (player: FieldPlayer) => seeded.findIndex((entry) => fullName(entry) === fullName(player));
  return seedOf(first) <= seedOf(second) ? [first, second] : [second, first];
}

export function pickedWinner(picks: BracketPicks, key: BracketMatchKey, seeded: FieldPlayer[]): FieldPlayer | undefined {
  const name = picks[key]?.winner;
  if (!name) {
    return undefined;
  }
  return seeded.find((player) => fullName(player) === name);
}

export function withPickedWinner(picks: BracketPicks, key: BracketMatchKey, winner: FieldPlayer): BracketPicks {
  const next: BracketPicks = { ...picks, [key]: { winner: fullName(winner), games: picks[key]?.games } };
  if (picks[key]?.winner !== fullName(winner)) {
    clearDownstreamOf(next, key, picks[key]?.winner);
  }
  return next;
}

export function withPickedGames(picks: BracketPicks, key: BracketMatchKey, games: GameScore): BracketPicks {
  const pick = picks[key];
  if (!pick) {
    return picks;
  }
  return { ...picks, [key]: { ...pick, games: pick.games === games ? undefined : games } };
}

export function matchPickPoints(
  match: BracketMatch,
  pick: BracketPick | undefined,
  result: MatchResult | undefined,
): number {
  if (!pick || !result || pick.winner !== fullName(result.winner)) {
    return 0;
  }
  const exact = pick.games === result.games ? BRACKET_EXACT_GAMES_BONUS : 0;
  return BRACKET_WINNER_POINTS[match.stage] + exact;
}

export function bracketScore(picks: BracketPicks, results: BracketResults): number {
  let total = 0;
  for (const match of BRACKET_MATCHES) {
    total += matchPickPoints(match, picks[match.key], results[match.key]);
  }
  return total;
}

export function correctCalls(picks: BracketPicks, results: BracketResults): { right: number; decided: number } {
  let right = 0;
  let decided = 0;
  for (const match of BRACKET_MATCHES) {
    const result = results[match.key];
    if (!result) {
      continue;
    }
    decided += 1;
    if (picks[match.key]?.winner === fullName(result.winner)) {
      right += 1;
    }
  }
  return { right, decided };
}

export function top8Bonus(player: FieldPlayer, seeded: FieldPlayer[], results: BracketResults | null): number {
  const name = fullName(player);
  if (!seeded.some((entry) => fullName(entry) === name)) {
    return 0;
  }
  let bonus = TOP8_REACHED_BONUS;
  if (!results) {
    return bonus;
  }
  for (const match of BRACKET_MATCHES) {
    const result = results[match.key];
    if (result && fullName(result.winner) === name) {
      bonus += match.stage === "final" ? TOP8_FINAL_WIN_BONUS : TOP8_MATCH_WIN_BONUS;
    }
  }
  return bonus;
}

function clearDownstreamOf(picks: BracketPicks, key: BracketMatchKey, previousWinner: string | undefined) {
  if (!previousWinner) {
    return;
  }
  for (const match of BRACKET_MATCHES) {
    if (match.feeders?.includes(key) && picks[match.key]?.winner === previousWinner) {
      delete picks[match.key];
      clearDownstreamOf(picks, match.key, previousWinner);
    }
  }
}

