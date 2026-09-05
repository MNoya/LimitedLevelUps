import { useEffect, useMemo, useRef, useState } from "react";
import { Link, Navigate, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { BookOpen, ChevronDown } from "lucide-react";

import { PodPage } from "./PodPage";

import { AppHeader } from "../components/AppHeader";
import { Footer } from "../components/Footer";
import { SectionLabel } from "../components/SectionLabel";
import { SetSwitcherDesktop } from "../components/SetSwitcher";
import { SetFilterDropdown, setFilterOptionsFrom } from "../components/SetFilterDropdown";
import { BoardWindowSelector, type BoardWindowOption } from "../components/BoardWindowSelector";
import { FilterDropdown, type FilterOption } from "../components/FilterDropdown";
import { AAvatar, setGlyphCode, SetGlyph, Trophy } from "../components/Brand";
import { ArrowRight, CalendarRange, GiRoundTable, TbCards } from "../components/Icons";
import { DiscordIcon } from "../components/BrandIcons";
import { Tooltip } from "../components/Tooltip";
import { DeckScreenshotModal } from "../components/pod/DeckScreenshotModal";
import { highlightEventLabel, PodEventTitle } from "../components/pod/EventLabel";
import { compareStandings, seatSide, teamSides, type TeamSeat } from "../components/pod/PodStandings";
import {
  COMPACT_STANDING_COLS_CLASS,
  deckPipSize,
  PodStandingRow,
  PodStandingRowSkeleton,
  SeatAvatar,
} from "../components/pod/PodStandingRow";
import { Pips } from "../components/ManaPips";
import {
  defaultSortFor,
  LeaderboardColumnHeader,
  LeaderboardTable,
  sortRows,
  type LeaderboardTableRow,
  type SortKey,
  type SortState,
} from "../components/LeaderboardTable";
import { useNow } from "../lib/countdown";
import { useIsMobile } from "../lib/use-is-mobile";
import { POD_SLOTS, easternHourInLocalTime } from "../lib/podSlots";
import { cn } from "../lib/utils";
import {
  cleanPodEventName,
  colorsOf,
  CUBE_BASE,
  fmtRange,
  orderedDeckColors,
  playerPath,
  podDiscordName,
  stripDiscriminator,
  weekOfSet,
} from "../data/utils";
import { ACTIVE_SET_CODE } from "../data/constants";
import { SITE_LINKS } from "../data/site";
import { useAuth } from "../auth/useAuth";
import {
  usePlayerSlugByDiscordId,
  usePodDraftArtifact,
  usePodEventDates,
  usePodEventMatches,
  usePodEventParticipants,
  usePodEvents,
  usePodResultsForSet,
  usePodSeasonEvents,
  usePodSeasonResults,
  usePodSetCodes,
  useSets,
} from "../data/hooks";
import {
  aggregatePodStandings,
  bucketBySetCode,
  bucketOf,
  inSeasonWindow,
  seasonsPlayed,
  currentSeason,
  podSeasons,
  seasonBuckets,
  seasonForDate,
  type PodFormatBucket,
} from "../data/podSeasons";
import { resolveDeck } from "../data/draft-artifact";
import { usePodDecklistAccess } from "../data/podDecklistAccess";
import type {
  PodEventParticipantRow,
  PodEventSummary,
  PodLeaderboardRow,
  PodSetCode,
  SetSummary,
} from "../types/leaderboard";

// A format tried once is not a board, so it stays out of the switcher and keeps its pods on the season
const MIN_BOARD_PODS = 2;

// A custom-format code longer than this overflows the chip and shows the generic CUBE label
const POD_CHIP_CODE_MAX = 4;

function synthesizePodSet(p: PodSetCode): SetSummary {
  const custom = p.label != null;
  return {
    code: p.code,
    name: p.label ?? p.code,
    startDate: "",
    endDate: "",
    isActive: false,
    custom,
    shortCode: custom && p.code.length > POD_CHIP_CODE_MAX ? CUBE_BASE : undefined,
  };
}

// A board that ran in one season has nothing to pick between, so it shows no season selector
const MIN_BOARD_SEASONS = 2;

const AXIS_ALL = "__all__";
const AXIS_PARAM_FORMAT = "format";
const AXIS_PARAM_SEASON = "season";

const FORMAT_BUCKETS: PodFormatBucket[] = ["set", "flashback", "cube", "mock"];

const POD_DESKTOP_WIDTH = 900;

const MONTHS_CAL = ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"];

function parseMonthDay(iso: string): { month: string; day: number } {
  const m = parseInt(iso.slice(5, 7), 10);
  const d = parseInt(iso.slice(8, 10), 10);
  return { month: MONTHS_CAL[m - 1] ?? "", day: d };
}

function toLeaderboardRow(r: PodLeaderboardRow): LeaderboardTableRow {
  return {
    setCode: r.setCode,
    slug: r.slug,
    displayName: r.displayName,
    avatarUrl: r.avatarUrl,
    rank: r.rank,
    trophies: r.trophies,
    score: r.points ?? 0,
    events: r.events,
    wins: r.wins,
    losses: r.losses,
    lastCalculatedAt: r.lastFinishedAt ?? "",
  };
}

export function PodsRoute() {
  const { slug } = useParams<{ slug: string }>();
  const { data: podSetCodes } = usePodSetCodes();
  const { data: allSets } = useSets();
  if (!slug) return <PodDraftsPage />;
  if (podSetCodes === undefined || allSets === undefined) {
    return (
      <div className="bg-bg text-text min-h-screen flex flex-col">
        <AppHeader subtitle="POD DRAFTS" />
      </div>
    );
  }
  const season = podSeasons(allSets).find((s) => s.code.toLowerCase() === slug.toLowerCase());
  if (season) {
    if (slug !== season.code) return <Navigate to={`/pods/${season.code}`} replace />;
    return <PodDraftsPage seasonCode={season.code} />;
  }
  const match = podSetCodes.find((p) => p.code.toLowerCase() === slug.toLowerCase());
  if (match) {
    if (slug !== match.code) return <Navigate to={`/pods/${match.code}`} replace />;
    return <PodDraftsPage setCode={match.code} />;
  }
  const window = boardWindowFromSlug(slug, podSetCodes, allSets);
  if (window) {
    return <Navigate to={`/pods/${window.board}?${AXIS_PARAM_SEASON}=${window.season}`} replace />;
  }
  return <PodPage />;
}

function boardWindowFromSlug(
  slug: string,
  podSetCodes: { code: string }[],
  allSets: SetSummary[],
): { board: string; season: string } | null {
  const split = slug.lastIndexOf("-");
  if (split <= 0) return null;
  const board = podSetCodes.find((p) => p.code.toLowerCase() === slug.slice(0, split).toLowerCase());
  const season = podSeasons(allSets).find((s) => s.code.toLowerCase() === slug.slice(split + 1).toLowerCase());
  return board && season ? { board: board.code, season: season.code } : null;
}

export function PodDraftsPage({
  setCode,
  seasonCode,
}: { setCode?: string; seasonCode?: string } = {}) {
  // Below the two-column grid's own breakpoint, so a phone asking for the desktop site gets the
  // desktop chrome stacked in one column instead of the mobile layout
  const isMobile = useIsMobile(POD_DESKTOP_WIDTH);
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const { data: allSets } = useSets();
  const { data: podSetCodes } = usePodSetCodes();
  const { data: podEventDates } = usePodEventDates();

  // A season lists once it holds a pod, inside its window or drafting its own set
  const seasons = useMemo<SetSummary[]>(() => {
    if (!allSets || !podEventDates || !podSetCodes) return [];
    const played = new Set(podSetCodes.map((p) => p.code));
    for (const date of podEventDates) {
      const season = seasonForDate(allSets, date);
      if (season) played.add(season.code);
    }
    return podSeasons(allSets).filter((s) => played.has(s.code));
  }, [allSets, podEventDates, podSetCodes]);

  const season = useMemo<SetSummary | undefined>(() => {
    if (setCode) return undefined;
    if (seasonCode) return seasons.find((s) => s.code === seasonCode);
    return currentSeason(allSets) ?? seasons[0];
  }, [setCode, seasonCode, seasons, allSets]);

  const legacySets = useMemo<SetSummary[]>(() => {
    if (!allSets || !podSetCodes) return [];
    const byCode = new Map(allSets.map((s) => [s.code, s]));
    // Real sets first, then pod-only codes with no visible `sets` row. A label marks a cube format
    // (custom → generic glyph); a bare code is a set hidden until release and keeps its own keyrune.
    const real = allSets.filter((s) => podSetCodes.some((p) => p.code === s.code));
    const synthesized = podSetCodes
      .filter((p) => !byCode.has(p.code) && (p.label == null || p.events >= MIN_BOARD_PODS))
      .map(synthesizePodSet);
    return [...real, ...synthesized];
  }, [allSets, podSetCodes]);

  const homeCode = useMemo(() => {
    const current = currentSeason(allSets);
    if (current && seasons.some((s) => s.code === current.code)) return current.code;
    return seasons[0]?.code ?? ACTIVE_SET_CODE;
  }, [allSets, seasons]);

  const activeSet = season?.code ?? setCode ?? homeCode;
  const onSelectSet = (code: string) => {
    navigate(code === homeCode ? "/pods" : `/pods/${code}`);
  };

  const axisParam = season ? AXIS_PARAM_FORMAT : AXIS_PARAM_SEASON;
  const rawAxis = searchParams.get(axisParam);
  const axis = season
    ? FORMAT_BUCKETS.find((bucket) => bucket === rawAxis)
    : podSeasons(allSets).find((s) => s.code === rawAxis)?.code;

  const seasonEvents = usePodSeasonEvents(season).data;
  const seasonResults = usePodSeasonResults(season).data;
  const boardEvents = usePodEvents(season ? undefined : activeSet).data;
  const boardResults = usePodResultsForSet(season ? undefined : activeSet).data;

  // A set below the board threshold still resolves its name when opened directly by code
  const directPod = podSetCodes?.find((p) => p.code === activeSet);
  const setMeta =
    season ?? legacySets.find((s) => s.code === activeSet) ?? (directPod ? synthesizePodSet(directPod) : undefined);
  const buckets = useMemo(() => seasonBuckets(seasonEvents, activeSet), [seasonEvents, activeSet]);
  const boardSeasons = useMemo(() => seasonsPlayed(boardEvents, allSets), [boardEvents, allSets]);

  // One control for both axes: a season board picks a format, a cube board picks a season window.
  // Chips could not survive a season with five buckets at 1200px, so the dropdown carries both.
  const selectorOptions = useMemo<BoardWindowOption[]>(() => {
    const calendar = <CalendarRange size={20} className="text-white shrink-0" />;
    // Which mode we are in comes from the route, not the data, so a cold start never flashes the
    // wrong control while the sets are still loading
    if (!setCode) {
      // The hero already says HOB overhead, so desktop drops the code and keeps the axis word
      const head = isMobile && season ? `${season.code} SEASON` : "SEASON";
      return [
        { value: AXIS_ALL, label: head, icon: calendar },
        ...buckets.map((b) => ({
          value: b.key,
          label: (b.key === "set" ? `${b.label} ONLY` : b.label).toUpperCase(),
          icon: <ChipIcon bucket={b.key} seasonMeta={season} className="text-white shrink-0" size={20} />,
        })),
      ];
    }
    if (boardSeasons.length < MIN_BOARD_SEASONS) return [];
    return [
      { value: AXIS_ALL, label: "ALL SEASONS", icon: calendar },
      ...boardSeasons.map(({ season: s }) => ({
        value: s.code,
        label: `${s.code} SEASON`,
        glyph: setGlyphCode(s),
      })),
    ];
  }, [setCode, season, buckets, boardSeasons, isMobile]);

  const selectorValue = axis ?? AXIS_ALL;

  const onSelectWindow = (value: string) => {
    const next = new URLSearchParams(searchParams);
    if (value === AXIS_ALL) {
      next.delete(axisParam);
    } else {
      next.set(axisParam, value);
    }
    setSearchParams(next);
  };

  // Mock pods play no rounds, so they never carry results and only their own filter can reach them
  const bucketCodes = useMemo(() => {
    if (!season || !axis) return undefined;
    if (axis === "mock") return new Set<string>();
    const byCode = bucketBySetCode(seasonEvents?.filter((e) => e.kind !== "mock"), activeSet);
    return new Set(Array.from(byCode).filter(([, b]) => b === axis).map(([code]) => code));
  }, [season, axis, seasonEvents, activeSet]);

  const boardWindow = useMemo(
    () => (season ? undefined : boardSeasons.find(({ season: s }) => s.code === axis)?.season),
    [season, axis, boardSeasons],
  );

  const events = useMemo(() => {
    if (!season) {
      if (!boardEvents) return undefined;
      if (!boardWindow) return boardEvents;
      return boardEvents.filter((e) => inSeasonWindow(boardWindow, e.eventDate));
    }
    if (!seasonEvents) return undefined;
    if (axis) return seasonEvents.filter((e) => bucketOf(e, activeSet) === axis);
    return seasonEvents.filter((e) => e.kind !== "mock" && inSeasonWindow(season, e.eventDate));
  }, [season, seasonEvents, boardEvents, boardWindow, axis, activeSet]);

  // Scoped by event id, since `event_time` is UTC and a late pod crosses a boundary its ET date does not
  const windowEventIds = useMemo(() => {
    const bounds = season ?? boardWindow;
    const scoped = season ? seasonEvents : boardEvents;
    if (!bounds || !scoped) return undefined;
    return new Set(scoped.filter((e) => inSeasonWindow(bounds, e.eventDate)).map((e) => e.eventId));
  }, [season, boardWindow, seasonEvents, boardEvents]);

  // The set's own chip carries every pod that drafted it, reaching past the season it sits in
  const unwindowed = axis === "set" || (!season && !boardWindow);

  const leaderboard = useMemo(() => {
    const results = season ? seasonResults : boardResults;
    if (unwindowed) return aggregatePodStandings(results, bucketCodes);
    if (!windowEventIds) return undefined;
    return aggregatePodStandings(results?.filter((r) => windowEventIds.has(r.eventId)), bucketCodes);
  }, [season, unwindowed, seasonResults, boardResults, bucketCodes, windowEventIds]);

  // Held whole until the query lands: a switcher that grows from one chip to six reads as broken
  const switcherSets = useMemo(() => {
    if (!podEventDates || !podSetCodes) return [];
    const seasonCodes = new Set(seasons.map((s) => s.code));
    return [...seasons, ...legacySets.filter((s) => !seasonCodes.has(s.code))];
  }, [podEventDates, podSetCodes, seasons, legacySets]);

  const [sort, setSort] = useState<SortState>(defaultSortFor("pod"));
  const sortedLeaderboard = useMemo(() => {
    if (!leaderboard) return undefined;
    const adapted: LeaderboardTableRow[] = leaderboard.map(toLeaderboardRow);
    return sortRows(adapted, sort);
  }, [leaderboard, sort]);
  const onSort = (key: SortKey) => {
    setSort((cur) =>
      cur.key === key
        ? { key, dir: cur.dir === "desc" ? "asc" : "desc" }
        : { key, dir: "desc" },
    );
  };

  const nowMs = useNow(60_000);
  // A pod that has not started has no result to show and UPCOMING is a Discord link, so it is dropped
  const { played, mock } = useMemo(() => {
    const p: PodEventSummary[] = [];
    const m: PodEventSummary[] = [];
    for (const e of events ?? []) {
      if (e.kind === "mock") m.push(e);
      else if (e.championDisplayName || new Date(e.eventTime).getTime() <= nowMs) p.push(e);
    }
    return { played: p, mock: m };
  }, [events, nowMs]);

  usePodEventParticipants(played[0]?.eventId);

  const onSeasonBoard = !!season && !axis;

  // Any season prints the set's own run, so it reads the same whether one pod happened in it or
  // twenty. Only a whole board, which spans no single set, falls back to the pods it actually holds.
  const boardRange = useMemo(() => {
    const window = season ?? boardWindow;
    if (window) {
      return fmtRange(window.startDate, window.endDate);
    }
    const dates = (events ?? []).filter((e) => e.kind !== "mock").map((e) => e.eventDate).sort();
    return dates.length > 0 ? fmtRange(dates[0], dates[dates.length - 1]) : null;
  }, [season, boardWindow, events]);

  const windowSelector = selectorOptions.length > 0 ? (
    <BoardWindowSelector
      value={selectorValue}
      options={selectorOptions}
      onSelect={onSelectWindow}
      variant={isMobile ? "mobile" : "hero"}
    />
  ) : null;

  const { user } = useAuth();
  const { data: mySlug } = usePlayerSlugByDiscordId(user?.discordId);

  const chromeRef = useRef<HTMLDivElement>(null);
  const chromeHeight = useMeasuredHeight(chromeRef, isMobile);
  const standingsHeadRef = useRef<HTMLDivElement>(null);
  const standingsHeadHeight = useMeasuredHeight(standingsHeadRef, isMobile);

  return (
    <div className="bg-bg text-text min-h-screen flex flex-col page-fade">
      {isMobile ? (
        <div ref={chromeRef} className="page-chrome sticky top-0 z-10 bg-bg">
          <AppHeader subtitle="POD DRAFTS" />
          <MobileFilterBar
            activeSet={activeSet}
            availableSets={switcherSets}
            onSelectSet={onSelectSet}
            windowSelector={windowSelector}
          />
        </div>
      ) : (
        <>
          <AppHeader subtitle="POD DRAFTS" />
          <SetHero
            activeSet={activeSet}
            setMeta={setMeta}
            sets={switcherSets}
            onSelectSet={onSelectSet}
            range={boardRange}
            isSeason={!!season}
            windowSelector={windowSelector}
          />
        </>
      )}

      <main className="flex-1 lg:pl-5 lg:pr-8 lg:pb-10">
        <div className="grid grid-cols-1 lg:grid-cols-[3fr_2fr] gap-x-6 lg:gap-y-8">
          <section className="order-1 lg:order-2 min-w-0 flex flex-col gap-4">
            {isMobile ? (
              <MobileEventsBlock
                played={played}
                loading={events === undefined}
                nowMs={nowMs}
                activeSet={activeSet}
              />
            ) : (
              <>
                {onSeasonBoard && <UpcomingBlock />}
                {events === undefined ? (
                  <EventsLoadingBlock />
                ) : played.length > 0 ? (
                  <EventsBlock events={played} nowMs={nowMs} />
                ) : (
                  <div>
                    <SectionHeading label="EVENTS" count={0} unit="EVENTS" />
                    <EmptyHint>No pod drafts recorded yet for {activeSet}</EmptyHint>
                  </div>
                )}
                {mock.length > 0 && <MockDraftsBlock events={mock} />}
              </>
            )}
          </section>

          <section className="order-2 lg:order-1 min-w-0">
            {/* Mobile folds the column header into the sticky chrome, desktop leaves it in the table */}
            {isMobile ? (
              <div ref={standingsHeadRef} className="sticky z-[9] bg-bg" style={{ top: chromeHeight }}>
                <StandingsHeading leaderboard={leaderboard} events={events} compact />
                {leaderboard !== undefined && leaderboard.length > 0 && (
                  <LeaderboardColumnHeader variant="mobile" mode="pod" sort={sort} onSort={onSort} />
                )}
              </div>
            ) : (
              <StandingsHeading leaderboard={leaderboard} events={events} />
            )}
            <LeaderboardTable
              rows={sortedLeaderboard}
              loading={leaderboard === undefined}
              variant={isMobile ? "mobile" : "desktop"}
              mode="pod"
              showHeader={!isMobile}
              sort={sort}
              onSort={onSort}
              stickyTop={chromeHeight + standingsHeadHeight}
              highlightSlug={mySlug ?? undefined}
              emptyMessage={`No player stats yet for ${activeSet}.`}
              playerHref={(row) => playerPath(row.slug, activeSet)}
            />
          </section>

          {isMobile && mock.length > 0 && (
            <section className="order-3">
              <MockDraftsBlock events={mock} stacked />
            </section>
          )}
        </div>
      </main>

      <Footer className="mt-auto px-5 py-4 md:pt-5 md:pb-3 shrink-0" />
    </div>
  );
}

// Returns 0 while the element is unmounted, so a desktop render contributes no sticky offset
function useMeasuredHeight(ref: React.RefObject<HTMLElement>, remountKey: unknown): number {
  const [height, setHeight] = useState(0);
  useEffect(() => {
    const el = ref.current;
    if (!el) {
      setHeight(0);
      return;
    }
    const measure = () => setHeight(el.getBoundingClientRect().height);
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(el);
    return () => observer.disconnect();
  }, [ref, remountKey]);
  return height;
}

function StandingsHeading({
  leaderboard,
  events,
  compact = false,
}: {
  leaderboard: PodLeaderboardRow[] | undefined;
  events: PodEventSummary[] | undefined;
  compact?: boolean;
}) {
  return (
    <SectionHeading
      label="STANDINGS"
      count={leaderboard ? leaderboard.length : undefined}
      unit={(leaderboard?.length ?? 0) === 1 ? "PLAYER" : "PLAYERS"}
      compact={compact}
      meta={
        !compact ? undefined : leaderboard && events ? (
          <span className="inline-flex items-baseline gap-2.5">
            <span>
              <span className="tabular-nums text-subtle">{leaderboard.length}</span>{" "}
              {leaderboard.length === 1 ? "PLAYER" : "PLAYERS"}
            </span>
            <span>
              <span className="tabular-nums text-subtle">{events.length}</span>{" "}
              {events.length === 1 ? "EVENT" : "EVENTS"}
            </span>
          </span>
        ) : (
          <span className="inline-block h-2.5 w-28 bg-surface2 animate-pulse" />
        )
      }
    />
  );
}

function SectionHeading({
  label,
  count,
  unit,
  compact,
  meta,
}: {
  label: string;
  count?: number;
  unit?: string;
  compact?: boolean;
  meta?: React.ReactNode;
}) {
  if (compact) {
    return (
      <div className="flex items-baseline justify-between gap-3 py-2 pl-5 pr-3 border-b border-border">
        <span className="font-display text-text text-[14px] tracking-[0.16em] leading-none">
          {label}
        </span>
        {meta && (
          <span className="font-display text-[12px] tracking-[0.14em] leading-none text-muted">
            {meta}
          </span>
        )}
      </div>
    );
  }
  return (
    <div className="relative flex items-baseline justify-between py-4 pl-2 pr-5 border-b border-border gap-4">
      <span
        className="flex-1 basis-0 min-w-0 font-display text-text tracking-[0.18em] leading-none"
        style={{ fontSize: 17 }}
      >
        {label}
      </span>
      {/* Out of flow, so a meta taller than the label cannot grow the row and shift the label */}
      {meta ? (
        <div className="absolute inset-y-0 right-0 flex items-center">{meta}</div>
      ) : (
        <div className="flex-1 basis-0 min-w-0 flex justify-end">
          {!unit ? null : count === undefined ? (
            <span className="inline-block h-3.5 w-24 bg-surface2 animate-pulse" />
          ) : count === 0 ? null : (
            <span
              className="font-display tracking-[0.18em] leading-none flex items-baseline gap-1.5 whitespace-nowrap"
              style={{ fontSize: 17 }}
            >
              <span className="tabular-nums text-subtle">{count}</span>
              <span className="text-muted">{unit}</span>
            </span>
          )}
        </div>
      )}
    </div>
  );
}

// A row's collapse is the reader's decision, so it outlives the tab switch that unmounts the row
function useRowDisclosure(defaultOpenId: string | undefined) {
  const [decisions, setDecisions] = useState<Record<string, boolean>>({});
  const isOpen = (id: string) => decisions[id] ?? id === defaultOpenId;
  const toggle = (id: string) => setDecisions((d) => ({ ...d, [id]: !isOpen(id) }));
  return { isOpen, toggle };
}

function EventsBlock({ events, nowMs }: { events: PodEventSummary[]; nowMs: number }) {
  const disclosure = useRowDisclosure(events[0]?.eventId);
  return (
    <div>
      <SectionHeading
        label="EVENTS"
        count={events.length}
        unit={events.length === 1 ? "EVENT" : "EVENTS"}
      />
      <div className="flex flex-col lg:gap-2">
        {events.map((e, i) => (
          <EventRow
            key={e.eventId}
            event={e}
            index={i}
            nowMs={nowMs}
            open={disclosure.isOpen(e.eventId)}
            onToggle={() => disclosure.toggle(e.eventId)}
          />
        ))}
      </div>
    </div>
  );
}

function UpcomingBlock() {
  return (
    <div>
      <SectionHeading label="UPCOMING" meta={<SlotSchedule />} />
      <div className="flex flex-col lg:gap-2">
        <PodActionRow />
      </div>
    </div>
  );
}

function SlotSchedule() {
  return (
    <span className="flex items-center gap-3 whitespace-nowrap">
      <span
        className="flex items-center gap-2 font-display text-text tracking-[0.16em] leading-none"
        style={{ fontSize: 12 }}
      >
        <CalendarRange size={15} className="text-subtle -translate-y-[2px]" />
        EVERY DAY
      </span>
      {POD_SLOTS.map((slot) => (
        <span
          key={slot.label}
          className="flex items-baseline gap-2 border border-border2 bg-surface2/40 px-2.5 py-1.5"
        >
          <span className="font-display text-muted tracking-[0.14em] leading-none" style={{ fontSize: 11 }}>
            {slot.label}
          </span>
          <span
            className="font-display text-green tabular-nums tracking-[0.04em] leading-none"
            style={{ fontSize: 13 }}
          >
            {easternHourInLocalTime(slot.easternHour)}
          </span>
        </span>
      ))}
    </span>
  );
}

// Two equal halves, Discord join and the guide, split by a divider in one row. Pods run every day, so
// there is always something to sign up for even with no slot open
function PodActionRow() {
  const half =
    "flex flex-1 items-center justify-center gap-2.5 min-h-[46px] bg-green/10 no-underline text-green hover:bg-green/20 transition-colors font-display tracking-[0.14em] leading-none";
  return (
    <div className="flex items-stretch border-b border-border">
      <a href={SITE_LINKS.discordPods} target="_blank" rel="noreferrer" className={half} style={{ fontSize: 15 }}>
        <DiscordIcon size={18} />
        SIGN UP ON DISCORD
      </a>
      <Link to="/pods/guide" className={cn(half, "border-l border-green/30")} style={{ fontSize: 15 }}>
        <BookOpen size={16} strokeWidth={2} />
        HOW TO PLAY
        <ArrowRight size={14} />
      </Link>
    </div>
  );
}

// One event row's frame, shared by the expanding row, the mock link and the skeleton. A stacked row
// drops the date rail for a date stamp on the title line, so it runs shorter and indents further in.
const ROW_FRAME = "bg-surface border-b lg:border border-border first:lg:border-t-0 animate-fadeUpIn";

function rowDelayStyle(index: number): React.CSSProperties {
  return { animationDelay: `${Math.min(index, 6) * 45}ms` };
}

function rowHeightClass(stacked: boolean): string {
  return stacked ? "min-h-[44px]" : "min-h-[52px]";
}

function rowBodyClass(stacked: boolean): string {
  return cn(
    "flex-1 min-w-0 flex items-center",
    stacked ? "gap-2.5 py-2 pl-5 pr-2" : "gap-4 py-2.5 px-4",
  );
}

function RowTitle({ stacked, children }: { stacked: boolean; children: React.ReactNode }) {
  return (
    <span
      className="font-display text-text min-w-0 flex-1 truncate"
      style={{ fontSize: stacked ? 16 : 18, letterSpacing: "0.04em", lineHeight: 1.15 }}
    >
      {children}
    </span>
  );
}

function MockDraftsBlock({ events, stacked = false }: { events: PodEventSummary[]; stacked?: boolean }) {
  return (
    <div>
      <SectionHeading
        label="MOCK DRAFTS"
        count={events.length}
        unit={events.length === 1 ? "DRAFT" : "DRAFTS"}
        compact={stacked}
      />
      <div className="flex flex-col lg:gap-2">
        {events.map((e, i) => (
          <MockEventRow key={e.eventId} event={e} index={i} stacked={stacked} />
        ))}
      </div>
    </div>
  );
}

function MockEventRow({
  event,
  index,
  stacked = false,
}: {
  event: PodEventSummary;
  index: number;
  stacked?: boolean;
}) {
  return (
    <div className={cn(ROW_FRAME, "flex items-stretch")} style={rowDelayStyle(index)}>
      <Link
        to={`/pods/${event.slug}`}
        className={cn(
          "group flex-1 min-w-0 flex items-stretch no-underline hover:bg-surface2/30 transition-colors",
          rowHeightClass(stacked),
        )}
      >
        {!stacked && <DateRail date={event.eventDate} highlighted={false} />}
        <div className={rowBodyClass(stacked)}>
          <RowTitle stacked={stacked}>
            {highlightEventLabel(cleanPodEventName(event.name, event.setCode).toUpperCase())}
          </RowTitle>
          {stacked && <DateStamp event={event} />}
        </div>
        {stacked && (
          <div className="flex items-center pl-2 pr-3 shrink-0 self-center">
            <ArrowRight size={14} className="text-muted transition-colors group-hover:text-text" />
          </div>
        )}
      </Link>
      {!stacked && <EventDetailsLink slug={event.slug} />}
    </div>
  );
}

function EventRow({
  event,
  index,
  nowMs,
  stacked = false,
  open: openRequested = false,
  onToggle,
}: {
  event: PodEventSummary;
  index: number;
  nowMs: number;
  stacked?: boolean;
  open?: boolean;
  onToggle?: () => void;
}) {
  const open = openRequested && !!onToggle;
  const headerClass = cn(
    "group flex-1 min-w-0 flex items-stretch text-left bg-transparent border-0 no-underline transition-colors",
    rowHeightClass(stacked),
    onToggle ? "cursor-pointer" : "cursor-default",
    open ? "bg-surface2/40" : "hover:bg-surface2/30",
  );
  const headerContent = (
    <>
      {!stacked && <DateRail date={event.eventDate} highlighted={open} />}
      <EventRowBody event={event} nowMs={nowMs} stacked={stacked} />
      <div className="flex items-center pl-2 pr-2.5 shrink-0 self-center">
        <ChevronDown
          size={15}
          className={cn(
            "text-muted transition-all duration-200 group-hover:text-text",
            open && "rotate-180 text-text",
          )}
        />
      </div>
    </>
  );
  return (
    <div
      className={cn(ROW_FRAME, "transition-colors", open && "bg-surface2/40")}
      style={rowDelayStyle(index)}
    >
      <div className="flex items-stretch">
        {onToggle ? (
          <button type="button" onClick={onToggle} aria-expanded={open} className={headerClass}>
            {headerContent}
          </button>
        ) : (
          <Link to={`/pods/${event.slug}`} className={headerClass}>
            {headerContent}
          </Link>
        )}
        {!stacked && <EventDetailsLink slug={event.slug} />}
      </div>

      <div
        className={cn(
          "grid transition-[grid-template-rows] duration-200 ease-out",
          open ? "grid-rows-[1fr]" : "grid-rows-[0fr]",
        )}
        aria-hidden={!open}
      >
        <div className="overflow-hidden">
          {open && (
            <>
              <EventStandings event={event} />
              {stacked && <BreakdownFooterLink slug={event.slug} />}
            </>
          )}
        </div>
      </div>
    </div>
  );
}

// A team draft crowns no player, so the winning side stands in for a champion. A stacked row has no
// width for three seats, so it names the format and leaves the sides to the expansion.
function TeamDraftResult({ event, stacked }: { event: PodEventSummary; stacked: boolean }) {
  const { data: rows } = usePodEventParticipants(stacked ? undefined : event.eventId);
  const winner = useMemo(() => {
    const seated = (rows ?? []).filter((r): r is TeamSeat => r.seatIndex != null);
    if (seated.length === 0) return null;
    return teamSides(seated).find((side) => side.won) ?? null;
  }, [rows]);
  if (!winner) {
    return (
      <span
        className="shrink-0 font-display tracking-[0.16em] leading-none text-muted"
        style={{ fontSize: 13 }}
      >
        TEAM DRAFT
      </span>
    );
  }
  return (
    <div className="flex items-center gap-2.5 shrink-0 min-w-0">
      <Trophy size={15} color="#ffc63a" />
      {winner.members.map((m) => (
        <span key={m.displayName} className="flex items-center gap-1 shrink-0">
          <SeatAvatar
            name={podDiscordName(m)}
            avatarUrl={m.avatarUrl}
            size={stacked ? 20 : 22}
            teamSide={winner.team === "A" ? "A" : "B"}
          />
          {/* Mains only: three full colour strings with splashes would outrun the row, and the
              expansion right below carries each deck in full */}
          <Pips colors={colorsOf(m.deckColors)} size={12} />
        </span>
      ))}
    </div>
  );
}

// Expanding and opening the pod are different intents, so the row carries both. The events column
// is the narrow one, so the label lives in the tooltip and the row keeps its width for the identity
function EventDetailsLink({ slug }: { slug: string }) {
  return (
    <Tooltip label="View Pod Breakdown" side="top" align="end">
      <Link
        to={`/pods/${slug}`}
        aria-label="View pod breakdown"
        className="group/details flex shrink-0 items-center justify-center gap-1.5 self-stretch pl-4 pr-2.5 bg-bg
          border-l border-border text-subtle no-underline transition-colors
          hover:border-green/60 hover:bg-green/10 hover:text-green"
      >
        <GiRoundTable size={22} className="shrink-0" />
        <ArrowRight size={13} className="shrink-0 transition-transform group-hover/details:translate-x-0.5" />
      </Link>
    </Tooltip>
  );
}

// Nothing else on a phone reaches the pod page, since the row's own tap expands it in place
function BreakdownFooterLink({ slug }: { slug: string }) {
  return (
    <Link
      to={`/pods/${slug}`}
      className="group/footer relative flex items-center justify-center gap-2 px-10 min-h-[40px] bg-surface2/20
        border-t border-dashed border-border2 no-underline text-subtle hover:text-green hover:bg-green/10 transition-colors"
    >
      <GiRoundTable size={18} className="shrink-0" />
      <span className="font-display tracking-[0.14em] leading-none" style={{ fontSize: 12 }}>
        VIEW POD BREAKDOWN
      </span>
      <ArrowRight
        size={13}
        className="absolute right-3 shrink-0 transition-transform group-hover/footer:translate-x-0.5"
      />
    </Link>
  );
}

function DateRail({ date, highlighted }: { date: string; highlighted: boolean }) {
  const { month, day } = parseMonthDay(date);
  return (
    <div
      className={cn(
        "flex flex-col items-center justify-center border-r transition-colors px-2.5 min-w-[64px]",
        highlighted
          ? "bg-surface2 border-border2"
          : "bg-surface2/40 border-border group-hover:bg-surface2/70",
      )}
    >
      <span className="font-display text-muted leading-none tracking-[0.06em] text-[14px]">
        {month}
      </span>
      <span className="font-display text-text leading-none tabular-nums mt-1 text-[21px]">
        {String(day).padStart(2, "0")}
      </span>
    </div>
  );
}

// The stacked row drops the rail, so the date closes the line instead
function DateStamp({ event }: { event: PodEventSummary }) {
  const { month, day } = parseMonthDay(event.eventDate);
  return (
    <span
      className="font-display text-subtle tabular-nums leading-none tracking-[0.08em] shrink-0 ml-1.5"
      style={{ fontSize: 13 }}
    >
      {month} {String(day).padStart(2, "0")}
    </span>
  );
}

function EventRowBody({
  event,
  nowMs,
  stacked = false,
}: {
  event: PodEventSummary;
  nowMs: number;
  stacked?: boolean;
}) {
  const inProgress = !event.isFinalized && new Date(event.eventTime).getTime() <= nowMs;
  const { data: matches } = usePodEventMatches(inProgress ? event.eventId : undefined);
  const currentRound = useMemo(() => {
    if (!matches || matches.length === 0) return null;
    let earliestUnreported = null;
    let latest = 1;
    for (const m of matches) {
      if (m.round > latest) latest = m.round;
      if (m.reportedAt == null && (earliestUnreported == null || m.round < earliestUnreported)) {
        earliestUnreported = m.round;
      }
    }
    const round = earliestUnreported ?? latest;
    return Math.min(round, event.totalRounds);
  }, [matches, event.totalRounds]);
  const title = (
    <RowTitle stacked={stacked}>
      <PodEventTitle event={event} omitQualifier={event.isTeamDraft} />
    </RowTitle>
  );
  // A pod with no champion is a pod still running, so the row says nothing about being in progress
  const outcome = (
    <>
      {event.isTeamDraft && <TeamDraftResult event={event} stacked={stacked} />}
      {event.championDisplayName && <ChampionResult event={event} stacked={stacked} />}
      {inProgress && currentRound != null && <RoundLabel round={currentRound} stacked={stacked} />}
    </>
  );
  return (
    <div className={rowBodyClass(stacked)}>
      {title}
      {outcome}
      {stacked && <DateStamp event={event} />}
    </div>
  );
}

function ChampionResult({ event, stacked }: { event: PodEventSummary; stacked: boolean }) {
  return (
    <div
      className={cn(
        "flex items-center min-w-0 shrink",
        stacked ? "gap-1.5 max-w-[52%]" : "max-w-[60%] gap-2.5",
      )}
    >
      {/* The events column is 40% of the page, so below xl the title needs the avatar's width more */}
      {!stacked && (
        <span className="hidden xl:block">
          <AAvatar
            displayName={event.championDisplayName ?? ""}
            avatarUrl={event.championAvatarUrl}
            size={22}
          />
        </span>
      )}
      <span
        className="font-display text-text tracking-[0.04em] truncate"
        style={{ fontSize: stacked ? 14 : 16, lineHeight: 1 }}
      >
        {stripDiscriminator(event.championDisplayName ?? "").toUpperCase()}
      </span>
      {event.championDeckColors && (
        <span className="shrink-0 flex">
          <Pips
            colors={orderedDeckColors(event.championDeckColors)}
            size={deckPipSize(event.championDeckColors, stacked ? 12 : 13)}
          />
        </span>
      )}
      {/* Last, so it lands at the block's fixed right edge and the trophies line up down the column */}
      <Trophy size={stacked ? 14 : 15} color="#ffc63a" />
    </div>
  );
}

function RoundLabel({ round, stacked }: { round: number; stacked: boolean }) {
  return (
    <span
      className="shrink-0 font-display text-subtle tracking-[0.18em] leading-none"
      style={{ fontSize: stacked ? 11 : 12 }}
    >
      ROUND {round}
    </span>
  );
}

const STANDINGS_SKELETON_ROWS = 8;

function EventStandings({ event }: { event: PodEventSummary }) {
  const { data: rows, isLoading } = usePodEventParticipants(event.eventId);
  const [deckTarget, setDeckTarget] = useState<PodEventParticipantRow | null>(null);
  const { data: draftArtifact } = usePodDraftArtifact(event.eventId);
  const decklistAccess = usePodDecklistAccess(event);
  const deckTargetMainboard = useMemo(
    () =>
      draftArtifact && deckTarget?.seatIndex != null
        ? resolveDeck(draftArtifact, deckTarget.seatIndex)
        : null,
    [draftArtifact, deckTarget],
  );
  const sorted = useMemo(() => {
    if (!rows) return [];
    return [...rows].sort(compareStandings);
  }, [rows]);
  const cycleDeck = (direction: number) => {
    if (!deckTarget || sorted.length === 0) return;
    const index = sorted.indexOf(deckTarget);
    if (index === -1) return;
    for (let step = 1; step <= sorted.length; step++) {
      const next = sorted[(((index + direction * step) % sorted.length) + sorted.length) % sorted.length];
      if (decklistAccess.canViewSeat(next.avatarUrl)) {
        setDeckTarget(next);
        return;
      }
    }
  };
  return (
    <>
      <div className="border-t border-dashed border-border2">
        <div className="flex flex-col gap-[1px] pb-[1px] bg-bg">
          {isLoading
            ? Array.from({ length: STANDINGS_SKELETON_ROWS }).map((_, i) => (
                <PodStandingRowSkeleton key={i} cols={COMPACT_STANDING_COLS_CLASS} compact />
              ))
            : sorted.map((p, index) => (
                <PodStandingRow
                  key={`${p.eventId}-${p.displayName}`}
                  p={decklistAccess.canViewSeat(p.avatarUrl) ? p : { ...p, deckColors: null }}
                  rank={p.placement ?? index + 1}
                  cols={COMPACT_STANDING_COLS_CLASS}
                  compact
                  teamSide={event.isTeamDraft ? seatSide(p.seatIndex) : null}
                  nameHref={p.playerSlug ? playerPath(p.playerSlug, event.setCode) : null}
                  logHref={
                    draftArtifact && decklistAccess.canViewSeat(p.avatarUrl)
                      ? `/pods/${event.slug}/${p.playerSlug ?? p.seatIndex}`
                      : null
                  }
                  onShowDeck={
                    p.deckScreenshotUrl && decklistAccess.canViewSeat(p.avatarUrl)
                      ? () => setDeckTarget(p)
                      : undefined
                  }
                />
              ))}
        </div>
      </div>
      {deckTarget && (
        <DeckScreenshotModal
          participant={{
            eventId: deckTarget.eventId,
            displayName: podDiscordName(deckTarget),
            participantDisplayName: deckTarget.displayName,
            deckColors: deckTarget.deckColors,
            deckScreenshotUrl: deckTarget.deckScreenshotUrl,
            deckScreenshotCaption: deckTarget.deckScreenshotCaption,
            mainboard: deckTargetMainboard,
            record: deckTarget.record,
          }}
          draftLogHref={
            draftArtifact && decklistAccess.canViewSeat(deckTarget.avatarUrl)
              ? `/pods/${event.slug}/${deckTarget.playerSlug ?? deckTarget.seatIndex}`
              : null
          }
          breakdownHref={`/pods/${event.slug}?player=${encodeURIComponent(podDiscordName(deckTarget))}`}
          onClose={() => setDeckTarget(null)}
          onPrev={() => cycleDeck(-1)}
          onNext={() => cycleDeck(1)}
        />
      )}
    </>
  );
}

function EventRowSkeleton({ index, stacked = false }: { index: number; stacked?: boolean }) {
  return (
    <div
      className={cn(ROW_FRAME, "flex items-stretch", rowHeightClass(stacked))}
      style={rowDelayStyle(index)}
    >
      {!stacked && (
        <div className="px-3 min-w-[64px] bg-surface2/40 border-r border-border flex flex-col items-center justify-center gap-1.5">
          <div className="h-3.5 w-9 bg-surface2 animate-pulse" />
          <div className="h-4 w-7 bg-surface2 animate-pulse" />
        </div>
      )}
      <div className={rowBodyClass(stacked)}>
        <div className="h-4 w-1/2 bg-surface2 animate-pulse" />
        {stacked && <div className="h-3 w-12 bg-surface2 animate-pulse ml-auto" />}
      </div>
    </div>
  );
}

function EventsLoadingBlock() {
  return (
    <div>
      <SectionHeading label="EVENTS" unit="EVENTS" />
      <div className="flex flex-col lg:gap-2">
        {[0, 1, 2].map((i) => (
          <EventRowSkeleton key={i} index={i} />
        ))}
      </div>
    </div>
  );
}

type EventsTab = "upcoming" | "all";

// The tab strip and the launcher need no data, so a load only ever skeletons the rows under them
function MobileEventsBlock({
  played,
  loading,
  nowMs,
  activeSet,
}: {
  played: PodEventSummary[];
  loading: boolean;
  nowMs: number;
  activeSet: string;
}) {
  const [tab, setTab] = useState<EventsTab>("upcoming");
  const disclosure = useRowDisclosure(undefined);
  return (
    <div>
      <div className="flex border-b border-border">
        <EventsTabButton active={tab === "upcoming"} onClick={() => setTab("upcoming")}>
          UPCOMING
        </EventsTabButton>
        <EventsTabButton active={tab === "all"} onClick={() => setTab("all")}>
          PAST EVENTS
        </EventsTabButton>
      </div>
      {tab === "upcoming" ? (
        <>
          <PodActionRow />
          {(loading || played[0]) && <SectionHeading label="LAST EVENT" compact />}
          {loading ? (
            <EventRowSkeleton index={0} stacked />
          ) : (
            played[0] && (
              <EventRow
                event={played[0]}
                index={0}
                nowMs={nowMs}
                stacked
                open={disclosure.isOpen(played[0].eventId)}
                onToggle={() => disclosure.toggle(played[0].eventId)}
              />
            )
          )}
        </>
      ) : loading ? (
        <div className="flex flex-col">
          {[0, 1, 2, 3].map((i) => (
            <EventRowSkeleton key={i} index={i} stacked />
          ))}
        </div>
      ) : played.length === 0 ? (
        <EmptyHint>No pod drafts recorded yet for {activeSet}</EmptyHint>
      ) : (
        <div className="flex flex-col">
          {played.map((e, i) => (
            <EventRow
              key={e.eventId}
              event={e}
              index={i}
              nowMs={nowMs}
              stacked
              open={disclosure.isOpen(e.eventId)}
              onToggle={() => disclosure.toggle(e.eventId)}
            />
          ))}
        </div>
      )}
    </div>
  );
}

function EventsTabButton({
  active,
  onClick,
  children,
}: {
  active: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "flex-1 py-2 px-1.5 bg-transparent cursor-pointer font-display text-[14px] tracking-[0.16em] leading-none transition-colors border-b-2 border-solid inline-flex items-center justify-center gap-1.5",
        active ? "text-text border-green" : "text-muted border-transparent",
      )}
      style={active ? { marginBottom: -1 } : undefined}
    >
      {children}
    </button>
  );
}

