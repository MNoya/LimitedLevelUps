import { useEffect, useState, type ReactNode } from "react";
import { Check, Copy, RotateCcw, Share2, Undo2 } from "lucide-react";
import { Link } from "react-router-dom";

import { LLU_LOGO_SRC, SetGlyph } from "../Brand";
import { cn } from "../../lib/utils";
import { useSets } from "../../data/hooks";
import { EMPTY_BASICS, nextTurnover, NO_FILTERS, servingDay } from "../../data/dailySealed";
import { DayNavBar } from "./shared";
import { useCountdown } from "./useCountdown";
import { BasicsGrid, DeckCount, DeckStats, PoolFilterBar } from "./controls";
import { chipClass, SURFACE_BUTTON, SwitchToggle } from "../pod/review/reviewControls";
import { Pane, Panel, SIDEBAR_WIDTH_CLASS, SORT_LABELS } from "./panels";
import { HiddenToggle, PILE_GAP } from "./piles";

const SIDE_PILE_SIZES = [13, 10, 14, 13, 15, 8, 9];
const DECK_PILE_SIZES = [2, 3, 0, 4, 1, 0, 2, 0];
const PILE_COLUMNS = `repeat(${DECK_PILE_SIZES.length}, minmax(0, 220px))`;
const PHONE_STRIP_GROUPS = [5, 4, 6, 3];
const BREAKDOWN_PILE_SIZES = [9, 7, 5, 4, 3];
const PAIR_ROWS = 5;
const PHONE_GRID_CARDS = 9;

export const DesktopBuilderSkeleton = ({ resting = false }: { resting?: boolean }) => {
  const dimmed = useDimmed(resting);
  const { data: sets } = useSets();
  const activeSet = sets?.find((set) => set.isActive);
  const setCode = activeSet?.code ?? "";
  return (
    <div
      className={cn("flex h-full min-h-0 flex-col", restingClass(resting, dimmed))}
      aria-busy={!resting}
      aria-label="Loading the pool"
    >
      <div className="flex h-12 shrink-0 items-center gap-4 border-b border-border px-3">
        <Link to="/tools" aria-label="Back to Tools" className="shrink-0">
          <img src={LLU_LOGO_SRC} alt="" className="h-8 w-8" />
        </Link>
        {resting && activeSet ? (
          <FirstPoolHeading setCode={activeSet.code} setName={activeSet.name} />
        ) : (
          <>
            <Block className="h-[22px] w-[22px] rounded-full" />
            <h1 className="font-display text-[18px] leading-none tracking-[0.12em]">DAILY SEALED</h1>
            <Block className="h-3.5 w-44" />
            <Block className="h-3.5 w-36" />
          </>
        )}
        <div className="ml-auto flex items-center gap-1.5 [&>*]:h-9">
          <PreviewButton icon={<Undo2 size={15} />} label="Undo" />
          <PreviewButton icon={<RotateCcw size={15} />} label="Reset" />
          <DeckCount size={0} />
          <PreviewButton icon={<Copy size={15} />} label="Copy Link" />
          <PreviewButton icon={<Share2 size={15} />} label="Share" />
          <span className="flex !h-10 items-center gap-2 rounded bg-surface2 px-4 font-display text-[14px] tracking-[0.14em] text-muted">
            <Check size={16} strokeWidth={2.5} />
            SUBMIT
          </span>
        </div>
      </div>
      <div className="grid min-h-0 flex-1 grid-cols-[max-content_minmax(0,1fr)]">
        <div className={cn("flex min-h-0 flex-col overflow-hidden border-r border-border", SIDEBAR_WIDTH_CLASS)}>
          <Panel title="FILTERS">
            <PoolFilterBar
              setCode={setCode}
              cards={[]}
              filters={NO_FILTERS}
              onChange={() => undefined}
              ratings={false}
              onToggleRatings={() => undefined}
              ratingsAvailable
            />
          </Panel>
          <Panel title="BASIC LANDS">
            <BasicsGrid basics={EMPTY_BASICS} />
          </Panel>
          <Panel title="DECK">
            <DeckStats deck={[]} basics={EMPTY_BASICS} />
          </Panel>
        </div>
        <div className="grid min-h-0 grid-rows-[minmax(0,3fr)_minmax(0,2fr)]">
          <Pane
            zone="side"
            title={<h2 className="font-display text-[15px] tracking-[0.18em]">SIDEBOARD</h2>}
            count={null}
            controls={<SortPreview />}
            extra={<HiddenToggle count={0} open={false} onToggle={() => undefined} hovered={false} />}
          >
            <PileRow sizes={SIDE_PILE_SIZES} />
          </Pane>
          <Pane
            zone="deck"
            title={<h2 className="font-display text-[15px] tracking-[0.18em]">DECK</h2>}
            count={null}
            controls={<SortPreview />}
            extra={
              <SwitchToggle
                label="SEPARATE NONCREATURES"
                on={false}
                onToggle={() => undefined}
                ariaLabel="Separate noncreatures"
                tooltip="Show noncreatures in a second row"
              />
            }
          >
            <PileRow sizes={DECK_PILE_SIZES} />
          </Pane>
        </div>
      </div>
    </div>
  );
};

