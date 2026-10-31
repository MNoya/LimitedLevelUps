import { describe, expect, it } from "vitest";

import { scoreWheel, type WheelPack } from "./draftGames";

describe("scoreWheel", () => {
  it.each([
    { seats: 6, packSize: 14, worstWheelPoints: 0, bestWheelPoints: 6 },
    { seats: 8, packSize: 15, worstWheelPoints: 0, bestWheelPoints: 7 },
    { seats: 8, packSize: 14, worstWheelPoints: 0, bestWheelPoints: 6 },
  ])("gives no free wheel points at a $seats-seat table", ({ seats, packSize, worstWheelPoints, bestWheelPoints }) => {
    const pack = wheelPack(seats, packSize);
    const realPicks = pack.order.map((pick) => pick.card);
    const mostWheelCardsPicked = pack.wheel.concat(realPicks).slice(0, seats);
    const realPicksWrongFirst = [...realPicks].reverse();

    const worst = scoreWheel(pack, mostWheelCardsPicked);
    const best = scoreWheel(pack, realPicksWrongFirst);

    expect(worst.points).toBe(worstWheelPoints);
    expect(best.points).toBe(bestWheelPoints);
  });
});

function wheelPack(seats: number, packSize: number): WheelPack {
  const pack = Array.from({ length: packSize }, (_, card) => card);
  return {
    eventId: "event",
    eventSlug: "event",
    setCode: "FRA",
    cards: [],
    pack,
    order: pack.slice(0, seats).map((card) => ({ card }) as WheelPack["order"][number]),
    wheel: pack.slice(seats),
    seats,
  };
}