function EmptyHint({ children }: { children: React.ReactNode }) {
  return (
    <div className="text-muted text-[13px] py-4 px-2 bg-surface border border-border">
      {children}
    </div>
  );
}

// One band holding both filters, so the set and the format never read as separate controls
function MobileFilterBar({
  activeSet,
  availableSets,
  onSelectSet,
  windowSelector,
}: {
  activeSet: string;
  availableSets: SetSummary[];
  onSelectSet: (code: string) => void;
  windowSelector?: React.ReactNode;
}) {
  const options = useMemo(() => setFilterOptionsFrom(availableSets, true), [availableSets]);
  // The set list is its own query, so hold the band's shape until it lands instead of pushing the
  // whole page down when it does
  if (options.length === 0) {
    return (
      <div className="px-3 py-2 border-b border-border bg-surface flex items-stretch gap-2">
        {[0, 1].map((i) => (
          <div key={i} className="basis-1/2 min-w-0 border border-border2 px-2.5 py-1.5">
            <div className="h-[21px] bg-surface2 animate-pulse" />
          </div>
        ))}
      </div>
    );
  }
  const second = windowSelector;
  return (
    <div className="px-3 py-2 border-b border-border bg-surface flex items-stretch gap-2">
      <div className={cn("min-w-0 flex", second ? "basis-1/2" : "flex-1")}>
        <SetFilterDropdown
          value={activeSet}
          options={options}
          onChange={onSelectSet}
          variant="mobile"
          searchable
          valueLabel="name"
        />
      </div>
      {second && <div className="basis-1/2 min-w-0 flex">{second}</div>}
    </div>
  );
}

