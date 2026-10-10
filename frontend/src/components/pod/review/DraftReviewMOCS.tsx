import {
  useCallback,
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
  type CSSProperties,
  type Dispatch,
  type ReactNode,
  type RefObject,
  type SetStateAction,
} from "react";
import { Link, useNavigate } from "react-router-dom";

import { frontFace } from "../../../lib/cardSlug";
import { cn } from "../../../lib/utils";
import { wheelPixels } from "../../../lib/use-wheel-trap";
import { ToggleSwitch } from "../../ToggleSwitch";
import { Pips } from "../../ManaPips";
import { Tooltip } from "../../Tooltip";
import { ArrowRight, GoSidebarCollapse, TbCards } from "../../Icons";
import {
  CARD_FRAME,
  CARD_FRAME_HOVER,
  CardGradeOverlay,
  CardImage,
  CardImageMapProvider,
  CardPreviewProvider,
  KEEPS_PREVIEW,
  ReviewSetProvider,
  StackColumn,
} from "./ReviewCard";
import { cardImageSources, useCardImageMap } from "../../../data/cardImages";
import { highlightEventLabel } from "../EventLabel";
import { AAvatar } from "../../Brand";
import { DeckScreenshotModal, type DeckLike } from "../DeckScreenshotModal";
import { onPlainClick, podDeckHref, podDraftPickHref, type InPlaceLink } from "../podLinks";
import { picksPerTurn, poolBefore, poolByPack, reconstructDraft, resolveDeck, seatHandle, type DraftPickView } from "../../../data/draft-artifact";
import { cleanPodEventName, stripDiscriminator } from "../../../data/utils";
import type { ArtifactCard, PodDraftArtifact } from "../../../types/leaderboard";

type RevealMode = "revealed" | "click";

const PASS_DIRS = [1, -1, 1];

interface DraftReviewMeta {
  setCode: string;
  name: string;
}

// Per-seat participant data the artifact doesn't carry — drives the final-deck popup. When absent the
// deck button stays hidden.
export interface ReviewSeatInfo {
  seatIndex: number;
  playerSlug: string | null;
  displayName: string;
  participantDisplayName: string;
  avatarUrl: string | null;
  deckColors: string | null;
  deckScreenshotUrl: string | null;
  deckScreenshotCaption: string | null;
  record: string | null;
}

interface DraftReviewMOCSProps {
  artifact: PodDraftArtifact;
  meta: DraftReviewMeta;
  seat: number;
  pack: number;
  pick: number;
  backHref: string;
  eventSlug: string;
  eventId?: string;
  seatInfo?: ReviewSeatInfo[];
  // Pin the review to one seat in scroll-only mode: no seat switching, no table, no other-seat decks.
  soloSeat?: number;
}

export function DraftReviewMOCS({
  artifact,
  meta,
  seat,
  pack: requestedPack,
  pick: requestedPick,
  backHref,
  eventSlug,
  eventId,
  seatInfo,
  soloSeat,
}: DraftReviewMOCSProps) {
  const navigate = useNavigate();
  const solo = soloSeat != null;
  const setSymbol = `/set-symbols/${meta.setCode.toLowerCase()}.png`;
  const eventTitle = useMemo(() => cleanPodEventName(meta.name, meta.setCode), [meta]);
  const N = artifact.seats.length;

  const seatInfoMap = useMemo(() => new Map((seatInfo ?? []).map((s) => [s.seatIndex, s])), [seatInfo]);

  const views = useMemo(() => reconstructDraft(artifact), [artifact]);
  const perTurn = useMemo(() => picksPerTurn(artifact), [artifact]);
  const imageItems = useMemo(
    () => artifact.cards.map((card) => ({ name: card.n, set: card.s ?? artifact.set })),
    [artifact],
  );
  const cardImages = useCardImageMap(imageItems);
  const seats = useMemo(
    () =>
      artifact.seats.map((name, i) => {
        const info = seatInfoMap.get(i);
        return {
          index: i,
          name: info ? stripDiscriminator(info.displayName) : seatHandle(name),
          colors: info?.deckColors ?? "",
          avatarUrl: info?.avatarUrl ?? null,
        };
      }),
    [artifact, seatInfoMap],
  );

  const pack = Math.min(2, Math.max(0, requestedPack));
  const pick = Math.min(views[seat][pack].length - 1, Math.max(0, requestedPick));
  const [viewMode, setViewMode] = usePersistentState<"step" | "scroll">("draftReviewViewMode", defaultViewMode());
  const effectiveViewMode = solo ? "scroll" : viewMode;
  const [showTable, setShowTable] = usePersistentBool("draftReviewShowTable", false);
  const [deckLayout, setDeckLayout] = usePersistentState<"order" | "columns">("draftReviewDeckLayout", "columns");
  const [revealMode, setRevealMode] = usePersistentState<RevealMode>("draftReviewRevealMode", "revealed");
  const [revealedAt, setRevealedAt] = useState<string | null>(null);
  const [splitSideboard, setSplitSideboard] = usePersistentBool("draftReviewSplitSideboard", false);
  const [splitTypes, setSplitTypes] = usePersistentBool("draftReviewSplitTypes", true);
  const [showGrades, setShowGrades] = usePersistentBool("draftReviewShowGrades", false);
  const [deckPopupSeat, setDeckPopupSeat] = useState<number | null>(null);
  const viewportHeight = useViewportHeight();
  const [zoom, setZoom] = usePersistentState<Zoom>("draftReviewBoosterZoom", "fit");
  const [fitCardWidth, setFitCardWidth] = useState(BOOSTER_CARD_WIDTH);
  const fitting = zoom === "fit";
  const boosterCardWidth = fitting ? fitCardWidth : Math.round(BOOSTER_CARD_WIDTH * Number(zoom));
  const boosterScale = boosterCardWidth / BOOSTER_CARD_WIDTH;
  const recapScale = fitting ? 1 : boosterScale;
  const stepZoom = useCallback((dir: 1 | -1) => setZoom(nextZoomStep(boosterScale, dir)), [boosterScale, setZoom]);
  const toggleFit = () => setZoom(fitting ? "1" : "fit");
  const shownScale = effectiveViewMode === "scroll" ? recapScale : boosterScale;
  const shownPercent = Math.round(shownScale * 100);
  const packFitTooltip = fitting ? `Cards at ${shownPercent}% to fit Pack` : "Fit Pack on screen";
  const [tallestBooster, setTallestBooster] = useState(0);
  const [tallestBoosterZoom, setTallestBoosterZoom] = useState(zoom);
  if (tallestBoosterZoom !== zoom) {
    setTallestBoosterZoom(zoom);
    setTallestBooster(0);
  }
  const reportBoosterHeight = useCallback((h: number) => setTallestBooster((prev) => (h > prev ? h : prev)), []);
  const deckPanelHeight = deckPanelDefaultHeight(viewportHeight, fitting ? 0 : tallestBooster);

  useEffect(() => {
    const html = document.documentElement;
    html.style.scrollbarGutter = "auto";
    return () => {
      html.style.scrollbarGutter = "";
    };
  }, []);

  const packTurns = views[seat][pack].length;
  const position = `${seat}/${pack}/${pick}`;
  const revealed = revealedAt === position;
  const reveal = () => setRevealedAt(position);

  const pickShown = revealMode === "revealed" || revealed;
  const awaitingReveal = revealMode === "click" && !revealed;

  const pickHref = (seatIndex: number, p: number, k: number) => {
    const playerSlug = seatInfoMap.get(seatIndex)?.playerSlug ?? null;
    return podDraftPickHref(eventSlug, { playerSlug, seatIndex }, p, k);
  };
  const jumpHref = (p: number, k: number) => pickHref(seat, p, k);
  const goTo = (p: number, k: number) => navigate(jumpHref(p, k), { replace: true });
  const prev = prevCoord(views, seat, pack, pick);
  const next = nextCoord(views, seat, pack, pick);
  const prevHref = prev ? jumpHref(prev.pack, prev.pick) : null;
  const nextHref = next ? jumpHref(next.pack, next.pick) : null;
  const handlePrev = () => {
    if (prev) {
      goTo(prev.pack, prev.pick);
    }
  };
  const handleNext = () => {
    if (next) {
      goTo(next.pack, next.pick);
    }
  };
  const changeReveal = (m: RevealMode) => {
    setRevealMode(m);
    setRevealedAt(null);
  };
  const seatHref = (i: number) => (next ? pickHref(i, pack, pick) : pickHref(i, 0, 0));

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (deckPopupSeat != null || e.metaKey || e.ctrlKey || e.altKey || e.shiftKey) {
        return;
      }
      const t = e.target;
      if (t instanceof HTMLElement && (t.tagName === "INPUT" || t.tagName === "TEXTAREA" || t.isContentEditable)) {
        return;
      }
      const navKey = e.key === "ArrowLeft" || e.key === "ArrowRight" || e.key === " ";
      if (navKey && document.activeElement instanceof HTMLElement) {
        document.activeElement.blur();
      }
      if (e.key === "ArrowLeft") {
        e.preventDefault();
        handlePrev();
      } else if (e.key === "ArrowRight") {
        e.preventDefault();
        if (awaitingReveal) {
          reveal();
        } else {
          handleNext();
        }
      } else if (e.key === " ") {
        e.preventDefault();
        changeReveal(revealMode === "revealed" ? "click" : "revealed");
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [handlePrev, handleNext, awaitingReveal, changeReveal, revealMode, deckPopupSeat]);

  useEffect(() => {
    const upcoming = nextCoord(views, seat, pack, pick);
    if (!upcoming) {
      return;
    }
    for (const idx of views[seat][upcoming.pack][upcoming.pick].booster) {
      const card = artifact.cards[idx];
      const url = cardImageSources(card.n, card.s ?? artifact.set, cardImages)[0];
      if (url) {
        new Image().src = url;
      }
    }
  }, [views, seat, pack, pick, artifact, cardImages]);

  const view = views[seat][pack][pick];
  const boosterCards = view.booster.map((idx) => artifact.cards[idx]);
  const active = seats[seat];
  const followsPick = effectiveViewMode === "step" && pickShown;
  const pickedCard = followsPick ? boosterCards[view.takenPositions[0]] : null;

  const deck = artifact.decks?.[seat];
  const sideSet = useMemo(() => new Set(deck?.side ?? []), [deck]);
  const hasSideboard = (deck?.side?.length ?? 0) > 0;

  const toCards = (indices: number[]) => indices.map((idx) => artifact.cards[idx]);
  const poolIdx = poolBefore(views, seat, pack, pick);
  const poolRowsIdx = poolByPack(views, seat, pack, pick);
  const pool = toCards(hasSideboard ? poolIdx.filter((idx) => !sideSet.has(idx)) : poolIdx);
  const poolRows = (hasSideboard ? poolRowsIdx.map((row) => row.filter((idx) => !sideSet.has(idx))) : poolRowsIdx).map(toCards);
  const sideboardCards = hasSideboard ? toCards(poolIdx.filter((idx) => sideSet.has(idx))) : [];
  const lastPicks = markedLastPicks(poolIdx.slice(-perTurn), hasSideboard ? sideSet : EMPTY_SIDEBOARD);

  const activeInfo = seatInfoMap.get(seat);
  const canOpenDeck = !!activeInfo && (activeInfo.deckScreenshotUrl != null || (deck?.main.length ?? 0) > 0);
  const deckLink: InPlaceLink | undefined =
    activeInfo && canOpenDeck
      ? {
          href: podDeckHref(eventSlug, activeInfo.displayName, activeInfo.displayName),
          open: () => setDeckPopupSeat(seat),
        }
      : undefined;
  const deckPopup = deckPopupSeat == null ? null : buildDeckLike(deckPopupSeat);

  function buildDeckLike(s: number): DeckLike | null {
    const info = seatInfoMap.get(s);
    if (!info) {
      return null;
    }
    return {
      eventId,
      displayName: info.displayName,
      participantDisplayName: info.participantDisplayName,
      deckColors: info.deckColors,
      deckScreenshotUrl: info.deckScreenshotUrl,
      deckScreenshotCaption: info.deckScreenshotCaption,
      mainboard: resolveDeck(artifact, s),
      record: info.record,
    };
  }

  const left = (seat - 1 + N) % N;
  const right = (seat + 1) % N;
  const dir = PASS_DIRS[pack];

  const pileFor = (seatIndex: number): Pile => {
    const indices = poolBefore(views, seatIndex, pack, pick);
    const side = new Set(artifact.decks?.[seatIndex]?.side ?? []);
    const main = toCards(indices.filter((i) => !side.has(i)));
    const board = toCards(indices.filter((i) => side.has(i)));
    return { main, board, lastPicks: markedLastPicks(indices.slice(-perTurn), side) };
  };
  const leftPile = pileFor(left);
  const centerPile = pileFor(seat);
  const rightPile = pileFor(right);

  return (
    <ReviewSetProvider value={artifact.set}>
    <CardImageMapProvider value={cardImages}>
    <CardPreviewProvider setCode={meta.setCode} followKey={`${position}/${followsPick}`} followCard={pickedCard}>
    <div className="fixed inset-0 z-50 flex select-none flex-col bg-bg text-text">
      <MobileTopBar
        setSymbol={setSymbol}
        left={seats[left]}
        active={active}
        right={seats[right]}
        passRight={dir === 1}
        leftHref={seatHref(left)}
        rightHref={seatHref(right)}
        backHref={backHref}
        scrollOn={effectiveViewMode === "scroll"}
        onToggleScroll={() => setViewMode(viewMode === "scroll" ? "step" : "scroll")}
        showGrades={showGrades}
        onToggleGrades={() => setShowGrades((v) => !v)}
        solo={solo}
      />
      <Header
        left={seats[left]}
        active={active}
        right={seats[right]}
        passRight={dir === 1}
        leftHref={seatHref(left)}
        rightHref={seatHref(right)}
        setSymbol={setSymbol}
        eventTitle={eventTitle}
        backHref={backHref}
        pack={pack}
        pick={pick}
        turns={packTurns}
        perTurn={perTurn}
        jumpHref={jumpHref}
        prevHref={prevHref}
        nextHref={nextHref}
        awaitingReveal={awaitingReveal}
        onReveal={reveal}
        revealMode={revealMode}
        onRevealMode={changeReveal}
        showGrades={showGrades}
        onToggleGrades={() => setShowGrades((v) => !v)}
        showTable={showTable}
        onToggleTable={() => setShowTable((v) => !v)}
        viewMode={effectiveViewMode}
        onViewMode={setViewMode}
        solo={solo}
      />
      <div className="relative flex min-h-0 flex-1">
        <section className="relative flex min-w-0 flex-1 flex-col">
          <div className="absolute bottom-3 right-4 z-20 hidden lg:block">
            <ZoomControl
              label={`${shownPercent}%`}
              fitting={fitting && effectiveViewMode === "step"}
              canShrink={shownScale > BOOSTER_MIN_ZOOM}
              canGrow={shownScale < BOOSTER_MAX_ZOOM}
              onStep={stepZoom}
              onToggleFit={effectiveViewMode === "step" ? toggleFit : undefined}
              fitTooltip={packFitTooltip}
              className="h-9"
            />
          </div>
          {effectiveViewMode === "scroll" ? (
            <>
              <div className="absolute right-2 top-1 z-20 lg:hidden">
                <MobileToggle
                  label="PICKS"
                  ariaLabel="Show picks"
                  on={revealMode === "revealed"}
                  onToggle={() => changeReveal(revealMode === "revealed" ? "click" : "revealed")}
                />
              </div>
              <DraftScrollRecap
                key={seat}
                packs={views[seat]}
                cards={artifact.cards}
                perTurn={perTurn}
                revealMode={revealMode}
                showGrades={showGrades}
                initialPack={pack}
                initialPick={pick}
                cardWidth={Math.round(RECAP_CARD_WIDTH * recapScale)}
                onZoomStep={stepZoom}
                onActivePick={(p, k) => {
                  if (p !== pack || k !== pick) {
                    goTo(p, k);
                  }
                }}
              />
            </>
          ) : (
            <>
              <BoosterPanel
                cards={boosterCards}
                pickedPositions={pickShown ? view.takenPositions : []}
                showGrades={showGrades}
                fadeKey={`${seat}-${pack}-${pick}`}
                onNaturalHeight={fitting ? undefined : reportBoosterHeight}
                cardWidth={boosterCardWidth}
                fitCount={fitting ? largestPackSize(views[seat]) : null}
                onFitWidth={setFitCardWidth}
                onZoomStep={stepZoom}
              />
              <MobileNavDivider
                pack={pack}
                pick={pick}
                perTurn={perTurn}
                jumpHref={jumpHref}
                prevHref={prevHref}
                nextHref={nextHref}
                awaitingReveal={awaitingReveal}
                onReveal={reveal}
                revealMode={revealMode}
                onRevealMode={changeReveal}
              />
              <PoolBar
                cards={pool}
                rows={poolRows}
                sideboard={sideboardCards}
                lastPicks={lastPicks}
                deckLayout={deckLayout}
                onToggleDeckLayout={() => setDeckLayout((l) => (l === "order" ? "columns" : "order"))}
                canSplit={hasSideboard}
                splitSideboard={splitSideboard}
                onToggleSplit={() => setSplitSideboard((v) => !v)}
                deckLink={deckLink}
              />
            </>
          )}
        </section>
        {!solo && (
          <aside
            className={cn(
              "relative hidden shrink-0 overflow-hidden bg-surface/40 transition-[width] duration-200 lg:block",
              showTable ? "w-[300px] border-l border-border" : "w-0",
            )}
          >
            <div className="h-full w-[300px]">
              <PlayerGrid
                seats={seats}
                activeSeat={seat}
                seatHref={seatHref}
                passRight={dir === 1}
              />
            </div>
          </aside>
        )}
      </div>
      {effectiveViewMode === "step" && (
        <BottomPanel
          defaultHeight={deckPanelHeight}
          activeName={active.name}
          activeAvatarUrl={active.avatarUrl}
          cards={pool}
          rows={poolRows}
          sideboard={sideboardCards}
          lastPicks={lastPicks}
          deckLayout={deckLayout}
          onToggleDeckLayout={() => setDeckLayout((l) => (l === "order" ? "columns" : "order"))}
          canSplit={hasSideboard}
          splitSideboard={splitSideboard}
          onToggleSplit={() => setSplitSideboard((v) => !v)}
          splitTypes={splitTypes}
          onToggleSplitTypes={() => setSplitTypes((v) => !v)}
          deckLink={deckLink}
          left={seats[left]}
          right={seats[right]}
          passRight={dir === 1}
          leftPile={leftPile}
          centerPile={centerPile}
          rightPile={rightPile}
        />
      )}
      {deckPopup && (
        <DeckScreenshotModal
          participant={deckPopup}
          hideDraftLog
          cardImages={cardImages}
          onClose={() => setDeckPopupSeat(null)}
          onPrev={() => setDeckPopupSeat((s) => (s == null ? s : (s - 1 + N) % N))}
          onNext={() => setDeckPopupSeat((s) => (s == null ? s : (s + 1) % N))}
        />
      )}
    </div>
    </CardPreviewProvider>
    </CardImageMapProvider>
    </ReviewSetProvider>
  );
}

