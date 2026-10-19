import { useMemo } from "react";
import { useQueries } from "@tanstack/react-query";

import { fetchPodEventParticipants } from "./api";
import { seatHandle } from "./draft-artifact";
import { dayNumber, seededShuffle, useWheelSets, type RoundMark } from "./draftGames";
import { orderedDeckColors } from "./utils";
import type { PodEventParticipantRow, PodEventSummary } from "../types/leaderboard";

export const TROPHY_MAGE_TITLE = "Trophy Mage";
export const TROPHY_DAILY_ROUNDS = 3;
export const TROPHY_POINTS = 2;
export const RECORD_POINTS = 1;
export const TROPHY_RECORD = "3-0";
export const OTHER_RECORDS = ["2-1", "1-2", "0-3"] as const;
export const ALL_RECORDS = [TROPHY_RECORD, ...OTHER_RECORDS] as const;
export const TROPHY_MAGE_ART = "https://cards.scryfall.io/art/front/c/0/c08c5ac8-5c0b-4c89-8f06-e5aadfccee01.webp";

const CANDIDATES_PER_ROUND = 4;
const FREE_PLAY_LOOKAHEAD = 3;

export type TrophyRecord = (typeof ALL_RECORDS)[number];

export interface TrophyMageDeck {
  key: string;
  displayName: string;
  participantDisplayName: string;
  playerSlug: string | null;
  seatIndex: number | null;
  deckColors: string;
  record: TrophyRecord;
  deckScreenshotUrl: string;
}

export interface TrophyMageRound {
  eventId: string;
  eventSlug: string;
  eventName: string;
  setCode: string;
  eventDate: string;
  decks: TrophyMageDeck[];
}

export interface TrophyCalls {
  crown: string | null;
  records: Record<string, TrophyRecord>;
}

export interface TrophyScore {
  points: number;
  max: number;
  crowned: boolean;
  recordsRight: number;
}

export const EMPTY_CALLS: TrophyCalls = { crown: null, records: {} };

export function scoreTrophyRound(round: TrophyMageRound, calls: TrophyCalls): TrophyScore {
  const trophy = round.decks.find((deck) => deck.record === TROPHY_RECORD);
  const crowned = trophy != null && calls.crown === trophy.key;
  let recordsRight = 0;
  for (const deck of round.decks) {
    if (deck.record !== TROPHY_RECORD && calls.records[deck.key] === deck.record) {
      recordsRight += 1;
    }
  }
  const points = (crowned ? TROPHY_POINTS : 0) + recordsRight * RECORD_POINTS;
  const max = TROPHY_POINTS + (round.decks.length - 1) * RECORD_POINTS;
  return { points, max, crowned, recordsRight };
}

export function callFor(calls: TrophyCalls, deck: TrophyMageDeck): TrophyRecord | null {
  if (calls.crown === deck.key) {
    return TROPHY_RECORD;
  }
  return calls.records[deck.key] ?? null;
}

export function trophyMark(score: TrophyScore): RoundMark {
  if (score.crowned) {
    return "hit";
  }
  return score.recordsRight > 0 ? "close" : "miss";
}

export function useDailyTrophyRounds(dayKey: string): { rounds: TrophyMageRound[]; isPending: boolean } {
  const { events, isPending: eventsPending } = useWheelSets();
  const seed = dayNumber(dayKey) * 104729;
  const slots = useMemo(() => dailySlots(events, dayKey, seed), [events, dayKey, seed]);
  const resolved = useRoundSlots(slots, seed);
  const loaded = resolved.every((round) => round !== undefined);
  const rounds = useMemo(
    () => (loaded ? resolved.filter((round): round is TrophyMageRound => round != null) : []),
    [resolved, loaded],
  );
  return { rounds, isPending: eventsPending || !loaded };
}

export function useFreePlayTrophyRounds(
  setCode: string,
  wanted: number,
  seed: number,
): { rounds: TrophyMageRound[]; isPending: boolean; exhausted: boolean } {
  const { events, isPending: eventsPending } = useWheelSets();
  const shuffled = useMemo(
    () =>
      seededShuffle(
        events.filter((event) => event.setCode === setCode),
        seed,
      ),
    [events, setCode, seed],
  );
  const slots = useMemo(
    () => shuffled.slice(0, wanted + FREE_PLAY_LOOKAHEAD).map((event) => [event]),
    [shuffled, wanted],
  );
  const resolved = useRoundSlots(slots, seed);
  const rounds: TrophyMageRound[] = [];
  let settled = true;
  for (const round of resolved) {
    if (round === undefined) {
      settled = false;
      break;
    }
    if (round) {
      rounds.push(round);
    }
  }
  const isPending = eventsPending || (!settled && rounds.length < wanted);
  const exhausted = !eventsPending && settled && slots.length === shuffled.length && rounds.length < wanted;
  return { rounds, isPending, exhausted };
}

