import { useEffect, useRef, useState, type ReactNode } from "react";
import {
  AutoScrollActivator,
  DndContext,
  DragOverlay,
  PointerSensor,
  useSensor,
  useSensors,
  type DragStartEvent,
} from "@dnd-kit/core";
import { ChartPie, Check, Copy, Hammer, RotateCcw, Share2, Undo2 } from "lucide-react";
import { useCopyFeedback } from "../CopyTextButton";

import { LLU_LOGO_SRC, SetGlyph } from "../Brand";
import { Link } from "react-router-dom";
import { cn } from "../../lib/utils";
import { DECK_SIZE, type PoolEntry } from "../../data/dailySealed";
import { BASICS_PILE_KEY, basicsColumnAt, basicsRow, type BasicsSlot, type PileTarget, type PileZone, type SortKey } from "../../data/dailySealedLayout";
import type { BuilderView } from "../../pages/DailySealedPage";
import { CardPreview, CardStack, NO_CARD_ACTIONS, REVEAL_RATIO } from "./cards";
import { BasicsGrid, DeckCount, DeckStats, FillLandsButton, PoolFilterBar } from "./controls";
import { HiddenPanel, HiddenToggle, PILE_GAP, PileBoard } from "./piles";
import { pileTargetAt, sameTarget } from "./pileHitTest";
import { DeckPanel, Pane, Panel, SIDEBAR_WIDTH_CLASS, SORT_LABELS } from "./panels";
import { usePreference } from "./usePreference";
import { fittedCardWidth, useWidth } from "./cardWidth";
import { DesktopBreakdown } from "./Breakdown";
import { TabButton } from "../TabButton";
import { chipClass, SURFACE_BUTTON, SwitchToggle } from "../pod/review/reviewControls";
import { DayNav, GREEN_CTA, PreviewMove, SubmitButton, Toast } from "./shared";
import { useCountdown } from "./useCountdown";
import { ShareDeckModal, ShareImageWarmup } from "./ShareDeckModal";
import { Tooltip } from "../Tooltip";

const DRAG_DISTANCE = 6;

type Mode = "build" | "breakdown";