function nextCoord(views: DraftPickView[][][], seat: number, pack: number, pick: number): { pack: number; pick: number } | null {
  if (pick + 1 < views[seat][pack].length) {
    return { pack, pick: pick + 1 };
  }
  if (pack < 2) {
    return { pack: pack + 1, pick: 0 };
  }
  return null;
}

const prevCoord = (views: DraftPickView[][][], seat: number, pack: number, pick: number) => {
  if (pick > 0) {
    return { pack, pick: pick - 1 };
  }
  if (pack > 0) {
    return { pack: pack - 1, pick: views[seat][pack - 1].length - 1 };
  }
  return null;
};

const DESKTOP_MIN_WIDTH = 1024;

function defaultViewMode(): "step" | "scroll" {
  if (typeof window === "undefined") {
    return "step";
  }
  return window.innerWidth < DESKTOP_MIN_WIDTH ? "scroll" : "step";
}

function usePersistentState<T extends string>(key: string, fallback: T): [T, Dispatch<SetStateAction<T>>] {
  const [value, setValue] = useState<T>(() => {
    if (typeof window === "undefined") {
      return fallback;
    }
    return (window.localStorage.getItem(key) as T | null) ?? fallback;
  });
  useEffect(() => {
    window.localStorage.setItem(key, value);
  }, [key, value]);
  return [value, setValue];
}

function usePersistentBool(key: string, fallback: boolean): [boolean, Dispatch<SetStateAction<boolean>>] {
  const [value, setValue] = useState<boolean>(() => {
    if (typeof window === "undefined") {
      return fallback;
    }
    const stored = window.localStorage.getItem(key);
    return stored == null ? fallback : stored === "1";
  });
  useEffect(() => {
    window.localStorage.setItem(key, value ? "1" : "0");
  }, [key, value]);
  return [value, setValue];
}

interface Seat {
  index: number;
  name: string;
  colors: string;
  avatarUrl: string | null;
}

interface Pile {
  main: ArtifactCard[];
  board: ArtifactCard[];
  lastPicks: LastPicks;
}

// How many of the newest cards to glow in each pool list. A Pick 2 turn adds two cards, and they can
// land on opposite sides of the maindeck/sideboard split.
interface LastPicks {
  main: number;
  side: number;
}

const NO_LAST_PICKS: LastPicks = { main: 0, side: 0 };
const EMPTY_SIDEBOARD: ReadonlySet<number> = new Set();

function markedLastPicks(taken: number[], side: ReadonlySet<number>): LastPicks {
  let main = 0;
  let board = 0;
  for (const idx of taken) {
    if (side.has(idx)) {
      board += 1;
    } else {
      main += 1;
    }
  }
  return { main, side: board };
}

// Indices of the last `count` cards in a list, the ones a just-taken glow lands on.
function lastIndexes(length: number, count: number): number[] {
  const out: number[] = [];
  for (let i = Math.max(0, length - count); i < length; i++) {
    out.push(i);
  }
  return out;
}

// A turn's label: the card numbers it takes, so a Pick 2 pass reads "1-2" over the 1-14 card count.
function pickLabel(turn: number, perTurn: number): string {
  if (perTurn === 1) {
    return String(turn + 1);
  }
  return `${turn * perTurn + 1}-${turn * perTurn + perTurn}`;
}

// Custom formats (peasant cube, etc.) have no per-set art, so fall back to the generic cube icon.
function SetSymbol({ src, className }: { src: string; className?: string }) {
  return (
    <img
      src={src}
      alt=""
      className={className}
      onError={(e) => {
        const img = e.currentTarget;
        if (img.dataset.fallback !== "1") {
          img.dataset.fallback = "1";
          img.src = "/set-symbols/cube.png";
        }
      }}
    />
  );
}

