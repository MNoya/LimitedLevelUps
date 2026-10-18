import { useEffect, useState } from "react";

import type { TrophyCalls, TrophyMageRound } from "../../../data/trophyMage";

export interface TrophyDay {
  advanced: number;
  current: number;
  drafts: Record<string, TrophyCalls>;
  locked: Record<string, TrophyCalls>;
}

const EMPTY_DAY: TrophyDay = { advanced: 0, current: 0, drafts: {}, locked: {} };

export function trophyDayStorageKey(dayKey: string): string {
  return `trophy-mage-daily:${dayKey}`;
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
    return startAt == null ? saved : { ...saved, current: startAt };
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
