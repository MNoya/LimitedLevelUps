import { SLOTS, fullName, type FieldPlayer, type Lineup, type SlotKey } from "./fantasyField";
import { playerPoints } from "./fantasyScoring";
import { liveBracketResults, type LiveEvent } from "./fantasyLive";
import {
  BRACKET_KEY,
  bracketScore,
  top8Bonus,
  type BracketPicks,
  type BracketResults,
  type GameScore,
} from "./fantasyTop8";
import type { FantasyBracketPickRow, FantasyLineupRow, FantasyMemberRow } from "../../types/fantasy";

export type Member = {
  name: string;
  isSelf: boolean;
  dayOneLineup: Lineup;
  lineup: Lineup;
  bracket: BracketPicks;
  savedOrder: number;
};

export type SlotBreakdown = {
  slot: SlotKey;
  dayOne: FieldPlayer;
  current: FieldPlayer;
  day1: number;
  day2: number;
  top8: number;
  total: number;
};

export type MemberStanding = {
  member: Member;
  rank: number;
  day1: number;
  day2: number;
  top8: number;
  total: number;
  bracketPoints: number | null;
  championCalled: boolean;
  slots: SlotBreakdown[];
};

export type StandingsDay = "overall" | "day1" | "day2" | "top8";

export type EventContext = {
  live: LiveEvent;
  results: BracketResults | null;
};

export function eventContext(live: LiveEvent): EventContext {
  return { live, results: liveBracketResults(live) };
}

export function membersFromRows(
  live: LiveEvent,
  members: FantasyMemberRow[],
  lineups: FantasyLineupRow[],
  brackets: FantasyBracketPickRow[],
): Member[] {
  return members.map((row, order) => {
    const dayOneLineup: Lineup = {};
    const lineup: Lineup = {};
    const currentFrom = new Map<string, number>();
    for (const pick of lineups) {
      const player = live.byId.get(pick.playerId);
      if (pick.memberKey !== row.memberKey || !player) {
        continue;
      }
      const slot = pick.slot as SlotKey;
      if (pick.fromRound === 1) {
        dayOneLineup[slot] = player;
      }
      if (pick.fromRound >= (currentFrom.get(slot) ?? 0)) {
        lineup[slot] = player;
        currentFrom.set(slot, pick.fromRound);
      }
    }
    const bracket: BracketPicks = {};
    for (const pick of brackets) {
      const winner = live.byId.get(pick.winnerId);
      const key = BRACKET_KEY[pick.position];
      if (pick.memberKey === row.memberKey && winner && key) {
        bracket[key] = { winner: fullName(winner), games: (pick.games ?? undefined) as GameScore | undefined };
      }
    }
    return { name: row.name, isSelf: row.isMe, dayOneLineup, lineup, bracket, savedOrder: order };
  });
}


export function standings(members: Member[], context: EventContext): MemberStanding[] {
  const rows = members.map((member) => memberStanding(member, context));
  rows.sort(
    (a, b) =>
      b.total - a.total ||
      Number(b.championCalled) - Number(a.championCalled) ||
      a.member.savedOrder - b.member.savedOrder,
  );
  rows.forEach((row, index) => {
    row.rank = index + 1;
  });
  return rows;
}

export function dayPoints(row: MemberStanding, day: StandingsDay): number {
  if (day === "day1") {
    return row.day1;
  }
  if (day === "day2") {
    return row.day2;
  }
  if (day === "top8") {
    return row.top8;
  }
  return row.total;
}

export function slotDayPoints(slot: SlotBreakdown, day: StandingsDay): number {
  if (day === "day1") {
    return slot.day1;
  }
  if (day === "day2") {
    return slot.day2;
  }
  if (day === "top8") {
    return slot.top8;
  }
  return slot.total;
}

function memberStanding(member: Member, context: EventContext): MemberStanding {
  const slots: SlotBreakdown[] = [];
  for (const slot of SLOTS) {
    const dayOne = member.dayOneLineup[slot.key];
    const current = member.lineup[slot.key];
    if (!dayOne || !current) {
      continue;
    }
    slots.push(slotBreakdown(slot.key, dayOne, current, context));
  }
  let day1 = 0;
  let day2 = 0;
  let top8 = 0;
  for (const slot of slots) {
    day1 += slot.day1;
    day2 += slot.day2;
    top8 += slot.top8;
  }
  const bracketPoints = context.results ? bracketScore(member.bracket, context.results) : null;
  const champion = context.results?.final ? fullName(context.results.final.winner) : null;
  const championCalled = champion !== null && member.bracket.final?.winner === champion;
  const sunday = top8 + (bracketPoints ?? 0);
  const total = day1 + day2 + sunday;
  return { member, rank: 0, day1, day2, top8: sunday, total, bracketPoints, championCalled, slots };
}

function slotBreakdown(slot: SlotKey, dayOne: FieldPlayer, current: FieldPlayer, context: EventContext): SlotBreakdown {
  const { live } = context;
  const dayOneEnd = Math.min(live.roundsPlayed, live.cutRound);
  const day1 = playerPoints(live, dayOne, slot, 1, dayOneEnd);
  const day2 = playerPoints(live, current, slot, live.cutRound + 1, live.roundsPlayed);
  const topEightOpen = live.phase === "top8" || live.phase === "final";
  const top8 = topEightOpen ? top8Bonus(current, live.seeded, context.results) : 0;
  return { slot, dayOne, current, day1, day2, top8, total: day1 + day2 + top8 };
}