// Mobile-only slim bar: the left and right neighbors stay anchored to their physical sides; the arrow
// between them points the way cards pass and flips for the right-to-left packs. Tapping a neighbor
// switches seats so you can walk the table.
function MobileTopBar({
  setSymbol,
  left,
  active,
  right,
  passRight,
  leftHref,
  rightHref,
  backHref,
  scrollOn,
  onToggleScroll,
  showGrades,
  onToggleGrades,
  solo = false,
}: {
  setSymbol: string;
  left: Seat;
  active: Seat;
  right: Seat;
  passRight: boolean;
  leftHref: string;
  rightHref: string;
  backHref: string;
  scrollOn: boolean;
  onToggleScroll: () => void;
  showGrades: boolean;
  onToggleGrades: () => void;
  solo?: boolean;
}) {
  const backClass = "flex shrink-0 items-center gap-1 text-subtle [-webkit-tap-highlight-color:transparent] active:text-text";
  return (
    <div className="flex h-10 shrink-0 items-center gap-2 border-b border-border bg-surface px-2 lg:hidden">
      <Link to={backHref} aria-label="Back to pod" className={backClass}>
        <ChevronIcon dir="left" />
        <SetSymbol src={setSymbol} className="h-5 w-5" />
      </Link>
      <SeatSwitcher
        left={left}
        active={active}
        right={right}
        passRight={passRight}
        leftHref={leftHref}
        rightHref={rightHref}
        solo={solo}
        size="mobile"
      />
      <MobileToggle label="GRADES" ariaLabel="Show grades" on={showGrades} onToggle={onToggleGrades} />
      {!solo && (
        <MobileToggle label="SCROLL" ariaLabel="Scroll the whole draft" on={scrollOn} onToggle={onToggleScroll} />
      )}
    </div>
  );
}

const SEAT_SWITCHER_SIZES = {
  mobile: { neighbor: "max-w-[78px] text-[13px]", arrow: "text-[13px]", active: "max-w-[96px] text-[15px]" },
  desktop: { neighbor: "max-w-[180px] text-[16px] hover:text-text", arrow: "text-[16px]", active: "max-w-[240px] text-[19px]" },
};

function SeatSwitcher({
  left,
  active,
  right,
  passRight,
  leftHref,
  rightHref,
  solo,
  size,
}: {
  left: Seat;
  active: Seat;
  right: Seat;
  passRight: boolean;
  leftHref: string;
  rightHref: string;
  solo: boolean;
  size: keyof typeof SEAT_SWITCHER_SIZES;
}) {
  const sizes = SEAT_SWITCHER_SIZES[size];
  const arrow = <span className={cn("shrink-0 font-mono text-subtle", sizes.arrow)}>{passRight ? "»" : "«"}</span>;
  const neighbor = cn(
    "truncate font-display tracking-[0.04em] text-subtle no-underline transition-colors",
    "[-webkit-tap-highlight-color:transparent] active:text-text",
    sizes.neighbor,
  );
  return (
    <div className="flex min-w-0 flex-1 items-center justify-center gap-1.5">
      {!solo && (
        <>
          <Link to={leftHref} replace className={neighbor}>
            {left.name}
          </Link>
          {arrow}
        </>
      )}
      <span className={cn("shrink truncate text-center font-display tracking-[0.06em] text-green", sizes.active)}>
        {active.name}
      </span>
      {!solo && (
        <>
          {arrow}
          <Link to={rightHref} replace className={neighbor}>
            {right.name}
          </Link>
        </>
      )}
    </div>
  );
}

function MobileToggle({ label, on, onToggle, ariaLabel }: { label: string; on: boolean; onToggle: () => void; ariaLabel: string }) {
  return (
    <button
      onClick={onToggle}
      role="switch"
      aria-checked={on}
      aria-label={ariaLabel}
      className="flex h-8 shrink-0 items-center gap-1.5 rounded-md border border-border bg-surface2 px-2 [-webkit-tap-highlight-color:transparent] active:bg-white/10"
    >
      <span className={cn("font-display text-[10px] tracking-[0.1em]", on ? "text-green" : "text-subtle")}>{label}</span>
      <span className={cn("relative h-3.5 w-6 rounded-full transition-colors", on ? "bg-green" : "bg-border2")}>
        <span className={cn("absolute top-[2px] h-2.5 w-2.5 rounded-full bg-white transition-all", on ? "left-[11px]" : "left-[2px]")} />
      </span>
    </button>
  );
}

function Header({
  left,
  active,
  right,
  passRight,
  leftHref,
  rightHref,
  setSymbol,
  eventTitle,
  backHref,
  pack,
  pick,
  turns,
  perTurn,
  jumpHref,
  prevHref,
  nextHref,
  awaitingReveal,
  onReveal,
  revealMode,
  onRevealMode,
  showGrades,
  onToggleGrades,
  showTable,
  onToggleTable,
  viewMode,
  onViewMode,
  solo = false,
}: {
  left: Seat;
  active: Seat;
  right: Seat;
  passRight: boolean;
  leftHref: string;
  rightHref: string;
  setSymbol: string;
  eventTitle: string;
  backHref: string;
  pack: number;
  pick: number;
  turns: number;
  perTurn: number;
  jumpHref: (pack: number, pick: number) => string;
  prevHref: string | null;
  nextHref: string | null;
  awaitingReveal: boolean;
  onReveal: () => void;
  revealMode: RevealMode;
  onRevealMode: (m: RevealMode) => void;
  showGrades: boolean;
  onToggleGrades: () => void;
  showTable: boolean;
  onToggleTable: () => void;
  viewMode: "step" | "scroll";
  onViewMode: (m: "step" | "scroll") => void;
  solo?: boolean;
}) {
  const revealControl = awaitingReveal ? (
    <Tooltip label="Reveal picked card" side="bottom">
      <button
        onClick={onReveal}
        aria-label="Reveal picked card"
        className="flex h-9 w-9 items-center justify-center gap-1.5 rounded-md border border-white/40 bg-surface2 font-display min-[1500px]:w-auto min-[1500px]:min-w-[84px] min-[1500px]:px-3 text-[13px] tracking-[0.12em] text-text transition-[transform,background-color,border-color,color] duration-150 ease-out touch-manipulation [-webkit-tap-highlight-color:transparent] hover:border-white/60 hover:bg-white/10 active:scale-90 active:bg-white/20 motion-reduce:active:scale-100"
      >
        <span className="hidden min-[1500px]:inline">REVEAL</span>
        <EyeIcon off={false} />
      </button>
    </Tooltip>
  ) : (
    <NavArrow dir="next" href={nextHref} />
  );

  const pickChipsRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    pickChipsRef.current?.querySelector("[aria-current]")?.scrollIntoView({ block: "nearest", inline: "nearest" });
  }, [pack, pick, viewMode]);

  const showPicksToggle = (
    <ShowPicksToggle
      showPicks={revealMode === "revealed"}
      onToggle={() => onRevealMode(revealMode === "revealed" ? "click" : "revealed")}
    />
  );

  return (
    <header {...KEEPS_PREVIEW} className="hidden h-[60px] shrink-0 items-center gap-3 border-b border-border bg-surface px-5 lg:flex">
      <div className="flex min-w-[54px] flex-1 items-center">
        <Link
          to={backHref}
          className="flex min-w-0 items-center gap-2.5 text-left transition-colors hover:text-green"
          aria-label="Back to pod"
        >
          <ChevronIcon dir="left" />
          <SetSymbol src={setSymbol} className="h-7 w-7 shrink-0" />
          <span className="truncate font-display text-[19px] tracking-[0.08em]">
            {highlightEventLabel(eventTitle)}
          </span>
        </Link>
      </div>

      {viewMode === "step" && (
        <div className="flex min-w-0 items-center gap-3 min-[1500px]:gap-5">
          <ChipRow label="PACK">
            {[0, 1, 2].map((p) => (
              <Chip key={p} active={p === pack} href={jumpHref(p, 0)}>
                {p + 1}
              </Chip>
            ))}
          </ChipRow>
          <div className="flex min-w-0 items-center gap-2">
            <ChipRow label="PICK" chipsRef={pickChipsRef}>
              {Array.from({ length: turns }, (_, k) => (
                <Chip key={k} active={k === pick} href={jumpHref(pack, k)}>
                  {pickLabel(k, perTurn)}
                </Chip>
              ))}
            </ChipRow>
            <div className="flex shrink-0 items-center gap-2">
              <NavArrow dir="prev" href={prevHref} />
              {revealControl}
            </div>
          </div>
        </div>
      )}

      {viewMode === "scroll" && (
        <SeatSwitcher
          left={left}
          active={active}
          right={right}
          passRight={passRight}
          leftHref={leftHref}
          rightHref={rightHref}
          solo={solo}
          size="desktop"
        />
      )}

      <div className="flex min-w-max flex-1 items-center justify-end gap-2">
        {showPicksToggle}
        <SwitchToggle
          label="GRADES"
          on={showGrades}
          onToggle={onToggleGrades}
          ariaLabel="Show grades"
          tooltip={showGrades ? "Hide 17Lands grades on the packs" : "Show 17Lands grades on the packs"}
        />
        {!solo && (
          <ScrollToggle on={viewMode === "scroll"} onToggle={() => onViewMode(viewMode === "scroll" ? "step" : "scroll")} />
        )}
        {!solo && (
          <SwitchToggle
            label="TABLE"
            on={showTable}
            onToggle={onToggleTable}
            ariaLabel="Show table"
            tooltip={showTable ? "Hide table" : "Show table"}
          />
        )}
        <Link
          to={backHref}
          aria-label="Close"
          className="flex h-9 w-9 items-center justify-center rounded-md border border-border bg-surface2 text-muted no-underline transition-colors hover:border-white/40 hover:bg-white/10 hover:text-text"
        >
          ✕
        </Link>
      </div>
    </header>
  );
}

function SwitchToggle({
  label,
  on,
  onToggle,
  tooltip,
  ariaLabel,
  disabled = false,
}: {
  label: ReactNode;
  on: boolean;
  onToggle: () => void;
  tooltip: string;
  ariaLabel: string;
  disabled?: boolean;
}) {
  const [hover, setHover] = useState(false);
  return (
    <Tooltip label={tooltip} side="bottom" open={hover && !disabled}>
      <button
        onClick={onToggle}
        onPointerEnter={(e) => e.pointerType === "mouse" && setHover(true)}
        onPointerLeave={() => setHover(false)}
        disabled={disabled}
        role="switch"
        aria-checked={on}
        aria-label={ariaLabel}
        className={cn(
          "flex h-9 shrink-0 items-center gap-2 rounded-md border border-border bg-surface2 px-2.5 transition-colors",
          "[-webkit-tap-highlight-color:transparent]",
          disabled ? "cursor-not-allowed opacity-40" : "hover:border-white/40 hover:bg-white/10",
        )}
      >
        <span className={cn("font-display text-[12px] tracking-[0.12em]", on ? "text-green" : "text-subtle")}>
          {label}
        </span>
        <ToggleSwitch on={on} />
      </button>
    </Tooltip>
  );
}

function ZoomControl({
  label,
  fitting,
  canShrink,
  canGrow,
  onStep,
  onToggleFit,
  fitTooltip,
  className,
  labelClassName,
}: {
  label: string;
  fitting: boolean;
  canShrink: boolean;
  canGrow: boolean;
  onStep: (dir: 1 | -1) => void;
  onToggleFit?: () => void;
  fitTooltip: string;
  className?: string;
  labelClassName?: string;
}) {
  const stepButton = cn(
    "flex h-full w-8 items-center justify-center text-[16px] text-subtle transition-colors",
    "hover:bg-white/10 hover:text-text disabled:cursor-not-allowed disabled:opacity-40 disabled:hover:bg-transparent",
  );
  const labelCell = "flex min-w-[52px] flex-1 items-center justify-center border-x border-border px-1.5";
  const shown = (
    <span
      className={cn(
        "font-display text-[14px] tracking-[0.12em] tabular-nums [text-box:trim-both_cap_alphabetic]",
        fitting ? "text-green" : cn("text-subtle", labelClassName),
      )}
    >
      {fitting ? "FIT" : label}
    </span>
  );
  return (
    <div
      className={cn(
        "flex shrink-0 items-stretch overflow-hidden rounded-md border border-border bg-surface2",
        className,
      )}
    >
      <Tooltip label="Smaller cards (Ctrl+Scroll)" side="top">
        <button onClick={() => onStep(-1)} disabled={!canShrink} aria-label="Smaller cards" className={stepButton}>
          −
        </button>
      </Tooltip>
      {onToggleFit ? (
        <Tooltip label={fitTooltip} side="top">
          <button
            onClick={onToggleFit}
            role="switch"
            aria-checked={fitting}
            aria-label="Fit"
            className={cn(labelCell, "transition-colors hover:bg-white/10")}
          >
            {shown}
          </button>
        </Tooltip>
      ) : (
        <span className={labelCell}>{shown}</span>
      )}
      <Tooltip label="Bigger cards (Ctrl+Scroll)" side="top">
        <button onClick={() => onStep(1)} disabled={!canGrow} aria-label="Bigger cards" className={stepButton}>
          +
        </button>
      </Tooltip>
    </div>
  );
}

