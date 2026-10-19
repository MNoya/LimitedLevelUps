import { useEffect, useMemo, useRef, useState, type PointerEvent as ReactPointerEvent, type ReactNode } from "react";
import { Navigate, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { ChevronLeft, ChevronUp } from "lucide-react";

import { PageShell } from "../components/PageShell";
import { Tooltip } from "../components/Tooltip";
import { Container } from "../components/Container";
import { CardImageMapProvider, useCardImageMapContext } from "../components/pod/review/ReviewCard";
import { podDraftPickHref } from "../components/pod/podLinks";
import { GameStatus } from "../components/draftGames/GameChrome";
import { CardTitle } from "../components/draftGames/wheel/CardTitle";
import { OrderSection, WheelSection } from "../components/draftGames/wheel/OrderPanel";
import { SpaceKey } from "../components/draftGames/wheel/SpaceKey";
import {
  CardZoom,
  GAME_COLUMNS,
  PackGrid,
  PackSlot,
  PickingCard,
  PulseCard,
  RevealCard,
  useRevealLayout,
  type CardOpening,
  type RevealLayout,
} from "../components/draftGames/wheel/PackGrid";
import { useWheelDay, wheelDayStorageKey } from "../components/draftGames/wheel/useWheelDay";
import { WheelBackdrop } from "../components/draftGames/wheel/WheelBackdrop";
import { WheelTitle } from "../components/draftGames/wheel/WheelTitle";
import { WheelHeader, type WheelHeaderTools, type WheelProgress } from "../components/draftGames/wheel/WheelHeader";
import { QuickHelpDialog, WheelHelpDialog } from "../components/draftGames/wheel/WheelHelp";
import { releaseFocus, useGuideHash, useNoScrollGutter, useTouchVerb } from "../components/draftGames/wheel/pageHooks";
import { FEATURED_PLAY, WheelIntro } from "../components/draftGames/wheel/WheelIntro";
import { WheelSummary } from "../components/draftGames/wheel/WheelSummary";
import { useFlip } from "../components/draftGames/wheel/motion";
import { cardImageSources, hasCardImage, useCardImageMap } from "../data/cardImages";
import {
  MINI_GAMES_HEADER,
  ordinal,
  scoreWheel,
  shortDayLabel,
  useFeaturedPacks,
  useFreePlayPacks,
  usePackNumbers,
  useWheelSets,
  gameDayKey,
  type WheelPack,
} from "../data/draftGames";
import type { ArtifactCard } from "../types/leaderboard";
import { cn } from "../lib/utils";
import {
  GOLD_BUTTON,
  PIXEL_HEADING,
  PIXEL_PANEL,
  PIXEL_TOOLTIP,
  WAITING_PIXEL_BUTTON,
} from "../components/draftGames/pixelStyles";

const WHEEL_PATH = "/wheel-of-fortune";
const SKELETON_CARDS = 14;
const QUICK_PATH = `${WHEEL_PATH}/quick`;
const DAY_PATH = /^\d{4}-\d{2}-\d{2}$/;

const GAME_LAYOUT = cn(
  "flex flex-col gap-3 pb-[88px] lg:grid lg:grid-rows-[auto_1fr]",
  GAME_COLUMNS,
  "lg:justify-center lg:gap-x-4 lg:gap-y-3 lg:pb-0",
);

type GameMode = "featured" | "free";

export function WheelOfFortunePage() {
  useNoScrollGutter();
  const [today] = useState(() => {
    const day = gameDayKey();
    if (import.meta.env.DEV) {
      resetDayOnRequest(day);
    }
    return day;
  });
  const { play, packNumber } = useParams<{ play?: string; packNumber?: string }>();
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const [helpOpen, openHelp, closeHelp] = useGuideHash("guide");
  const [quickHelpOpen, openQuickHelp, closeQuickHelp] = useGuideHash("quick-guide");
  const touchVerb = useTouchVerb();
  const exit = () => navigate(WHEEL_PATH);
  const playPath = (next: string) => `${WHEEL_PATH}/${next === FEATURED_PLAY ? today : next.toLowerCase()}`;

  const legacyPlay = params.get("play");
  if (legacyPlay) {
    return <Navigate to={playPath(legacyPlay)} replace />;
  }
  const isDay = play != null && DAY_PATH.test(play);
  if (isDay && play > today) {
    return <Navigate to={playPath(FEATURED_PLAY)} replace />;
  }

  let body: ReactNode;
  if (!play) {
    body = (
      <WheelIntro
        dayKey={today}
        onPlay={(next) => navigate(playPath(next))}
        onHelp={openHelp}
        onQuickHelp={openQuickHelp}
        helpOpen={helpOpen}
        onCloseHelp={closeHelp}
      />
    );
  } else if (isDay) {
    body = <FeaturedGame key={play} dayKey={play} helpOpen={helpOpen} onHelp={openHelp} onExit={exit} />;
  } else {
    const setCode = play.toUpperCase();
    body = (
      <FreePlayGame
        key={setCode}
        setCode={setCode}
        startNumber={Number(packNumber) || null}
        helpOpen={helpOpen}
        onHelp={openHelp}
        onExit={exit}
      />
    );
  }

  return (
    <PageShell
      subtitle="WHEEL OF FORTUNE"
      titleHref="/wheel-of-fortune"
      subtitleShort={MINI_GAMES_HEADER}
      phoneTitle={play ? <WheelTitle scale={2} interactive={false} /> : undefined}
      footer={false}
    >
      <Container
        className={cn("draft-game pt-3 pb-4", play ? "lg:px-4 2xl:px-10" : "flex flex-1 flex-col max-sm:pb-2")}
      >
        <WheelBackdrop />
        <div className={cn("relative z-[1]", !play && "flex flex-1 flex-col")}>{body}</div>
      </Container>
      {play && <WheelHelpDialog open={helpOpen} onClose={closeHelp} touchVerb={touchVerb} />}
      <QuickHelpDialog
        open={quickHelpOpen}
        onClose={closeQuickHelp}
        action={{ label: "Play", onClick: () => navigate(QUICK_PATH) }}
      />
    </PageShell>
  );
}

interface ModeProps {
  helpOpen: boolean;
  onHelp: () => void;
  onExit: () => void;
}

function FeaturedGame({ dayKey, ...modeProps }: ModeProps & { dayKey: string }) {
  const { packs, isPending } = useFeaturedPacks(dayKey);
  const cardImages = usePackImages(packs);
  if (isPending) {
    return <WheelSkeleton />;
  }
  if (packs.length === 0) {
    return <GameStatus>No Pods to feature yet</GameStatus>;
  }
  return (
    <CardImageMapProvider value={cardImages}>
      <WheelGame
        key={dayKey}
        mode="featured"
        packs={packs}
        dayKey={dayKey}
        storageKey={wheelDayStorageKey(dayKey)}
        {...modeProps}
      />
    </CardImageMapProvider>
  );
}

function FreePlayGame({
  setCode,
  startNumber,
  ...modeProps
}: ModeProps & { setCode: string; startNumber: number | null }) {
  const navigate = useNavigate();
  const [seed] = useState(() => Math.floor(Math.random() * 1_000_000));
  const [firstNumber] = useState(startNumber);
  const [wanted, setWanted] = useState(1);
  const { packs, isPending, exhausted, packNumbers } = useFreePlayPacks(setCode, wanted, seed, firstNumber);
  const packNumberOf = (pack: WheelPack) => packNumbers.get(pack.eventId) ?? null;
  const showPackInAddress = (pack: WheelPack) => {
    const number = packNumberOf(pack);
    if (number != null) {
      navigate(`${WHEEL_PATH}/${setCode.toLowerCase()}/${number}`, { replace: true });
    }
  };
  const { sets, isPending: setsPending } = useWheelSets();
  const cardImages = usePackImages(packs);
  if (!setsPending && !sets.some((set) => set.code === setCode)) {
    return <GameStatus>No Pods to play for this set yet</GameStatus>;
  }
  if (packs.length === 0) {
    return isPending ? <WheelSkeleton /> : <GameStatus>No Pods to play for this set yet</GameStatus>;
  }
  return (
    <CardImageMapProvider value={cardImages}>
      <WheelGame
        mode="free"
        packs={packs}
        dayKey={null}
        storageKey={null}
        exhausted={exhausted}
        onAdvance={(index) => setWanted(index + 1)}
        packNumberOf={packNumberOf}
        onPackShown={showPackInAddress}
        {...modeProps}
      />
    </CardImageMapProvider>
  );
}

interface GridDrag {
  card: number;
  x: number;
  y: number;
  index: number | null;
}

function WheelGame({
  mode,
  packs,
  dayKey,
  storageKey,
  exhausted = false,
  helpOpen,
  onHelp,
  onExit,
  onAdvance,
  packNumberOf,
  onPackShown,
}: ModeProps & {
  mode: GameMode;
  packs: WheelPack[];
  dayKey: string | null;
  storageKey: string | null;
  exhausted?: boolean;
  onAdvance?: (index: number) => void;
  packNumberOf?: (pack: WheelPack) => number | null;
  onPackShown?: (pack: WheelPack) => void;
}) {
  const { day, setDraft: saveDraft, lockIn, goTo, advance, finish } = useWheelDay(storageKey, packs);
  const { sets } = useWheelSets();
  const packNumbers = usePackNumbers();
  const [freshReveal, setFreshReveal] = useState(false);
  const [freshSummary, setFreshSummary] = useState(false);
  const [zoom, setZoom] = useState<ArtifactCard | null>(null);
  const [sheetOpen, setSheetOpen] = useState(false);
  const [gridDrag, setGridDrag] = useState<GridDrag | null>(null);
  const [reviewing, setReviewing] = useState<number | null>(null);
  const [showDrafters, setShowDrafters] = useState(false);
  const listRef = useRef<HTMLDivElement>(null);
  const touchVerb = useTouchVerb();
  const revealLayout = useRevealLayout();
  const gridRef = useRef<HTMLDivElement>(null);
  useFlip(gridRef, null, 700, freshReveal);

  const featured = mode === "featured";
  const finished = featured && day.advanced >= packs.length;
  const viewIndex = finished ? (reviewing ?? 0) : Math.min(day.current, packs.length - 1);
  const pack: WheelPack | undefined = packs[viewIndex];
  const shownEventId = pack?.eventId;
  const announcePack = useRef(() => pack && onPackShown?.(pack));
  announcePack.current = () => pack && onPackShown?.(pack);
  useEffect(() => {
    announcePack.current();
  }, [shownEventId]);
  const artResolved = usePackArtResolved(pack);
  const [opening, setOpening] = useState<PackOpening | null>(null);
  if (pack && opening?.eventId !== pack.eventId) {
    const previousId = artResolved ? (opening?.eventId ?? null) : null;
    setOpening({ eventId: pack.eventId, previousId, openedAt: performance.now() });
  }
  const locked = pack ? day.locked[pack.eventId] : undefined;
  const slots = locked ?? (pack ? (day.drafts[pack.eventId] ?? []) : []);
  const setDraft = (draft: number[]) => pack && saveDraft(pack.eventId, draft);
  const score = pack && locked ? scoreWheel(pack, locked) : null;
  const slotCount = pack?.order.length ?? 0;
  const ready = slotCount > 0 && slots.length === slotCount;
  const nextOpen = featured ? nextUnlockedIndex(packs, day.locked, viewIndex) : null;
  const last = featured && nextOpen == null;
  usePreloadPackArt(featured ? (nextOpen != null ? packs[nextOpen] : undefined) : packs[viewIndex + 1]);

  const place = (card: number, at: number) => {
    const without = slots.filter((c) => c !== card);
    without.splice(Math.min(at, without.length), 0, card);
    setDraft(without.slice(0, slotCount));
  };
  const remove = (card: number) => setDraft(slots.filter((c) => c !== card));
  const toggle = (card: number) => (slots.includes(card) ? remove(card) : place(card, slots.length));
  const lock = () => {
    if (!pack || !ready || score) {
      return;
    }
    lockIn(pack.eventId, slots);
    setFreshReveal(true);
  };
  const next = () => {
    setFreshReveal(false);
    setSheetOpen(false);
    setFreshSummary(last);
    if (!featured) {
      advance();
      onAdvance?.(day.advanced + 1);
    } else if (nextOpen == null) {
      finish();
    } else {
      goTo(nextOpen);
    }
    window.scrollTo({ top: 0 });
  };
  const jumpTo = (index: number) => {
    setFreshReveal(false);
    setSheetOpen(false);
    if (finished) {
      openReview(index);
    } else {
      goTo(index);
    }
    window.scrollTo({ top: 0 });
  };
  const openReview = (index: number) => {
    if (reviewing == null) {
      window.history.pushState({ ...window.history.state, wheelReview: true }, "");
    }
    setReviewing(index);
    window.scrollTo({ top: 0 });
  };
  const showResults = () => {
    setReviewing(null);
    setFreshSummary(false);
    window.scrollTo({ top: 0 });
  };
  const closeReview = () => {
    if (window.history.state?.wheelReview) {
      window.history.back();
      return;
    }
    showResults();
  };
  useEffect(() => {
    const onBack = () => {
      if (!window.history.state?.wheelReview) {
        showResults();
      }
    };
    window.addEventListener("popstate", onBack);
    return () => window.removeEventListener("popstate", onBack);
  }, []);

  useEffect(() => {
    if (!pack || (finished && reviewing == null)) {
      return;
    }
    const onKey = (e: KeyboardEvent) => {
      const typing = e.target instanceof HTMLElement && e.target.closest("input, textarea, [contenteditable]");
      if (helpOpen || typing || e.metaKey || e.ctrlKey || e.altKey) {
        return;
      }
      const confirmKey = e.key === " " || e.key === "Enter";
      if (confirmKey || e.key === "Backspace") {
        releaseFocus();
      }
      if (reviewing != null && (confirmKey || e.key === "Escape")) {
        e.preventDefault();
        closeReview();
        return;
      }
      if (confirmKey) {
        e.preventDefault();
        if (score) {
          next();
        } else {
          lock();
        }
      }
      if (e.key === "Backspace" && !score && slots.length > 0) {
        e.preventDefault();
        setDraft(slots.slice(0, -1));
      }
    };
    window.addEventListener("keydown", onKey, true);
    return () => window.removeEventListener("keydown", onKey, true);
  });

  useEffect(() => {
    if (!gridDrag) {
      return;
    }
    const indexAt = (y: number, x: number) => {
      const list = listRef.current?.getBoundingClientRect();
      if (!list || x < list.left - 40 || x > list.right + 40 || y < list.top - 24 || y > list.bottom + 24) {
        return null;
      }
      const filled = slots.filter((c) => c !== gridDrag.card).length;
      const pitch = list.height / slotCount;
      return Math.min(filled, Math.max(0, Math.round((y - list.top) / pitch)));
    };
    const onMove = (e: PointerEvent) => {
      setGridDrag((d) => d && { ...d, x: e.clientX, y: e.clientY, index: indexAt(e.clientY, e.clientX) });
    };
    const onUp = (e: PointerEvent) => {
      const index = indexAt(e.clientY, e.clientX);
      if (index != null) {
        place(gridDrag.card, index);
      }
      setGridDrag(null);
    };
    window.addEventListener("pointermove", onMove);
    window.addEventListener("pointerup", onUp, { once: true });
    return () => {
      window.removeEventListener("pointermove", onMove);
      window.removeEventListener("pointerup", onUp);
    };
  });

  const setName = (code: string) => sets.find((set) => set.code === code)?.name ?? code;
  const featuredSteps = packs.map((p) => ({
    setCode: p.setCode,
    name: setName(p.setCode),
    mark: day.locked[p.eventId] ? scoreWheel(p, day.locked[p.eventId]).mark : null,
  }));

  if (finished && reviewing == null && dayKey) {
    return (
      <WheelSummary
        packs={packs}
        locked={day.locked}
        dayKey={dayKey}
        animate={freshSummary}
        onExit={onExit}
        onReview={openReview}
      />
    );
  }
  if (!pack) {
    if (exhausted) {
      return (
        <GameStatus>
          You played every Pod in this set.{" "}
          <button onClick={onExit} className="font-bold text-[#f6c95e] hover:underline">
            Pick another set
          </button>
        </GameStatus>
      );
    }
    return <WheelSkeleton />;
  }

  const progress: WheelProgress = featured
    ? { kind: "featured", steps: featuredSteps, current: viewIndex, onSelect: jumpTo }
    : { kind: "free", packNumber: viewIndex + 1 };

  const startGridDrag = (card: number) => (e: ReactPointerEvent) =>
    setGridDrag({ card, x: e.clientX, y: e.clientY, index: null });
  const opener = pack.order[0];
  const draftHref = podDraftPickHref(pack.eventSlug, { playerSlug: opener.drafterSlug, seatIndex: opener.seat }, 0, 0);
  const nextDelay = freshReveal ? 400 : 0;
  const renderAction = (floating: boolean) => {
    const size = floating ? "pointer-events-auto px-10 py-3.5 text-3xl" : "px-5 py-2.5 text-xl";
    const keyInset = floating ? "lg:gap-8 lg:pr-3.5" : "lg:gap-4 lg:pr-2.5";
    if (reviewing != null) {
      return (
        <button onClick={closeReview} className={cn(GOLD_BUTTON, "gap-1.5 pl-3.5", size)}>
          <ChevronLeft className="size-[1em]" strokeWidth={3} />
          Back to Results
        </button>
      );
    }
    if (score) {
      return (
        <span key="next" className="flex animate-fadeUpIn" style={{ animationDelay: `${nextDelay}ms` }}>
          <button onClick={next} className={cn(GOLD_BUTTON, size, keyInset)}>
            {last ? "Results" : "Next Pack"}
            <SpaceKey />
          </button>
        </span>
      );
    }
    if (!ready) {
      return <WaitingConfirm key="waiting" remaining={slotCount - slots.length} className={size} />;
    }
    return (
      <button key="ready" onClick={lock} className={cn(GOLD_BUTTON, keyInset, size)}>
        Confirm
        <SpaceKey />
      </button>
    );
  };
  const floatingAction = (ready || score || reviewing != null) && (
    <div className="pointer-events-none absolute inset-x-0 bottom-5 z-10 hidden justify-center lg:flex">
      {renderAction(true)}
    </div>
  );

  let sheetStatus: ReactNode = `${slots.length} of ${slotCount} Picked`;
  if (score) {
    sheetStatus = `${score.points} of ${score.max} Points`;
  } else if (!ready) {
    sheetStatus = `${ordinal(slots.length + 1)} Pick`;
  }

  const revealCard = (card: number) => (
    <RevealCard pack={pack} card={card} slots={slots} animate={freshReveal} showDrafter={showDrafters} />
  );
  const previousPack = packs.find((played) => played.eventId === opening?.previousId);
  const previousOrder = previousPack
    ? gridOrderFor(previousPack, Boolean(day.locked[previousPack.eventId]), revealLayout)
    : [];
  const formatChanged =
    previousPack != null && (previousPack.setCode !== pack.setCode || previousOrder.length !== pack.pack.length);
  const underlayAt = (index: number): CardOpening["underlay"] => {
    if (!previousPack) {
      return "skeleton";
    }
    return formatChanged ? "empty" : previousPack.cards[previousOrder[index]];
  };
  const pickingCard = (card: number, index: number) => (
    <PickingCard
      card={pack.cards[card]}
      pickNumber={slots.includes(card) ? slots.indexOf(card) + 1 : null}
      opening={{
        index,
        openedAt: opening?.openedAt ?? 0,
        underlay: underlayAt(index),
      }}
      onToggle={() => toggle(card)}
      onDragOut={startGridDrag(card)}
      onZoom={() => setZoom(pack.cards[card])}
    />
  );
  const gridOrder = gridOrderFor(pack, score != null, revealLayout);

  const headerTools: WheelHeaderTools = score
    ? {
        draftHref,
        draftersShown: showDrafters,
        onToggleDrafters: import.meta.env.DEV ? () => setShowDrafters((shown) => !shown) : undefined,
        onReset: dayKey ? () => restartToday(dayKey) : undefined,
      }
    : {};
  const packNumber = featured ? (packNumbers.get(pack.eventId) ?? null) : packNumberOf?.(pack);
  const featuredTitle = `${setName(pack.setCode)} Pack #${packNumber ?? viewIndex + 1}`;
  const freePlayTitle = packNumber ? `${setName(pack.setCode)} Pack #${packNumber}` : setName(pack.setCode);
  const header = (className: string, compact: boolean) => (
    <WheelHeader
      setCode={pack.setCode}
      title={featured ? featuredTitle : freePlayTitle}
      dayLabel={dayKey ? `${shortDayLabel(dayKey)} Packs` : undefined}
      progress={progress}
      tools={headerTools}
      onHelp={onHelp}
      onExit={onExit}
      compact={compact}
      className={className}
    />
  );

  return (
    <>
      <CardZoom card={zoom} onClose={() => setZoom(null)} />
      <div className={GAME_LAYOUT}>
        {header(cn(PIXEL_PANEL, "h-[84px] px-3 py-2 lg:hidden"), true)}
        <PackGrid
          key={pack.eventId}
          cardCount={gridOrder.length}
          onClick={score && freshReveal ? () => setFreshReveal(false) : undefined}
          gridRef={gridRef}
        >
          {gridOrder.map((card, index) => (
            <PackSlot key={card} index={index} flipKey={`${pack.eventId}-${card}`}>
              {score ? revealCard(card) : artResolved ? pickingCard(card, index) : <PulseCard index={index} />}
            </PackSlot>
          ))}
          {floatingAction}
        </PackGrid>
        <div
          className={cn(
            "fixed inset-x-0 bottom-0 z-20 border-t-[3px] border-[#1a120b]",
            "shadow-[inset_0_2px_0_#5a3a1e] transition-[max-height,background-color] duration-300 ease-out",
            sheetOpen ? "max-h-[82vh] overflow-y-auto bg-[#16110c]/90" : "max-h-[76px] overflow-hidden bg-[#16110c]",
            "isolate lg:relative lg:col-start-2 lg:row-span-2 lg:row-start-1 lg:flex lg:max-h-[calc(100vh-125px)]",
            "lg:flex-col lg:overflow-y-auto lg:border-[3px] lg:p-4 [@media(max-height:760px)]:lg:p-3",
            "lg:bg-[#16110c]/95 lg:shadow-[inset_0_0_0_2px_#5a3a1e,6px_6px_0_#05070a]",
          )}
        >
          {header(
            cn(
              "mb-4 hidden border-b-2 border-[#3a2a17] pb-4 lg:block",
              "[@media(max-height:760px)]:lg:mb-2.5 [@media(max-height:760px)]:lg:pb-2.5",
            ),
            false,
          )}
          <SheetBar
            open={sheetOpen}
            onToggle={() => setSheetOpen(!sheetOpen)}
            status={sheetStatus}
            action={renderAction(false)}
          />
          <div className={cn("px-4 pb-4 lg:flex lg:flex-1 lg:flex-col lg:p-0", !sheetOpen && "max-lg:invisible")}>
            <OrderSection
              pack={pack}
              slots={slots}
              score={score}
              animate={freshReveal}
              listRef={listRef}
              dropIndex={gridDrag?.index ?? null}
              hint={`${touchVerb} a Card`}
              onRemove={remove}
              onReorder={setDraft}
            />
            <WheelSection pack={pack} slots={slots} score={score} animate={freshReveal} />
          </div>
        </div>
      </div>
      {gridDrag && (
        <div
          className="pointer-events-none fixed top-0 left-0 z-50 w-72 drop-shadow-[0_12px_24px_rgba(0,0,0,0.7)]"
          style={{ transform: `translate(${gridDrag.x - 40}px, ${gridDrag.y - 14}px) rotate(-2deg)` }}
        >
          <CardTitle card={pack.cards[gridDrag.card]} />
        </div>
      )}
    </>
  );
}

function WaitingConfirm({ remaining, className }: { remaining: number; className: string }) {
  const [tapped, setTapped] = useState(false);
  useEffect(() => {
    if (!tapped) {
      return;
    }
    const timer = window.setTimeout(() => setTapped(false), 2200);
    return () => window.clearTimeout(timer);
  }, [tapped]);
  return (
    <Tooltip
      label={`Pick ${remaining} more ${remaining === 1 ? "card" : "cards"}`}
      open={tapped || undefined}
      delayDuration={0}
      hideArrow
      className={PIXEL_TOOLTIP}
    >
      <button
        type="button"
        aria-disabled
        onClick={() => setTapped(true)}
        className={cn(WAITING_PIXEL_BUTTON, className)}
      >
        Confirm
      </button>
    </Tooltip>
  );
}

function SheetBar({
  open,
  onToggle,
  status,
  action,
}: {
  open: boolean;
  onToggle: () => void;
  status: ReactNode;
  action: ReactNode;
}) {
  return (
    <div onClick={onToggle} className="flex h-[76px] cursor-pointer items-center gap-3 px-4 lg:hidden">
      <button
        aria-label={open ? "Hide Order" : "Show Order"}
        aria-expanded={open}
        className="grid size-8 shrink-0 place-items-center text-[#f6c95e]"
      >
        <ChevronUp
          size={22}
          strokeWidth={3}
          className={cn("transition-transform duration-300", open && "rotate-180")}
        />
      </button>
      <span className={cn("min-w-0 flex-1 truncate text-xl", PIXEL_HEADING)}>{status}</span>
      <span onClick={(e) => e.stopPropagation()}>{action}</span>
    </div>
  );
}

function WheelSkeleton() {
  return (
    <div className={GAME_LAYOUT}>
      <div className={cn(PIXEL_PANEL, "h-[84px] lg:col-start-2 lg:row-start-1")} />
      <PackGrid cardCount={SKELETON_CARDS}>
        {Array.from({ length: SKELETON_CARDS }, (_, i) => (
          <PackSlot key={i} index={i}>
            <PulseCard index={i} />
          </PackSlot>
        ))}
      </PackGrid>
      <div className={cn(PIXEL_PANEL, "hidden h-[620px] p-4 lg:col-start-2 lg:row-start-2 lg:block")}>
        <h2 className={cn("text-2xl", PIXEL_HEADING)}>Your Order</h2>
      </div>
    </div>
  );
}

interface PackOpening {
  eventId: string;
  previousId: string | null;
  openedAt: number;
}

function gridOrderFor(pack: WheelPack, revealed: boolean, revealLayout: RevealLayout): number[] {
  if (revealed && revealLayout === "real-order") {
    return [...pack.order.map((pick) => pick.card), ...pack.wheel];
  }
  return pack.pack;
}

function usePackArtResolved(pack: WheelPack | undefined): boolean {
  const cardImages = useCardImageMapContext();
  if (!pack) {
    return false;
  }
  return (
    cardImages.ready || pack.pack.every((card) => hasCardImage(cardImages, pack.cards[card].n, pack.cards[card].s))
  );
}

function usePreloadPackArt(pack: WheelPack | undefined) {
  const cardImages = useCardImageMapContext();
  const artResolved = usePackArtResolved(pack);
  useEffect(() => {
    if (!pack || !artResolved) {
      return;
    }
    for (const card of pack.pack) {
      preloadImage(cardImageSources(pack.cards[card].n, pack.cards[card].s, cardImages)[0]);
    }
  }, [pack, artResolved, cardImages]);
}

function preloadImage(src: string | undefined) {
  if (src) {
    new Image().src = src;
  }
}

function usePackImages(packs: WheelPack[]) {
  const imageItems = useMemo(
    () => packs.flatMap((pack) => pack.pack.map((i) => ({ name: pack.cards[i].n, set: pack.cards[i].s }))),
    [packs],
  );
  return useCardImageMap(imageItems);
}

function nextUnlockedIndex(packs: WheelPack[], locked: Record<string, number[]>, from: number): number | null {
  for (let step = 1; step < packs.length; step++) {
    const index = (from + step) % packs.length;
    if (!locked[packs[index].eventId]) {
      return index;
    }
  }
  return null;
}

function restartToday(dayKey: string | null) {
  if (dayKey) {
    localStorage.removeItem(wheelDayStorageKey(dayKey));
  }
  window.location.reload();
}

function resetDayOnRequest(dayKey: string) {
  const url = new URL(window.location.href);
  if (!url.searchParams.has("reset")) {
    return;
  }
  localStorage.removeItem(wheelDayStorageKey(dayKey));
  url.searchParams.delete("reset");
  window.history.replaceState(null, "", url);
}
