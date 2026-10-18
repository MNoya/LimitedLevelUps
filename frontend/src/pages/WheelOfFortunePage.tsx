import { useEffect, useMemo, useRef, useState, type PointerEvent as ReactPointerEvent, type ReactNode } from "react";
import { Navigate, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { ChevronUp } from "lucide-react";

import { PageShell } from "../components/PageShell";
import { Container } from "../components/Container";
import { CardImageMapProvider } from "../components/pod/review/ReviewCard";
import { podDraftPickHref } from "../components/pod/podLinks";
import { GameStatus } from "../components/draftGames/GameChrome";
import { CardTitle } from "../components/draftGames/wheel/CardTitle";
import { OrderSection, WheelSection } from "../components/draftGames/wheel/OrderPanel";
import { SpaceKey } from "../components/draftGames/wheel/SpaceKey";
import {
  CardZoom,
  GAME_COLUMNS,
  PackGrid,
  PickingCard,
  RevealCard,
  useRevealLayout,
  SkeletonCard,
} from "../components/draftGames/wheel/PackGrid";
import { useWheelDay, wheelDayStorageKey } from "../components/draftGames/wheel/useWheelDay";
import { WheelBackdrop } from "../components/draftGames/wheel/WheelBackdrop";
import { WheelHeader, type WheelHeaderTools, type WheelProgress } from "../components/draftGames/wheel/WheelHeader";
import { QuickHelpDialog, WheelHelpDialog } from "../components/draftGames/wheel/WheelHelp";
import { useGuideHash, useNoScrollGutter, useTouchVerb } from "../components/draftGames/wheel/pageHooks";
import { FEATURED_PLAY, WheelIntro } from "../components/draftGames/wheel/WheelIntro";
import { WheelSummary } from "../components/draftGames/wheel/WheelSummary";
import { useFlip } from "../components/draftGames/wheel/motion";
import { useCardImageMap } from "../data/cardImages";
import {
  MINI_GAMES_HEADER,
  ordinal,
  scoreWheel,
  shortDayLabel,
  useFeaturedPacks,
  useFreePlayPacks,
  useWheelSets,
  utcDayKey,
  type WheelPack,
} from "../data/draftGames";
import type { ArtifactCard } from "../types/leaderboard";
import { cn } from "../lib/utils";
import { GOLD_BUTTON, PIXEL_HEADING, PIXEL_PANEL, WAITING_PIXEL_BUTTON } from "../components/draftGames/pixelStyles";

const WHEEL_PATH = "/wheel-of-fortune";
const DAY_PATH = /^\d{4}-\d{2}-\d{2}$/;

const GAME_LAYOUT = cn(
  "flex flex-col gap-3 pb-28 lg:grid lg:grid-rows-[auto_1fr]",
  GAME_COLUMNS,
  "lg:justify-center lg:gap-x-4 lg:gap-y-3 lg:pb-0",
);

type GameMode = "featured" | "free";

export function WheelOfFortunePage() {
  useNoScrollGutter();
  const [today] = useState(() => {
    const day = utcDayKey();
    if (import.meta.env.DEV) {
      resetDayOnRequest(day);
    }
    return day;
  });
  const { play } = useParams<{ play?: string }>();
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
      />
    );
  } else if (isDay) {
    body = <FeaturedGame key={play} dayKey={play} helpOpen={helpOpen} onHelp={openHelp} onExit={exit} />;
  } else {
    const setCode = play.toUpperCase();
    body = <FreePlayGame key={setCode} setCode={setCode} helpOpen={helpOpen} onHelp={openHelp} onExit={exit} />;
  }

  return (
    <PageShell subtitle="WHEEL OF FORTUNE" subtitleShort={MINI_GAMES_HEADER} footer={false}>
      <Container
        className={cn("draft-game pt-3 pb-4", play ? "lg:px-4 2xl:px-10" : "flex flex-1 flex-col max-sm:pb-2")}
      >
        <WheelBackdrop />
        <div className={cn("relative z-[1]", !play && "flex flex-1 flex-col")}>{body}</div>
      </Container>
      <WheelHelpDialog open={helpOpen} onClose={closeHelp} touchVerb={touchVerb} />
      <QuickHelpDialog open={quickHelpOpen} onClose={closeQuickHelp} />
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

function FreePlayGame({ setCode, ...modeProps }: ModeProps & { setCode: string }) {
  const [seed] = useState(() => Math.floor(Math.random() * 1_000_000));
  const [wanted, setWanted] = useState(1);
  const { packs, isPending, exhausted } = useFreePlayPacks(setCode, wanted, seed);
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
}: ModeProps & {
  mode: GameMode;
  packs: WheelPack[];
  dayKey: string | null;
  storageKey: string | null;
  exhausted?: boolean;
  onAdvance?: (index: number) => void;
}) {
  const { day, setDraft: saveDraft, lockIn, goTo, advance, finish } = useWheelDay(storageKey, packs);
  const { sets } = useWheelSets();
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
  useFlip(gridRef, null, 700);

  const featured = mode === "featured";
  const finished = featured && day.advanced >= packs.length;
  const viewIndex = finished ? (reviewing ?? 0) : Math.min(day.current, packs.length - 1);
  const pack: WheelPack | undefined = packs[viewIndex];
  const locked = pack ? day.locked[pack.eventId] : undefined;
  const slots = locked ?? (pack ? (day.drafts[pack.eventId] ?? []) : []);
  const setDraft = (draft: number[]) => pack && saveDraft(pack.eventId, draft);
  const score = pack && locked ? scoreWheel(pack, locked) : null;
  const slotCount = pack?.order.length ?? 0;
  const ready = slotCount > 0 && slots.length === slotCount;
  const nextOpen = featured ? nextUnlockedIndex(packs, day.locked, viewIndex) : null;
  const last = featured && nextOpen == null;

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
      setReviewing(index);
    } else {
      goTo(index);
    }
    window.scrollTo({ top: 0 });
  };
  const closeReview = () => {
    setReviewing(null);
    setFreshSummary(false);
    window.scrollTo({ top: 0 });
  };

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
        touchVerb={touchVerb}
        setName={setName}
        onExit={onExit}
        onReview={(index) => {
          setReviewing(index);
          window.scrollTo({ top: 0 });
        }}
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

  let sessionPoints = 0;
  let sessionMax = 0;
  for (const played of packs) {
    const playedSlots = day.locked[played.eventId];
    if (playedSlots) {
      const playedScore = scoreWheel(played, playedSlots);
      sessionPoints += playedScore.points;
      sessionMax += playedScore.max;
    }
  }
  const progress: WheelProgress = featured
    ? { kind: "featured", steps: featuredSteps, current: viewIndex, onSelect: jumpTo }
    : { kind: "free", packNumber: viewIndex + 1, points: sessionPoints, max: sessionMax };

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
        <button onClick={closeReview} className={cn(GOLD_BUTTON, size)}>
          Back to Today's Score
        </button>
      );
    }
    if (score) {
      return (
        <span key="next" className="flex animate-fadeUpIn" style={{ animationDelay: `${nextDelay}ms` }}>
          <button onClick={next} className={cn(GOLD_BUTTON, size, keyInset)}>
            {last ? "See Today's Score" : "Next Pack"}
            <SpaceKey />
          </button>
        </span>
      );
    }
    return (
      <button
        key={ready ? "ready" : "waiting"}
        onClick={lock}
        disabled={!ready}
        className={cn(ready ? cn(GOLD_BUTTON, keyInset) : WAITING_PIXEL_BUTTON, size)}
      >
        Confirm
        {ready && <SpaceKey />}
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
  const pickingCard = (card: number, i: number) => (
    <PickingCard
      card={pack.cards[card]}
      pickNumber={slots.includes(card) ? slots.indexOf(card) + 1 : null}
      dealIndex={i}
      onToggle={() => toggle(card)}
      onDragOut={startGridDrag(card)}
      onZoom={() => setZoom(pack.cards[card])}
    />
  );
  let gridOrder = pack.pack;
  if (score && revealLayout === "real-order") {
    gridOrder = [...pack.order.map((pick) => pick.card), ...pack.wheel];
  }

  const headerTools: WheelHeaderTools = score
    ? {
        draftHref,
        draftersShown: showDrafters,
        onToggleDrafters: import.meta.env.DEV ? () => setShowDrafters((shown) => !shown) : undefined,
        onReset: import.meta.env.DEV ? () => restartToday(dayKey) : undefined,
      }
    : {};
  const header = (className: string, compact: boolean) => (
    <WheelHeader
      setCode={pack.setCode}
      title={featured ? `${setName(pack.setCode)} #${viewIndex + 1}` : setName(pack.setCode)}
      subtitle={featured ? undefined : "Free Play"}
      dayLabel={dayKey ? shortDayLabel(dayKey) : undefined}
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
          {gridOrder.map((card, i) => (
            <div key={card} data-flip={`${pack.eventId}-${card}`}>
              {score ? revealCard(card) : pickingCard(card, i)}
            </div>
          ))}
          {floatingAction}
        </PackGrid>
        <div
          className={cn(
            "fixed inset-x-0 bottom-0 z-20 border-t-[3px] border-[#1a120b] bg-[#16110c]",
            "shadow-[inset_0_2px_0_#5a3a1e,0_-8px_0_rgba(5,7,10,0.6)] transition-[max-height] duration-300 ease-out",
            sheetOpen ? "max-h-[82vh] overflow-y-auto" : "max-h-[76px] overflow-hidden",
            "isolate lg:relative lg:col-start-2 lg:row-span-2 lg:row-start-1 lg:flex lg:max-h-[calc(100vh-125px)]",
            "lg:flex-col lg:overflow-y-auto lg:border-[3px] lg:p-4",
            "lg:bg-[#16110c]/95 lg:shadow-[inset_0_0_0_2px_#5a3a1e,6px_6px_0_#05070a]",
          )}
        >
          {header("mb-4 hidden border-b-2 border-[#3a2a17] pb-4 lg:block", false)}
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
    <div className="flex h-[76px] items-center gap-3 px-4 lg:hidden">
      <button onClick={onToggle} className="flex min-w-0 flex-1 items-center gap-2 text-left" aria-expanded={open}>
        <ChevronUp size={20} className={cn("shrink-0 transition-transform duration-300", open && "rotate-180")} />
        <span className="min-w-0">
          <span className={cn("block text-xl", PIXEL_HEADING)}>{status}</span>
          <span className="block text-sm text-subtle">{open ? "Hide Order" : "Show Order"}</span>
        </span>
      </button>
      {action}
    </div>
  );
}

function WheelSkeleton() {
  return (
    <div className={GAME_LAYOUT}>
      <div className={cn(PIXEL_PANEL, "h-[84px] animate-pulse lg:col-start-2 lg:row-start-1")} />
      <PackGrid cardCount={15}>
        {Array.from({ length: 15 }, (_, i) => (
          <SkeletonCard key={i} index={i} />
        ))}
      </PackGrid>
      <div className={cn(PIXEL_PANEL, "hidden h-[620px] animate-pulse lg:col-start-2 lg:row-start-2 lg:block")} />
    </div>
  );
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
