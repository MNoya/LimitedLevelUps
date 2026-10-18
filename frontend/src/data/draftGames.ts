import { useMemo } from "react";
import { useQueries } from "@tanstack/react-query";

import { fetchPodDraftArtifact, fetchPodEventParticipants } from "./api";
import { picksPerTurn, reconstructDraft, seatHandle } from "./draft-artifact";
import { useAllPodEvents, usePodSetCodes, useSets } from "./hooks";
import { orderedDeckColors } from "./utils";
import type { ArtifactCard, PodDraftArtifact, PodEventParticipantRow, PodEventSummary } from "../types/leaderboard";

export const DAILY_ROUNDS = 5;
export const CUBE_SET_CODE = "PEASANT";
const MIN_SET_PODS = 10;
export const WHEEL_CARD_POINTS = 1;
export const FIRST_PICK_POINTS = 3;
export const WHEEL_GAME_TITLE = "Wheel of Fortune";
export const WHEEL_GAME_ART = "/games/wheel-of-fortune/wheel-art.webp";
export const TROPHY_GAME_TITLE = "Trophy Mage";
export const MINI_GAMES_HEADER = "MINI GAMES";

export type RoundMark = "hit" | "close" | "miss";

export interface WheelPick {
  card: number;
  drafter: string;
  drafterSlug: string | null;
  deckColors: string;
  seat: number;
  trophy: boolean;
  madeDeck: boolean | null;
}

export interface WheelPack {
  eventId: string;
  eventSlug: string;
  setCode: string;
  cards: ArtifactCard[];
  pack: number[];
  order: WheelPick[];
  wheel: number[];
  seats: number;
}

export interface WheelSetOption {
  code: string;
  name: string;
  pods: number;
  releaseDate: string | null;
}

export interface WheelScore {
  points: number;
  max: number;
  baseline: number;
  firstPickExact: boolean;
  wheelCalled: number;
  mark: RoundMark;
}

export function utcDayKey(now: Date = new Date()): string {
  return now.toISOString().slice(0, 10);
}

export function dayNumber(dayKey: string): number {
  const firstDay = Date.UTC(2026, 9, 15);
  return Math.round((Date.parse(`${dayKey}T00:00:00Z`) - firstDay) / 86_400_000) + 1;
}

export function msUntilNextDay(now: Date = new Date()): number {
  const tomorrow = Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate() + 1);
  return tomorrow - now.getTime();
}

export function seededShuffle<T>(list: T[], seed: number): T[] {
  const out = [...list];
  let state = seed % 233280;
  for (let i = out.length - 1; i > 0; i--) {
    state = (state * 9301 + 49297) % 233280;
    const j = Math.floor((state / 233280) * (i + 1));
    [out[i], out[j]] = [out[j], out[i]];
  }
  return out;
}

export function setShortLabel(code: string): string {
  if (code.length <= 4) {
    return code;
  }
  return code.charAt(0) + code.slice(1).toLowerCase();
}

export function shortDayLabel(dayKey: string): string {
  return new Date(`${dayKey}T00:00:00Z`).toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    timeZone: "UTC",
  });
}

export function ordinal(n: number): string {
  return `${n}${ordinalSuffix(n)}`;
}

export function ordinalSuffix(n: number): string {
  const suffixes = ["th", "st", "nd", "rd"];
  const tens = n % 100;
  return tens >= 11 && tens <= 13 ? "th" : (suffixes[n % 10] ?? "th");
}

export function isTrophyRecord(record: string | null): boolean {
  return Boolean(record && record.startsWith("3-"));
}

export function scoreWheel(pack: WheelPack, slots: number[]): WheelScore {
  const firstPickExact = slots[0] === pack.order[0].card;
  const slotted = new Set(slots);
  const wheelCalled = pack.wheel.filter((card) => !slotted.has(card)).length;
  const points = wheelCalled * WHEEL_CARD_POINTS + (firstPickExact ? FIRST_PICK_POINTS : 0);
  const max = pack.wheel.length * WHEEL_CARD_POINTS + FIRST_PICK_POINTS;
  const baseline = randomBaseline(pack);
  return { points, max, baseline, firstPickExact, wheelCalled, mark: wheelMark(points - baseline) };
}

export function useWheelSets(): { sets: WheelSetOption[]; events: PodEventSummary[]; isPending: boolean } {
  const { data: allEvents, isPending } = useAllPodEvents(true);
  const { data: setSummaries } = useSets();
  const { data: podSetCodes } = usePodSetCodes();
  return useMemo(() => {
    const events = wheelEvents(allEvents);
    const bySet = new Map<string, PodEventSummary[]>();
    for (const event of events) {
      bySet.set(event.setCode, [...(bySet.get(event.setCode) ?? []), event]);
    }
    const sets: WheelSetOption[] = [];
    for (const [code, setEvents] of bySet) {
      if (setEvents.length < MIN_SET_PODS) {
        continue;
      }
      const summary = setSummaries?.find((set) => set.code === code);
      const podLabel = podSetCodes?.find((set) => set.code === code)?.label;
      const name = summary?.name ?? podLabel ?? code;
      sets.push({ code, name, pods: setEvents.length, releaseDate: summary?.startDate ?? null });
    }
    sets.sort(byNewestRelease);
    return { sets: withCubeSecond(sets), events, isPending };
  }, [allEvents, setSummaries, podSetCodes, isPending]);
}

