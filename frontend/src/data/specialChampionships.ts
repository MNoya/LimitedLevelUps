import type { PodChampionshipLinksRow } from "../types/leaderboard";

export interface SpecialChampionship {
  eventId: string;
  setCode: string;
  title: string;
  threadId: string;
  vodUrl: string;
  podEventIds: string[];
}

export const SPECIAL_CHAMPIONSHIPS: SpecialChampionship[] = [
  {
    eventId: "4e15afa9-d144-4275-8df5-5e08d8080f53",
    setCode: "DSK",
    title: "Duskmourn Halloween Champion",
    threadId: "1566144689118118039",
    vodUrl: "https://www.youtube.com/watch?v=h6jl_J7NqeE",
    podEventIds: [
      "e20828a1-09c1-4df6-adf2-383bc3867671",
      "926c1fb5-0c2d-4d0b-9658-3a86ba3401d6",
      "bd29d000-3f6c-4068-9a95-16b1a2f838ef",
    ],
  },
];

export const SPECIAL_CHAMPIONSHIP_EVENT_IDS: ReadonlySet<string> = new Set(
  SPECIAL_CHAMPIONSHIPS.flatMap((special) => [special.eventId, ...special.podEventIds]),
);

export function specialChampionship(eventId: string): SpecialChampionship | undefined {
  for (const special of SPECIAL_CHAMPIONSHIPS) {
    if (special.eventId === eventId) {
      return special;
    }
  }
  return undefined;
}

export function specialChampionshipPodNumber(eventId: string): number | null {
  for (const special of SPECIAL_CHAMPIONSHIPS) {
    const index = special.podEventIds.indexOf(eventId);
    if (index !== -1) {
      return index + 1;
    }
  }
  return null;
}

export function specialChampionshipLinks(): PodChampionshipLinksRow[] {
  return SPECIAL_CHAMPIONSHIPS.map(({ eventId, setCode, threadId, vodUrl }) => ({
    eventId,
    setCode,
    threadId,
    vodUrl,
  }));
}
