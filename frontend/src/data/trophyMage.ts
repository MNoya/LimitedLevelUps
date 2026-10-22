import { useMemo } from "react";
import { keepPreviousData, useQuery, useQueryClient, type QueryClient } from "@tanstack/react-query";

import { fetchPodEventsParticipants } from "./api";
import { seatHandle } from "./draft-artifact";
import {
  CUBE_SET_CODE,
  dayNumber,
  featuredSlots,
  seededShuffle,
  useWheelSets,
  type RoundMark,
  type WheelSetOption,
} from "./draftGames";
import { orderedDeckColors } from "./utils";
import type { PodEventParticipantRow, PodEventSummary } from "../types/leaderboard";

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

export function useDailyTrophyRounds(
  dayKey: string,
  enabled = true,
): { rounds: TrophyMageRound[]; isPending: boolean } {
  const { events, sets, isPending: eventsPending } = useWheelSets();
  const seed = dayNumber(dayKey) * 104729;
  const slots = useMemo(() => dealDailySlots(events, sets, dayKey, seed), [events, sets, dayKey, seed]);
  const resolved = useRoundSlots(slots, seed, enabled);
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

export function dealDailySlots(
  events: PodEventSummary[],
  sets: WheelSetOption[],
  dayKey: string,
  seed: number,
): PodEventSummary[][] {
  return featuredSlots(withoutFreshLatestSetPods(events, dayKey), sets, dayKey, seed, CANDIDATES_PER_ROUND);
}

function withoutFreshLatestSetPods(events: PodEventSummary[], dayKey: string): PodEventSummary[] {
  let latestSet: string | null = null;
  for (const event of events) {
    if (event.eventDate < dayKey && event.setCode !== CUBE_SET_CODE) {
      latestSet = event.setCode;
      break;
    }
  }
  const minAgeDays = 7;
  const newestAllowed = new Date(Date.parse(`${dayKey}T00:00:00Z`) - minAgeDays * 86_400_000)
    .toISOString()
    .slice(0, 10);
  return events.filter((event) => event.setCode !== latestSet || event.eventDate <= newestAllowed);
}

function useRoundSlots(
  slots: PodEventSummary[][],
  seed: number,
  enabled = true,
): (TrophyMageRound | null | undefined)[] {
  const queryClient = useQueryClient();
  const flat = useMemo(() => slots.flat(), [slots]);
  const eventIds = useMemo(() => flat.map((event) => event.eventId), [flat]);
  const { data: participantsByEvent } = useQuery({
    queryKey: ["pod-events-participants", eventIds],
    queryFn: () => fetchParticipantsByEvent(eventIds, queryClient),
    enabled: enabled && eventIds.length > 0,
    staleTime: Infinity,
    placeholderData: keepPreviousData,
  });
  const participants = useMemo(
    () => flat.map((event) => participantsByEvent?.get(event.eventId)),
    [flat, participantsByEvent],
  );
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
        const round = buildRound(candidates[k], people, seed + slotIndex);
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

async function fetchParticipantsByEvent(
  eventIds: string[],
  queryClient: QueryClient,
): Promise<Map<string, PodEventParticipantRow[]>> {
  const participantsByEvent = new Map<string, PodEventParticipantRow[]>();
  const missing: string[] = [];
  for (const eventId of eventIds) {
    const cached = queryClient.getQueryData<PodEventParticipantRow[]>(["pod-event-participants", eventId]);
    if (cached) {
      participantsByEvent.set(eventId, cached);
    } else {
      missing.push(eventId);
    }
  }
  const rows = await fetchPodEventsParticipants(missing);
  for (const eventId of missing) {
    const eventRows = rows.filter((row) => row.eventId === eventId);
    queryClient.setQueryData(["pod-event-participants", eventId], eventRows);
    participantsByEvent.set(eventId, eventRows);
  }
  return participantsByEvent;
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