export function useFeaturedSetCodes(dayKey: string): string[] {
  const { events, sets } = useWheelSets();
  const seed = dayNumber(dayKey) * 7919;
  return useMemo(() => {
    const codes: string[] = [];
    for (const slot of featuredSlots(events, sets, dayKey, seed)) {
      if (slot.length > 0) {
        codes.push(slot[0].setCode);
      }
    }
    return codes;
  }, [events, sets, dayKey, seed]);
}

export function useFeaturedPacks(dayKey: string): { packs: WheelPack[]; isPending: boolean } {
  const { events, sets, isPending: setsPending } = useWheelSets();
  const seed = dayNumber(dayKey) * 7919;
  const slots = useMemo(() => featuredSlots(events, sets, dayKey, seed), [events, sets, dayKey, seed]);
  const slotPacks = usePackSlots(slots, seed);
  const loaded = slotPacks.every((pack) => pack !== undefined);
  const packs = useMemo(() => slotPacks.filter((pack): pack is WheelPack => pack != null), [slotPacks]);
  return { packs, isPending: setsPending || !loaded };
}

export function useFreePlayPacks(
  setCode: string,
  wanted: number,
  seed: number,
): { packs: WheelPack[]; isPending: boolean; exhausted: boolean } {
  const { events, isPending: setsPending } = useWheelSets();
  const shuffled = useMemo(
    () =>
      seededShuffle(
        events.filter((event) => event.setCode === setCode),
        seed,
      ),
    [events, setCode, seed],
  );
  const lookahead = 4;
  const slots = useMemo(() => shuffled.slice(0, wanted + lookahead).map((event) => [event]), [shuffled, wanted]);
  const slotPacks = usePackSlots(slots, seed);
  const packs: WheelPack[] = [];
  let resolved = true;
  for (const pack of slotPacks) {
    if (pack === undefined) {
      resolved = false;
      break;
    }
    if (pack) {
      packs.push(pack);
    }
  }
  const isPending = setsPending || (!resolved && packs.length < wanted);
  const consumedAll = slots.length === shuffled.length;
  const exhausted = !setsPending && resolved && consumedAll && packs.length < wanted;
  return { packs, isPending, exhausted };
}

function usePackSlots(slots: PodEventSummary[][], seed: number): (WheelPack | null | undefined)[] {
  const flat = useMemo(() => slots.flat(), [slots]);
  const artifacts = useQueries({
    queries: flat.map((event) => ({
      queryKey: ["pod-draft-artifact", event.eventId],
      queryFn: () => fetchPodDraftArtifact(event.eventId),
      staleTime: Infinity,
    })),
    combine: settledData,
  });
  const participants = useParticipants(flat);
  return useMemo(() => {
    let offset = 0;
    return slots.map((candidates, slotIndex) => {
      let result: WheelPack | null | undefined = null;
      for (let k = 0; k < candidates.length; k++) {
        const artifact = artifacts[offset + k];
        const people = participants[offset + k];
        if (artifact === undefined || people === undefined) {
          result = undefined;
          break;
        }
        if (artifact && picksPerTurn(artifact) === 1) {
          result = buildWheelPack(candidates[k], artifact, people ?? [], seed + slotIndex);
          break;
        }
      }
      offset += candidates.length;
      return result;
    });
  }, [slots, artifacts, participants, seed]);
}

function featuredSlots(
  events: PodEventSummary[],
  sets: WheelSetOption[],
  dayKey: string,
  seed: number,
): PodEventSummary[][] {
  const settled = events.filter((event) => event.eventDate < dayKey);
  const eligible = sets.filter((set) => settled.filter((event) => event.setCode === set.code).length >= MIN_SET_PODS);
  if (eligible.length === 0) {
    return [];
  }
  const isEligible = (code: string | undefined): code is string => eligible.some((set) => set.code === code);
  const latestSet = settled.find((event) => event.setCode !== CUBE_SET_CODE)?.setCode;
  const others = seededShuffle(
    eligible.map((set) => set.code).filter((code) => code !== latestSet && code !== CUBE_SET_CODE),
    seed,
  );
  const order: string[] = [];
  for (const code of [latestSet, latestSet, CUBE_SET_CODE, CUBE_SET_CODE, CUBE_SET_CODE]) {
    order.push(isEligible(code) ? code : (others[order.length % Math.max(others.length, 1)] ?? eligible[0].code));
  }
  const slots: PodEventSummary[][] = [];
  for (let slot = 0; slot < DAILY_ROUNDS; slot++) {
    const setCode = order[slot];
    const used = new Set(slots.flat().map((event) => event.eventId));
    const pool = settled.filter((event) => event.setCode === setCode && !used.has(event.eventId));
    slots.push(seededShuffle(pool, seed + slot).slice(0, 3));
  }
  return slots;
}

