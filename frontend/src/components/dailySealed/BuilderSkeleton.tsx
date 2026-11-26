import { Link } from "react-router-dom";

import { LLU_LOGO_SRC } from "../Brand";
import { cn } from "../../lib/utils";
import { FilterBlock } from "./controls";
import { Pane, Panel } from "./panels";
import { PILE_GAP } from "./piles";

const SIDE_PILE_SIZES = [13, 10, 14, 13, 15, 8, 9];
const DECK_PILE_COUNT = 8;
const PILE_COLUMNS = `repeat(${DECK_PILE_COUNT}, minmax(0, 220px))`;
const PHONE_STRIP_GROUPS = [5, 4, 6, 3];
const FILTER_SKELETONS = [
  { label: "COLOR", width: 200 },
  { label: "RARITY", width: 164 },
  { label: "TYPE", width: 80 },
  { label: "SEARCH", width: "100%" },
];

export const DesktopBuilderSkeleton = () => (
  <div className="flex h-full min-h-0 flex-col" aria-busy="true" aria-label="Loading the pool">
    <div className="flex h-12 shrink-0 items-center gap-4 border-b border-border px-3">
      <Link to="/tools" aria-label="Back to Tools" className="shrink-0">
        <img src={LLU_LOGO_SRC} alt="" className="h-8 w-8" />
      </Link>
      <Block className="h-[22px] w-[22px] rounded-full" />
      <h1 className="font-display text-[18px] leading-none tracking-[0.12em]">DAILY SEALED</h1>
      <Block className="h-3.5 w-44" />
      <Block className="h-3.5 w-36" />
      <div className="ml-auto flex items-center gap-1.5">
        {[72, 76, 64, 100, 150, 96].map((width, index) => (
          <Block key={index} className="h-9 rounded-md" style={{ width }} />
        ))}
      </div>
    </div>
    <div className="grid min-h-0 flex-1 grid-cols-[230px_minmax(0,1fr)]">
      <div className="flex min-h-0 flex-col overflow-hidden border-r border-border">
        <Panel title="FILTERS">
          <div className="flex flex-col gap-3">
            {FILTER_SKELETONS.map(({ label, width }) => (
              <FilterBlock key={label} label={label}>
                <Block className="h-8" style={{ width }} />
              </FilterBlock>
            ))}
          </div>
        </Panel>
        <Panel title="BASIC LANDS">
          <div className="grid grid-cols-5 gap-1.5">
            {Array.from({ length: 5 }, (_, index) => (
              <Block key={index} className="h-[104px]" />
            ))}
          </div>
          <Block className="mt-2 h-[28px] w-full" />
        </Panel>
        <Panel title="DECK">
          <Block className="h-[136px] w-full" />
        </Panel>
      </div>
      <div className="grid min-h-0 grid-rows-[minmax(0,3fr)_minmax(0,2fr)]">
        <Pane
          zone="side"
          title={<h2 className="font-display text-[15px] tracking-[0.18em]">SIDEBOARD</h2>}
          count={null}
          controls={<SortSkeleton />}
          extra={<Block className="h-8 w-24" />}
        >
          <PileRow sizes={SIDE_PILE_SIZES} />
        </Pane>
        <Pane
          zone="deck"
          title={<h2 className="font-display text-[15px] tracking-[0.18em]">DECK</h2>}
          count={null}
          controls={<SortSkeleton />}
          extra={<Block className="h-8 w-48" />}
        >
          <PileRow sizes={Array.from({ length: DECK_PILE_COUNT }, () => 0)} />
        </Pane>
      </div>
    </div>
  </div>
);

export const PhoneBuilderSkeleton = () => (
  <div className="flex flex-col pb-[60px]" aria-busy="true" aria-label="Loading the pool">
    <div className="flex items-center justify-between gap-2 px-2 pt-2">
      <Block className="h-3 w-40" />
      <Block className="h-3 w-28" />
    </div>
    <div className="flex items-center gap-2 border-b border-border px-2 py-1.5">
      <Block className="h-[22px] w-[22px] shrink-0 rounded-full" />
      <Block className="h-9 flex-1" />
      <Block className="h-9 w-9 shrink-0" />
      <Block className="h-9 w-9 shrink-0" />
    </div>
    <div className="flex flex-col gap-3 px-2 pt-2">
      <div className="flex items-start justify-between gap-2">
        <Block className="h-[52px] w-[176px]" />
        <Block className="h-[52px] w-[128px]" />
      </div>
      <div className="flex items-center justify-between">
        <Block className="h-3.5 w-16" />
        <Block className="h-7 w-[104px]" />
      </div>
      {PHONE_STRIP_GROUPS.map((count, group) => (
        <div key={group} className="flex animate-pulse flex-col gap-[3px]">
          {Array.from({ length: count }, (_, index) => (
            <div key={index} className="aspect-[432/42] w-full rounded-[3.8%/40%] bg-surface2" />
          ))}
        </div>
      ))}
    </div>
    <div className="fixed inset-x-0 bottom-0 z-50 flex items-center gap-1.5 border-t border-border bg-surface px-2 py-2">
      <Block className="h-9 w-[76px]" />
      <Block className="h-9 w-9" />
      <Block className="h-9 flex-1" />
    </div>
  </div>
);

const SortSkeleton = () => (
  <div className="ml-4 flex items-center gap-2">
    <span className="font-display text-[13px] tracking-[0.18em] text-subtle">SORT BY</span>
    <Block className="h-8 w-[204px]" />
  </div>
);

const PileRow = ({ sizes }: { sizes: number[] }) => (
  <div className="grid" style={{ gridTemplateColumns: PILE_COLUMNS, gap: PILE_GAP }}>
    {sizes.map((size, index) => (
      <div key={index} className="flex animate-pulse flex-col gap-1">
        <div className="flex h-6 items-center justify-center">
          <div className="h-3 w-8 rounded bg-surface2" />
        </div>
        {size > 0 && (
          <div className="flex flex-col">
            {Array.from({ length: size - 1 }, (_, strip) => (
              <div key={strip} className="aspect-[488/76] w-full rounded-t-[5%_30%] border-b border-bg bg-surface2" />
            ))}
            <div className="aspect-[488/680] w-full rounded-[4.5%/3.2%] bg-surface2" />
          </div>
        )}
      </div>
    ))}
  </div>
);

const Block = ({ className, style }: { className?: string; style?: React.CSSProperties }) => (
  <div className={cn("animate-pulse rounded bg-surface2", className)} style={style} />
);
