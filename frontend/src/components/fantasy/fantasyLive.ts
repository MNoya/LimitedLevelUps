import { createContext, useContext } from "react";
import { formatRecord, fullName, type FieldPlayer } from "./fantasyField";
import { fantasyEventHeader, type FantasyEventEntry } from "./fantasyEvents";
import { playerSlugs, type EventReplay, type ReplayPlayer } from "./fantasyReplay";
import { BRACKET_KEY, BRACKET_MATCHES, type BracketResults, type GameScore } from "./fantasyTop8";
import type { EventPhase, RoundResult } from "./fantasyScoring";
import type { FantasyDemo, FantasyEventState, FantasyFieldRow, FantasyResultRow } from "../../types/fantasy";

export type LiveEvent = Omit<EventReplay, "results"> & {
  results: BracketResults;
  phase: EventPhase;
  roundsPlayed: number;
  byId: Map<number, ReplayPlayer>;
  replacementsOpen: boolean;
  topEightStarted: boolean;
  bracketWindowOpen: boolean;
  demo: FantasyDemo | null;
  readOnly: boolean;
};

export function buildLiveEvent(
  event: FantasyEventEntry,
  state: FantasyEventState,
  field: FantasyFieldRow[],
  allResults: FantasyResultRow[],
  throughRound: number,
  now: Date,
  demo: FantasyDemo | null = null,
  readOnly = false,
): LiveEvent {
  const results = allResults.filter((row) => row.round <= throughRound);
  const roundsPlayed = Math.min(throughRound, event.swissRounds);
  const swiss = results.filter((row) => row.stage === "swiss");
  const standings = rankAfterEachRound(field, swiss, roundsPlayed);
  const finalRanks = standings[roundsPlayed - 1] ?? alphabeticalRanks(field);
  const players = field.map((row) => livePlayer(row, swiss, standings, finalRanks, roundsPlayed));
  players.sort((a, b) => a.rank - b.rank);
  const byId = new Map(players.map((player) => [player.id as number, player]));
  const byRank = new Map(players.map((player) => [player.rank, player]));
  const seeded = topEightSeeds(results, players, byId, roundsPlayed >= event.swissRounds);
  const { bySlug, slugOf } = playerSlugs(players);
  const header = fantasyEventHeader(event);
  const picksLockAt = new Date(state.picksLockAt).getTime();
  const dayTwoStartAt = picksLockAt + 24 * 60 * 60 * 1000;
  const dayTwoStarted = state.dayTwoStartedAt !== null || now.getTime() >= dayTwoStartAt;
  return {
    event,
    header: { title: header.title, city: header.city, setCode: header.setCode },
    name: event.shortName,
    constructedFormat: event.constructedFormat,
    swissRounds: event.swissRounds,
    cutRound: event.cutRound,
    lastRound: roundsPlayed,
    draftRounds: event.draftRounds,
    players,
    seeded,
    results: bracketResults(results, byId),
    byName: new Map(players.map((player) => [fullName(player), player])),
    byRank,
    bySlug,
    slugOf,
    byId,
    phase: phaseOf(event, results, roundsPlayed, now, picksLockAt, dayTwoStarted),
    roundsPlayed,
    replacementsOpen: !dayTwoStarted && now.getTime() >= picksLockAt,
    topEightStarted: state.top8StartedAt !== null || results.some((row) => row.stage !== "swiss"),
    bracketWindowOpen: state.revealedThroughRound >= event.swissRounds && state.top8StartedAt === null,
    demo,
    readOnly,
  };
}

export const LiveEventContext = createContext<LiveEvent | null>(null);

export function useLiveEvent(): LiveEvent {
  const live = useContext(LiveEventContext);
  if (!live) {
    throw new Error("useLiveEvent needs a LiveEventContext provider");
  }
  return live;
}

export function liveBracketResults(live: LiveEvent): BracketResults | null {
  for (const match of BRACKET_MATCHES) {
    if (live.results[match.key]) {
      return live.results;
    }
  }
  return null;
}

const MINIMUM_PERCENTAGE = 1 / 3;

function phaseOf(
  event: FantasyEventEntry,
  results: FantasyResultRow[],
  roundsPlayed: number,
  now: Date,
  picksLockAt: number,
  dayTwoStarted: boolean,
): EventPhase {
  if (now.getTime() < picksLockAt) {
    return "picking";
  }
  if (results.some((row) => row.stage === "final")) {
    return "final";
  }
  if (roundsPlayed >= event.swissRounds) {
    return "top8";
  }
  if (roundsPlayed >= event.cutRound && !dayTwoStarted) {
    return "cut";
  }
  return roundsPlayed > event.cutRound || dayTwoStarted ? "day2" : "day1";
}

type Tally = { matchPoints: number; matches: number; gamePoints: number; games: number; opponents: number[] };

function rankAfterEachRound(
  field: FantasyFieldRow[],
  swiss: FantasyResultRow[],
  roundsPlayed: number,
): Map<number, number>[] {
  const ranks: Map<number, number>[] = [];
  for (let round = 1; round <= roundsPlayed; round += 1) {
    const tallies = new Map<number, Tally>();
    for (const row of field) {
      tallies.set(row.id, { matchPoints: 0, matches: 0, gamePoints: 0, games: 0, opponents: [] });
    }
    for (const row of swiss) {
      const tally = tallies.get(row.playerId);
      if (!tally || row.round > round) {
        continue;
      }
      tally.matchPoints += row.result === "W" ? 3 : row.result === "D" ? 1 : 0;
      tally.matches += 1;
      tally.gamePoints += row.gameWins * 3 + row.gameDraws;
      tally.games += row.gameWins + row.gameLosses + row.gameDraws;
      if (!row.isBye && row.opponentId !== null) {
        tally.opponents.push(row.opponentId);
      }
    }
    ranks.push(rankByTiebreakers(field, tallies));
  }
  return ranks;
}

