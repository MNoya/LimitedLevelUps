import { useMemo } from "react";
import { BreakdownList } from "./BreakdownList";
import type { BreakdownRow } from "./BreakdownList";
import { SLOTS } from "../../data/p0p1Slots";
import { GIH_SAMPLE_FLOOR } from "../../data/p0p1Results";
import type { CardRating, GihwrBounds } from "../../data/p0p1Results";
import type { Card, P0P1PickStat, SlotKey } from "../../types/p0p1";

export function MidwayBreakdownList({
  cards,
  cardsByName,
  ratingsByName,
  yourCardBySlot,
  pickStats,
  bounds,
  setCode,
}: {
  cards: Card[];
  cardsByName: Map<string, Card>;
  ratingsByName: Map<string, CardRating>;
  yourCardBySlot: Map<SlotKey, string>;
  pickStats: P0P1PickStat[];
  bounds: GihwrBounds;
  setCode?: string;
}) {
  const pickedBySlot = useMemo(() => {
    const map = new Map<SlotKey, Set<string>>();
    for (const stat of pickStats) {
      const set = map.get(stat.slot) ?? new Set<string>();
      set.add(stat.cardName);
      map.set(stat.slot, set);
    }
    return map;
  }, [pickStats]);

  // Build per-slot rows with raw gihwr for the global scale computation
  const rawBySlot = useMemo(() => {
    const empty = new Set<string>();
    return new Map(
      SLOTS.map((slot) => {
        const picked = pickedBySlot.get(slot.key) ?? new Set<string>();
        const eligible = cards.filter((c) => slot.filter(c, empty) && picked.has(c.name));
        const rows = eligible.map((c) => {
          const r = ratingsByName.get(c.name);
          const gihwr = r && r.gih >= GIH_SAMPLE_FLOOR && r.gihwr !== null ? r.gihwr : null;
          return { card: c, gihwr, isYours: yourCardBySlot.get(slot.key) === c.name };
        });
        rows.sort((a, b) => {
          if (a.gihwr !== null && b.gihwr !== null) return b.gihwr - a.gihwr;
          if (a.gihwr !== null) return -1;
          if (b.gihwr !== null) return 1;
          return 0;
        });
        return [slot.key as SlotKey, rows] as const;
      }),
    );
  }, [cards, ratingsByName, yourCardBySlot, pickedBySlot]);

  const bySlot = useMemo(() => {
    const span = bounds.max - bounds.min;
    return new Map(
      [...rawBySlot.entries()].map(([slotKey, rows]) => {
        const breakdownRows: BreakdownRow[] = rows.map((row) => ({
          name: row.card.name,
          card: cardsByName.get(row.card.name),
          isYours: row.isYours,
          fillPct:
            row.gihwr !== null
              ? span > 0
                ? Math.max(((row.gihwr - bounds.min) / span) * 100, 3)
                : 100
              : 0,
          value: (
            <span className={`font-mono tabular-nums text-[13px] font-semibold ${row.gihwr !== null ? "text-text" : "text-muted"}`}>
              {row.gihwr !== null ? `${(row.gihwr * 100).toFixed(1)}%` : "—"}
            </span>
          ),
        }));
        return [slotKey, breakdownRows] as const;
      }),
    );
  }, [rawBySlot, bounds, cardsByName]);

  return <BreakdownList title="GIH WINRATE BREAKDOWN" bySlot={bySlot} setCode={setCode} />;
}
