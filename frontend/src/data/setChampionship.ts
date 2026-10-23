import { DISCORD_GUILD_ID } from "./site";
import { isChampionshipEvent, stripDiscriminator } from "./utils";
import type { PodEventMatchRow, PodEventParticipantRow } from "../types/leaderboard";

export const HALL_OF_FAME_PATH = "/hall-of-fame";

export const hallOfFameSetHref = (setCode: string) => `${HALL_OF_FAME_PATH}/${setCode}`;

export type PodView = `pod-${number}`;

export type ChampionshipView = "table" | "bracket" | "top8" | PodView;

const VIEW_SEGMENTS: Record<"bracket" | "top8", string> = { bracket: "bracket", top8: "top-8" };

export function podView(pod: number): PodView {
  return `pod-${pod}`;
}

export function isPodView(view: string): view is PodView {
  return /^pod-\d+$/.test(view);
}

export function championshipPodNumber(name: string): number | null {
  const match = name.match(/\bpod\s+(\d+)\s*$/i);
  return match ? Number(match[1]) : null;
}

export function championshipViewHref(setCode: string, view: ChampionshipView): string {
  if (view === "table") {
    return hallOfFameSetHref(setCode);
  }
  const segment = isPodView(view) ? view : VIEW_SEGMENTS[view];
  return `${hallOfFameSetHref(setCode)}/${segment}`;
}

export function championshipViewFromSegment(segment: string | undefined): ChampionshipView | null {
  if (!segment) {
    return "table";
  }
  if (isPodView(segment)) {
    return segment;
  }
  for (const [view, path] of Object.entries(VIEW_SEGMENTS)) {
    if (path === segment) {
      return view as ChampionshipView;
    }
  }
  return null;
}

const SKIPPED_WINNER = "(skipped)";

export interface SwissGroup {
  wins: number;
  losses: number;
  isFinal: boolean;
  matches: PodEventMatchRow[];
}

export interface SwissRound {
  round: number;
  groups: SwissGroup[];
}

export function buildSwissRounds(matches: PodEventMatchRow[], totalRounds: number): SwissRound[] {
  const played = matches.filter((match) => match.winnerName !== SKIPPED_WINNER);
  const rounds: SwissRound[] = [];
  for (let round = 1; round <= totalRounds; round++) {
    const earlier = played.filter((match) => match.round < round);
    const groups = new Map<string, SwissGroup>();
    for (const match of played.filter((entry) => entry.round === round)) {
      const { wins, losses } = recordOf(earlier, match.playerAName);
      const key = `${wins}-${losses}`;
      const isFinal = round === totalRounds && losses === 0;
      const group = groups.get(key) ?? { wins, losses, isFinal, matches: [] };
      group.matches.push(match);
      groups.set(key, group);
    }
    const ordered = [...groups.values()].sort((a, b) => b.wins - a.wins || a.losses - b.losses);
    rounds.push({ round, groups: ordered });
  }
  return rounds;
}

export interface ChampionshipBracket {
  quarterfinals: (PodEventMatchRow | undefined)[];
  semifinals: (PodEventMatchRow | undefined)[];
  final: PodEventMatchRow | undefined;
}

export function buildChampionshipBracket(rounds: SwissRound[]): ChampionshipBracket {
  const roundOne = rounds[0]?.groups.flatMap((group) => group.matches) ?? [];
  const semifinals = rounds[1]?.groups.find((group) => group.losses === 0)?.matches ?? [];
  const final = rounds[rounds.length - 1]?.groups.find((group) => group.isFinal)?.matches[0];

  const quarterfinals: (PodEventMatchRow | undefined)[] = [];
  for (const semifinal of [semifinals[0], semifinals[1]]) {
    for (const name of semifinal ? [semifinal.playerAName, semifinal.playerBName] : [null, null]) {
      quarterfinals.push(name ? roundOne.find((match) => involves(match, name)) : undefined);
    }
  }
  const unplaced = roundOne.filter((match) => !quarterfinals.includes(match));
  for (let index = 0; index < quarterfinals.length; index++) {
    if (!quarterfinals[index]) {
      quarterfinals[index] = unplaced.shift();
    }
  }
  return { quarterfinals, semifinals: [semifinals[0], semifinals[1]], final };
}