function ShowPicksToggle({ showPicks, onToggle }: { showPicks: boolean; onToggle: () => void }) {
  return (
    <SwitchToggle
      label={
        <>
          <span className="hidden min-[1500px]:inline">SHOW </span>PICKS
        </>
      }
      on={showPicks}
      onToggle={onToggle}
      ariaLabel="Show picks"
      tooltip={showPicks ? "Hide picks to guess before revealing (Space)" : "Reveal picks automatically (Space)"}
    />
  );
}

function ShowNeighborsToggle({ on, onToggle }: { on: boolean; onToggle: () => void }) {
  return (
    <SwitchToggle
      label="SHOW NEIGHBORS"
      on={on}
      onToggle={onToggle}
      ariaLabel="Show neighbors"
      tooltip={on ? "Hide Left & Right players" : "Show Left & Right players"}
    />
  );
}

function ScrollToggle({ on, onToggle }: { on: boolean; onToggle: () => void }) {
  return (
    <SwitchToggle
      label={
        <>
          SCROLL<span className="hidden min-[1500px]:inline"> MODE</span>
        </>
      }
      on={on}
      onToggle={onToggle}
      ariaLabel="Scroll the whole draft"
      tooltip={on ? "Whole draft in one scrollable view" : "One pick at a time"}
    />
  );
}

function ChipRow({
  label,
  chipsRef,
  children,
}: {
  label: string;
  chipsRef?: React.Ref<HTMLDivElement>;
  children: React.ReactNode;
}) {
  return (
    <div className={cn("flex items-center gap-2", chipsRef ? "min-w-0" : "shrink-0")}>
      <span className="font-display text-[14px] tracking-[0.18em] text-subtle">{label}</span>
      <div ref={chipsRef} className="no-scrollbar flex min-w-0 gap-1 overflow-x-auto">
        {children}
      </div>
    </div>
  );
}

function Chip({ active, href, children }: { active: boolean; href: string; children: React.ReactNode }) {
  return (
    <Link
      to={href}
      replace
      aria-current={active || undefined}
      className={cn(
        "flex h-8 min-w-[32px] shrink-0 items-center justify-center rounded border px-2 font-display text-[16px] tracking-[0.04em] tabular-nums no-underline transition-colors",
        active
          ? "border-green/60 bg-green/15 text-green"
          : "border-border bg-surface2 text-subtle hover:border-white/40 hover:bg-white/10 hover:text-text",
      )}
    >
      {children}
    </Link>
  );
}

const BOOSTER_GAP = 8;
const BOOSTER_PAD = 12;

function BoosterPanel({
  cards,
  pickedPositions,
  showGrades,
  fadeKey,
  onNaturalHeight,
  cardWidth,
  fitCount,
  onFitWidth,
  onZoomStep,
}: {
  cards: ArtifactCard[];
  pickedPositions: number[];
  showGrades: boolean;
  fadeKey: string;
  onNaturalHeight?: (height: number) => void;
  cardWidth: number;
  fitCount: number | null;
  onFitWidth: (width: number) => void;
  onZoomStep: (dir: 1 | -1) => void;
}) {
  const scrollRef = useRef<HTMLDivElement>(null);
  useCtrlWheelZoom(scrollRef, onZoomStep);
  const area = useElementSize(scrollRef);
  const measured = fitCount !== null && area.width > 0;
  const usableWidth = area.width - BOOSTER_PAD * 2;
  const usableHeight = area.height - BOOSTER_PAD * 2;
  const fitWidth = measured ? widestFittingCard(fitCount, usableWidth, usableHeight) : null;
  useLayoutEffect(() => {
    if (fitWidth !== null) {
      onFitWidth(fitWidth);
    }
  }, [fitWidth, onFitWidth]);
  useLayoutEffect(() => {
    const content = scrollRef.current?.firstElementChild as HTMLElement | null | undefined;
    if (!content || !onNaturalHeight) {
      return;
    }
    const measure = () => onNaturalHeight(content.offsetHeight + BOOSTER_PAD * 2);
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(content);
    return () => observer.disconnect();
  }, [cards, onNaturalHeight]);
  return (
    <div ref={scrollRef} className="themed-scrollbar min-h-0 flex-1 overflow-y-auto" style={{ padding: BOOSTER_PAD }}>
      <div key={fadeKey} className="animate-fadeUpIn">
        <BoosterGrid cards={cards} pickedPositions={pickedPositions} showGrades={showGrades} cardWidth={cardWidth} />
      </div>
    </div>
  );
}

function BoosterGrid({
  cards,
  pickedPositions,
  showGrades,
  cardWidth,
}: {
  cards: ArtifactCard[];
  pickedPositions: number[];
  showGrades: boolean;
  cardWidth: number;
}) {
  const gridStyle = { gap: BOOSTER_GAP, "--booster-card-w": `${cardWidth}px` } as CSSProperties;
  return (
    <div className="flex flex-wrap content-start justify-center" style={gridStyle}>
      {cards.map((card, i) => (
        <div key={i} className="w-[calc((100%-16px)/3)] sm:w-[calc((100%-24px)/4)] lg:w-[var(--booster-card-w)]">
          <BoosterCard card={card} picked={pickedPositions.includes(i)} showGrades={showGrades} />
        </div>
      ))}
    </div>
  );
}

function BoosterCard({ card, picked, showGrades }: { card: ArtifactCard; picked: boolean; showGrades: boolean }) {
  return (
    <div
      className={cn(
        CARD_FRAME,
        "relative",
        "transition-transform duration-150 hover:z-10 hover:scale-[1.04]",
        picked && "p0p1-card-selected z-10 scale-[1.03] hover:scale-[1.05]",
      )}
    >
      <CardImage card={card} />
      {showGrades && <CardGradeOverlay card={card} />}
    </div>
  );
}

const BOOSTER_CARD_WIDTH = 210;
const RECAP_CARD_WIDTH = 148;
const BOOSTER_ZOOM_STEPS = [0.6, 0.7, 0.8, 0.9, 1, 1.15, 1.3];
const BOOSTER_MIN_ZOOM = BOOSTER_ZOOM_STEPS[0];
const BOOSTER_MAX_ZOOM = BOOSTER_ZOOM_STEPS[BOOSTER_ZOOM_STEPS.length - 1];

type Zoom = "fit" | `${number}`;

function nextZoomStep(current: number, dir: 1 | -1): Zoom {
  const steps = dir === 1 ? BOOSTER_ZOOM_STEPS : [...BOOSTER_ZOOM_STEPS].reverse();
  for (const step of steps) {
    if ((step - current) * dir > 0.01) {
      return `${step}`;
    }
  }
  return `${steps[steps.length - 1]}`;
}

function widestFittingCard(count: number, width: number, height: number): number {
  const narrowest = Math.round(BOOSTER_CARD_WIDTH * BOOSTER_MIN_ZOOM);
  const widest = Math.round(BOOSTER_CARD_WIDTH * BOOSTER_MAX_ZOOM);
  for (let cardWidth = widest; cardWidth > narrowest; cardWidth -= 2) {
    const columns = Math.floor((width + BOOSTER_GAP) / (cardWidth + BOOSTER_GAP));
    const rows = Math.ceil(count / Math.max(1, columns));
    const gridHeight = rows * cardWidth * CARD_ASPECT + (rows - 1) * BOOSTER_GAP;
    if (columns > 0 && gridHeight <= height) {
      return cardWidth;
    }
  }
  return narrowest;
}

function largestPackSize(packs: DraftPickView[][]): number {
  let largest = 0;
  for (const pickViews of packs) {
    largest = Math.max(largest, pickViews[0]?.booster.length ?? 0);
  }
  return largest;
}

function useCtrlWheelZoom(ref: RefObject<HTMLElement | null>, onStep: (dir: 1 | -1) => void) {
  const onStepRef = useRef(onStep);
  onStepRef.current = onStep;
  useEffect(() => {
    const el = ref.current;
    if (!el) {
      return;
    }
    let pending = 0;
    const onWheel = (e: WheelEvent) => {
      if (!e.ctrlKey) {
        return;
      }
      e.preventDefault();
      pending += wheelPixels(e, el);
      if (Math.abs(pending) < 40) {
        return;
      }
      onStepRef.current(pending < 0 ? 1 : -1);
      pending = 0;
    };
    el.addEventListener("wheel", onWheel, { passive: false });
    return () => el.removeEventListener("wheel", onWheel);
  }, [ref]);
}

// Continuous-scroll recap: every pick across all three packs stacked top-to-bottom for one seat, each
// section showing that pick's booster with the taken card highlighted. No deck/pool state, just the
// sequence — a fast skim. Honors the reveal mode: "click" hides each pick until its REVEAL is tapped.
function DraftScrollRecap({
  packs,
  cards,
  perTurn,
  revealMode,
  showGrades,
  initialPack,
  initialPick,
  cardWidth,
  onZoomStep,
  onActivePick,
}: {
  packs: DraftPickView[][];
  cards: ArtifactCard[];
  perTurn: number;
  revealMode: RevealMode;
  showGrades: boolean;
  initialPack: number;
  initialPick: number;
  cardWidth: number;
  onZoomStep: (dir: 1 | -1) => void;
  onActivePick: (pack: number, pick: number) => void;
}) {
  const ref = useRef<HTMLDivElement>(null);
  useCtrlWheelZoom(ref, onZoomStep);
  const onActivePickRef = useRef(onActivePick);
  onActivePickRef.current = onActivePick;
  useLayoutEffect(() => {
    const root = ref.current;
    const target = root?.querySelector(`[data-pick="${initialPack}-${initialPick}"]`);
    if (!root || !(target instanceof HTMLElement)) {
      return;
    }
    const offset = target.getBoundingClientRect().top - root.getBoundingClientRect().top;
    root.scrollTop += offset - parseFloat(getComputedStyle(root).paddingTop);
  }, []);
  useEffect(() => {
    const root = ref.current;
    if (!root) {
      return;
    }
    const observer = new IntersectionObserver(
      (entries) => {
        let topmost: IntersectionObserverEntry | null = null;
        for (const entry of entries) {
          if (entry.isIntersecting && (!topmost || entry.boundingClientRect.top < topmost.boundingClientRect.top)) {
            topmost = entry;
          }
        }
        const key = topmost && (topmost.target as HTMLElement).dataset.pick;
        if (!key) {
          return;
        }
        const [p, k] = key.split("-").map(Number);
        onActivePickRef.current(p, k);
      },
      { root, rootMargin: "0px 0px -85% 0px", threshold: 0 },
    );
    root.querySelectorAll("[data-pick]").forEach((el) => observer.observe(el));
    return () => observer.disconnect();
  }, []);
  return (
    <div
      ref={ref}
      className="themed-scrollbar min-h-0 flex-1 overflow-y-auto px-3 pb-3 pt-1 lg:px-8 lg:pb-6 lg:pt-3"
      style={{ "--recap-card-w": `${cardWidth}px` } as CSSProperties}
    >
      {packs.map((pickViews, p) =>
        pickViews.map((view, k) => (
          <RecapSection
            key={`${p}-${k}`}
            pack={p}
            pick={k}
            perTurn={perTurn}
            view={view}
            cards={cards}
            revealMode={revealMode}
            showGrades={showGrades}
          />
        )),
      )}
    </div>
  );
}