export const PhoneBuilderSkeleton = ({ resting = false }: { resting?: boolean }) => {
  const dimmed = useDimmed(resting);
  return (
    <div
      className={cn("flex flex-col pb-[60px]", restingClass(resting, dimmed))}
      aria-busy={!resting}
      aria-label="Loading the pool"
    >
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
};

export const DesktopBreakdownSkeleton = () => (
  <div
    className="grid min-h-0 flex-1 grid-cols-[max-content_minmax(0,1fr)]"
    aria-busy
    aria-label="Loading the builds"
  >
    <div className={cn("flex min-h-0 flex-col overflow-hidden border-r border-border", SIDEBAR_WIDTH_CLASS)}>
      <Panel title="ORIGINAL BUILD">
        <div className="flex flex-col items-center gap-1.5">
          <Block className="h-10 w-40" />
          <Block className="h-3 w-24" />
        </div>
      </Panel>
      <Panel title="COLORS">
        <div className="flex flex-col gap-1">
          {Array.from({ length: PAIR_ROWS }, (_, row) => (
            <Block key={row} className="h-8 w-full" />
          ))}
        </div>
        <div className="mt-3 flex items-center gap-3">
          <Block className="h-[140px] w-[140px] shrink-0 rounded-full" />
          <div className="flex flex-1 flex-col gap-2">
            <Block className="h-3 w-full" />
            <Block className="h-3 w-full" />
            <Block className="h-3 w-full" />
          </div>
        </div>
      </Panel>
      <Panel title="INSIGHTS" grow>
        <div className="flex flex-col items-center gap-6 pt-4">
          <Block className="h-7 w-full" />
          <Block className="h-7 w-full" />
          <Block className="h-9 w-32" />
        </div>
      </Panel>
    </div>
    <Pane zone="side" title={<Block className="h-4 w-96" />} count={null} controls={<Block className="h-8 w-72" />}>
      <PileRow sizes={BREAKDOWN_PILE_SIZES} />
    </Pane>
  </div>
);

export const PhoneBreakdownSkeleton = () => (
  <div className="flex flex-col gap-3 pt-2" aria-busy aria-label="Loading the builds">
    <Block className="h-9 w-full" />
    <div className="flex gap-1.5">
      <Block className="h-9 w-16" />
      <Block className="h-9 w-20" />
      <Block className="h-9 w-20" />
      <Block className="h-9 w-20" />
    </div>
    <div className="grid grid-cols-3 gap-2">
      {Array.from({ length: PHONE_GRID_CARDS }, (_, card) => (
        <Block key={card} className="aspect-[488/680] w-full rounded-[4.5%/3.2%]" />
      ))}
    </div>
  </div>
);

const useDimmed = (resting: boolean) => {
  const [dimmed, setDimmed] = useState(false);
  useEffect(() => {
    if (!resting) {
      return;
    }
    const frame = requestAnimationFrame(() => setDimmed(true));
    return () => cancelAnimationFrame(frame);
  }, [resting]);
  return dimmed;
};

const restingClass = (resting: boolean, dimmed: boolean) =>
  cn(
    resting && "pointer-events-none transition-[opacity,filter] duration-500 [&_*]:animate-none",
    dimmed && "opacity-40 blur-[1px]",
  );

const FirstPoolHeading = ({ setCode, setName }: { setCode: string; setName: string }) => {
  const countdown = useCountdown(true);
  return (
    <>
      <SetGlyph code={setCode} size={22} />
      <div className="flex min-w-0 flex-1 items-center gap-3 whitespace-nowrap">
        <div className="flex items-baseline gap-3">
          <h1 className="font-display text-[18px] leading-none tracking-[0.12em]">DAILY SEALED</h1>
          <span className="font-display text-[14px] leading-none tracking-[0.12em] text-subtle">
            {setName.toUpperCase()} POOL <span className="text-green">#1</span>
          </span>
        </div>
        <div className="ml-1 font-display text-[15px] leading-none tracking-[0.14em] text-subtle">
          <DayNavBar day={servingDay(nextTurnover())} dateClassName="relative top-px" />
        </div>
        {countdown && (
          <span className="flex-1 text-center text-[13px] leading-none text-subtle max-xl:hidden">
            New pool in {countdown}
          </span>
        )}
      </div>
    </>
  );
};

const SortPreview = () => (
  <div className="ml-4 flex items-center gap-2">
    <span className="font-display text-[13px] tracking-[0.18em] text-subtle">SORT BY</span>
    <div className="flex gap-1">
      {Object.values(SORT_LABELS).map((label) => (
        <span
          key={label}
          className={cn("flex h-8 items-center px-2.5 text-[12px] uppercase tracking-[0.12em]", chipClass(false))}
        >
          {label}
        </span>
      ))}
    </div>
  </div>
);

const PreviewButton = ({ icon, label }: { icon: ReactNode; label: string }) => (
  <span className={SURFACE_BUTTON}>
    {icon}
    <span className="uppercase">{label}</span>
  </span>
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