function dailySlots(events: PodEventSummary[], dayKey: string, seed: number): PodEventSummary[][] {
  const settled = events.filter((event) => event.eventDate < dayKey);
  const shuffled = seededShuffle(settled, seed);
  const bySet = new Map<string, PodEventSummary[]>();
  for (const event of shuffled) {
    const pods = bySet.get(event.setCode) ?? [];
    pods.push(event);
    bySet.set(event.setCode, pods);
  }
  const setPods = [...bySet.values()];
  const slots: PodEventSummary[][] = [];
  if (setPods.length === 0) {
    return slots;
  }
  for (let slot = 0; slot < TROPHY_DAILY_ROUNDS; slot++) {
    const pods = setPods[slot % setPods.length];
    const start = Math.floor(slot / setPods.length) * CANDIDATES_PER_ROUND;
    slots.push(pods.slice(start, start + CANDIDATES_PER_ROUND));
  }
  return slots;
}

function useRoundSlots(slots: PodEventSummary[][], seed: number): (TrophyMageRound | null | undefined)[] {
  const flat = useMemo(() => slots.flat(), [slots]);
  const participants = useQueries({
    queries: flat.map((event) => ({
      queryKey: ["pod-event-participants", event.eventId],
      queryFn: () => fetchPodEventParticipants(event.eventId),
      staleTime: Infinity,
    })),
    combine: (results) => results.map((result) => (result.isPending ? undefined : (result.data ?? null))),
  });
  return useMemo(() => {
    let offset = 0;
    return slots.map((candidates, slotIndex) => {
      let result: TrophyMageRound | null | undefined = null;
      for (let k = 0; k < candidates.length; k++) {
        const people = participants[offset + k];
        if (people === undefined) {
          result = undefined;
          break;
        }
        const round = buildRound(candidates[k], people ?? [], seed + slotIndex);
        if (round) {
          result = round;
          break;
        }
      }
      offset += candidates.length;
      return result;
    });
  }, [slots, participants, seed]);
}

function buildRound(event: PodEventSummary, participants: PodEventParticipantRow[], seed: number) {
  const withDeck = participants.filter((p) => p.deckScreenshotUrl && p.record);
  const trophy = withDeck.find((p) => p.record === TROPHY_RECORD);
  if (!trophy) {
    return null;
  }
  const others = seededShuffle(
    withDeck.filter((p) => OTHER_RECORDS.some((record) => record === p.record)),
    seed,
  );
  const othersWanted = 2;
  const picked: PodEventParticipantRow[] = [];
  for (const record of seededShuffle([...OTHER_RECORDS], seed * 5 + 1)) {
    const first = others.find((p) => p.record === record);
    if (first && picked.length < othersWanted) {
      picked.push(first);
    }
  }
  for (const other of others) {
    if (picked.length >= othersWanted) {
      break;
    }
    if (!picked.includes(other)) {
      picked.push(other);
    }
  }
  if (picked.length < othersWanted) {
    return null;
  }
  const decks = [trophy, ...picked].map((p) => toDeck(event, p));
  return {
    eventId: event.eventId,
    eventSlug: event.slug,
    eventName: event.name,
    setCode: event.setCode,
    eventDate: event.eventDate,
    decks: seededShuffle(decks, seed * 7 + 3),
  };
}

function toDeck(event: PodEventSummary, participant: PodEventParticipantRow): TrophyMageDeck {
  return {
    key: `${event.eventId}:${participant.displayName}`,
    displayName: participant.playerDisplayName ?? seatHandle(participant.displayName),
    participantDisplayName: participant.displayName,
    playerSlug: participant.playerSlug,
    seatIndex: participant.seatIndex,
    deckColors: orderedDeckColors(participant.deckColors),
    record: participant.record as TrophyRecord,
    deckScreenshotUrl: participant.deckScreenshotUrl!,
  };
}