export const DesktopBuilder = ({ view }: { view: BuilderView }) => {
  const { builder } = view;
  const [dragging, setDragging] = useState<number[] | null>(null);
  const [ghost, setGhost] = useState<Ghost | null>(null);
  const [dragWidth, setDragWidth] = useState<number | null>(null);
  const grab = useRef({ x: 0, y: 0 });
  const [overHidden, setOverHidden] = useState(false);
  const mode: Mode = view.showingBreakdown ? "breakdown" : "build";
  const paneRef = useRef<HTMLDivElement>(null);
  const [hiddenWidth, setHiddenWidth] = useHiddenWidth();
  const [hiddenOpenPref, setHiddenOpenPref] = usePreference<"open" | "closed">(HIDDEN_OPEN_KEY, "closed");
  const hiddenOpen = hiddenOpenPref === "open";
  const landsRow = basicsRow(builder.layout);
  const widestRow = Math.max(
    ...builder.layout.side.map((row) => row.length),
    ...builder.layout.deck.map((row) => row.length),
  );
  const fittedWidth = fittedCardWidth(useWidth(paneRef) - (hiddenOpen ? hiddenWidth : 0), widestRow);
  const cardWidth = dragWidth ?? fittedWidth;
  const sensors = useSensors(useSensor(PointerSensor, { activationConstraint: { distance: DRAG_DISTANCE } }));
  const latest = useRef({ builder, dragging, ghost, width: cardWidth });
  latest.current = { builder, dragging, ghost, width: cardWidth };
  const lastTarget = useRef<PileTarget | null>(null);
  const lastPoint = useRef<{ x: number; y: number } | null>(null);

  const placeAtPointer = () => {
    const { builder: current, dragging: indexes, ghost: drag, width } = latest.current;
    const point = lastPoint.current;
    if (!indexes || !point) {
      return;
    }
    if (drag?.column) {
      const target = pileTargetAt(point.x, point.y, current.layout, [], PILE_GAP, width);
      if (target?.zone !== "deck" || (lastTarget.current?.row === target.row && lastTarget.current?.pile === target.pile)) {
        return;
      }
      lastTarget.current = target;
      const slot = { row: target.row, pile: target.pile };
      if (drag.landsPile) {
        current.dragLandsPileTo(drag.landsPile, slot);
      } else {
        current.dragBasicsTo(slot);
      }
      return;
    }
    const underPointer = pileTargetAt(point.x, point.y, current.layout, indexes, PILE_GAP, width);
    const cardX = point.x - grab.current.x + width / 2;
    const titleY = point.y - grab.current.y + (width * REVEAL_RATIO) / 2;
    const target =
      underPointer?.zone === "hidden" ? underPointer : pileTargetAt(cardX, titleY, current.layout, indexes, PILE_GAP, width);
    setOverHidden(target?.zone === "hidden");
    if (sameTarget(target, lastTarget.current)) {
      return;
    }
    lastTarget.current = target;
    current.dragTo(indexes, target);
  };
  usePointerFrames(dragging !== null, lastPoint, placeAtPointer);

  const onDragStart = (event: DragStartEvent) => {
    const data = event.active.data.current;
    const picked = (data?.indexes as number[] | undefined) ?? [];
    const landsPile = (data?.landsPile as BasicsSlot | null | undefined) ?? null;
    const column = !!data?.basics || landsPile !== null;
    const indexes = column ? [] : picked;
    const nextGhost = { indexes: picked, column, landsPile, belowHeader: !!data?.pileHeader };
    setGhost(nextGhost);
    builder.beginDrag(!column);
    lastTarget.current = null;
    lastPoint.current = null;
    setDragWidth(cardWidth);
    grab.current = grabPointOf(event);
    setDragging(indexes);
    latest.current = { builder, dragging: indexes, ghost: nextGhost, width: cardWidth };
  };
  const finishDrag = () => {
    setDragging(null);
    setGhost(null);
    setDragWidth(null);
    setOverHidden(false);
    lastTarget.current = null;
    lastPoint.current = null;
  };
  const onDragEnd = () => {
    placeAtPointer();
    builder.endDrag();
    finishDrag();
  };
  const onDragCancel = () => {
    builder.cancelDrag();
    finishDrag();
  };

  return (
    <DndContext
      sensors={sensors}
      autoScroll={{
        activator: AutoScrollActivator.Pointer,
        threshold: { x: 0.04, y: 0.08 },
        acceleration: 6,
        canScroll: (element) => pointerInside(element, lastPoint.current),
      }}
      onDragStart={onDragStart}
      onDragEnd={onDragEnd}
      onDragCancel={onDragCancel}
    >
      <div className="flex flex-col lg:h-full lg:min-h-0">
        <Header
          view={view}
          mode={mode}
          onMode={(next) => (next === "build" ? view.showBuild() : view.showBreakdown())}
        />
        {mode === "breakdown" ? (
          <DesktopBreakdown view={view} />
        ) : (
          <div className="grid min-h-0 flex-1 grid-cols-[max-content_minmax(0,1fr)]">
            <div className={cn("flex min-h-0 flex-col overflow-y-auto border-r border-border", SIDEBAR_WIDTH_CLASS)}>
              <Panel title="FILTERS">
                <PoolFilterBar
                  setCode={view.pool.setCode}
                  cards={view.pool.cards}
                  filters={view.filters}
                  onChange={view.setFilters}
                  ratings={view.ratings}
                  onToggleRatings={view.toggleRatings}
                  ratingsAvailable={view.ratingsAvailable}
                />
              </Panel>
              <Panel title="BASIC LANDS">
                <BasicsGrid basics={builder.basics} onAdjust={builder.adjustBasic} footer={<FillLandsButton builder={builder} />} />
              </Panel>
              <Panel title="DECK">
                <DeckStats deck={builder.deck} basics={builder.basics} />
              </Panel>
            </div>
            <div ref={paneRef} className="flex min-h-0 flex-col">
              <Pane
                zone="side"
                className="flex-1 border-b-0"
                title={<h2 className="font-display text-[15px] tracking-[0.18em]">SIDEBOARD</h2>}
                count={view.sideEntries.length}
                total={builder.side.length}
                controls={<SortControls builder={builder} zone="side" />}
                extra={
                  <HiddenToggle
                    count={builder.hidden.length}
                    open={hiddenOpen}
                    onToggle={() => setHiddenOpenPref(hiddenOpen ? "closed" : "open")}
                    hovered={overHidden && !hiddenOpen}
                  />
                }
                flush
              >
                <div className="min-h-0 min-w-0 flex-1 overflow-auto px-2 py-1.5">
                  <PileBoard
                    zone="side"
                    setCode={view.pool.setCode}
                    rows={builder.layout.side}
                    cards={view.pool.cards}
                    width={cardWidth}
                    visible={new Set(view.sideEntries.map((entry) => entry.index))}
                    actions={view.sideActions}
                    dragging={dragging}
                  />
                </div>
                {hiddenOpen && (
                  <HiddenPanel
                    hidden={builder.hidden.map((entry) => entry.index)}
                    cards={view.pool.cards}
                    width={hiddenWidth}
                    cardWidth={cardWidth}
                    actions={{
                      onPick: (entry) => builder.move([entry.index], "side"),
                      onPreview: view.openPreview,
                    }}
                    dragging={dragging}
                    hovered={overHidden}
                    onClear={builder.clearHidden}
                    onResize={setHiddenWidth}
                  />
                )}
              </Pane>
              <DeckPanel
                title={<h2 className="font-display text-[15px] tracking-[0.18em]">DECK</h2>}
                storageKey="daily-sealed:deck"
                count={`${builder.deckSize} / ${DECK_SIZE}`}
                controls={<SortControls builder={builder} zone="deck" />}
                extra={
                  <SwitchToggle
                    label="SEPARATE NONCREATURES"
                    on={builder.split}
                    onToggle={builder.toggleSplit}
                    ariaLabel="Separate noncreatures"
                    tooltip="Show noncreatures in a second row"
                  />
                }
              >
                <PileBoard
                  zone="deck"
                  setCode={view.pool.setCode}
                  rows={builder.layout.deck}
                  cards={view.pool.cards}
                  width={cardWidth}
                  visible={null}
                  actions={view.deckActions}
                  dragging={dragging}
                  draggingLands={ghost?.column ?? false}
                  basics={{
                    row: landsRow,
                    pileKey: BASICS_PILE_KEY[builder.sort.deck],
                    entries: view.basicCards,
                    at: basicsColumnAt(builder.layout, builder.sort.deck, builder.layout.deck[landsRow]?.length ?? 0),
                  }}
                />
              </DeckPanel>
            </div>
          </div>
        )}
      </div>
      {view.notice && <Toast notice={view.notice} phone={false} />}
      <DragOverlay dropAnimation={null}>
        {ghost && <DragGhost ghost={ghost} view={view} cardWidth={cardWidth} />}
      </DragOverlay>
      {view.preview && (
        <CardPreview entry={view.preview} onClose={view.closePreview} step={view.previewStep}>
          <PreviewMove view={view} entry={view.preview} />
        </CardPreview>
      )}
    </DndContext>
  );
};

