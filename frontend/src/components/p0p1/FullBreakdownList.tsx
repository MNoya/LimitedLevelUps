import { useMemo } from "react";
import { BreakdownList } from "./BreakdownList";
import type { BreakdownRow } from "./BreakdownList";
import { groupBySlot, participantCount } from "../../data/p0p1Stats";
import { SLOTS } from "../../data/p0p1Slots";
import type { Card, P0P1PickStat, SlotKey } from "../../types/p0p1";

export function FullBreakdownList({
  pickStats,
  cardsByName,
  picksBySlot,
  setCode,
}: {
  pickStats: P0P1PickStat[];
  cardsByName: Map<string, Card>;
  picksBySlot?: Map<string, string>;
  setCode?: string;
}) {
  const bySlot = useMemo(() => {
    const grouped = groupBySlot(pickStats);
    return new Map(
      SLOTS.map((slot) => {
        const stats = [...(grouped.get(slot.key) ?? [])].sort((a, b) => b.pickCount - a.pickCount);
        const topPct = stats.length ? stats[0].pickPct : 0;
        const rows: BreakdownRow[] = stats.map((stat) => ({
          name: stat.cardName,
          card: cardsByName.get(stat.cardName),
          isYours: picksBySlot?.get(slot.key) === stat.cardName,
          fillPct: topPct > 0 ? Math.max((stat.pickPct / topPct) * 100, 3) : 0,
          value: (
            <span className="font-mono tabular-nums text-[16px] font-semibold text-text w-8 text-right">
              {stat.pickCount}
            </span>
          ),
        }));
        return [slot.key as SlotKey, rows] as const;
      }),
    );
  }, [pickStats, cardsByName, picksBySlot]);

  const entryCount = useMemo(() => participantCount(pickStats), [pickStats]);

  return (
    <BreakdownList
      title="FULL BREAKDOWN"
      headerAside={`${entryCount} player${entryCount !== 1 ? "s" : ""}`}
      bySlot={bySlot}
      setCode={setCode}
    />
  );
}