function RecapSection({
  pack,
  pick,
  perTurn,
  view,
  cards,
  revealMode,
  showGrades,
}: {
  pack: number;
  pick: number;
  perTurn: number;
  view: DraftPickView;
  cards: ArtifactCard[];
  revealMode: RevealMode;
  showGrades: boolean;
}) {
  const [clicked, setClicked] = useState(false);
  const shown = revealMode === "revealed" || clicked;
  const boosterCards = view.booster.map((idx) => cards[idx]);
  const takenNames = view.takenPositions.map((pos) => frontFace(boosterCards[pos]?.n ?? "")).join(", ");
  return (
    <section data-pick={`${pack}-${pick}`} className="mb-7 lg:mb-9">
      <div className="mb-2 flex h-9 items-center gap-3 border-b border-border lg:mb-3 lg:h-10">
        <span className="shrink-0 whitespace-nowrap font-display text-[15px] tracking-[0.16em] text-subtle">
          PACK {pack + 1}
        </span>
        <span className="shrink-0 whitespace-nowrap font-display text-[15px] tracking-[0.16em] text-subtle">
          PICK {pickLabel(pick, perTurn)}
        </span>
        {shown ? (
          <span className="flex min-w-0 items-center gap-2">
            <ArrowRight size={16} className="shrink-0 text-subtle" aria-hidden="true" />
            <span className="truncate font-display text-[16px] tracking-[0.04em] text-green">{takenNames}</span>
          </span>
        ) : (
          <button
            onClick={() => setClicked(true)}
            className="ml-1 rounded border border-border bg-surface2 px-2.5 py-1 font-display text-[12px] tracking-[0.12em] text-subtle transition-colors hover:border-white/40 hover:text-text"
          >
            REVEAL
          </button>
        )}
      </div>
      <div
        className={cn(
          "grid gap-2 [grid-template-columns:repeat(auto-fill,minmax(104px,1fr))]",
          "lg:[grid-template-columns:repeat(auto-fill,minmax(var(--recap-card-w),1fr))]",
        )}
      >
        {boosterCards.map((card, i) => (
          <BoosterCard key={i} card={card} picked={shown && view.takenPositions.includes(i)} showGrades={showGrades} />
        ))}
      </div>
    </section>
  );
}

const PANEL_DRAG_THRESHOLD = 4;
const PANEL_MIN_HEIGHT = 64;
const PANEL_COLLAPSE_AT = 40;

function useResizableHeight(baseHeight: number, storageKey: string, onCollapse?: () => void) {
  const [dragHeight, setDragHeight] = useState<number | null>(() => storedPanelHeight(storageKey));
  const [dragging, setDragging] = useState(false);
  const height = dragHeight ?? baseHeight;
  useEffect(() => {
    if (dragging) {
      return;
    }
    if (dragHeight == null) {
      window.localStorage.removeItem(storageKey);
    } else {
      window.localStorage.setItem(storageKey, `${Math.round(dragHeight)}`);
    }
  }, [dragHeight, dragging, storageKey]);
  const beginResize = (startY: number, fromHeight?: number) => {
    const startHeight = fromHeight ?? dragHeight ?? baseHeight;
    let collapsible = fromHeight == null;
    if (fromHeight != null) {
      setDragHeight(fromHeight);
    }
    setDragging(true);
    const onMove = (ev: PointerEvent) => {
      const next = startHeight - (ev.clientY - startY);
      if (next >= PANEL_MIN_HEIGHT) {
        collapsible = true;
      }
      if (onCollapse && collapsible && next < PANEL_COLLAPSE_AT) {
        onCollapse();
        setDragHeight(null);
        cleanup();
        return;
      }
      const floor = collapsible ? PANEL_MIN_HEIGHT : 0;
      setDragHeight(Math.min(window.innerHeight * DECK_PANEL_MAX_FRACTION, Math.max(floor, next)));
    };
    const onUp = () => cleanup();
    function cleanup() {
      setDragging(false);
      setDragHeight((h) => (h != null && h < PANEL_MIN_HEIGHT ? PANEL_MIN_HEIGHT : h));
      window.removeEventListener("pointermove", onMove);
      window.removeEventListener("pointerup", onUp);
    }
    window.addEventListener("pointermove", onMove);
    window.addEventListener("pointerup", onUp);
  };
  return { height, beginResize, dragging };
}

function storedPanelHeight(storageKey: string): number | null {
  if (typeof window === "undefined") {
    return null;
  }
  const stored = Number(window.localStorage.getItem(storageKey));
  if (!stored) {
    return null;
  }
  return Math.min(stored, window.innerHeight * DECK_PANEL_MAX_FRACTION);
}

// Thick bar shared by the deck pool and the neighbor band: a tap toggles the panel collapsed, a press
// and drag past a small threshold resizes it instead. The chevron tab on the top edge shows which way
// a tap moves it. With nothing to show (no neighbor picks yet) it renders static, no toggle or resize.
function PanelBar({
  open,
  canCollapse,
  onToggle,
  onResizeStart,
  children,
}: {
  open: boolean;
  canCollapse: boolean;
  onToggle: () => void;
  onResizeStart: (startY: number, fromHeight?: number) => void;
  children: React.ReactNode;
}) {
  const handlePointerDown = (e: React.PointerEvent) => {
    if (e.button !== 0) {
      return;
    }
    e.preventDefault();
    const startY = e.clientY;
    let dragging = false;
    const onMove = (ev: PointerEvent) => {
      if (!dragging && Math.abs(ev.clientY - startY) > PANEL_DRAG_THRESHOLD) {
        dragging = true;
        if (open) {
          onResizeStart(startY);
        } else {
          onToggle();
          onResizeStart(startY, 0);
        }
      }
    };
    const onUp = () => {
      window.removeEventListener("pointermove", onMove);
      window.removeEventListener("pointerup", onUp);
      if (!dragging) {
        onToggle();
      }
    };
    window.addEventListener("pointermove", onMove);
    window.addEventListener("pointerup", onUp);
  };
  if (!canCollapse) {
    return (
      <div className="relative hidden h-10 w-full shrink-0 items-center border-t border-border bg-bg lg:flex">
        {children}
      </div>
    );
  }
  return (
    <div
      onPointerDown={handlePointerDown}
      className="group relative hidden h-10 w-full shrink-0 cursor-row-resize select-none items-center border-t border-border bg-bg transition-colors hover:bg-surface2 lg:flex"
    >
      <span className="absolute bottom-full left-1/2 flex -translate-x-1/2 translate-y-px items-center justify-center rounded-t-md border border-b-0 border-border bg-bg px-3 text-subtle transition-colors group-hover:bg-surface2 group-hover:text-text">
        <ChevronIcon dir={open ? "down" : "up"} />
      </span>
      {children}
    </div>
  );
}

function DeckBarStat({ n, label }: { n: number; label: string }) {
  if (n === 0) {
    return null;
  }
  return (
    <span className="flex items-baseline gap-1">
      <span className="tabular-nums text-subtle">{n}</span>
      <span className="text-[12px] tracking-[0.1em] text-muted">{label}</span>
    </span>
  );
}

// Mobile deck pool: always visible below the booster, no collapse. Desktop deck+neighbors live in
// BottomPanel instead.
function PoolBar({
  cards,
  rows,
  sideboard,
  lastPicks,
  deckLayout,
  onToggleDeckLayout,
  canSplit,
  splitSideboard,
  onToggleSplit,
  deckLink,
}: {
  cards: ArtifactCard[];
  rows: ArtifactCard[][];
  sideboard: ArtifactCard[];
  lastPicks: LastPicks;
  deckLayout: "order" | "columns";
  onToggleDeckLayout: () => void;
  canSplit: boolean;
  splitSideboard: boolean;
  onToggleSplit: () => void;
  deckLink?: InPlaceLink;
}) {
  const order = deckLayout === "order";
  return (
    <div className="relative shrink-0 border-t border-border bg-surface/60 pb-1 pl-0 pr-1 pt-0 lg:hidden">
      <div className="absolute bottom-2 right-2 z-20">
        <PoolControls
          canSplit={canSplit}
          splitSideboard={splitSideboard}
          onToggleSplit={onToggleSplit}
          deckLink={deckLink}
          deckLayout={deckLayout}
          onToggleDeckLayout={onToggleDeckLayout}
        />
      </div>
      <div className={cn("flex gap-1", order ? "h-[24dvh]" : "h-[32dvh]")}>
        <PoolCards
          order={order}
          rows={rows}
          cards={cards}
          lastPicks={lastPicks}
          splitSideboard={splitSideboard}
          sideboard={sideboard}
          cardWidth={104}
          reveal={order ? 21 : 16}
          sideReveal={14}
          poolAlign="right"
        />
      </div>
    </div>
  );
}

function PoolCards({
  order,
  rows,
  cards,
  lastPicks,
  splitSideboard,
  sideboard,
  cardWidth,
  reveal,
  sideReveal,
  curve,
  poolAlign,
  controls,
}: {
  order: boolean;
  rows: ArtifactCard[][];
  cards: ArtifactCard[];
  lastPicks: LastPicks;
  splitSideboard: boolean;
  sideboard: ArtifactCard[];
  cardWidth: number;
  reveal: number;
  sideReveal: number;
  curve?: CurveMode;
  poolAlign?: "left" | "right";
  controls?: ReactNode;
}) {
  const showPane = splitSideboard && sideboard.length > 0;
  const inlineSideboard = showPane ? [] : sideboard;
  const paneCardWidth = Math.round(cardWidth * SIDE_PANE_RATIO);
  return (
    <>
      <div className="relative min-w-0 flex-1">
        {controls}
        {order ? (
          <OrderStrip rows={rows} sideboard={inlineSideboard} lastPicks={lastPicks} cardWidth={cardWidth} reveal={reveal} />
        ) : (
          <Pool
            cards={cards}
            sideboard={inlineSideboard}
            lastPicks={lastPicks}
            curve={curve}
            align={poolAlign}
            cardWidth={cardWidth}
            reveal={reveal}
          />
        )}
      </div>
      {showPane && (
        <SideboardPane cards={sideboard} markCount={lastPicks.side} cardWidth={paneCardWidth} reveal={sideReveal} />
      )}
    </>
  );
}