const Header = ({ view, mode, onMode }: { view: BuilderView; mode: Mode; onMode: (mode: Mode) => void }) => {
  const { builder, submitState } = view;
  const countdown = useCountdown(view.isToday);
  const [sharing, setSharing] = useState(false);
  return (
    <div className="flex h-12 shrink-0 items-center gap-4 border-b border-border px-3">
      <Link to="/tools" aria-label="Back to Tools" className="shrink-0">
        <img src={LLU_LOGO_SRC} alt="" className="h-8 w-8" />
      </Link>
      <SetGlyph code={view.pool.setCode} size={22} />
      <div className="flex min-w-0 items-center gap-3 whitespace-nowrap">
        <div className="flex items-baseline gap-3">
          <h1 className="font-display text-[18px] leading-none tracking-[0.12em]">DAILY SEALED</h1>
          <span className="font-display text-[14px] leading-none tracking-[0.12em] text-subtle">
            {view.setName.toUpperCase()} POOL <span className="text-green">#{view.pool.poolNumber}</span>
          </span>
        </div>
        <div className="ml-1 font-display text-[15px] leading-none tracking-[0.14em] text-subtle">
          <DayNav view={view} dateClassName="relative top-px" />
        </div>
        {countdown && (
          <span className="ml-2 w-[11em] text-[13px] leading-none text-subtle max-xl:hidden">
            New pool in {countdown}
          </span>
        )}
      </div>
      <div className="flex min-w-0 flex-1 justify-center self-stretch">
        {view.results.available && (
          <div className="flex shrink-0 [&>button]:h-full [&>button]:flex-none [&>button]:gap-2 [&>button]:px-5">
            <TabButton active={mode === "build"} onClick={() => onMode("build")}>
              <Hammer size={16} />
              BUILD
            </TabButton>
            <TabButton active={mode === "breakdown"} onClick={() => onMode("breakdown")}>
              <ChartPie size={16} />
              CARD BREAKDOWN
            </TabButton>
          </div>
        )}
      </div>
      <div className="flex items-center gap-1.5 [&>*]:h-9">
        <BuildActions shown={mode === "build"}>
          <HeaderButton icon={<Undo2 size={15} />} label="Undo" onClick={builder.undo} disabled={!builder.canUndo} />
          <HeaderButton icon={<RotateCcw size={15} />} label="Reset" onClick={builder.reset} />
          <DeckCount size={builder.deckSize} />
        </BuildActions>
        <CopyHeaderButton
          icon={<Copy size={15} />}
          label="Copy Link"
          text={view.linkText}
          onBlocked={view.copyBlocked}
        />
        <Tooltip label="Share an image of your deck" side="bottom">
          <button
            type="button"
            onClick={() => setSharing(true)}
            className={cn("flex items-center gap-2 whitespace-nowrap px-3", GREEN_CTA)}
          >
            <Share2 size={15} />
            SHARE
          </button>
        </Tooltip>
        <BuildActions shown={mode === "build" || submitState.submitted}>
          {submitState.visible && <SubmitButton view={view} statusOnly={mode === "breakdown"} />}
        </BuildActions>
      </div>
      {sharing && <ShareDeckModal view={view} onClose={() => setSharing(false)} />}
      {view.submits > 0 && <ShareImageWarmup key={view.submits} view={view} />}
    </div>
  );
};

