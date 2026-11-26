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
import { Check, Copy, Download, RotateCcw, Undo2 } from "lucide-react";
import { useCopyFeedback } from "../CopyTextButton";

import { LLU_LOGO_SRC, SetGlyph } from "../Brand";
import { Link } from "react-router-dom";
import { cn } from "../../lib/utils";
import { BASICS_PILE_KEY, type PileTarget, type PileZone, type SortKey } from "../../data/dailySealedLayout";
import type { BuilderView } from "../../pages/DailySealedPage";
import { CardFace, CardPreview, REVEAL_RATIO } from "./cards";
import { BasicsGrid, DeckCount, DeckStats, PoolFilterBar } from "./controls";
import { HiddenPanel, HiddenToggle, PILE_GAP, PileBoard } from "./piles";
import { pileTargetAt, sameTarget } from "./pileHitTest";
import { DeckPanel, Pane, Panel, SORT_LABELS } from "./panels";
import { usePreference } from "./usePreference";
import { fittedCardWidth, useWidth } from "./cardWidth";
import { breakdownTabFromHash, DesktopBreakdown, setAnchor } from "./Breakdown";
import { TabButton } from "../TabButton";
import { chipClass, SURFACE_BUTTON, SwitchToggle } from "../pod/review/reviewControls";
import { DayNav, PreviewMove, SubmitButton, Toast } from "./shared";
import { useCountdown } from "./useCountdown";

const DRAG_DISTANCE = 6;

type Mode = "build" | "breakdown";

export const DesktopBuilder = ({ view }: { view: BuilderView }) => {
  const { builder } = view;
  const [dragging, setDragging] = useState<number[] | null>(null);
  const [dragWidth, setDragWidth] = useState<number | null>(null);
  const grab = useRef({ x: 0, y: 0 });
  const [overHidden, setOverHidden] = useState(false);
  const [chosenMode, setMode] = useState<Mode>(view.isToday && !breakdownTabFromHash() ? "build" : "breakdown");
  const mode = view.results.available ? chosenMode : "build";
  const paneRef = useRef<HTMLDivElement>(null);
  const [hiddenWidth, setHiddenWidth] = useHiddenWidth();
  const [hiddenOpenPref, setHiddenOpenPref] = usePreference<"open" | "closed">(HIDDEN_OPEN_KEY, "closed");
  const hiddenOpen = hiddenOpenPref === "open";
  const widestRow = Math.max(
    ...builder.layout.side.map((row) => row.length),
    ...builder.layout.deck.map((row) => row.length),
  );
  const fittedWidth = fittedCardWidth(useWidth(paneRef) - (hiddenOpen ? hiddenWidth : 0), widestRow);
  const cardWidth = dragWidth ?? fittedWidth;
  const sensors = useSensors(useSensor(PointerSensor, { activationConstraint: { distance: DRAG_DISTANCE } }));
  const latest = useRef({ builder, dragging, width: cardWidth });
  latest.current = { builder, dragging, width: cardWidth };
  const lastTarget = useRef<PileTarget | null>(null);
  const lastPoint = useRef<{ x: number; y: number } | null>(null);

  const placeAtPointer = () => {
    const { builder: current, dragging: indexes, width } = latest.current;
    const point = lastPoint.current;
    if (!indexes || !point) {
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
    const indexes = (event.active.data.current?.indexes as number[] | undefined) ?? null;
    builder.beginDrag();
    lastTarget.current = null;
    lastPoint.current = null;
    setDragWidth(cardWidth);
    grab.current = grabPointOf(event);
    setDragging(indexes);
    latest.current = { builder, dragging: indexes, width: cardWidth };
  };
  const finishDrag = () => {
    setDragging(null);
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
          onMode={(next) => {
            if (next === "build") {
              setAnchor(null);
            }
            setMode(next);
          }}
        />
        {mode === "breakdown" ? (
          <DesktopBreakdown view={view} />
        ) : (
          <div className="grid min-h-0 flex-1 grid-cols-[max-content_minmax(0,1fr)]">
            <div className="flex min-h-0 flex-col overflow-y-auto border-r border-border">
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
                <BasicsGrid builder={builder} readOnly={false} />
              </Panel>
              <Panel title="DECK">
                <DeckStats builder={builder} />
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
                count={builder.deck.length}
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
                  basics={{
                    row: builder.layout.deck.length - 1,
                    pileKey: BASICS_PILE_KEY[builder.sort.deck],
                    entries: view.basicCards,
                  }}
                />
              </DeckPanel>
            </div>
          </div>
        )}
      </div>
      {view.notice && <Toast notice={view.notice} phone={false} />}
      <DragOverlay dropAnimation={null}>
        {dragging && <DragGhost indexes={dragging} view={view} cardWidth={cardWidth} />}
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
  return (
    <div className="flex h-12 shrink-0 items-center gap-4 border-b border-border px-3">
      <Link to="/tools" aria-label="Back to Tools" className="shrink-0">
        <img src={LLU_LOGO_SRC} alt="" className="h-8 w-8" />
      </Link>
      <SetGlyph code={view.pool.setCode} size={22} />
      <div className="flex min-w-0 flex-1 items-center gap-3 whitespace-nowrap">
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
          <span className="flex-1 text-center text-[13px] leading-none text-subtle max-xl:hidden">
            New pool in {countdown}
          </span>
        )}
      </div>
      {view.results.available && (
        <div className="flex w-[300px] shrink-0 self-stretch [&>button]:h-full">
          <TabButton active={mode === "build"} onClick={() => onMode("build")}>
            BUILD
          </TabButton>
          <TabButton active={mode === "breakdown"} onClick={() => onMode("breakdown")}>
            CARD BREAKDOWN
          </TabButton>
        </div>
      )}
      <div className="ml-auto flex items-center gap-1.5 [&>*]:h-9">
        {mode === "build" && (
          <>
            <HeaderButton icon={<Undo2 size={15} />} label="Undo" onClick={builder.undo} disabled={!builder.canUndo} />
            <HeaderButton icon={<RotateCcw size={15} />} label="Reset" onClick={builder.reset} />
            <DeckCount size={builder.deckSize} />
          </>
        )}
        <CopyHeaderButton
          icon={<Copy size={15} />}
          label="Copy Link"
          text={view.linkText}
          onBlocked={view.copyBlocked}
        />
        {mode === "build" && (
          <CopyHeaderButton
            icon={<Download size={15} />}
            label="Export for Arena"
            text={view.exportText}
            onBlocked={view.copyBlocked}
          />
        )}
        {mode === "build" && submitState.visible && <SubmitButton view={view} />}
      </div>
    </div>
  );
};

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

const DragGhost = ({ indexes, view, cardWidth }: { indexes: number[]; view: BuilderView; cardWidth: number }) => {
  const card = view.pool.cards[indexes[0]];
  if (!card) {
    return null;
  }
  return (
    <div className="relative opacity-90" style={{ width: cardWidth }}>
      <CardFace card={card} />
      {indexes.length > 1 && (
        <span className="absolute -right-2 -top-2 rounded-full bg-green px-2 font-num text-[13px] text-bg">
          {indexes.length}
        </span>
      )}
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