// Desktop bottom zone: one bar identifying the active player, its DECK|NEIGHBORS switch, and a single
// collapsible/resizable panel that shows either the player's own pool or the two neighbors' pools.
function BottomPanel({
  defaultHeight,
  activeName,
  activeAvatarUrl,
  cards,
  rows,
  sideboard,
  lastPicks,
  deckLayout,
  onToggleDeckLayout,
  canSplit,
  splitSideboard,
  onToggleSplit,
  splitTypes,
  onToggleSplitTypes,
  deckLink,
  left,
  right,
  passRight,
  leftPile,
  centerPile,
  rightPile,
}: {
  defaultHeight: number;
  activeName: string;
  activeAvatarUrl: string | null;
  cards: ArtifactCard[];
  rows: ArtifactCard[][];
  sideboard: ArtifactCard[];
  lastPicks: LastPicks;
  deckLayout: "order" | "columns";
  onToggleDeckLayout: () => void;
  canSplit: boolean;
  splitSideboard: boolean;
  onToggleSplit: () => void;
  splitTypes: boolean;
  onToggleSplitTypes: () => void;
  deckLink?: InPlaceLink;
  left: Seat;
  right: Seat;
  passRight: boolean;
  leftPile: Pile;
  centerPile: Pile;
  rightPile: Pile;
}) {
  const [open, setOpen] = usePersistentBool("draftReviewDeckPanelOpen", true);
  const [tab, setTab] = useState<"deck" | "neighbors">("deck");
  const order = deckLayout === "order";
  const showSideboard = splitSideboard && sideboard.length > 0;
  const collapse = () => setOpen(false);
  const { height, beginResize, dragging } = useResizableHeight(defaultHeight, "draftReviewDeckPanelHeight", collapse);
  const [deckZoom, setDeckZoom] = usePersistentState<Zoom>("draftReviewDeckZoom", "fit");
  const deckAreaRef = useRef<HTMLDivElement>(null);
  const deckAreaWidth = useElementSize(deckAreaRef).width;
  const curve: CurveMode = splitTypes ? "split" : "mixed";
  const track = deckTrack(order, rows, cards, showSideboard ? [] : sideboard, curve);
  const paneShare = showSideboard ? SIDE_PANE_RATIO : 0;
  const widthForColumns = (columns: number) => deckCardWidthFor(deckAreaWidth, columns, 0, paneShare);
  const deckFitting = deckZoom === "fit";
  const trackFitWidth = deckCardWidthFor(deckAreaWidth, track.cardColumns, track.spacers, paneShare);
  const chosenWidth = deckFitting ? Math.min(DECK_CARD_WIDTH, trackFitWidth) : widthForColumns(Number(deckZoom));
  const clampedWidth = Math.min(DECK_MAX_CARD_WIDTH, Math.max(DECK_MIN_CARD_WIDTH, chosenWidth));
  const deckCardWidth = deckAreaWidth > 0 ? clampedWidth : DECK_CARD_WIDTH;
  const deckColumns = columnsShowing(deckCardWidth, widthForColumns);
  const deckScale = deckCardWidth / DECK_CARD_WIDTH;
  const stepDeckZoom = (dir: 1 | -1) => setDeckZoom(`${Math.max(1, deckColumns - dir)}`);
  const toggleDeckFit = () => setDeckZoom(deckFitting ? `${columnsShowing(DECK_CARD_WIDTH, widthForColumns)}` : "fit");
  useCtrlWheelZoom(deckAreaRef, stepDeckZoom);
  const deckControls = (
    <div className="absolute bottom-1 right-6 z-20">
      <PoolControls
        zoom={
          <ZoomControl
            label={`${deckColumns} COLS`}
            fitting={deckFitting}
            canShrink={widthForColumns(deckColumns + 1) >= DECK_MIN_CARD_WIDTH}
            canGrow={deckColumns > 1 && deckCardWidth < DECK_MAX_CARD_WIDTH}
            onStep={stepDeckZoom}
            onToggleFit={toggleDeckFit}
            fitTooltip={deckFitting ? "Cards sized so every column fits" : "Fit Deck to the panel width"}
            className="h-8"
            labelClassName="text-[13px]"
          />
        }
        canSplit={canSplit}
        splitSideboard={splitSideboard}
        onToggleSplit={onToggleSplit}
        splitTypes={splitTypes}
        onToggleSplitTypes={onToggleSplitTypes}
        deckLink={deckLink}
        deckLayout={deckLayout}
        onToggleDeckLayout={onToggleDeckLayout}
      />
    </div>
  );

  const activeTab = tab;
  let creatures = 0;
  let lands = 0;
  for (const card of cards) {
    const type = card.type ?? "";
    if (/creature/i.test(type)) {
      creatures++;
    } else if (/land/i.test(type)) {
      lands++;
    }
  }
  const selectTab = (t: "deck" | "neighbors") => {
    setTab(t);
    setOpen(true);
  };

  return (
    <div className="hidden shrink-0 flex-col lg:flex">
      <PanelBar open={open} canCollapse onToggle={() => setOpen((v) => !v)} onResizeStart={beginResize}>
        <BottomBar
          activeName={activeName}
          activeAvatarUrl={activeAvatarUrl}
          tab={activeTab}
          onTab={selectTab}
          total={cards.length}
          creatures={creatures}
          lands={lands}
          left={left}
          right={right}
          passRight={passRight}
        />
      </PanelBar>
      <div
        ref={deckAreaRef}
        className="relative shrink-0 overflow-hidden bg-surface/60"
        style={{ height: open ? height : 0, transition: dragging ? "none" : "height 200ms ease" }}
      >
        {activeTab === "deck" ? (
          <div className="relative flex h-full py-1 pl-6">
            <PoolCards
              order={order}
              rows={rows}
              cards={cards}
              lastPicks={lastPicks}
              splitSideboard={splitSideboard}
              sideboard={sideboard}
              cardWidth={deckCardWidth}
              reveal={Math.round((order ? DECK_ORDER_REVEAL : DECK_CURVE_REVEAL) * deckScale)}
              sideReveal={Math.round(DECK_SIDE_REVEAL * deckScale)}
              curve={curve}
              controls={deckControls}
            />
          </div>
        ) : (
          <NeighborColumns left={leftPile} center={centerPile} right={rightPile} />
        )}
      </div>
    </div>
  );
}

const DECK_CARD_WIDTH = 176;
const DECK_CURVE_REVEAL = 28;
const DECK_ORDER_REVEAL = 44;
const DECK_SIDE_REVEAL = 24;
const DECK_MIN_CARD_WIDTH = 64;
const DECK_MAX_CARD_WIDTH = 260;
const SIDE_PANE_RATIO = 0.9;

function deckTrack(
  order: boolean,
  rows: ArtifactCard[][],
  cards: ArtifactCard[],
  inlineSideboard: ArtifactCard[],
  curve: CurveMode,
) {
  const sideColumns = inlineSideboard.length > 0 ? 1 : 0;
  if (order) {
    let positions = 0;
    for (const row of rows) {
      positions = Math.max(positions, row.length);
    }
    return { cardColumns: positions + sideColumns, spacers: sideColumns };
  }
  let cardColumns = sideColumns;
  let spacers = sideColumns;
  for (const group of curveColumns(cards.map((card, idx) => ({ card, idx })), curve)) {
    if (group) {
      cardColumns++;
    } else {
      spacers++;
    }
  }
  return { cardColumns, spacers };
}

function deckCardWidthFor(areaWidth: number, cardColumns: number, spacers: number, paneShare: number): number {
  const insetAndScrollbar = 64;
  const elements = cardColumns + spacers;
  const fixedWidth = insetAndScrollbar + POOL_PAD * 2 + Math.max(0, elements - 1) * POOL_GAP;
  const widthUnits = cardColumns + spacers * SIDE_COLUMN_GAP_RATIO + paneShare;
  return Math.floor((areaWidth - fixedWidth) / Math.max(1, widthUnits));
}

function columnsShowing(cardWidth: number, widthForColumns: (columns: number) => number): number {
  let columns = 1;
  while (widthForColumns(columns + 1) >= cardWidth) {
    columns++;
  }
  return columns;
}
const CARD_ASPECT = 680 / 488;
const DECK_PANEL_MAX_FRACTION = 0.72;
const DECK_PANEL_FLOOR = 120;
const DECK_WRAPPER_PAD_Y = 4;
const REVIEW_HEADER_HEIGHT = 60;
const DECK_PANEL_BAR_HEIGHT = 40;

function useViewportHeight() {
  const [viewportHeight, setViewportHeight] = useState(() => (typeof window === "undefined" ? 900 : window.innerHeight));
  useEffect(() => {
    const onResize = () => setViewportHeight(window.innerHeight);
    window.addEventListener("resize", onResize);
    return () => window.removeEventListener("resize", onResize);
  }, []);
  return viewportHeight;
}

function useElementSize(ref: RefObject<HTMLElement | null>) {
  const [size, setSize] = useState({ width: 0, height: 0 });
  useLayoutEffect(() => {
    const el = ref.current;
    if (!el) {
      return;
    }
    const measure = () => {
      const width = el.clientWidth;
      const height = el.clientHeight;
      setSize((prev) => (prev.width === width && prev.height === height ? prev : { width, height }));
    };
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(el);
    return () => observer.disconnect();
  }, [ref]);
  return size;
}

function deckPanelDefaultHeight(viewportHeight: number, boosterHeight: number) {
  const oneCard = Math.ceil(DECK_CARD_WIDTH * CARD_ASPECT + POOL_PAD * 2 + DECK_WRAPPER_PAD_Y * 2);
  const cap = Math.min(oneCard, viewportHeight * DECK_PANEL_MAX_FRACTION);
  const leftoverBelowBooster = viewportHeight - REVIEW_HEADER_HEIGHT - DECK_PANEL_BAR_HEIGHT - boosterHeight;
  return Math.max(DECK_PANEL_FLOOR, Math.min(cap, leftoverBelowBooster));
}

function BottomBar({
  activeName,
  activeAvatarUrl,
  tab,
  onTab,
  total,
  creatures,
  lands,
  left,
  right,
  passRight,
}: {
  activeName: string;
  activeAvatarUrl: string | null;
  tab: "deck" | "neighbors";
  onTab: (t: "deck" | "neighbors") => void;
  total: number;
  creatures: number;
  lands: number;
  left: Seat;
  right: Seat;
  passRight: boolean;
}) {
  const arrow = passRight ? "»" : "«";
  return (
    <div className="relative flex h-full w-full items-center font-display">
      {tab === "deck" ? (
        <>
          <div className="flex w-1/2 min-w-0 items-center justify-center gap-2 text-[15px] tracking-[0.08em]">
            <AAvatar displayName={activeName} avatarUrl={activeAvatarUrl} size={22} green />
            <span className="max-w-[220px] truncate text-green">{activeName}</span>
          </div>
          <div className="absolute left-1/2 flex -translate-x-1/2 items-center gap-3.5 text-[14px] tracking-[0.08em]">
            <span className="tracking-[0.16em] text-subtle">DECK</span>
            <DeckBarStat n={total} label="CARDS" />
            <DeckBarStat n={creatures} label="CREATURES" />
            <DeckBarStat n={lands} label="LANDS" />
            <DeckBarStat n={total - creatures - lands} label="SPELLS" />
          </div>
        </>
      ) : (
        <div className="flex w-full items-stretch text-[14px] tracking-[0.08em]">
          <div className="flex min-w-0 flex-1 items-center justify-end gap-2 pr-3">
            <NeighborName seat={left} />
            <span className="font-mono text-muted">{arrow}</span>
          </div>
          <div className="w-0.5 shrink-0" />
          <div className="flex min-w-0 flex-[1.7] items-center justify-center gap-2 text-[15px]">
            <AAvatar displayName={activeName} avatarUrl={activeAvatarUrl} size={20} green />
            <span className="max-w-[220px] truncate text-green">{activeName}</span>
          </div>
          <div className="w-0.5 shrink-0" />
          <div className="flex min-w-0 flex-1 items-center justify-start gap-2 pl-3">
            <span className="font-mono text-muted">{arrow}</span>
            <NeighborName seat={right} />
          </div>
        </div>
      )}
      <span className="absolute right-4 top-1/2 -translate-y-1/2" onPointerDown={(e) => e.stopPropagation()}>
        <ShowNeighborsToggle
          on={tab === "neighbors"}
          onToggle={() => onTab(tab === "neighbors" ? "deck" : "neighbors")}
        />
      </span>
    </div>
  );
}

function NeighborName({ seat }: { seat: Seat }) {
  return (
    <span className="flex min-w-0 items-center gap-2">
      <AAvatar displayName={seat.name} avatarUrl={seat.avatarUrl} size={18} />
      <span className="max-w-[150px] truncate text-subtle">{seat.name}</span>
    </span>
  );
}

