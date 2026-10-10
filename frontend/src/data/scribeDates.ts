import calendar from "../../../scribe_calendar.json";
import type { SetSummary } from "../types/leaderboard";
import { isRealSeasonSet } from "./utils";

export interface ScribeDate {
  label: string;
  start: number;
  end: number;
  live: boolean;
  playIn: boolean;
}

export interface SetDates {
  setEnd: number;
  dates: ScribeDate[];
}

interface RawScribeEvent {
  title: string;
  tags: { slug: string }[];
  utc_start_date: string;
  utc_end_date: string;
}

const STANDING_QUEUES = ["Premier Draft", "Traditional Draft", "Pick-Two Draft", "Sealed", "Traditional Sealed"];
const LIMITED_TAGS = ["limited", "draft", "sealed"];
const SKIPPED_TAGS = ["welcome-decks", "constructed", "digital-release"];

export function setDates(set: SetSummary, sets: SetSummary[], now: number): SetDates | null {
  const events = (calendar as RawScribeEvent[]).filter(isArenaLimited);
  const premier = events.find((e) => isReleasePremier(e, set));
  if (!premier) {
    return null;
  }
  const setStart = parseUtc(premier.utc_start_date);
  const setEnd = parseUtc(premier.utc_end_date);
  if (now < setStart || now >= setEnd) {
    return null;
  }

  const dates: ScribeDate[] = [];
  for (const event of events) {
    const start = parseUtc(event.utc_start_date);
    const end = parseUtc(event.utc_end_date);
    const outsideSet = end <= now || start >= setEnd;
    if (outsideSet || isStandingQueue(event.title, set.name)) {
      continue;
    }
    const label = shortLabel(event.title, sets);
    const playIn = event.tags.some((t) => t.slug === "play-in");
    dates.push({ label, start, end, live: start <= now, playIn });
  }
  dates.sort((a, b) => a.start - b.start || a.end - b.end);
  return { setEnd, dates };
}

function isArenaLimited(event: RawScribeEvent): boolean {
  const tags = event.tags.map((t) => t.slug);
  if (!tags.includes("arena") || tags.some((t) => SKIPPED_TAGS.includes(t))) {
    return false;
  }
  return tags.some((t) => LIMITED_TAGS.includes(t));
}

function isReleasePremier(event: RawScribeEvent, set: SetSummary): boolean {
  const opensOnRelease = event.utc_start_date.startsWith(set.startDate);
  return opensOnRelease && event.title === `Premier Draft: ${set.name}`;
}

function isStandingQueue(title: string, setName: string): boolean {
  return STANDING_QUEUES.some((queue) => title === `${queue}: ${setName}`);
}

function shortLabel(title: string, sets: SetSummary[]): string {
  let label = title
    .replace("Arena Limited Championship Qualifier", "Arena LCQ")
    .replace(/^Premier Draft: (.+ Alchemy)$/, "$1")
    .replace(/^ACQ /, "")
    .replace(" (Bonus)", "")
    .replace(/ Sealed$/, "");
  for (const s of sets.filter(isRealSeasonSet)) {
    label = label.replace(s.name, s.code);
  }
  return label;
}

function parseUtc(value: string): number {
  return Date.parse(`${value.replace(" ", "T")}Z`);
}