const BuildActions = ({ shown, children }: { shown: boolean; children: ReactNode }) => (
  <div aria-hidden={!shown} className={cn("flex items-center gap-1.5 [&>*]:h-9", !shown && "invisible")}>
    {children}
  </div>
);

const HeaderButton = ({
  icon,
  label,
  onClick,
  disabled = false,
}: {
  icon: ReactNode;
  label: string;
  onClick: () => void;
  disabled?: boolean;
}) => (
  <button type="button" onClick={onClick} disabled={disabled} className={SURFACE_BUTTON}>
    {icon}
    <span className="uppercase">{label}</span>
  </button>
);

const CopyHeaderButton = ({
  icon,
  label,
  text,
  onBlocked,
}: {
  icon: ReactNode;
  label: string;
  text: () => string;
  onBlocked: () => void;
}) => {
  const { copied, copy } = useCopyFeedback();
  const run = async () => {
    if (!(await copy(text()))) {
      onBlocked();
    }
  };
  return (
    <button
      type="button"
      onClick={run}
      className={cn(SURFACE_BUTTON, copied && "border-green/60 text-green hover:border-green/60 hover:text-green")}
    >
      {copied ? <Check size={15} /> : icon}
      <span className="grid uppercase">
        <span className={cn("col-start-1 row-start-1", copied && "invisible")}>{label}</span>
        <span className={cn("col-start-1 row-start-1 text-center", !copied && "invisible")}>Copied!</span>
      </span>
    </button>
  );
};

