import {
  formatRecord,
  fullName,
  playerSlug,
  type EventHeader,
  type FieldPlayer,
  type MatchRecord,
} from "./fantasyMock";
import { meleeEventUrl, type FantasyEventEntry } from "./fantasyEvents";
import { BRACKET_MATCHES, type BracketMatchKey, type BracketResults, type GameScore } from "./fantasyTop8";
import type { RoundResult } from "./fantasyEvent";
import type { MatchHistoryRow, ProfileEvent } from "./PlayerProfilePanel";

type PlayedRound = [result: RoundResult, opponentRank: number, gameWins: number, gameLosses: number, gameDraws: number];

export type ReplayPlayer = FieldPlayer & {
  rank: number;
  matchRecord: string;
  deck: string | null;
  decklistUrl: string | null;
  rounds: (PlayedRound | null)[];
  ranks: number[];
};

export type ReplayStage = "top8" | "day2" | "day1";

export type EventReplay = StandingsSource & {
  event: FantasyEventEntry;
  header: EventHeader;
  name: string;
  constructedFormat: string;
  draftRounds: number[];
  seeded: ReplayPlayer[];
  results: Required<BracketResults>;
  byName: Map<string, ReplayPlayer>;
  byRank: Map<number, ReplayPlayer>;
  bySlug: Map<string, ReplayPlayer>;
  slugOf: Map<ReplayPlayer, string>;
};

export type ProfileSource = Omit<EventReplay, "results">;

export type StandingsSource = {
  players: ReplayPlayer[];
  swissRounds: number;
  cutRound: number;
  lastRound: number;
};

export type StandingsRow = { player: ReplayPlayer; rank: number; movement: number | null; record: MatchRecord };

type ReplayFile = {
  players: ReplayPlayer[];
  bracket: Record<BracketMatchKey, { winner: number; loser: number; games: GameScore }>;
};

export const REPLAY_STAGE_LABEL: Record<ReplayStage, string> = {
  top8: "TOP 8",
  day2: "DAY 2",
  day1: "DAY 1",
};

const REPLAY_FILES: Record<string, () => Promise<{ default: unknown }>> = {
  PTMSH: () => import("../../data/fantasyReplayPtmsh.json"),
  PTSOS: () => import("../../data/fantasyReplayPtsos.json"),
  PTECL: () => import("../../data/fantasyReplayPtecl.json"),
  WC31: () => import("../../data/fantasyReplayWc31.json"),
  PTEOE: () => import("../../data/fantasyReplayPteoe.json"),
  PTFIN: () => import("../../data/fantasyReplayPtfin.json"),
  PTDFT: () => import("../../data/fantasyReplayPtdft.json"),
  WC30: () => import("../../data/fantasyReplayWc30.json"),
};

export function hasReplay(event: FantasyEventEntry): boolean {
  return event.code in REPLAY_FILES;
}

export async function loadReplay(event: FantasyEventEntry): Promise<EventReplay> {
  const file = (await REPLAY_FILES[event.code]()).default as ReplayFile;
  return toReplay(event, file);
}

export function replayStage(replay: EventReplay, player: ReplayPlayer): ReplayStage {
  if (replay.seeded.includes(player)) {
    return "top8";
  }
  return player.rounds.length > replay.cutRound ? "day2" : "day1";
}

export function standingsRound(source: StandingsSource, requested: string | null): number {
  const round = Number(requested);
  return round >= 1 && round <= source.lastRound ? round : source.lastRound;
}

export function standingsAfter(source: StandingsSource, round: number): StandingsRow[] {
  const groupNow = pointsGroupRanks(source, round);
  const groupBefore = round > 1 ? pointsGroupRanks(source, round - 1) : null;
  const rows = source.players.map((player) => {
    const rank = player.ranks[round - 1];
    const changedGroup = groupBefore !== null && groupBefore.get(player) !== groupNow.get(player);
    const movement = changedGroup ? player.ranks[round - 2] - rank : null;
    return { player, rank, movement, record: recordThrough(player, round) };
  });
  rows.sort((a, b) => a.rank - b.rank);
  return rows;
}

