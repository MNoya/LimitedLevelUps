import { useEffect, useMemo, useState } from "react";
import { useParams } from "react-router-dom";

import { PageShell } from "../components/PageShell";
import { DesktopBuilder } from "../components/dailySealed/DesktopBuilder";
import { DesktopBuilderSkeleton, PhoneBuilderSkeleton } from "../components/dailySealed/BuilderSkeleton";
import { MobileBuilder } from "../components/dailySealed/MobileBuilder";
import { breakdownTabFromHash, setAnchor } from "../components/dailySealed/Breakdown";
import { useBuilder } from "../components/dailySealed/useBuilder";
import type { CardActions } from "../components/dailySealed/cards";
import type { Notice } from "../components/dailySealed/shared";
import { useAuth } from "../auth/useAuth";
import { useSets } from "../data/hooks";
import { useCardStats } from "../data/tierList";
import { useCardImageMap } from "../data/cardImages";
import {
  basicColorOf,
  basicEntries,
  BASIC_NAMES,
  COLORS,
  DAILY_SEALED_BLURB,
  isBasicIndex,
  DECK_SIZE,
  filterEntries,
  groupByColor,
  nextTurnover,
  NO_FILTERS,
  servingDay,
  type Basics,
  type DailySealedPool,
  type PoolEntry,
  type PoolFilters,
} from "../data/dailySealed";
import {
  useDailySealedBuilds,
  useDailySealedDays,
  useDailySealedPool,
  useOwnDailySealedBuild,
  useSaveDailySealedBuild,
  type DailySealedDay,
  type OwnBuildInput,
} from "../data/dailySealedApi";
import { useIsMobile } from "../lib/use-is-mobile";
import { cn } from "../lib/utils";

const NOTICE_MS = 2500;

export const DailySealedPage = () => {
  const { day } = useParams();
  const { data: pool, isPending, isError } = useDailySealedPool(day);
  const isMobile = useIsMobile();
  const screen = useState<ScreenChoice | null>(null);

  const awaitingFirstPool = !isPending && !isError && !pool && !day;
  if (!isMobile && (pool || isPending || awaitingFirstPool)) {
    return (
      <div className="flex h-[100dvh] flex-col overflow-hidden bg-bg text-text">
        {pool ? (
          <PoolBuilder key={pool.day} pool={pool} isMobile={false} screen={screen} />
        ) : awaitingFirstPool ? (
          <FirstPoolTeaser isMobile={false} />
        ) : (
          <DesktopBuilderSkeleton />
        )}
      </div>
    );
  }

  return (
    <PageShell subtitle="TOOLS" fill={!isMobile} footer={false}>
      {isPending ? (
        <PhoneBuilderSkeleton />
      ) : isError ? (
        <PageMessage text="Pool didn't load. Refresh to try again" />
      ) : awaitingFirstPool ? (
        <FirstPoolTeaser isMobile={isMobile} />
      ) : !pool ? (
        <PageMessage text="No pool on this day" />
      ) : (
        <PoolBuilder key={pool.day} pool={pool} isMobile={isMobile} screen={screen} />
      )}
    </PageShell>
  );
};

const localTurnoverTime = () => nextTurnover().toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });

const FirstPoolTeaser = ({ isMobile }: { isMobile: boolean }) => (
  <div className={cn("relative flex flex-1 flex-col overflow-hidden", isMobile ? "min-h-[80vh]" : "min-h-0")}>
    <div aria-hidden className="flex min-h-0 flex-1 flex-col">
      {isMobile ? <PhoneBuilderSkeleton resting /> : <DesktopBuilderSkeleton resting />}
    </div>
    <div className="absolute inset-0 flex items-start justify-center px-4 pt-[10vh]">
      <div className="flex max-w-[420px] flex-col items-center gap-3 rounded-md border border-border bg-surface px-6 py-6 text-center shadow-xl">
        <h1 className="font-display text-[22px] tracking-[0.14em] text-text">DAILY SEALED</h1>
        <p className="text-[14px] text-subtle">{DAILY_SEALED_BLURB}</p>
        <p className="text-[15px] text-green">First pool drops at {localTurnoverTime()}</p>
      </div>
    </div>
  </div>
);