const SortControls = ({ builder, zone }: { builder: BuilderView["builder"]; zone: PileZone }) => (
  <div className="ml-4 flex items-center gap-2">
    <span className="font-display text-[13px] tracking-[0.18em] text-subtle">SORT BY</span>
    <div className="flex gap-1">
      {(Object.keys(SORT_LABELS) as SortKey[]).map((key) => (
        <button
          key={key}
          type="button"
          onClick={() => builder.sortBy(zone, key)}
          className={cn(
            "h-8 px-2.5 text-[12px] uppercase tracking-[0.12em]",
            chipClass(false),
            "transition-[color,background-color,border-color,transform] duration-100",
            "hover:border-green/60 hover:bg-green/15 hover:text-green active:scale-95 active:bg-green/30",
          )}
        >
          {SORT_LABELS[key]}
        </button>
      ))}
    </div>
  </div>
);

interface Ghost {
  indexes: number[];
  column: boolean;
  landsPile: BasicsSlot | null;
  belowHeader: boolean;
}

const DragGhost = ({ ghost, view, cardWidth }: { ghost: Ghost; view: BuilderView; cardWidth: number }) => {
  const entries: PoolEntry[] = [
    ...ghost.indexes.map((index) => ({ index, card: view.pool.cards[index] })),
    ...(ghost.column ? view.basicCards : []),
  ];
  return (
    <div className={cn("opacity-90", ghost.belowHeader && "pt-7")}>
      <CardStack entries={entries} width={cardWidth} actions={NO_CARD_ACTIONS} />
    </div>
  );
};

const usePointerFrames = (
  active: boolean,
  point: { current: { x: number; y: number } | null },
  onFrame: () => void,
) => {
  const frameHandler = useRef(onFrame);
  frameHandler.current = onFrame;
  useEffect(() => {
    if (!active) {
      return;
    }
    let frame = 0;
    const run = () => {
      frame = 0;
      frameHandler.current();
    };
    const schedule = () => {
      if (frame === 0) {
        frame = requestAnimationFrame(run);
      }
    };
    const onMove = (event: PointerEvent) => {
      point.current = { x: event.clientX, y: event.clientY };
      schedule();
    };
    window.addEventListener("pointermove", onMove);
    window.addEventListener("scroll", schedule, true);
    return () => {
      window.removeEventListener("pointermove", onMove);
      window.removeEventListener("scroll", schedule, true);
      cancelAnimationFrame(frame);
    };
  }, [active, point]);
};

const grabPointOf = (event: DragStartEvent) => {
  const start = event.activatorEvent;
  if (!(start instanceof MouseEvent) || !(start.target instanceof Element)) {
    return { x: 0, y: 0 };
  }
  const grabbed = start.target.closest('[aria-roledescription="draggable"]');
  const rect = grabbed?.getBoundingClientRect();
  return rect ? { x: start.clientX - rect.left, y: start.clientY - rect.top } : { x: 0, y: 0 };
};

const pointerInside = (element: Element, point: { x: number; y: number } | null) => {
  if (!point) {
    return false;
  }
  const rect = element.getBoundingClientRect();
  return point.x >= rect.left && point.x <= rect.right && point.y >= rect.top && point.y <= rect.bottom;
};

const HIDDEN_WIDTH_KEY = "daily-sealed:hidden-width";
const HIDDEN_OPEN_KEY = "daily-sealed:hidden-open";
const HIDDEN_DEFAULT_WIDTH = 190;
const HIDDEN_MIN_WIDTH = 140;
const HIDDEN_MAX_WIDTH = 420;

const useHiddenWidth = (): [number, (width: number) => void] => {
  const [width, setWidth] = useState(() => {
    try {
      return Number(localStorage.getItem(HIDDEN_WIDTH_KEY)) || HIDDEN_DEFAULT_WIDTH;
    } catch {
      return HIDDEN_DEFAULT_WIDTH;
    }
  });
  const resize = (next: number) => {
    const clamped = Math.min(HIDDEN_MAX_WIDTH, Math.max(HIDDEN_MIN_WIDTH, Math.round(next)));
    setWidth(clamped);
    try {
      localStorage.setItem(HIDDEN_WIDTH_KEY, String(clamped));
    } catch {
      return;
    }
  };
  return [width, resize];
};
