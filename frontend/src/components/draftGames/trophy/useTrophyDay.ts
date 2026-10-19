import { useEffect, useState } from "react";

import { TROPHY_DAILY_ROUNDS, type TrophyCalls, type TrophyMageRound } from "../../../data/trophyMage";

export interface TrophyDay {
  advanced: number;
  current: number;
  drafts: Record<string, TrophyCalls>;
  locked: Record<string, TrophyCalls>;
}

const EMPTY_DAY: TrophyDay = { advanced: 0, current: 0, drafts: {}, locked: {} };
const OPEN_DAYS = 3;
const DAY_MS = 86_400_000;

export function trophyDayStorageKey(dayKey: string): string {
  return `trophy-mage-daily:${dayKey}`;
}

export function nextOpenDay(todayKey: string, currentKey: string | null): string | null {
  for (let offset = 0; offset < OPEN_DAYS; offset++) {
    const key = daysBefore(todayKey, offset);
    if (key === currentKey) {
      continue;
    }
    const saved = readTrophyDay(trophyDayStorageKey(key));
    if (!saved || saved.advanced < TROPHY_DAILY_ROUNDS) {
      return key;
    }
  }
  return null;
}

export function daysBefore(dayKey: string, days: number): string {
  return new Date(Date.parse(`${dayKey}T12:00:00Z`) - days * DAY_MS).toISOString().slice(0, 10);
}

export function readTrophyDay(storageKey: string): TrophyDay | null {
  const raw = localStorage.getItem(storageKey);
  if (!raw) {
    return null;
  }
  try {
    return { ...EMPTY_DAY, ...(JSON.parse(raw) as Partial<TrophyDay>) };
  } catch {
    return null;
  }
}

export function useTrophyDay(storageKey: string | null, rounds: TrophyMageRound[], startAt: number | null = null) {
  const [day, setDay] = useState<TrophyDay>(() => {
    const saved = storageKey ? readMatchingDay(storageKey, rounds) : EMPTY_DAY;
    if (startAt != null) {
      return { ...saved, current: startAt };
    }
    const firstOpen = rounds.findIndex((round) => !saved.locked[round.eventId]);
    return firstOpen >= 0 ? { ...saved, current: firstOpen } : saved;
  });

  useEffect(() => {
    if (storageKey) {
      localStorage.setItem(storageKey, JSON.stringify(day));
    }
  }, [storageKey, day]);

  const setDraft = (eventId: string, calls: TrophyCalls) =>
    setDay((d) => ({ ...d, drafts: { ...d.drafts, [eventId]: calls } }));
  const lockIn = (eventId: string, calls: TrophyCalls) =>
    setDay((d) => ({ ...d, locked: { ...d.locked, [eventId]: calls } }));
  const goTo = (index: number) => setDay((d) => ({ ...d, current: index }));
  const advance = () => setDay((d) => ({ ...d, advanced: d.advanced + 1, current: d.advanced + 1 }));
  const finish = () => setDay((d) => ({ ...d, advanced: rounds.length }));
  return { day, setDraft, lockIn, goTo, advance, finish };
}

function readMatchingDay(storageKey: string, rounds: TrophyMageRound[]): TrophyDay {
  const saved = readTrophyDay(storageKey);
  if (!saved) {
    return EMPTY_DAY;
  }
  const eventIds = new Set(rounds.map((round) => round.eventId));
  const matches = Object.keys(saved.locked).every((eventId) => eventIds.has(eventId));
  return matches ? saved : EMPTY_DAY;
}