const PageMessage = ({ text }: { text: string }) => (
  <div className="flex flex-1 items-center justify-center px-4 py-20 text-[14px] text-subtle">{text}</div>
);

export type PhoneTab = "pool" | "deck";

type ScreenChoice = { day: string; breakdown: boolean; phoneTab: PhoneTab };

type ScreenState = [ScreenChoice | null, (choice: ScreenChoice) => void];

const PoolBuilder = ({ pool, isMobile, screen }: { pool: DailySealedPool; isMobile: boolean; screen: ScreenState }) => {
  const view = useBuilderView(pool, isMobile, screen);
  return isMobile ? <MobileBuilder view={view} /> : <DesktopBuilder view={view} />;
};

export type BuilderView = ReturnType<typeof useBuilderView>;

const useBuilderView = (pool: DailySealedPool, isMobile: boolean, [chosenScreen, chooseScreen]: ScreenState) => {
  const { user, signIn } = useAuth();
  const isToday = pool.day === servingDay();
  const screen = chosenScreen?.day === pool.day ? chosenScreen : startingScreen(pool.day, isToday);
  const { data: ownBuild, isSuccess: ownBuildLoaded } = useOwnDailySealedBuild(pool.day, !!user);
  const builder = useBuilder(pool, ownBuild);
  const submitted = !!ownBuild;
  const resultsAvailable = submitted || !isToday;
  const { data: builds, isPending: buildsPending } = useDailySealedBuilds(pool.day, resultsAvailable);
  const { data: days } = useDailySealedDays();
  const { data: sets } = useSets();
  const save = useSaveDailySealedBuild(pool.day);
  const stats = useCardStats(pool.setCode);
  const [filters, setFilters] = useState<PoolFilters>(NO_FILTERS);
  const [ratings, setRatings] = useState(false);
  const [showHidden, setShowHidden] = useState(false);
  const preview = useCardStepper(pool);
  const basicArt = useCardImageMap(useMemo(() => basicLandItems(pool.setCode), [pool.setCode]));
  const [notice, setNotice] = useState<Notice | null>(null);

  useEffect(() => {
    if (!notice) {
      return;
    }
    const timer = window.setTimeout(() => setNotice(null), NOTICE_MS);
    return () => window.clearTimeout(timer);
  }, [notice]);

  const sideEntries = filterEntries(showHidden ? builder.hidden : builder.side, filters);
  const previewOrder = (entry: PoolEntry): number[] => {
    const zone = builder.zoneOf(entry.index);
    if (zone === "deck") {
      return builder.deck.map((card) => card.index);
    }
    if (isMobile) {
      return groupByColor(sideEntries).flatMap((group) => group.entries.map((card) => card.index));
    }
    if (zone === "hidden") {
      return builder.hidden.map((card) => card.index);
    }
    const shown = new Set(sideEntries.map((card) => card.index));
    return builder.side.map((card) => card.index).filter((index) => shown.has(index));
  };
  const openPreview = (entry: PoolEntry) => preview.open(entry, previewOrder(entry));
  const ratingFor = ratings && stats ? (card: { name: string }) => stats.statsFor(card.name)?.gihWr ?? null : undefined;
  const sideActions: CardActions = {
    onPick: (entry) => builder.move([entry.index], showHidden ? "side" : "deck"),
    onHide: showHidden ? undefined : (entry) => builder.move([entry.index], "hidden"),
    onPreview: openPreview,
    ratingFor,
  };
  const deckActions: CardActions = {
    onPick: (entry) =>
      isBasicIndex(entry.index)
        ? builder.adjustBasic(basicColorOf(entry.index), -1)
        : builder.move([entry.index], "side"),
    onPreview: (entry) => {
      if (!isBasicIndex(entry.index)) {
        openPreview(entry);
      }
    },
    ratingFor,
  };
  const submission = builder.submission();
  const unchanged = !!ownBuild && sameBuild(ownBuild, submission);
  const setName = useMemo(
    () => sets?.find((set) => set.code === pool.setCode)?.name ?? pool.setCode,
    [sets, pool.setCode],
  );

  const submit = async () => {
    if (!user) {
      signIn();
      return;
    }
    try {
      await save.mutateAsync(submission);
      setNotice({ text: submitted ? "Build updated!" : "Build submitted!", tone: "ok" });
    } catch {
      setNotice({ text: "Your build didn't save. Submit it again", tone: "error" });
    }
  };

  return {
    pool,
    builder,
    setName,
    isToday,
    neighbors: neighborDays(days ?? [], pool.day),
    filters,
    setFilters,
    ratings,
    ratingsAvailable: !!stats?.hasStats,
    toggleRatings: () => setRatings((prev) => !prev),
    showHidden,
    toggleShowHidden: () => setShowHidden((prev) => !prev),
    sideEntries,
    basicCards: basicEntries(builder.basics, basicArt.images, pool.setCode),
    sideActions,
    deckActions,
    preview: preview.entry,
    previewStep: preview.step,
    openPreview,
    openCard: (entry: PoolEntry) => preview.open(entry, null),
    closePreview: preview.close,
    yourMain: ownBuild?.main ?? null,
    yourBuild: ownBuild ?? null,
    gihWrOf: (name: string) => stats?.statsFor(name)?.gihWr ?? null,
    basicCardsOf: (basics: Basics) => basicEntries(basics, basicArt.images, pool.setCode),
    notice,
    results: { available: resultsAvailable, builds: builds ?? [], loading: buildsPending },
    showingBreakdown: resultsAvailable && screen.breakdown,
    phoneTab: screen.phoneTab,
    showBreakdown: () => chooseScreen({ ...screen, breakdown: true }),
    showBuild: (phoneTab: PhoneTab = screen.phoneTab) => {
      setAnchor(null);
      chooseScreen({ ...screen, breakdown: false, phoneTab });
    },
    submitState: {
      visible: isToday,
      signedIn: !!user,
      ready: builder.deckSize >= DECK_SIZE,
      submitted,
      unchanged,
      pending: save.isPending || (!!user && !ownBuildLoaded),
      run: submit,
    },
    linkText: () => `${window.location.origin}/daily-sealed/${pool.day}`,
    exportText: builder.exportText,
    copyBlocked: () => setNotice({ text: "Copying is blocked in this browser", tone: "error" }),
  };
};