function NeighborColumns({ left, center, right }: { left: Pile; center: Pile; right: Pile }) {
  return (
    <div className="flex h-full items-stretch">
      <div className="min-w-0 flex-1 pt-2">
        <Pool cards={left.main} sideboard={left.board} lastPicks={left.lastPicks} cardWidth={140} reveal={22} />
      </div>
      <div className="w-0.5 shrink-0 self-stretch bg-border" />
      <div className="min-w-0 flex-[1.7] pt-2">
        <Pool cards={center.main} sideboard={center.board} lastPicks={center.lastPicks} cardWidth={166} reveal={26} />
      </div>
      <div className="w-0.5 shrink-0 self-stretch bg-border" />
      <div className="min-w-0 flex-1 pt-2">
        <Pool cards={right.main} sideboard={right.board} lastPicks={right.lastPicks} cardWidth={140} reveal={22} align="right" />
      </div>
    </div>
  );
}

function PoolControls({
  canSplit,
  splitSideboard,
  onToggleSplit,
  deckLink,
  deckLayout,
  onToggleDeckLayout,
  zoom,
  splitTypes,
  onToggleSplitTypes,
}: {
  canSplit: boolean;
  splitSideboard: boolean;
  onToggleSplit: () => void;
  deckLink?: InPlaceLink;
  deckLayout: "order" | "columns";
  onToggleDeckLayout: () => void;
  zoom?: ReactNode;
  splitTypes?: boolean;
  onToggleSplitTypes?: () => void;
}) {
  const pill = "flex h-7 items-center justify-center gap-1.5 rounded border px-2.5 font-display text-[11px] tracking-[0.12em] transition-colors lg:h-8 lg:rounded-md lg:px-3 lg:text-[13px]";
  const idle = "border-border bg-surface2 text-subtle hover:border-white/40 hover:text-text";
  const active = "border-green/60 bg-surface2 text-green [background-image:linear-gradient(rgba(46,232,92,0.15),rgba(46,232,92,0.15))]";
  return (
    <div className="flex flex-col items-stretch gap-1.5">
      {zoom}
      {(deckLink || canSplit) && (
        <div className="flex w-full gap-1.5">
          {deckLink && (
            <Link
              to={deckLink.href}
              onClick={onPlainClick(deckLink.open)}
              className={cn(pill, idle, "flex-1 no-underline")}
            >
              DECK
              <TbCards size={14} aria-hidden="true" />
            </Link>
          )}
          {canSplit && (
            <Tooltip label={splitSideboard ? "Merge the sideboard into the deck column" : "Split the sideboard into its own panel"} side="top">
              <button
                onClick={onToggleSplit}
                aria-pressed={splitSideboard}
                className={cn(pill, splitSideboard ? active : idle, "flex-1")}
              >
                SIDE
                <GoSidebarCollapse size={15} aria-hidden="true" />
              </button>
            </Tooltip>
          )}
        </div>
      )}
      <LayoutToggle
        layout={deckLayout}
        onToggle={onToggleDeckLayout}
        splitTypes={splitTypes}
        onToggleSplitTypes={onToggleSplitTypes}
      />
    </div>
  );
}

// The final sideboard cut as a single stacked column to the right of the deck. Cards fan top-to-bottom
// like a pool column; the last-pick glow lands here when the most recent pick was ultimately cut.
function SideboardPane({
  cards,
  markCount,
  cardWidth,
  reveal,
}: {
  cards: ArtifactCard[];
  markCount: number;
  cardWidth: number;
  reveal: number;
}) {
  return (
    <div className="flex shrink-0 flex-col">
      <div className="themed-scrollbar min-h-0 flex-1 overflow-y-auto overflow-x-hidden py-2 pl-0.5 pr-2">
        <StackColumn
          count={cards.length}
          reveal={reveal}
          width={cardWidth}
          cardClassName={CARD_FRAME_HOVER}
          glowIndexes={lastIndexes(cards.length, markCount)}
          cardAt={(i) => cards[i]}
          renderCard={(i) => <CardImage card={cards[i]} />}
        />
      </div>
    </div>
  );
}

// Mobile-only: the pick navigator sits on top of the deck, doubling as its divider. Pack chips let
// you jump packs instead of stepping 14+ times; prev/next walk picks within the pack.
function MobileNavDivider({
  pack,
  pick,
  perTurn,
  jumpHref,
  prevHref,
  nextHref,
  awaitingReveal,
  onReveal,
  revealMode,
  onRevealMode,
}: {
  pack: number;
  pick: number;
  perTurn: number;
  jumpHref: (pack: number, pick: number) => string;
  prevHref: string | null;
  nextHref: string | null;
  awaitingReveal: boolean;
  onReveal: () => void;
  revealMode: RevealMode;
  onRevealMode: (m: RevealMode) => void;
}) {
  const arrow = "flex h-8 w-8 shrink-0 items-center justify-center rounded-md border transition-[transform,background-color,border-color,color] duration-150 ease-out touch-manipulation [-webkit-tap-highlight-color:transparent]";
  const arrowIdle =
    "border-white/40 bg-surface2 text-text active:scale-90 active:bg-white/20 motion-reduce:active:scale-100";
  const arrowDisabled = "border-border text-dim opacity-40";
  return (
    <div {...KEEPS_PREVIEW} className="flex h-12 shrink-0 items-center justify-between gap-1.5 border-t border-border bg-surface px-2 lg:hidden">
      <div className="flex gap-1">
        {[0, 1, 2].map((p) => (
          <Link
            key={p}
            to={jumpHref(p, 0)}
            replace
            aria-current={p === pack || undefined}
            className={cn(
              "flex h-8 min-w-[30px] items-center justify-center rounded border px-1.5 font-display text-[15px] tracking-[0.04em] tabular-nums no-underline transition-colors",
              p === pack
                ? "border-green/60 bg-green/15 text-green"
                : "border-border bg-surface2 text-subtle hover:border-white/40 hover:bg-white/10 hover:text-text",
            )}
          >
            {p + 1}
          </Link>
        ))}
      </div>

      <div className="flex items-center gap-1.5">
        {prevHref ? (
          <Link to={prevHref} replace aria-label="Previous pick" className={cn(arrow, arrowIdle)}>
            <ChevronIcon dir="left" />
          </Link>
        ) : (
          <button disabled aria-label="Previous pick" className={cn(arrow, arrowDisabled)}>
            <ChevronIcon dir="left" />
          </button>
        )}
        <span className="min-w-[56px] text-center font-display text-[17px] tracking-[0.06em] text-text">
          P{pack + 1}P{pickLabel(pick, perTurn)}
        </span>
        {awaitingReveal ? (
          <button onClick={onReveal} aria-label="Reveal picked card" className={cn(arrow, arrowIdle)}>
            <EyeIcon off={false} />
          </button>
        ) : nextHref ? (
          <Link to={nextHref} replace aria-label="Next pick" className={cn(arrow, arrowIdle)}>
            <ChevronIcon dir="right" />
          </Link>
        ) : (
          <button disabled aria-label="Next pick" className={cn(arrow, arrowDisabled)}>
            <ChevronIcon dir="right" />
          </button>
        )}
      </div>

      <MobileToggle
        label="PICKS"
        ariaLabel="Show picks"
        on={revealMode === "revealed"}
        onToggle={() => onRevealMode(revealMode === "revealed" ? "click" : "revealed")}
      />
    </div>
  );
}

function LayoutToggle({
  layout,
  onToggle,
  splitTypes = true,
  onToggleSplitTypes,
}: {
  layout: "order" | "columns";
  onToggle: () => void;
  splitTypes?: boolean;
  onToggleSplitTypes?: () => void;
}) {
  const onCurve = layout === "columns";
  const showSplitSwitch = onCurve && onToggleSplitTypes !== undefined;
  const clickCurve = onCurve ? onToggleSplitTypes : onToggle;
  const curveButton = (
    <button
      onClick={clickCurve}
      aria-pressed={showSplitSwitch ? splitTypes : undefined}
      className={cn(
        "flex flex-1 items-center justify-center gap-2 rounded px-2 py-1 text-center lg:px-3.5 lg:py-1.5",
        onCurve ? "bg-green/15 text-green" : "text-muted hover:text-subtle",
      )}
    >
      CURVE
      {showSplitSwitch && <ToggleSwitch on={splitTypes} />}
    </button>
  );
  return (
    <div className="flex w-full rounded border border-border bg-surface2 p-0.5 font-display text-[10px] tracking-[0.1em] lg:rounded-md lg:p-1 lg:text-[13px] lg:tracking-[0.12em]">
      {showSplitSwitch ? (
        <Tooltip label="Split View" side="top">
          {curveButton}
        </Tooltip>
      ) : (
        curveButton
      )}
      <button
        onClick={() => layout !== "order" && onToggle()}
        className={cn("flex-1 rounded px-2 py-1 text-center lg:px-3.5 lg:py-1.5", layout === "order" ? "bg-green/15 text-green" : "text-muted hover:text-subtle")}
      >
        ORDER
      </button>
    </div>
  );
}

