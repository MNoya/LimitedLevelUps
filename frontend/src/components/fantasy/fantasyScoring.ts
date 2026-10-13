import { SLOTS, formatRecord, fullName, type FieldPlayer, type Lineup, type SlotKey } from "./fantasyField";
import type { LiveEvent } from "./fantasyLive";

export type EventPhase = "picking" | "day1" | "cut" | "day2" | "top8" | "final";

export type RoundResult = "W" | "L" | "D";

const POINTS: Record<RoundResult, number> = { W: 3, D: 1, L: 0 };

export function roundResults(live: LiveEvent, player: FieldPlayer): (RoundResult | null)[] {
  const entry = live.byName.get(fullName(player));
  if (!entry) {
    return [];
  }
  return entry.rounds.slice(0, live.roundsPlayed).map((played) => played?.[0] ?? null);
}

export function madeDayTwo(live: LiveEvent, player: FieldPlayer): boolean {
  const results = roundResults(live, player);
  if (live.roundsPlayed > live.cutRound) {
    return results.length > live.cutRound;
  }
  const dayTwoMatchPoints = 12;
  let matchPoints = 0;
  for (const result of results.slice(0, live.cutRound)) {
    matchPoints += result ? POINTS[result] : 0;
  }
  return matchPoints >= dayTwoMatchPoints;
}

export function isOut(live: LiveEvent, player: FieldPlayer): boolean {
  return live.roundsPlayed >= live.cutRound && !madeDayTwo(live, player);
}

export function slotMultiplier(live: LiveEvent, slotKey: SlotKey, round: number): number {
  const draft = live.draftRounds.includes(round);
  if (slotKey === "captain") {
    return 2;
  }
  if (slotKey === "drafter") {
    return draft ? 3 : 0;
  }
  if (slotKey === "constructed") {
    return draft ? 0 : 2;
  }
  return 1;
}

export function playerPoints(
  live: LiveEvent,
  player: FieldPlayer,
  slotKey: SlotKey,
  fromRound: number,
  toRound: number,
): number {
  const results = roundResults(live, player);
  let total = 0;
  for (let round = fromRound; round <= toRound; round += 1) {
    const result = results[round - 1];
    total += result ? POINTS[result] * slotMultiplier(live, slotKey, round) : 0;
  }
  return total;
}

export function slotScore(live: LiveEvent, slotKey: SlotKey, dayOneLineup: Lineup, lineup: Lineup): number {
  const original = dayOneLineup[slotKey];
  const current = lineup[slotKey];
  if (!original || !current) {
    return 0;
  }
  if (fullName(original) === fullName(current)) {
    return playerPoints(live, current, slotKey, 1, live.roundsPlayed);
  }
  const dayOne = playerPoints(live, original, slotKey, 1, Math.min(live.roundsPlayed, live.cutRound));
  const dayTwo = playerPoints(live, current, slotKey, live.cutRound + 1, live.roundsPlayed);
  return dayOne + dayTwo;
}

export function lineupScore(live: LiveEvent, dayOneLineup: Lineup, lineup: Lineup): number {
  let total = 0;
  for (const slot of SLOTS) {
    total += slotScore(live, slot.key, dayOneLineup, lineup);
  }
  return total;
}

export function dayOneRecord(live: LiveEvent, player: FieldPlayer): string {
  return recordThrough(live, player, live.cutRound);
}

export function recordThrough(live: LiveEvent, player: FieldPlayer, lastRound: number = live.roundsPlayed): string {
  let wins = 0;
  let losses = 0;
  let draws = 0;
  for (const result of roundResults(live, player).slice(0, lastRound)) {
    if (result === "W") {
      wins += 1;
    } else if (result === "L") {
      losses += 1;
    } else if (result === "D") {
      draws += 1;
    }
  }
  return formatRecord({ wins, losses, draws });
}
