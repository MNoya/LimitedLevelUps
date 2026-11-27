import { useRef, useState, type ReactNode, type RefObject } from "react";
import { DndContext, DragOverlay } from "@dnd-kit/core";
import { ChartPie, Check, Copy, Hammer, RotateCcw, Share2, Undo2 } from "lucide-react";
import { useCopyFeedback } from "../CopyTextButton";

import { LLU_LOGO_SRC, SetGlyph } from "../Brand";
import { Link } from "react-router-dom";
import { cn } from "../../lib/utils";
import { DECK_SIZE } from "../../data/dailySealed";
import { BASICS_PILE_KEY, basicsColumnAt, basicsRow } from "../../data/dailySealedLayout";
import type { BuilderView } from "../../pages/DailySealedPage";
import { CardPreview } from "./cards";
import { BasicsGrid, DeckCount, DeckStats, FillLandsButton, PoolFilterBar } from "./controls";
import { HiddenToggle, ListPanel, PileBoard } from "./piles";
import { PileDragGhost, usePileDrag } from "./pileDrag";
import { DeckPanel, Pane, Panel, SIDEBAR_WIDTH_CLASS, SortControls } from "./panels";
import { usePreference } from "./usePreference";
import { fittedCardWidth } from "./cardWidth";
import { useWidth } from "./elementSize";
import { DesktopBreakdown } from "./Breakdown";
import { TabButton } from "../TabButton";
import { SURFACE_BUTTON, SwitchToggle, useCtrlWheelZoom, ZoomControl } from "../pod/review/reviewControls";
import { DayNav, GREEN_CTA, PreviewMove, SubmitButton, Toast } from "./shared";
import { useCountdown } from "./useCountdown";
import { ShareDeckModal, ShareImageWarmup } from "./ShareDeckModal";
import { Tooltip } from "../Tooltip";

type Mode = "build" | "breakdown";

export const DesktopBuilder = ({ view }: { view: BuilderView }) => {
  const { builder } = view;
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
  const zoom = useBoardZoom(paneRef);
  const { dragging, ghost, overZone, cardWidth, contextProps } = usePileDrag(
    builder,
    Math.round(fittedWidth * zoom.scale),
  );
  const overHidden = overZone === "hidden";

  return (
    <DndContext {...contextProps}>
      <div className="flex flex-col lg:h-full lg:min-h-0">
        <Header
          view={view}
          mode={mode}
          onMode={(next) => (next === "build" ? view.showBuild() : view.showBreakdown())}
          zoomControl={<BoardZoomControl zoom={zoom} />}
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
                  ratingsLoading={view.ratingsLoading}
                />
              </Panel>
              <Panel title="BASIC LANDS">
                <BasicsGrid
                  basics={builder.basics}
                  onAdjust={builder.adjustBasic}
                  footer={<FillLandsButton builder={builder} />}
                />
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
                controls={<SortControls onSort={(key) => builder.sortBy("side", key)} />}
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
                  <ListPanel
                    title="HIDDEN"
                    emptyText="Drag cards here to hide them"
                    indexes={builder.hidden.map((entry) => entry.index)}
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
                controls={<SortControls onSort={(key) => builder.sortBy("deck", key)} />}
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
        {ghost && (
          <PileDragGhost ghost={ghost} cards={view.pool.cards} basicCards={view.basicCards} cardWidth={cardWidth} />
        )}
      </DragOverlay>
      {view.preview && (
        <CardPreview entry={view.preview} onClose={view.closePreview} step={view.previewStep}>
          <PreviewMove view={view} entry={view.preview} />
        </CardPreview>
      )}
    </DndContext>
  );
};

const Header = ({
  view,
  mode,
  onMode,
  zoomControl,
}: {
  view: BuilderView;
  mode: Mode;
  onMode: (mode: Mode) => void;
  zoomControl?: ReactNode;
}) => {
  const { builder, submitState } = view;
  const countdown = useCountdown(view.isToday);
  const [sharing, setSharing] = useState(false);
  return (
    <div className="flex h-12 shrink-0 items-center gap-4 border-b border-border px-3 max-[1679px]:gap-3">
      <Link to="/tools" aria-label="Back to Tools" className="shrink-0">
        <img src={LLU_LOGO_SRC} alt="" className="h-8 w-8" />
      </Link>
      <SetGlyph code={view.pool.setCode} size={22} />
      <div className="flex min-w-0 items-center gap-3 whitespace-nowrap">
        <div className="flex items-baseline gap-3">
          <h1 className="font-display text-[18px] leading-none tracking-[0.12em]">DAILY SEALED</h1>
          <span className="font-display text-[14px] leading-none tracking-[0.12em] text-subtle">
            <span className="max-[1679px]:hidden">{view.setName.toUpperCase()} POOL </span>
            <span className="text-green">#{view.pool.poolNumber}</span>
          </span>
        </div>
        <div className="ml-1 font-display text-[15px] leading-none tracking-[0.14em] text-subtle">
          <DayNav view={view} dateClassName="relative top-px" />
        </div>
        {countdown && (
          <span className="ml-2 w-[11em] text-[13px] leading-none text-subtle max-[1679px]:hidden">
            New pool in {countdown}
          </span>
        )}
      </div>
      <div className="flex min-w-0 flex-1 justify-center self-stretch">
        {view.results.available && (
          <div className="flex shrink-0 [&>button]:h-full [&>button]:flex-none [&>button]:gap-2 [&>button]:px-5 max-[1679px]:[&>button]:px-2.5">
            <TabButton active={mode === "build"} onClick={() => onMode("build")}>
              <Hammer size={16} />
              BUILD
            </TabButton>
            <TabButton active={mode === "breakdown"} onClick={() => onMode("breakdown")}>
              <ChartPie size={16} />
              <span>
                <span className="max-[1679px]:hidden">CARD </span>BREAKDOWN
              </span>
            </TabButton>
          </div>
        )}
      </div>
      <div className="flex items-center gap-1.5 [&>*]:h-9">
        <BuildActions shown={mode === "build"}>
          {zoomControl}
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

const HIDDEN_WIDTH_KEY = "daily-sealed:hidden-width";
const HIDDEN_OPEN_KEY = "daily-sealed:hidden-open";
const ZOOM_KEY = "daily-sealed:zoom";
const ZOOM_STEPS = [0.7, 0.8, 0.9, 1, 1.15, 1.3, 1.5];

type BoardZoom = ReturnType<typeof useBoardZoom>;

const useBoardZoom = (boardRef: RefObject<HTMLElement | null>) => {
  const [stored, setStored] = usePreference<string>(ZOOM_KEY, "1");
  const scale = ZOOM_STEPS.includes(Number(stored)) ? Number(stored) : 1;
  const position = ZOOM_STEPS.indexOf(scale);
  const step = (dir: 1 | -1) => {
    const next = ZOOM_STEPS[position + dir];
    if (next !== undefined) {
      setStored(String(next));
    }
  };
  useCtrlWheelZoom(boardRef, step);
  return {
    scale,
    fitting: scale === 1,
    canShrink: position > 0,
    canGrow: position < ZOOM_STEPS.length - 1,
    step,
    fit: () => setStored("1"),
  };
};

const BoardZoomControl = ({ zoom }: { zoom: BoardZoom }) => (
  <ZoomControl
    label={`${Math.round(zoom.scale * 100)}%`}
    fitting={zoom.fitting}
    canShrink={zoom.canShrink}
    canGrow={zoom.canGrow}
    onStep={zoom.step}
    onToggleFit={zoom.fit}
    fitTooltip="Fit cards to the board"
    highlightFit={false}
  />
);
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
