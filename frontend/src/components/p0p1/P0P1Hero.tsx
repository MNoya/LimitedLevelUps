import type { ReactNode, Ref } from "react";
import { SetGlyph } from "../Brand";
import { SectionLabel } from "../SectionLabel";
import { P0P1Countdown } from "./Countdown";
import { P0P1CountdownBar } from "./CountdownBar";
import { P0P1IntroText } from "./P0P1IntroText";
import type { FeaturedContest } from "../../data/p0p1Slots";
import type { P0P1Phase, RatingsSnapshot } from "../../data/p0p1Results";

export function P0P1Hero({
  featured,
  cta,
  innerRef,
  belowIntro,
  phase,
  dateRange,
}: {
  featured: FeaturedContest;
  cta: ReactNode;
  innerRef?: Ref<HTMLDivElement>;
  belowIntro?: ReactNode;
  phase: P0P1Phase;
  dateRange?: RatingsSnapshot["dateRange"];
}) {
  const isPastDeadline = phase !== "voting";
  return (
    <div ref={innerRef} className="sticky top-0 z-30 px-10 py-5 border-b border-border bg-surface flex flex-wrap items-center gap-x-8 gap-y-3">
      <SetGlyph code={featured.code} size={84} />
      <div className="shrink-0">
        <SectionLabel size={13}>PACK 0, PICK 1</SectionLabel>
        <div className="flex items-baseline gap-3.5 mt-0.5">
          <span className="font-display tracking-[0.04em]" style={{ fontSize: 56, lineHeight: 0.9 }}>
            {featured.code}
          </span>
          <span className="font-display text-[22px] text-muted tracking-[0.06em]">{featured.name.toUpperCase()}</span>
        </div>
        <div className="mono text-[11px] mt-1 flex items-center justify-between gap-x-6">
          <P0P1Countdown deadline={featured.votingDeadline} scoringDate={featured.scoringDate} size={11} phase={phase} />
          {phase === "final" && featured.next && (
            <span className="flex items-center gap-1.5 text-muted">
              NEXT
              <SetGlyph code={featured.next.code} size={14} className="text-white" />
              <span className="text-white">{featured.next.name}</span>
            </span>
          )}
        </div>
        {isPastDeadline && (
          <div className="w-full mt-2">
            <P0P1CountdownBar from={featured.votingDeadline} to={featured.scoringDate} />
          </div>
        )}
      </div>
      <div className="flex-1 min-w-0 self-stretch flex flex-col items-center justify-center gap-y-3">
        <p className="max-w-[580px] text-center text-subtle text-[14px] leading-[1.55]">
          <P0P1IntroText setName={featured.name} votingDeadline={featured.votingDeadline} scoringDate={featured.scoringDate} phase={phase} dateRange={dateRange} multiline />
        </p>
        {belowIntro}
      </div>
      <div className="shrink-0 ml-auto flex justify-end min-w-[280px]">{cta}</div>
    </div>
  );
}