export function replayProfileEvent(
  replay: ProfileSource,
  player: FieldPlayer,
  hrefFor?: (player: ReplayPlayer) => string,
): ProfileEvent | undefined {
  const entry = replay.byName.get(fullName(player));
  if (!entry) {
    return undefined;
  }
  const rounds = [];
  for (let round = 1; round <= replay.swissRounds; round += 1) {
    rounds.push({
      round,
      result: entry.rounds[round - 1]?.[0] ?? null,
      draft: replay.draftRounds.includes(round),
    });
  }
  const deck = entry.deck ? { name: entry.deck, url: entry.decklistUrl } : undefined;
  return {
    title: replay.name.toUpperCase(),
    headline: `RANK ${entry.rank}`,
    detail: entry.matchRecord,
    rounds,
    dayOneRounds: replay.cutRound,
    meleeUrl: meleeEventUrl(replay.event.code),
    constructedFormat: replay.constructedFormat,
    deck,
    history: matchHistory(replay, entry, hrefFor),
  };
}

function matchHistory(
  replay: ProfileSource,
  player: ReplayPlayer,
  hrefFor?: (player: ReplayPlayer) => string,
): MatchHistoryRow[] {
  const history: MatchHistoryRow[] = [];
  player.rounds.forEach((played, index) => {
    if (!played) {
      return;
    }
    const round = index + 1;
    const [result, opponentRank, gameWins, gameLosses, gameDraws] = played;
    const opponent = replay.byRank.get(opponentRank) ?? null;
    const draft = replay.draftRounds.includes(round);
    history.push({
      round,
      draft,
      opponent,
      opponentHref: opponent && hrefFor ? hrefFor(opponent) : undefined,
      opponentDeck: draft ? null : (opponent?.deck ?? null),
      result,
      games: gameWins + gameLosses > 0 ? formatRecord({ wins: gameWins, losses: gameLosses, draws: gameDraws }) : "",
    });
  });
  return history;
}

function pointsGroupRanks(source: StandingsSource, round: number): Map<ReplayPlayer, number> {
  const points = new Map<ReplayPlayer, number>();
  for (const player of source.players) {
    const record = recordThrough(player, round);
    points.set(player, record.wins * 3 + record.draws);
  }
  const ranks = new Map<ReplayPlayer, number>();
  for (const player of source.players) {
    const own = points.get(player) as number;
    let ahead = 0;
    for (const other of points.values()) {
      if (other > own) {
        ahead += 1;
      }
    }
    ranks.set(player, ahead + 1);
  }
  return ranks;
}

export function recordThrough(player: ReplayPlayer, round: number): MatchRecord {
  const record = { wins: 0, losses: 0, draws: 0 };
  for (const played of player.rounds.slice(0, round)) {
    if (played?.[0] === "W") {
      record.wins += 1;
    } else if (played?.[0] === "L") {
      record.losses += 1;
    } else if (played?.[0] === "D") {
      record.draws += 1;
    }
  }
  return record;
}

function toReplay(event: FantasyEventEntry, file: ReplayFile): EventReplay {
  const players = file.players.map((player) => ({ ...player, matchRecord: meleeRecord(player.matchRecord) }));
  const byRank = new Map(players.map((player) => [player.rank, player]));
  const seeded = players.filter((player) => player.rank <= 8);
  const results = {} as Required<BracketResults>;
  for (const match of BRACKET_MATCHES) {
    const played = file.bracket[match.key];
    results[match.key] = {
      winner: byRank.get(played.winner) as ReplayPlayer,
      loser: byRank.get(played.loser) as ReplayPlayer,
      games: played.games,
    };
  }
  const { bySlug, slugOf } = playerSlugs(players);
  return {
    event,
    header: { title: event.shortName.toUpperCase(), city: event.city.toUpperCase(), setCode: event.setCode },
    name: event.shortName,
    constructedFormat: event.constructedFormat,
    swissRounds: event.swissRounds,
    lastRound: event.swissRounds,
    cutRound: event.cutRound,
    draftRounds: event.draftRounds,
    players,
    seeded,
    results,
    byName: new Map(players.map((player) => [fullName(player), player])),
    byRank,
    bySlug,
    slugOf,
  };
}

export function playerSlugs(players: ReplayPlayer[]) {
  const bySlug = new Map<string, ReplayPlayer>();
  const slugOf = new Map<ReplayPlayer, string>();
  for (const player of players) {
    const base = playerSlug(player);
    const slug = !base ? `player-${player.rank}` : bySlug.has(base) ? `${base}-${player.rank}` : base;
    bySlug.set(slug, player);
    slugOf.set(player, slug);
  }
  return { bySlug, slugOf };
}

function meleeRecord(record: string): string {
  const [wins, losses, draws] = record.split("-").map(Number);
  return formatRecord({ wins, losses, draws });
}
