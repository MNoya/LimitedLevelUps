// Synthetic ballots for dev previews and mock mode: ~100 popularity-weighted
// ballots derived from pick stats, 90 complete + 10 partial so partial-sum
// ranking is exercised.

import type { P0P1BallotRow, P0P1PickStat, SlotKey } from "../types/p0p1";
import { slotsForSet } from "./p0p1Slots";

export function syntheticBallotsFromStats(
  pickStats: P0P1PickStat[],
  setCode: string,
): P0P1BallotRow[] {
  let seed = 777;
  const rng = () => { seed = (seed * 1103515245 + 12345) & 0x7fffffff; return seed / 0x7fffffff; };
  const TOTAL = 100;
  const PARTIAL_START = TOTAL - 10;

  const statsBySlot = new Map<SlotKey, P0P1PickStat[]>();
  for (const stat of pickStats) {
    const arr = statsBySlot.get(stat.slot) ?? [];
    arr.push(stat);
    statsBySlot.set(stat.slot, arr);
  }

  const rows: P0P1BallotRow[] = [];
  const slots = slotsForSet(setCode);

  for (let ballotId = 1; ballotId <= TOTAL; ballotId++) {
    const isPartial = ballotId > PARTIAL_START;
    const usedCards = new Set<string>();

    for (const { key: slot } of slots) {
      if (isPartial && rng() < 0.4) continue;

      const candidates = statsBySlot.get(slot) ?? [];
      if (candidates.length === 0) continue;

      const total = candidates.reduce((s, c) => s + c.pickCount, 0);
      let threshold = rng() * total;
      let picked: string | null = null;
      for (const stat of candidates) {
        threshold -= stat.pickCount;
        if (threshold <= 0 && !usedCards.has(stat.cardName)) {
          picked = stat.cardName;
          break;
        }
      }
      if (!picked) {
        for (const stat of candidates) {
          if (!usedCards.has(stat.cardName)) { picked = stat.cardName; break; }
        }
      }
      if (picked) {
        usedCards.add(picked);
        rows.push({
          setCode,
          ballotId,
          name: `Player ${ballotId}`,
          avatarUrl: null,
          slot,
          cardName: picked,
        });
      }
    }
  }

  return rows;
}