// Order view: one row of columns by pick position; every pack piles at its position (P1P1 on top,
// then P2P1, then P3P1), the same fanned treatment the curve uses by cost. Single horizontal scroll.
function OrderStrip({
  rows,
  sideboard = [],
  lastPicks = NO_LAST_PICKS,
  cardWidth,
  reveal,
}: {
  rows: ArtifactCard[][];
  sideboard?: ArtifactCard[];
  lastPicks?: LastPicks;
  cardWidth: number;
  reveal: number;
}) {
  const positions = rows.reduce((max, r) => Math.max(max, r.length), 0);
  let lastRow = -1;
  for (let r = 0; r < rows.length; r++) {
    if (rows[r].length > 0) {
      lastRow = r;
    }
  }
  const glowCols = lastRow >= 0 ? lastIndexes(rows[lastRow].length, lastPicks.main) : [];
  const glowSide = lastIndexes(sideboard.length, lastPicks.side);
  return (
    <div className="themed-scrollbar flex h-full items-start gap-1 overflow-x-auto px-2 py-2">
      {Array.from({ length: positions }, (_, i) => {
        const stack = rows.map((r, ri) => ({ card: r[i], ri })).filter((e) => e.card);
        return (
          <div
            key={i}
            className="relative shrink-0"
            style={{ width: cardWidth, height: Math.max(0, stack.length - 1) * reveal + cardWidth * 1.4 }}
          >
            {stack.map(({ card, ri }, di) => (
              <div
                key={di}
                className={cn(
                  "absolute w-full",
                  CARD_FRAME,
                  ri === lastRow && glowCols.includes(i) && "review-last-pick z-10",
                )}
                style={{ top: di * reveal }}
              >
                <CardImage card={card} />
              </div>
            ))}
          </div>
        );
      })}
      {sideboard.length > 0 && <div className="shrink-0" style={{ width: Math.round(cardWidth * SIDE_COLUMN_GAP_RATIO) }} />}
      {sideboard.length > 0 && (
        <div
          className="relative shrink-0"
          style={{ width: cardWidth, height: Math.max(0, sideboard.length - 1) * reveal + cardWidth * 1.4 }}
        >
          {sideboard.map((card, di) => (
            <div
              key={di}
              className={cn(
                "absolute w-full",
                CARD_FRAME,
                glowSide.includes(di) && "review-last-pick z-10",
              )}
              style={{ top: di * reveal }}
            >
              <CardImage card={card} />
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

type PoolEntry = { card: ArtifactCard; idx: number };

const POOL_PAD = 8;
const POOL_GAP = 4;
const SIDE_COLUMN_GAP_RATIO = 0.1;

function Pool({
  cards,
  sideboard = [],
  lastPicks = NO_LAST_PICKS,
  curve,
  align = "left",
  cardWidth = 116,
  reveal = 26,
}: {
  cards: ArtifactCard[];
  sideboard?: ArtifactCard[];
  lastPicks?: LastPicks;
  curve?: CurveMode;
  align?: "left" | "right";
  cardWidth?: number;
  reveal?: number;
}) {
  const column = (key: string, entries: PoolEntry[], glowing: number[]) => {
    const group = lastPicksAtBottom(entries, glowing);
    return (
      <StackColumn
        key={key}
        count={group.length}
        reveal={reveal}
        width={cardWidth}
        className="shrink-0"
        cardClassName={CARD_FRAME_HOVER}
        glowIndexes={group.flatMap((e, i) => (glowing.includes(e.idx) ? [i] : []))}
        cardAt={(i) => group[i].card}
        renderCard={(i) => <CardImage card={group[i].card} />}
      />
    );
  };
  const entries = cards.map((card, idx) => ({ card, idx }));
  const glowMain = lastIndexes(cards.length, lastPicks.main);
  const glowSide = lastIndexes(sideboard.length, lastPicks.side);

  let track;
  if (curve) {
    const spacerWidth = Math.round(cardWidth * SIDE_COLUMN_GAP_RATIO);
    track = (
      <>
        {curveColumns(entries, curve).map((group, i) =>
          group ? (
            column(`g${i}`, group, glowMain)
          ) : (
            <div key={`gap${i}`} className="shrink-0" style={{ width: spacerWidth }} />
          ),
        )}
        {sideboard.length > 0 && <div key="side-gap" className="shrink-0" style={{ width: spacerWidth }} />}
        {sideboard.length > 0 &&
          column(
            "side",
            sideboard.map((card, idx) => ({ card, idx })),
            glowSide,
          )}
      </>
    );
  } else {
    track = (
      <>
        {cmcColumns(entries).map(([cmc, group]) => column(`m${cmc}`, group, glowMain))}
        {sideboard.length > 0 &&
          column(
            "side",
            sideboard.map((card, idx) => ({ card, idx })),
            glowSide,
          )}
      </>
    );
  }
  return (
    <div className="themed-scrollbar h-full overflow-auto" style={{ padding: POOL_PAD }}>
      <div className={cn("flex w-max items-start", align === "right" && "ml-auto")} style={{ gap: POOL_GAP }}>
        {track}
      </div>
    </div>
  );
}

type CurveMode = "split" | "mixed";

function curveColumns(entries: PoolEntry[], curve: CurveMode): (PoolEntry[] | null)[] {
  const creatures: PoolEntry[] = [];
  const lands: PoolEntry[] = [];
  const spells: PoolEntry[] = [];
  for (const entry of entries) {
    const type = entry.card.type ?? "";
    if (/creature/i.test(type)) {
      creatures.push(entry);
    } else if (/land/i.test(type)) {
      lands.push(entry);
    } else {
      spells.push(entry);
    }
  }
  if (curve === "mixed") {
    const mixedCols = cmcColumns([...creatures, ...spells]).map(([, group]) => group);
    return lands.length > 0 ? [...mixedCols, null, lands] : mixedCols;
  }
  const creatureCols = creatureCurveColumns(creatures).filter((column) => column.length > 0);
  const spellsByCost = cmcColumns(spells);
  const spellCols = spellsByCost.length > 4 ? groupLowSpellColumns(spellsByCost) : spellsByCost;
  const landsOrGap = lands.length > 0 ? lands : null;
  return [...creatureCols, landsOrGap, ...spellCols.map(([, group]) => group)];
}

function lastPicksAtBottom(entries: PoolEntry[], glowing: number[]): PoolEntry[] {
  const earlier: PoolEntry[] = [];
  const latest: PoolEntry[] = [];
  for (const entry of entries) {
    if (glowing.includes(entry.idx)) {
      latest.push(entry);
    } else {
      earlier.push(entry);
    }
  }
  return [...earlier, ...latest];
}

function creatureCurveColumns(entries: PoolEntry[]): PoolEntry[][] {
  if (entries.length === 0) {
    return [];
  }
  const byCmc = new Map<number, PoolEntry[]>();
  let minCmc = 2;
  let maxCmc = 2;
  for (const entry of entries) {
    const cmc = Math.max(0, Math.round(entry.card.cmc ?? 0));
    minCmc = Math.min(minCmc, cmc);
    maxCmc = Math.max(maxCmc, cmc);
    const list = byCmc.get(cmc);
    if (list) {
      list.push(entry);
    } else {
      byCmc.set(cmc, [entry]);
    }
  }
  const columns: PoolEntry[][] = [];
  for (let cmc = minCmc; cmc <= maxCmc; cmc++) {
    columns.push(byCmc.get(cmc) ?? []);
  }
  return columns;
}

function groupLowSpellColumns(columns: [number, PoolEntry[]][]): [number, PoolEntry[]][] {
  const cheap: PoolEntry[] = [];
  const rest: [number, PoolEntry[]][] = [];
  for (const [cmc, group] of columns) {
    if (cmc === 1 || cmc === 2) {
      cheap.push(...group);
    } else {
      rest.push([cmc, group]);
    }
  }
  if (cheap.length === 0) {
    return columns;
  }
  return [[2, cheap], ...rest];
}

function cmcColumns(entries: PoolEntry[]): [number, PoolEntry[]][] {
  const byCmc = new Map<number, PoolEntry[]>();
  let maxCmc = 0;
  for (const entry of entries) {
    const cmc = Math.max(0, Math.round(entry.card.cmc ?? 0));
    maxCmc = Math.max(maxCmc, cmc);
    const list = byCmc.get(cmc);
    if (list) {
      list.push(entry);
    } else {
      byCmc.set(cmc, [entry]);
    }
  }
  const columns: [number, PoolEntry[]][] = [];
  for (let c = 1; c <= maxCmc; c++) {
    const group = byCmc.get(c) ?? [];
    if (group.length === 0) {
      continue;
    }
    columns.push([c, group]);
  }
  const lands = byCmc.get(0) ?? [];
  if (lands.length) {
    columns.push([0, lands]);
  }
  return columns;
}

function PassArrow({ dir }: { dir: "up" | "down" | "left" | "right" }) {
  const rotation = { right: "", left: "rotate-180", down: "rotate-90", up: "-rotate-90" }[dir];
  return <span className={cn("inline-block font-mono text-[15px] leading-none text-subtle", rotation)}>»</span>;
}

// Two columns of four seats laid out so the arrows trace the pack-pass loop around the table: across the
// top, down one column, across the bottom, up the other. The loop reverses for the right-to-left packs.
type RingRow = { left: number; right: number | null; top: boolean; bottom: boolean };

// Seats fold into two columns around a table: seat 0 at top-left, the right column
// running down 1..⌊n/2⌋, the left column running back up the rest. Odd pods leave the
// bottom-right cell empty. Clockwise ring order 0..n-1 drives the pass arrows.
function buildRing(n: number): RingRow[] {
  const rows = Math.ceil(n / 2);
  const rightCount = Math.floor(n / 2);
  const ring: RingRow[] = [];
  for (let r = 0; r < rows; r++) {
    const right = r + 1 <= rightCount ? r + 1 : null;
    ring.push({ left: r === 0 ? 0 : n - r, right, top: r === 0, bottom: r === rows - 1 });
  }
  return ring;
}

function PlayerGrid({
  seats,
  activeSeat,
  seatHref,
  passRight,
}: {
  seats: Seat[];
  activeSeat: number;
  seatHref: (i: number) => string;
  passRight: boolean;
}) {
  const ring = buildRing(seats.length);
  const topDir = passRight ? "right" : "left";
  const bottomDir = passRight ? "left" : "right";
  const leftColDir = passRight ? "up" : "down";
  const rightColDir = passRight ? "down" : "up";
  const arrowRiseToAvatar = 20;
  const tile = (i: number | null) =>
    i == null || !seats[i] ? (
      <div className="flex-1" />
    ) : (
      <PlayerTile seat={seats[i]} active={i === activeSeat} href={seatHref(i)} />
    );
  return (
    <div className="flex h-full flex-col px-1.5 py-2">
      {ring.map((row, i) => (
        <div key={i} className="relative flex flex-1 items-stretch">
          {tile(row.left)}
          {tile(row.right)}
          {(row.top || (row.bottom && row.right != null)) && (
            <span
              className="pointer-events-none absolute left-1/2 top-1/2"
              style={{ transform: `translate(-50%, calc(-50% - ${arrowRiseToAvatar}px))` }}
            >
              <PassArrow dir={row.top ? topDir : bottomDir} />
            </span>
          )}
          {i < ring.length - 1 && (
            <>
              <span className="pointer-events-none absolute bottom-0 left-1/4 -translate-x-1/2 translate-y-1/2">
                <PassArrow dir={leftColDir} />
              </span>
              {ring[i + 1].right != null && (
                <span className="pointer-events-none absolute bottom-0 left-3/4 -translate-x-1/2 translate-y-1/2">
                  <PassArrow dir={rightColDir} />
                </span>
              )}
            </>
          )}
        </div>
      ))}
    </div>
  );
}

function PlayerTile({
  seat,
  active,
  href,
}: {
  seat: Seat;
  active: boolean;
  href: string;
}) {
  return (
    <Link
      to={href}
      replace
      aria-current={active || undefined}
      className={cn(
        "flex h-full w-full min-w-0 flex-col items-center justify-center gap-1.5 rounded-lg px-2 no-underline transition-colors",
        active ? "bg-white/[0.06]" : "hover:bg-white/[0.04]",
      )}
    >
      <AAvatar displayName={seat.name} avatarUrl={seat.avatarUrl} size={58} green={active} />
      <span
        className={cn(
          "max-w-full truncate font-display text-[15px] leading-none tracking-[0.04em]",
          active ? "text-green" : "text-subtle",
        )}
      >
        {seat.name}
      </span>
      <Pips colors={seat.colors} size={14} />
    </Link>
  );
}

function NavArrow({ dir, href }: { dir: "prev" | "next"; href: string | null }) {
  const primary = dir === "next";
  const label = primary ? "Next Pick" : "Previous Pick";
  const tooltip = primary ? "Next Pick (Arrow Right)" : "Previous Pick (Arrow Left)";
  const [hover, setHover] = useState(false);
  const className = cn(
    "flex h-9 items-center justify-center rounded-md border bg-surface2",
    primary
      ? "w-9 gap-1.5 font-display text-[13px] tracking-[0.12em] min-[1500px]:w-auto min-[1500px]:min-w-[84px] min-[1500px]:px-3"
      : "w-9",
    "transition-[transform,background-color,border-color,color] duration-150 ease-out",
    "touch-manipulation [-webkit-tap-highlight-color:transparent]",
    href
      ? "border-white/40 text-text no-underline hover:border-white/60 hover:bg-white/10 active:scale-90 active:bg-white/20 motion-reduce:active:scale-100"
      : "border-border text-dim opacity-40",
  );
  const content = (
    <>
      {primary && <span className="hidden min-[1500px]:inline">NEXT</span>}
      <ChevronIcon dir={primary ? "right" : "left"} />
    </>
  );
  const hoverTracking = {
    onPointerEnter: (e: React.PointerEvent) => e.pointerType === "mouse" && setHover(true),
    onPointerLeave: () => setHover(false),
  };
  return (
    <Tooltip label={tooltip} side="bottom" open={hover && !!href}>
      {href ? (
        <Link to={href} replace {...hoverTracking} aria-label={label} className={className}>
          {content}
        </Link>
      ) : (
        <button disabled {...hoverTracking} aria-label={label} className={className}>
          {content}
        </button>
      )}
    </Tooltip>
  );
}

function ChevronIcon({ dir }: { dir: "up" | "down" | "left" | "right" }) {
  const path = {
    up: "M6 15l6-6 6 6",
    down: "M6 9l6 6 6-6",
    left: "M15 18l-6-6 6-6",
    right: "M9 6l6 6-6 6",
  }[dir];
  return (
    <svg className="shrink-0" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
      <path d={path} />
    </svg>
  );
}

function EyeIcon({ off }: { off: boolean }) {
  return (
    <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7-10-7-10-7Z" />
      <circle cx="12" cy="12" r="3" />
      {off && <line x1="3" y1="3" x2="21" y2="21" />}
    </svg>
  );
}