function ChipIcon({
  bucket,
  seasonMeta,
  className,
  size = 16,
}: {
  bucket: PodFormatBucket;
  seasonMeta: SetSummary | undefined;
  className: string;
  size?: number;
}) {
  if (bucket === "mock") return <TbCards size={size} className={className} />;
  if (bucket === "set") {
    return seasonMeta ? <SetGlyph code={setGlyphCode(seasonMeta)} size={size} className={className} /> : null;
  }
  return <SetGlyph code={bucket === "cube" ? CUBE_BASE : "FLASHBACK"} size={size} className={className} />;
}

function SetHero({
  activeSet,
  setMeta,
  sets,
  onSelectSet,
  windowSelector,
  range,
  isSeason,
}: {
  activeSet: string;
  setMeta: SetSummary | undefined;
  sets: SetSummary[];
  onSelectSet: (code: string) => void;
  windowSelector?: React.ReactNode;
  range?: string | null;
  isSeason: boolean;
}) {
  const week = isSeason ? weekOfSet(setMeta) : null;
  const isActive = setMeta?.isActive ?? false;
  return (
    <div className="relative px-10 py-5 border-b border-border bg-surface flex items-center gap-6">
      <SetGlyph code={setMeta ? setGlyphCode(setMeta) : activeSet} size={84} />
      <div>
        <SectionLabel size={13} className={cn("text-green", !isActive && "invisible")}>LIVE</SectionLabel>
        <div className="flex items-baseline gap-3.5 mt-0.5">
          <span className="font-display tracking-[0.04em]" style={{ fontSize: 56, lineHeight: 0.9 }}>
            {activeSet}
          </span>
          <span className="font-display text-[22px] text-muted tracking-[0.06em]">
            {setMeta?.name?.toUpperCase() ?? ""}
          </span>
        </div>
        {windowSelector ? (
          // Same line the cube header uses: the range holds it at text height while the zero-height
          // wrapper lets the larger selector float over it, so the set code never moves
          <div className="mono text-[11px] text-muted mt-1 tracking-[0.04em] flex items-center gap-6 h-4">
            <div className="h-0 shrink-0 flex items-center">{windowSelector}</div>
            {/* Nudged onto the selector's baseline: the two sit in one line box at 11px and 20px, so
                box alignment leaves the smaller text riding high. Transform, so the hero keeps its height. */}
            <span className="whitespace-nowrap ml-auto self-end translate-y-[4px]">{range || " "}</span>
          </div>
        ) : (
          <div className="mono text-[11px] text-muted mt-1 flex items-center justify-between gap-4 h-4">
            <span>{range || " "}</span>
            {week && <span>{week}</span>}
          </div>
        )}
      </div>
      <div className="flex-1" />
      {sets.length > 0 && (
        <SetSwitcherDesktop sets={sets} activeCode={activeSet} onChange={onSelectSet} />
      )}
    </div>
  );
}