const startingScreen = (day: string, isToday: boolean): ScreenChoice => ({
  day,
  breakdown: !isToday || breakdownTabFromHash() !== null,
  phoneTab: "pool",
});

const basicLandItems = (setCode: string) => COLORS.map((color) => ({ name: BASIC_NAMES[color], set: setCode }));

const useCardStepper = (pool: DailySealedPool) => {
  const [state, setState] = useState<{ index: number; order: number[] | null } | null>(null);
  const position = state?.order ? state.order.indexOf(state.index) : -1;
  const stepBy = (offset: number) => {
    const target = state?.order?.[position + offset];
    if (state && target !== undefined) {
      setState({ ...state, index: target });
    }
  };
  const hasOrder = !!state?.order && position >= 0;
  return {
    entry: state ? { index: state.index, card: pool.cards[state.index] } : null,
    step: hasOrder
      ? {
          prev: position > 0 ? () => stepBy(-1) : null,
          next: position < (state?.order?.length ?? 0) - 1 ? () => stepBy(1) : null,
        }
      : null,
    open: (entry: PoolEntry, order: number[] | null) => setState({ index: entry.index, order }),
    close: () => setState(null),
  };
};

const sameBuild = (a: OwnBuildInput, b: OwnBuildInput) => {
  const left = [...a.main].sort((x, y) => x - y).join(",");
  const right = [...b.main].sort((x, y) => x - y).join(",");
  return left === right && COLORS.every((color) => a.basics[color] === b.basics[color]);
};

const neighborDays = (days: DailySealedDay[], current: string) => {
  const index = days.findIndex((entry) => entry.day === current);
  return {
    newer: index > 0 ? days[index - 1] : null,
    older: index >= 0 && index < days.length - 1 ? days[index + 1] : null,
  };
};
