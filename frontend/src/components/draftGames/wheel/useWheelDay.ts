import { useEffect, useState } from "react";

import type { WheelPack } from "../../../data/draftGames";

export interface WheelDay {
  advanced: number;
  current: number;
  locked: Record<string, number[]>;
  drafts: Record<string, number[]>;
}

const EMPTY_DAY: WheelDay = { advanced: 0, current: 0, locked: {}, drafts: {} };

export function wheelDayStorageKey(dayKey: string): string {
  return `wheel-of-fortune-featured:${dayKey}`;
}

export function readFeaturedDay(dayKey: string): WheelDay | null {
  const raw = localStorage.getItem(wheelDayStorageKey(dayKey));
  if (!raw) {
    return null;
  }
  try {
    return withDefaults(JSON.parse(raw) as Partial<WheelDay>);
  } catch {
    return null;
  }
}

export function useWheelDay(storageKey: string | null, packs: WheelPack[]) {
  const [day, setDay] = useState<WheelDay>(() => (storageKey ? readDay(storageKey, packs) : EMPTY_DAY));

  useEffect(() => {
    if (storageKey) {
      localStorage.setItem(storageKey, JSON.stringify(day));
    }
  }, [storageKey, day]);

  const setDraft = (eventId: string, draft: number[]) =>
    setDay((d) => ({ ...d, drafts: { ...d.drafts, [eventId]: draft } }));
  const lockIn = (eventId: string, slots: number[]) =>
    setDay((d) => {
      const { [eventId]: _locked, ...drafts } = d.drafts;
      return { ...d, locked: { ...d.locked, [eventId]: slots }, drafts };
    });
  const goTo = (index: number) => setDay((d) => ({ ...d, current: index }));
  const advance = () => setDay((d) => ({ ...d, advanced: d.advanced + 1, current: d.advanced + 1 }));
  const finish = () => setDay((d) => ({ ...d, advanced: packs.length }));
  return { day, setDraft, lockIn, goTo, advance, finish };
}

function readDay(storageKey: string, packs: WheelPack[]): WheelDay {
  const raw = localStorage.getItem(storageKey);
  if (!raw) {
    return EMPTY_DAY;
  }
  try {
    const saved = withDefaults(JSON.parse(raw) as Partial<WheelDay>);
    const packCards = new Map(packs.map((pack) => [pack.eventId, new Set(pack.pack)]));
    const lockedEntries = Object.entries(saved.locked ?? {});
    const matchesPacks = lockedEntries.every(([eventId, slots]) => {
      const cards = packCards.get(eventId);
      return cards != null && slots.every((card) => cards.has(card));
    });
    return matchesPacks ? saved : EMPTY_DAY;
  } catch {
    return EMPTY_DAY;
  }
}

function withDefaults(saved: Partial<WheelDay>): WheelDay {
  return {
    advanced: saved.advanced ?? 0,
    current: saved.current ?? saved.advanced ?? 0,
    locked: saved.locked ?? {},
    drafts: saved.drafts ?? {},
  };
}
