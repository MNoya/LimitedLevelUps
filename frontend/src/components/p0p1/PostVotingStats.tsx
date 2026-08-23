import type { ReactNode } from "react";
import { CommunityGrid } from "./CommunityGrid";
import { FullBreakdownList } from "./FullBreakdownList";
import type { Card, P0P1PickStat } from "../../types/p0p1";

export function PostVotingStats({
  pickStats,
  cardsByName,
  picksBySlot,
  setCode,
  yourPicks,
}: {
  pickStats: P0P1PickStat[];
  cardsByName: Map<string, Card>;
  picksBySlot?: Map<string, string>;
  setCode?: string;
  yourPicks?: ReactNode;
}) {
  return (
    <div className="flex flex-col gap-3 lg:gap-6">
      {yourPicks}
      <CommunityGrid pickStats={pickStats} cardsByName={cardsByName} picksBySlot={picksBySlot} setCode={setCode} />
      <FullBreakdownList pickStats={pickStats} cardsByName={cardsByName} picksBySlot={picksBySlot} setCode={setCode} />
    </div>
  );
}