function rankByTiebreakers(field: FantasyFieldRow[], tallies: Map<number, Tally>): Map<number, number> {
  const matchWin = (id: number) => percentage(tallies.get(id), (tally) => [tally.matchPoints, tally.matches * 3]);
  const gameWin = (id: number) => percentage(tallies.get(id), (tally) => [tally.gamePoints, tally.games * 3]);
  const opponentAverage = (id: number, of: (opponent: number) => number) => {
    const opponents = tallies.get(id)?.opponents ?? [];
    if (opponents.length === 0) {
      return 0;
    }
    let total = 0;
    for (const opponent of opponents) {
      total += of(opponent);
    }
    return total / opponents.length;
  };
  const keyed = field.map((row) => ({
    id: row.id,
    name: `${row.firstName} ${row.lastName}`,
    matchPoints: tallies.get(row.id)?.matchPoints ?? 0,
    opponentMatchWin: opponentAverage(row.id, matchWin),
    gameWin: gameWin(row.id),
    opponentGameWin: opponentAverage(row.id, gameWin),
  }));
  keyed.sort(
    (a, b) =>
      b.matchPoints - a.matchPoints ||
      b.opponentMatchWin - a.opponentMatchWin ||
      b.gameWin - a.gameWin ||
      b.opponentGameWin - a.opponentGameWin ||
      a.name.localeCompare(b.name),
  );
  return new Map(keyed.map((entry, index) => [entry.id, index + 1]));
}

function percentage(tally: Tally | undefined, parts: (tally: Tally) => [number, number]): number {
  if (!tally) {
    return MINIMUM_PERCENTAGE;
  }
  const [earned, possible] = parts(tally);
  return possible === 0 ? MINIMUM_PERCENTAGE : Math.max(MINIMUM_PERCENTAGE, earned / possible);
}

function alphabeticalRanks(field: FantasyFieldRow[]): Map<number, number> {
  const sorted = [...field].sort((a, b) => a.lastName.localeCompare(b.lastName));
  return new Map(sorted.map((row, index) => [row.id, index + 1]));
}

function livePlayer(
  row: FantasyFieldRow,
  swiss: FantasyResultRow[],
  standings: Map<number, number>[],
  finalRanks: Map<number, number>,
  roundsPlayed: number,
): ReplayPlayer {
  const rounds: ReplayPlayer["rounds"] = [];
  const record = { wins: 0, losses: 0, draws: 0 };
  for (const result of swiss) {
    if (result.playerId !== row.id) {
      continue;
    }
    const opponentRank = result.opponentId === null ? 0 : (finalRanks.get(result.opponentId) ?? 0);
    rounds[result.round - 1] = [
      result.result as RoundResult,
      opponentRank,
      result.gameWins,
      result.gameLosses,
      result.gameDraws,
    ];
    if (result.result === "W") {
      record.wins += 1;
    } else if (result.result === "L") {
      record.losses += 1;
    } else {
      record.draws += 1;
    }
  }
  const lastPlayed = rounds.length;
  for (let index = 0; index < lastPlayed; index += 1) {
    rounds[index] = rounds[index] ?? null;
  }
  const ranks = standings.slice(0, roundsPlayed).map((ranksAfter) => ranksAfter.get(row.id) ?? 0);
  return {
    id: row.id,
    firstName: row.firstName,
    lastName: row.lastName,
    country: row.country ?? "",
    countryCode: row.countryCode,
    sources: row.sources,
    photoUrl: row.photoUrl,
    photoSource: photoSourceOf(row.photoUrl),
    rank: finalRanks.get(row.id) ?? 0,
    matchRecord: formatRecord(record),
    deck: row.deckName,
    decklistUrl: row.decklistId ? `https://melee.gg/Decklist/View/${row.decklistId}` : null,
    rounds,
    ranks,
  };
}

function photoSourceOf(url: string | null): FieldPlayer["photoSource"] {
  if (!url) {
    return null;
  }
  if (url.includes("ctfassets.net")) {
    return url.includes("f=face") ? "magicgg-face" : "magicgg";
  }
  if (url.includes("melee.gg")) {
    return "melee";
  }
  return url.includes("twimg.com") ? "x" : "other";
}

function topEightSeeds(
  results: FantasyResultRow[],
  players: ReplayPlayer[],
  byId: Map<number, ReplayPlayer>,
  swissComplete: boolean,
): ReplayPlayer[] {
  const quarterfinalists = new Set<ReplayPlayer>();
  for (const row of results) {
    const player = byId.get(row.playerId);
    if (row.stage === "quarterfinal" && player) {
      quarterfinalists.add(player);
    }
  }
  if (quarterfinalists.size > 0) {
    return [...quarterfinalists].sort((a, b) => a.rank - b.rank);
  }
  return swissComplete ? players.slice(0, 8) : [];
}

function bracketResults(results: FantasyResultRow[], byId: Map<number, ReplayPlayer>): BracketResults {
  const bracket: BracketResults = {};
  for (const row of results) {
    const key = row.bracketPosition ? BRACKET_KEY[row.bracketPosition] : undefined;
    const winner = byId.get(row.playerId);
    const loser = row.opponentId === null ? undefined : byId.get(row.opponentId);
    if (!key || row.result !== "W" || !winner || !loser) {
      continue;
    }
    bracket[key] = { winner, loser, games: `${row.gameWins}-${row.gameLosses}` as GameScore };
  }
  return bracket;
}
