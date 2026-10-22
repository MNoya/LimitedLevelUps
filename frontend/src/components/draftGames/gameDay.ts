import { useEffect, useState } from "react";

import { daysBefore } from "../../data/draftGames";

export interface GameDay<Pick> {
  advanced: number;
  current: number;
  locked: Record<string, Pick>;
  drafts: Record<string, Pick>;
}

export interface GameDayRules<Pick, Round extends { eventId: string }> {
  storagePrefix: string;
  roundsPerDay: number;
  openDays: number;
  pickFitsRound?: (round: Round, pick: Pick) => boolean;
}

export function gameDayStorageKey(rules: { storagePrefix: string }, dayKey: string): string {
  return `${rules.storagePrefix}:${dayKey}`;
}

export function readGameDay<Pick, Round extends { eventId: string }>(
  rules: GameDayRules<Pick, Round>,
  dayKey: string,
): GameDay<Pick> | null {
  const raw = localStorage.getItem(gameDayStorageKey(rules, dayKey));
  if (!raw) {
    return null;
  }
  try {
    return withDefaults(JSON.parse(raw) as Partial<GameDay<Pick>>);
  } catch {
    return null;
  }
}

export function nextOpenGameDay<Pick, Round extends { eventId: string }>(
  rules: GameDayRules<Pick, Round>,
  todayKey: string,
  currentKey: string | null,
): string | null {
  for (let offset = 0; offset < rules.openDays; offset++) {
    const key = daysBefore(todayKey, offset);
    if (key === currentKey) {
      continue;
    }
    const saved = readGameDay(rules, key);
    if (!saved || saved.advanced < rules.roundsPerDay) {
      return key;
    }
  }
  return null;
}

export const PLAY_ACTION = "Play";
export const CONTINUE_ACTION = "Continue";
export const RESULTS_ACTION = "Results";
export const NEXT_DAY_ACTION = "Next";
export const ENDLESS_ACTION = "Endless";

export type NextPlay =
  { label: typeof NEXT_DAY_ACTION; dayKey: string } | { label: typeof ENDLESS_ACTION; setCode: string | null };

export function dayAction(rules: { roundsPerDay: number }, day: GameDay<unknown> | null): string {
  if (!day) {
    return PLAY_ACTION;
  }
  if (day.advanced >= rules.roundsPerDay) {
    return RESULTS_ACTION;
  }
  const started = Object.keys(day.locked).length + Object.keys(day.drafts).length > 0;
  return started ? CONTINUE_ACTION : PLAY_ACTION;
}

export function nextPlayAfter<Pick, Round extends { eventId: string }>(
  rules: GameDayRules<Pick, Round>,
  todayKey: string,
  currentKey: string | null,
  newestSet: string | undefined,
): NextPlay {
  const dayKey = nextOpenGameDay(rules, todayKey, currentKey);
  if (dayKey) {
    return { label: NEXT_DAY_ACTION, dayKey };
  }
  return { label: ENDLESS_ACTION, setCode: newestSet ?? null };
}

export function nextUnlockedIndex(
  rounds: { eventId: string }[],
  locked: Record<string, unknown>,
  from: number,
): number | null {
  for (let step = 1; step < rounds.length; step++) {
    const index = (from + step) % rounds.length;
    if (!locked[rounds[index].eventId]) {
      return index;
    }
  }
  return null;
}

export function useGameDay<Pick, Round extends { eventId: string }>(
  rules: GameDayRules<Pick, Round>,
  dayKey: string | null,
  rounds: Round[],
  startAt: "saved" | "firstOpen" | number = "saved",
) {
  const [day, setDay] = useState<GameDay<Pick>>(() => {
    const saved = dayKey ? readMatchingDay(rules, dayKey, rounds) : emptyDay<Pick>();
    if (typeof startAt === "number") {
      return { ...saved, current: startAt };
    }
    if (startAt === "firstOpen") {
      const firstOpen = rounds.findIndex((round) => !saved.locked[round.eventId]);
      return firstOpen >= 0 ? { ...saved, current: firstOpen } : saved;
    }
    return saved;
  });

  useEffect(() => {
    if (dayKey) {
      localStorage.setItem(gameDayStorageKey(rules, dayKey), JSON.stringify(day));
    }
  }, [rules, dayKey, day]);

  const setDraft = (eventId: string, pick: Pick) => setDay((d) => ({ ...d, drafts: { ...d.drafts, [eventId]: pick } }));
  const lockIn = (eventId: string, pick: Pick) =>
    setDay((d) => {
      const { [eventId]: _locked, ...drafts } = d.drafts;
      return { ...d, locked: { ...d.locked, [eventId]: pick }, drafts };
    });
  const goTo = (index: number) => setDay((d) => ({ ...d, current: index }));
  const advance = () => setDay((d) => ({ ...d, advanced: d.advanced + 1, current: d.advanced + 1 }));
  const finish = () => setDay((d) => ({ ...d, advanced: rounds.length }));
  return { day, setDraft, lockIn, goTo, advance, finish };
}

function readMatchingDay<Pick, Round extends { eventId: string }>(
  rules: GameDayRules<Pick, Round>,
  dayKey: string,
  rounds: Round[],
): GameDay<Pick> {
  const saved = readGameDay(rules, dayKey);
  if (!saved) {
    return emptyDay();
  }
  const roundsById = new Map(rounds.map((round) => [round.eventId, round]));
  for (const [eventId, pick] of Object.entries(saved.locked)) {
    const round = roundsById.get(eventId);
    if (!round || (rules.pickFitsRound && !rules.pickFitsRound(round, pick))) {
      return emptyDay();
    }
  }
  return saved;
}

function emptyDay<Pick>(): GameDay<Pick> {
  return { advanced: 0, current: 0, locked: {}, drafts: {} };
}

function withDefaults<Pick>(saved: Partial<GameDay<Pick>>): GameDay<Pick> {
  return {
    advanced: saved.advanced ?? 0,
    current: saved.current ?? saved.advanced ?? 0,
    locked: saved.locked ?? {},
    drafts: saved.drafts ?? {},
  };
}