function useParticipants(events: PodEventSummary[]) {
  return useQueries({
    queries: events.map((event) => ({
      queryKey: ["pod-event-participants", event.eventId],
      queryFn: () => fetchPodEventParticipants(event.eventId),
      staleTime: Infinity,
    })),
    combine: settledData,
  });
}

function withCubeSecond(sets: WheelSetOption[]): WheelSetOption[] {
  const cube = sets.find((set) => set.code === CUBE_SET_CODE);
  if (!cube) {
    return sets;
  }
  const rest = sets.filter((set) => set !== cube);
  return [...rest.slice(0, 1), cube, ...rest.slice(1)];
}

function byNewestRelease(a: WheelSetOption, b: WheelSetOption): number {
  if (a.releaseDate === b.releaseDate) {
    return b.pods - a.pods;
  }
  if (!a.releaseDate) {
    return 1;
  }
  if (!b.releaseDate) {
    return -1;
  }
  return a.releaseDate < b.releaseDate ? 1 : -1;
}

function settledData<T>(results: { data: T | undefined; isPending: boolean }[]): (T | null | undefined)[] {
  return results.map((result) => (result.isPending ? undefined : (result.data ?? null)));
}

function playableEvents(events: PodEventSummary[] | undefined): PodEventSummary[] {
  return (events ?? []).filter(
    (event) => event.kind === "tournament" && event.isFinalized && !event.isTeamDraft && !event.closedDecklist,
  );
}

function wheelEvents(events: PodEventSummary[] | undefined): PodEventSummary[] {
  return playableEvents(events).filter((event) => event.participantCount >= 6 && event.participantCount <= 8);
}

function randomBaseline(pack: WheelPack): number {
  const leftOutShare = pack.wheel.length / pack.pack.length;
  const firstPickChance = 1 / pack.pack.length;
  return pack.wheel.length * leftOutShare * WHEEL_CARD_POINTS + firstPickChance * FIRST_PICK_POINTS;
}

function wheelMark(pointsAboveRandom: number): RoundMark {
  if (pointsAboveRandom >= 2) {
    return "hit";
  }
  if (pointsAboveRandom >= -0.5) {
    return "close";
  }
  return "miss";
}

function buildWheelPack(
  event: PodEventSummary,
  artifact: PodDraftArtifact,
  participants: PodEventParticipantRow[],
  seed: number,
): WheelPack {
  const seats = artifact.seats.length;
  const opener = seed % seats;
  const views = reconstructDraft(artifact);
  const first = views[opener][0][0].booster;
  let remaining = [...first];
  const order: WheelPick[] = [];
  for (let turn = 0; turn < seats; turn++) {
    for (let seat = 0; seat < seats; seat++) {
      const view = views[seat][0][turn];
      const sameSize = view && view.booster.length === remaining.length;
      const samePack = sameSize && view.booster.every((c) => remaining.includes(c));
      if (samePack) {
        const card = view.takenCards[0];
        const participant = seatParticipant(artifact.seats[seat], participants);
        order.push({
          card,
          drafter: participant?.playerDisplayName ?? seatHandle(participant?.displayName ?? artifact.seats[seat]),
          drafterSlug: participant?.playerSlug ?? null,
          deckColors: orderedDeckColors(participant?.deckColors),
          seat,
          trophy: isTrophyRecord(participant?.record ?? null),
          madeDeck: artifact.decks ? artifact.decks[seat].main.includes(card) : null,
        });
        remaining = remaining.filter((c) => c !== card);
        break;
      }
    }
  }
  return {
    eventId: event.eventId,
    eventSlug: event.slug,
    setCode: event.setCode,
    cards: artifact.cards,
    pack: event.setCode === CUBE_SET_CODE ? first : byRarity(first, artifact.cards),
    order,
    wheel: remaining,
    seats,
  };
}

function byRarity(cards: number[], table: ArtifactCard[]): number[] {
  const rank = (card: number) => {
    const rarity = table[card].r?.toLowerCase() ?? "";
    const index = ["mythic", "rare", "uncommon", "common"].indexOf(rarity);
    return index < 0 ? 4 : index;
  };
  return [...cards].sort((a, b) => rank(a) - rank(b));
}

function seatParticipant(seatName: string, participants: PodEventParticipantRow[]): PodEventParticipantRow | null {
  for (const participant of participants) {
    if (participant.draftmancerName === seatName) {
      return participant;
    }
  }
  return null;
}
