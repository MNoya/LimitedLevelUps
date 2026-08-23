import type { ReactNode } from "react";
import { CommunityGrid } from "./CommunityGrid";
import { FullBreakdownList } from "./FullBreakdownList";
import type { Card, P0P1PickStat } from "../../types/p0p1";
import type { ContestChipInfo } from "../../data/p0p1Slots";

export function PostVotingStats({
  pickStats,
  cardsByName,
  picksBySlot,
  setCode,
  yourPicks,
  contests,
  onContestChange,
}: {
  pickStats: P0P1PickStat[];
  cardsByName: Map<string, Card>;
  picksBySlot?: Map<string, string>;
  setCode?: string;
  yourPicks?: ReactNode;
  contests?: ContestChipInfo[];
  onContestChange?: (code: string) => void;
}) {
  return (
    <div className="flex flex-col gap-3 lg:gap-6">
      {yourPicks}
      <CommunityGrid pickStats={pickStats} cardsByName={cardsByName} picksBySlot={picksBySlot} setCode={setCode} contests={contests} onContestChange={onContestChange} />
      <FullBreakdownList pickStats={pickStats} cardsByName={cardsByName} picksBySlot={picksBySlot} setCode={setCode} />
    </div>
  );
}