export function championOf(rounds: SwissRound[]): string | null {
  const lastRound = rounds[rounds.length - 1];
  const final = lastRound?.groups.find((group) => group.isFinal)?.matches[0];
  return final?.winnerName ?? null;
}

export function isChampionshipLive(event: { eventTime: string; isFinalized: boolean }, now = Date.now()): boolean {
  return !event.isFinalized && new Date(event.eventTime).getTime() <= now;
}

export function isStartingOrLive(event: { eventTime: string; isFinalized: boolean }): boolean {
  const halfHour = 30 * 60 * 1000;
  return isChampionshipLive(event, Date.now() + halfHour);
}

export function isLiveChampionship(event: { name: string; eventTime: string; isFinalized: boolean } | null | undefined) {
  return !!event && isChampionshipEvent(event.name) && isChampionshipLive(event);
}

export function championshipThreadUrl(threadId: string | null): string | null {
  return threadId ? `https://discord.com/channels/${DISCORD_GUILD_ID}/${threadId}` : null;
}

export const CHAMPIONSHIP_SEATS = 8;
export const CHAMPIONSHIP_INVITE_DEPTH = 32;

export type ChampionshipRsvp = "yes" | "maybe" | "no";

export interface ChampionshipEntrant {
  rank: number;
  slug: string | null;
  displayName: string;
  avatarUrl: string | null;
  score: number;
  trophies: number | null;
  wildcard: boolean;
  rsvp: ChampionshipRsvp | null;
}

export function projectChampionshipSeats(entrants: ChampionshipEntrant[]): ChampionshipEntrant[] {
  const byRank = [...entrants].sort((a, b) => a.rank - b.rank);
  const confirmed = byRank.filter((entrant) => entrant.rsvp === "yes");
  const undecided = byRank.filter((entrant) => entrant.rsvp === null || entrant.rsvp === "maybe");
  return holdWildcardSeat([...confirmed, ...undecided]).slice(0, CHAMPIONSHIP_SEATS);
}

export function pickPodWildcard(
  board: { slug: string; rank: number }[],
  podStandings: { slug: string }[],
): string | null {
  const boardRanks = new Map<string, number>();
  for (const row of board) {
    boardRanks.set(row.slug, row.rank);
  }
  for (const standing of podStandings) {
    const rank = boardRanks.get(standing.slug);
    if (rank === undefined || rank > CHAMPIONSHIP_SEATS) {
      return standing.slug;
    }
  }
  return null;
}

export function formatChampionshipDay(day: string): string {
  const date = new Date(`${day.slice(0, 10)}T12:00:00`);
  return date.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
}

export function participantByName(participants: PodEventParticipantRow[]): Map<string, PodEventParticipantRow> {
  const byName = new Map<string, PodEventParticipantRow>();
  for (const participant of participants) {
    byName.set(participant.displayName, participant);
  }
  return byName;
}

export function playerLabel(participant: PodEventParticipantRow | undefined, fallbackName: string): string {
  return stripDiscriminator(participant?.playerDisplayName ?? participant?.displayName ?? fallbackName);
}

export function gamesWon(match: PodEventMatchRow, name: string): number | null {
  if (!match.winnerName || !match.score) {
    return null;
  }
  const [winnerGames, loserGames] = match.score.split("-").map(Number);
  return match.winnerName === name ? winnerGames : loserGames;
}

function holdWildcardSeat(ranked: ChampionshipEntrant[]): ChampionshipEntrant[] {
  const wildcards = ranked.filter((entrant) => entrant.wildcard);
  if (wildcards.length === 0) {
    return ranked;
  }
  const rest = ranked.filter((entrant) => !entrant.wildcard);
  const cut = Math.max(0, CHAMPIONSHIP_SEATS - wildcards.length);
  return [...rest.slice(0, cut), ...wildcards, ...rest.slice(cut)];
}

function involves(match: PodEventMatchRow, name: string): boolean {
  return match.playerAName === name || match.playerBName === name;
}

function recordOf(matches: PodEventMatchRow[], name: string): { wins: number; losses: number } {
  let wins = 0;
  let losses = 0;
  for (const match of matches) {
    if (!involves(match, name)) {
      continue;
    }
    if (match.winnerName === name) {
      wins += 1;
    } else if (match.winnerName) {
      losses += 1;
    }
  }
  return { wins, losses };
}
