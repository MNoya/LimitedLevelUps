import { describe, expect, it } from "vitest";

import { CUBE_SET_CODE, type WheelSetOption } from "./draftGames";
import { dealDailySlots, scoreTrophyRound, type TrophyCalls, type TrophyMageRound } from "./trophyMage";
import type { PodEventSummary } from "../types/leaderboard";

const DAY = "2026-10-18";
const LATEST_SET = "FRA";
const FLASHBACK_SETS = ["HOB", "MSH", "SOS"];

describe("dealDailySlots", () => {
  it("deals the latest set, then Cube, then a flashback set", () => {
    const events = podHistory();
    const sets = setOptions(events);

    for (let seed = 1; seed <= 25; seed++) {
      const slots = dealDailySlots(events, sets, DAY, seed);

      expect(setsIn(slots[0])).toEqual([LATEST_SET]);
      expect(setsIn(slots[1])).toEqual([CUBE_SET_CODE]);
      expect(FLASHBACK_SETS).toContain(setsIn(slots[2])[0]);
    }
  });

  it("only deals latest set Pods that are at least a week old", () => {
    const events = podHistory();
    const sets = setOptions(events);

    for (let seed = 1; seed <= 25; seed++) {
      const slots = dealDailySlots(events, sets, DAY, seed);

      for (const event of slots[0]) {
        expect(event.eventDate <= "2026-10-11").toBe(true);
      }
    }
  });

  it("never deals a Pod from the day itself or later", () => {
    const events = podHistory();
    const sets = setOptions(events);

    const slots = dealDailySlots(events, sets, DAY, 7);

    for (const event of slots.flat()) {
      expect(event.eventDate < DAY).toBe(true);
    }
  });
});

describe("scoreTrophyRound", () => {
  const cases: { name: string; calls: TrophyCalls; points: number }[] = [
    { name: "right 3-0 and every record", calls: callsOf("trophy", { a: "2-1", b: "0-3" }), points: 4 },
    { name: "right 3-0 only", calls: callsOf("trophy", {}), points: 2 },
    { name: "wrong 3-0 with one right record", calls: callsOf("a", { b: "0-3" }), points: 1 },
    { name: "no calls", calls: callsOf(null, {}), points: 0 },
  ];

  for (const { name, calls, points } of cases) {
    it(`scores ${name}`, () => {
      const round = threeDeckRound();

      const score = scoreTrophyRound(round, calls);

      expect(score.points).toBe(points);
      expect(score.max).toBe(4);
    });
  }
});

function podHistory(): PodEventSummary[] {
  const events: PodEventSummary[] = [];
  for (let i = 0; i < 20; i++) {
    events.push(pod(LATEST_SET, daysBefore(DAY, i * 2)));
  }
  for (const setCode of [CUBE_SET_CODE, ...FLASHBACK_SETS]) {
    for (let i = 0; i < 12; i++) {
      events.push(pod(setCode, daysBefore("2026-09-01", i * 3)));
    }
  }
  events.sort((a, b) => b.eventDate.localeCompare(a.eventDate));
  return events;
}

function setOptions(events: PodEventSummary[]): WheelSetOption[] {
  const codes = [...new Set(events.map((event) => event.setCode))];
  return codes.map((code) => ({
    code,
    name: code,
    pods: events.filter((event) => event.setCode === code).length,
    releaseDate: null,
  }));
}

function setsIn(slot: PodEventSummary[]): string[] {
  return [...new Set(slot.map((event) => event.setCode))];
}

let podCount = 0;

function pod(setCode: string, eventDate: string): PodEventSummary {
  podCount += 1;
  return {
    eventId: `pod-${podCount}`,
    slug: `pod-${podCount}`,
    name: `Pod ${podCount}`,
    setCode,
    kind: "tournament",
    eventDate,
    eventTime: `${eventDate}T20:00:00Z`,
    formatLabel: null,
    totalRounds: 3,
    championPlayerSlug: null,
    championDisplayName: null,
    championAvatarUrl: null,
    championDeckColors: null,
    championRecord: "3-0",
    participantCount: 8,
    isFinalized: true,
  };
}

function daysBefore(dayKey: string, days: number): string {
  return new Date(Date.parse(`${dayKey}T00:00:00Z`) - days * 86_400_000).toISOString().slice(0, 10);
}

function threeDeckRound(): TrophyMageRound {
  const deck = (key: string, record: "3-0" | "2-1" | "0-3") => ({
    key,
    displayName: key,
    participantDisplayName: key,
    playerSlug: null,
    seatIndex: null,
    deckColors: "",
    record,
    deckScreenshotUrl: "",
  });
  return {
    eventId: "pod",
    eventSlug: "pod",
    eventName: "Pod",
    setCode: LATEST_SET,
    eventDate: DAY,
    decks: [deck("trophy", "3-0"), deck("a", "2-1"), deck("b", "0-3")],
  };
}

function callsOf(crown: string | null, records: TrophyCalls["records"]): TrophyCalls {
  return { crown, records };
}
