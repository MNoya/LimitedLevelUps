import { createContext, useContext } from "react";
import type { FantasyEventState } from "../../types/fantasy";
import { formatEventDays } from "./eventDays";
import registry from "../../../../fantasy_events.json";

export type FantasyEventEntry = {
  code: string;
  name: string;
  slug: string;
  shortName: string;
  title?: string;
  setCode: string;
  city: string;
  startDate: string;
  endDate: string;
  constructedFormat: string;
  swissRounds: number;
  cutRound: number;
  draftRounds: number[];
  meleeTournamentId?: number;
  crest?: string;
  replayOnly?: boolean;
  live?: boolean;
  picksLockAt: string;
  bracketLockAt: string;
};

export const FANTASY_EVENTS: FantasyEventEntry[] = Object.entries(registry)
  .map(([code, config]) => ({ code, ...config }))
  .sort((a, b) => b.startDate.localeCompare(a.startDate));

export function fantasyEventBySlug(slug: string | undefined): FantasyEventEntry | undefined {
  return FANTASY_EVENTS.find((event) => event.slug === slug);
}

export const PRO_PLAY_BASE = "/pro-play";

export function fantasyEventByCode(code: string): FantasyEventEntry | undefined {
  return FANTASY_EVENTS.find((event) => event.code === code);
}

export function fantasyEventPath(event: FantasyEventEntry): string {
  return `${PRO_PLAY_BASE}/${event.slug}`;
}

export function currentFantasyEvent(now: Date): FantasyEventEntry {
  const navEvent = fantasyNavEvent(now);
  if (navEvent) {
    return navEvent;
  }
  for (const event of FANTASY_EVENTS) {
    if (event.startDate <= isoDay(now)) {
      return event;
    }
  }
  return FANTASY_EVENTS[FANTASY_EVENTS.length - 1];
}

export function proPlayHomeEvent(now: Date): FantasyEventEntry {
  for (const event of [...FANTASY_EVENTS].reverse()) {
    if (event.meleeTournamentId && !event.replayOnly && picksOpen(event, now)) {
      return event;
    }
  }
  return currentFantasyEvent(now);
}

export function meleeEventUrl(code: string): string | undefined {
  const event = FANTASY_EVENTS.find((entry) => entry.code === code);
  if (!event?.meleeTournamentId) {
    return undefined;
  }
  return `https://melee.gg/Tournament/View/${event.meleeTournamentId}`;
}

export type FantasyEventHeader = {
  code: string;
  title: string;
  shortName: string;
  city: string;
  setCode: string;
  constructedFormat: string;
  crestUrl?: string;
  crestAlt: string;
  picksLockAt: Date;
  bracketLockAt: Date;
};

export function fantasyEventHeader(event: FantasyEventEntry): FantasyEventHeader {
  return {
    code: event.code,
    title: event.title ?? event.shortName.toUpperCase(),
    shortName: event.shortName,
    city: event.city.toUpperCase(),
    setCode: event.setCode,
    constructedFormat: event.constructedFormat,
    crestUrl: event.crest,
    crestAlt: event.name,
    picksLockAt: new Date(event.picksLockAt),
    bracketLockAt: new Date(event.bracketLockAt),
  };
}

export function eventDays(event: FantasyEventEntry, now: Date): string {
  const sameYearAsNow = new Date(`${event.endDate}T12:00:00Z`).getUTCFullYear() === now.getFullYear();
  return formatEventDays(event, !sameYearAsNow);
}

const NAV_DAYS_AFTER = 7;

export function fantasyNavEvent(now: Date): FantasyEventEntry | undefined {
  const day = 24 * 60 * 60 * 1000;
  for (const event of FANTASY_EVENTS) {
    if (event.replayOnly || !event.live) {
      continue;
    }
    const opens = oneMonthBefore(event.startDate).getTime();
    const closes = new Date(`${event.endDate}T23:59:59Z`).getTime() + NAV_DAYS_AFTER * day;
    if (now.getTime() >= opens && now.getTime() <= closes) {
      return event;
    }
  }
  return undefined;
}

export function fantasyNavLabel(event: FantasyEventEntry, now: Date, state: FantasyEventState | null): string {
  if (now.getTime() < new Date(state?.picksLockAt ?? event.picksLockAt).getTime()) {
    return "OPEN";
  }
  if (!state) {
    return isEventLive(event, now) ? "LIVE" : "RESULTS";
  }
  const revealed = state.revealedThroughRound ?? 0;
  const top8Stages = 3;
  if (revealed >= event.swissRounds + top8Stages) {
    return "RESULTS";
  }
  if (revealed >= event.swissRounds) {
    return "TOP 8";
  }
  return `ROUND ${revealed + 1}`;
}


export function switcherTag(event: FantasyEventEntry, now: Date): "LIVE" | "NEXT UP" | undefined {
  if (isEventLive(event, now)) {
    return "LIVE";
  }
  return event.code === nextUpFantasyEvent(now)?.code ? "NEXT UP" : undefined;
}

export function nextUpFantasyEvent(now: Date): FantasyEventEntry | undefined {
  let next: FantasyEventEntry | undefined;
  for (const event of FANTASY_EVENTS) {
    if (picksOpen(event, now) && (!next || event.startDate < next.startDate)) {
      next = event;
    }
  }
  return next;
}

function picksOpen(event: FantasyEventEntry, now: Date): boolean {
  return now.getTime() < new Date(event.picksLockAt).getTime();
}

function isEventLive(event: FantasyEventEntry, now: Date): boolean {
  return !picksOpen(event, now) && now.getTime() <= new Date(`${event.endDate}T23:59:59Z`).getTime();
}

export const FantasyEventContext = createContext<FantasyEventHeader>(
  fantasyEventHeader(currentFantasyEvent(new Date())),
);

export function useFantasyEvent(): FantasyEventHeader {
  return useContext(FantasyEventContext);
}

function oneMonthBefore(isoDate: string): Date {
  const date = new Date(`${isoDate}T00:00:00Z`);
  date.setUTCMonth(date.getUTCMonth() - 1);
  return date;
}

function isoDay(date: Date): string {
  return date.toISOString().slice(0, 10);
}

