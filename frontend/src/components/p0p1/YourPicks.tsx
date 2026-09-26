import { SectionLabel } from "../SectionLabel";
import { PickGrid, type PickEntry } from "./CommunityGrid";
import { groupBySlot, findExtremes, classifyYourPick } from "../../data/p0p1Stats";
import type { Card, P0P1PickStat, SlotDefinition } from "../../types/p0p1";

export function YourPicks({
  contestSlots,
  pickStats,
  cardsByName,
  picksBySlot,
  setCode,
  compact = false,
}: {
  contestSlots: SlotDefinition[];
  pickStats: P0P1PickStat[];
  cardsByName: Map<string, Card>;
  picksBySlot: Map<string, string>;
  setCode?: string;
  compact?: boolean;
}) {
  const entries = yourPickEntries(contestSlots, pickStats, picksBySlot);

  return (
    <div>
      <div className="flex items-baseline justify-center gap-2 mb-1.5 lg:mb-2">
        <SectionLabel size={22} className="text-white">YOUR PICKS</SectionLabel>
      </div>
      <PickGrid
        entries={entries}
        cardsByName={cardsByName}
        picksBySlot={picksBySlot}
        setCode={setCode}
        compact={compact}
      />
    </div>
  );
}

function yourPickEntries(
  contestSlots: SlotDefinition[],
  pickStats: P0P1PickStat[],
  picksBySlot: Map<string, string>,
): PickEntry[] {
  const grouped = groupBySlot(pickStats);
  return contestSlots.map((slot) => {
    const cardName = picksBySlot.get(slot.key);
    const slotStats = grouped.get(slot.key) ?? [];
    const yourStat = cardName ? slotStats.find((s) => s.cardName === cardName) : undefined;
    const extremes = findExtremes(slotStats);
    const classification = yourStat ? classifyYourPick(yourStat, extremes.most, extremes.least) : undefined;
    return {
      slotKey: slot.key,
      label: slot.label,
      stats: yourStat ? [yourStat] : [],
      slotStats,
      badge: classification?.state === "rogue" ? classification.qualifier : undefined,
    };
  });
}
