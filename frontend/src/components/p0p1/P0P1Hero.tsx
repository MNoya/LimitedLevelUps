import type { ReactNode, Ref } from "react";
import { SetGlyph } from "../Brand";
import { SectionLabel } from "../SectionLabel";
import { P0P1Countdown } from "./Countdown";
import { P0P1CountdownBar } from "./CountdownBar";
import { P0P1IntroText } from "./P0P1IntroText";
import { NextContestOpens } from "./NextContestOpens";
import { P0P1ContestDropdown } from "./P0P1ContestDropdown";
import type { FeaturedContest, ContestChipInfo } from "../../data/p0p1Slots";
import type { P0P1Phase, RatingsSnapshot } from "../../data/p0p1Results";

export function P0P1Hero({
  featured,
  contests,
  onContestChange,
  cta,
  innerRef,
  belowIntro,
  phase,
  dateRange,
  isCurrent,
}: {
  featured: FeaturedContest;
  contests: ContestChipInfo[];
  onContestChange: (code: string) => void;
  cta: ReactNode;
  innerRef?: Ref<HTMLDivElement>;
  belowIntro?: ReactNode;
  phase: P0P1Phase;
  dateRange?: RatingsSnapshot["dateRange"];
  isCurrent: boolean;
}) {
  const isPastDeadline = phase !== "voting" && phase !== "comingSoon";
  return (
    <div ref={innerRef} className="sticky top-0 z-30 relative px-10 py-5 border-b border-border bg-surface flex flex-wrap items-center gap-x-8 gap-y-3">
      <SetGlyph code={featured.code} size={84} />
      <div className="shrink-0">
        <SectionLabel size={13}>PACK 0, PICK 1</SectionLabel>
        <div className="flex items-baseline gap-3.5 mt-0.5">
          {contests.length > 1 ? (
            <P0P1ContestDropdown
              contests={contests}
              activeCode={featured.code}
              onSelect={onContestChange}
            />
          ) : (
            <>
              <span className="font-display tracking-[0.04em]" style={{ fontSize: 56, lineHeight: 0.9 }}>
                {featured.code}
              </span>
              <span className="font-display text-[22px] text-muted tracking-[0.06em]">{featured.name.toUpperCase()}</span>
            </>
          )}
        </div>
        <div className="font-mono text-[11px] mt-1 flex items-center justify-between gap-x-6">
          <P0P1Countdown deadline={featured.votingDeadline} scoringDate={featured.scoringDate} opensAt={featured.previewsOpen} size={11} phase={phase} isCurrent={isCurrent} />
        </div>
        {isPastDeadline && (
          <div className="w-full mt-2">
            <P0P1CountdownBar from={featured.votingDeadline} to={featured.scoringDate} phase={phase} />
          </div>
        )}
      </div>
      <div className="flex-1 min-w-0 flex flex-col items-center justify-center gap-2.5 xl:absolute xl:left-1/2 xl:top-1/2 xl:w-[580px] xl:-translate-x-1/2 xl:-translate-y-1/2 xl:flex-none">
        <p className="max-w-[580px] text-center text-subtle text-[14px] leading-[1.55]">
          <P0P1IntroText setName={featured.name} setCode={featured.code} phase={phase} dateRange={dateRange} multiline />
        </p>
        <div className="w-full flex justify-center text-subtle text-[14px]">
          {phase === "final" ? <NextContestOpens next={featured.next} /> : belowIntro}
        </div>
      </div>
      <div className="shrink-0 ml-auto flex justify-end min-w-[280px]">{cta}</div>
    </div>
  );
}
