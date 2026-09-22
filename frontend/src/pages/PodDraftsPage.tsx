import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link, Navigate, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { ArrowUpRight, BookOpen, ChevronDown } from "lucide-react";

import { PodPage } from "./PodPage";

import { AppHeader } from "../components/AppHeader";
import { Footer } from "../components/Footer";
import { SectionHeading } from "../components/SectionHeading";
import { SectionLabel } from "../components/SectionLabel";
import { TabButton } from "../components/TabButton";
import { SetSwitcherDesktop } from "../components/SetSwitcher";
import { type InlineFilterOption } from "../components/InlineFilterSelect";
import { FilterDropdown, type FilterOption } from "../components/FilterDropdown";
import { SetFilterDropdown, type SetFilterOption } from "../components/SetFilterDropdown";
import { AAvatar, setGlyphCode, SetGlyph, Trophy } from "../components/Brand";
import { ArrowRight, BsAsterisk, CalendarRange, GiCardPick, GiArcheryTarget, GiRoundTable, TbListNumbers } from "../components/Icons";
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
import { POD_SLOTS, easternHourInLocalTime, viewerTimeZoneAbbr } from "../lib/podSlots";
import { cubeCobraUrl } from "../data/podFormats";
import { cn } from "../lib/utils";
import {
  cleanPodEventName,
  colorsOf,
  CUBE_BASE,
  fmtRange,
  isCubeCode,
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
  usePodEventMatches,
  usePodEventParticipants,
  usePodCalendar,
  usePodSetCodes,
  useSets,
  useAllPodEvents,
  useAllPodResults,
} from "../data/hooks";
import {
  aggregatePodStandings,
  bucketOf,
  lifetimeBucketOf,
  inSeasonWindow,
  seasonsPlayed,
  currentSeason,
  podSeasons,
  podFormatBuckets,
  POD_FORMAT_BUCKETS,
  seasonForDate,
  type PodFormatBucket,
} from "../data/podSeasons";
import { resolveDeck } from "../data/draft-artifact";
import { usePodDecklistAccess } from "../data/podDecklistAccess";
import { hasCardData } from "../data/podCards";
import type {
  PodCalendarDayRow,
  PodCalendarEntry,
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
    startDate: p.firstEvent ?? "",
    endDate: "",
    isActive: false,
    custom,
    shortCode: custom && p.code.length > POD_CHIP_CODE_MAX ? CUBE_BASE : undefined,
  };
}

// A board that ran in one season has nothing to pick between, so it shows no season selector
const MIN_BOARD_SEASONS = 2;

// One format plus the "all" entry is the same board twice, so the format selector stays hidden
const MIN_BOARD_FORMATS = 2;

const AXIS_ALL = "all";
const AXIS_PARAM_FORMAT = "format";
const AXIS_PARAM_SEASON = "season";
const AXIS_PARAM_SET = "set";
const SCOPE_SET_PREFIX = "set:";

function formatBucketLabel(bucket: PodFormatBucket, season: SetSummary | undefined): string {
  if (bucket === "set") return season ? `${season.code} Only` : "Live Sets";
  if (bucket === "flashback") return "Flashbacks";
  return bucket === "cube" ? "Peasant Cube" : "Mock Drafts";
}

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
  // The whole pod history in two reads; every scope is derived from these client-side, so switching
  // season / board / format never fires another request
  const { data: allEvents } = useAllPodEvents(true);
  const { data: allResults } = useAllPodResults(true);

  useEffect(() => {
    window.scrollTo(0, 0);
  }, [setCode, seasonCode]);

  // A season lists once it holds a pod, inside its window or drafting its own set
  const seasons = useMemo<SetSummary[]>(() => {
    if (!allSets || !allEvents || !podSetCodes) return [];
    const played = new Set(podSetCodes.map((p) => p.code));
    for (const e of allEvents) {
      const season = seasonForDate(allSets, e.eventDate);
      if (season) played.add(season.code);
    }
    return podSeasons(allSets).filter((s) => played.has(s.code));
  }, [allSets, allEvents, podSetCodes]);

  const seasonAxis = searchParams.get(AXIS_PARAM_SEASON);
  // Every season at once, the one window a route cannot name
  const allSeasons = !setCode && seasonAxis === AXIS_ALL;
  const bySetCode =
    !setCode && !seasonCode && seasonAxis !== AXIS_ALL ? searchParams.get(AXIS_PARAM_SET) : null;

  const season = useMemo<SetSummary | undefined>(() => {
    if (setCode || allSeasons || bySetCode) return undefined;
    const wanted = seasonCode ?? (seasonAxis === AXIS_ALL ? null : seasonAxis);
    if (wanted) return seasons.find((s) => s.code === wanted) ?? podSeasons(allSets).find((s) => s.code === wanted);
    return currentSeason(allSets) ?? seasons[0];
  }, [setCode, allSeasons, bySetCode, seasonCode, seasonAxis, seasons, allSets]);

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

  const activeSet = season?.code ?? setCode ?? bySetCode ?? homeCode;
  const onSelectSet = (code: string) => {
    navigate(code === homeCode ? "/pods" : `/pods/${code}`);
  };

  const boardEvents = useMemo(
    () => (setCode ? allEvents?.filter((e) => e.setCode === setCode) : undefined),
    [setCode, allEvents],
  );

  // A season's candidates mirror the old windowed + own-set scan; the leaderboard narrows results by
  // event id, so scopeResults can stay the full set
  const scopeEvents = useMemo(() => {
    if (!allEvents) return undefined;
    if (allSeasons) return allEvents;
    if (bySetCode) return allEvents.filter((e) => e.setCode === bySetCode);
    if (setCode) return boardEvents;
    if (season) {
      return allEvents.filter(
        (e) => e.setCode === season.code || (e.kind !== "mock" && inSeasonWindow(season, e.eventDate)),
      );
    }
    return allEvents;
  }, [allEvents, allSeasons, bySetCode, setCode, boardEvents, season]);
  const scopeResults = allResults;

  // A set below the board threshold still resolves its name when opened directly by code
  const directPod = podSetCodes?.find((p) => p.code === activeSet);
  const setMeta =
    season ?? legacySets.find((s) => s.code === activeSet) ?? (directPod ? synthesizePodSet(directPod) : undefined);
  const boardSeasons = useMemo(() => seasonsPlayed(boardEvents, allSets), [boardEvents, allSets]);

  // A format board is already one format, so only a season board buckets. Across every season an
  // event is a set draft against the season it was played in, not against the one on screen.
  const bucketFor = useMemo(() => {
    if (setCode || bySetCode) return undefined;
    if (season) return (e: PodEventSummary) => bucketOf(e, season.code);
    return (e: PodEventSummary) => lifetimeBucketOf(e, allSets);
  }, [setCode, bySetCode, season, allSets]);

  const formatBuckets = useMemo(
    () => (bucketFor ? podFormatBuckets(scopeEvents, bucketFor) : []),
    [scopeEvents, bucketFor],
  );

  // Held until the events land, so a format the new season never played does not filter to nothing
  const requestedFormat = POD_FORMAT_BUCKETS.find((bucket) => bucket === searchParams.get(AXIS_PARAM_FORMAT));
  const format =
    !scopeEvents || formatBuckets.some((b) => b.key === requestedFormat) ? requestedFormat : undefined;

  const boardWindow = useMemo(
    () => (setCode ? boardSeasons.find(({ season: s }) => s.code === seasonAxis)?.season : undefined),
    [setCode, seasonAxis, boardSeasons],
  );

  const setAxisParam = (param: string, value: string | null) => {
    const next = new URLSearchParams(searchParams);
    if (value) next.set(param, value);
    else next.delete(param);
    setSearchParams(next);
  };

  // A format board keeps its window in the query; a season board is a route, so only "all" is a param
  const onSelectSeason = (value: string) => {
    if (setCode) {
      setAxisParam(AXIS_PARAM_SEASON, value === AXIS_ALL ? null : value);
      return;
    }
    const next = new URLSearchParams(searchParams);
    if (value === AXIS_ALL) {
      next.set(AXIS_PARAM_SEASON, AXIS_ALL);
      navigate({ pathname: "/pods", search: next.toString() });
      return;
    }
    next.delete(AXIS_PARAM_SEASON);
    navigate({ pathname: value === homeCode ? "/pods" : `/pods/${value}`, search: next.toString() });
  };

  const onSelectFormat = (value: string) => {
    setAxisParam(AXIS_PARAM_FORMAT, value === AXIS_ALL ? null : value);
  };

  const events = useMemo(() => {
    if (!scopeEvents) return undefined;
    if (setCode) {
      return boardWindow ? scopeEvents.filter((e) => inSeasonWindow(boardWindow, e.eventDate)) : scopeEvents;
    }
    // A format carries every pod it holds, so the set's own bucket reaches past the season it sits in
    if (format && bucketFor) return scopeEvents.filter((e) => bucketFor(e) === format);
    if (season) return scopeEvents.filter((e) => e.kind !== "mock" && inSeasonWindow(season, e.eventDate));
    return scopeEvents.filter((e) => e.kind !== "mock");
  }, [scopeEvents, setCode, boardWindow, format, bucketFor, season]);

  // Scoped by event id, since `event_time` is UTC and a late pod crosses a boundary its ET date does not
  const eventIds = useMemo(() => events && new Set(events.map((e) => e.eventId)), [events]);

  const leaderboard = useMemo(() => {
    if (!scopeResults || !eventIds) return undefined;
    return aggregatePodStandings(scopeResults.filter((r) => eventIds.has(r.eventId)));
  }, [scopeResults, eventIds]);

  // Held whole until the query lands: a switcher that grows from one chip to six reads as broken
  const switcherSets = useMemo(() => {
    if (!allEvents || !podSetCodes) return [];
    const seasonCodes = new Set(seasons.map((s) => s.code));
    return [...seasons, ...legacySets.filter((s) => !seasonCodes.has(s.code))];
  }, [allEvents, podSetCodes, seasons, legacySets]);

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

  const showingMocks = format === "mock";

  const showUpcoming = true;

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

  const liveSeason = currentSeason(allSets);
  const liveSeasonCode = liveSeason?.code;
  const iconSize = isMobile ? 16 : 18;

  const scopeOptions = useMemo<SetFilterOption[]>(() => {
    const all: SetFilterOption = {
      value: AXIS_ALL,
      label: "All Seasons",
      triggerLabel: "All Seasons",
      icon: <GiRoundTable size={20} className="text-white shrink-0" />,
    };
    const setRow = (s: SetSummary): SetFilterOption => ({
      value: `${SCOPE_SET_PREFIX}${s.code}`,
      label: s.name,
      triggerLabel: s.name,
      code: s.code,
      glyphCode: setGlyphCode(s),
      section: "By Set",
    });
    const recencyKey = (s: SetSummary) => (s.code === "PEASANT" ? "9999-99-99" : s.startDate || "");
    const bySetRows = [...switcherSets]
      .sort((a, b) => {
        const ak = recencyKey(a);
        const bk = recencyKey(b);
        return ak < bk ? 1 : ak > bk ? -1 : 0;
      })
      .map(setRow);
    if (setCode) {
      const windowRow = (s: SetSummary): SetFilterOption => {
        const label = `${s.code} Season`;
        return { value: s.code, label, triggerLabel: label, glyphCode: setGlyphCode(s) };
      };
      const windows = boardSeasons.length >= MIN_BOARD_SEASONS ? boardSeasons.map((b) => windowRow(b.season)) : [];
      return [all, ...windows, ...bySetRows];
    }
    const seasonRow = (s: SetSummary): SetFilterOption => {
      const label = `${s.code} Season`;
      const meta =
        s.code === liveSeasonCode ? (
          <span className="font-mono text-[10px] tracking-[0.18em] text-green shrink-0">LIVE</span>
        ) : undefined;
      return { value: s.code, label, triggerLabel: label, glyphCode: setGlyphCode(s), meta };
    };
    return [all, ...seasons.map(seasonRow), ...bySetRows];
  }, [setCode, boardSeasons, seasons, switcherSets, liveSeasonCode]);

  const routeToSet = (code: string) => {
    if (isCubeCode(code) || switcherSets.find((s) => s.code === code)?.custom) {
      onSelectSet(code);
      return;
    }
    navigate({ pathname: "/pods", search: `?${AXIS_PARAM_SET}=${code}` });
  };

  const onSelectScope = (value: string) => {
    if (value === AXIS_ALL) {
      onSelectSeason(AXIS_ALL);
      return;
    }
    if (value.startsWith(SCOPE_SET_PREFIX)) {
      routeToSet(value.slice(SCOPE_SET_PREFIX.length));
      return;
    }
    onSelectSet(value);
  };

  const onSelectBoardScope = (value: string) => {
    if (value.startsWith(SCOPE_SET_PREFIX)) {
      routeToSet(value.slice(SCOPE_SET_PREFIX.length));
      return;
    }
    onSelectSeason(value);
  };

  const formatOptions = useMemo<InlineFilterOption[]>(() => {
    if (!bucketFor || formatBuckets.length < MIN_BOARD_FORMATS) return [];
    return [
      {
        value: AXIS_ALL,
        label: "All Formats",
        icon: <BsAsterisk size={iconSize - 3} className="text-white shrink-0" />,
      },
      ...formatBuckets.map(({ key }) => ({
        value: key,
        label: formatBucketLabel(key, season),
        icon: (
          <ChipIcon
            bucket={key}
            seasonMeta={season ?? liveSeason}
            className="text-white shrink-0"
            size={iconSize}
          />
        ),
      })),
    ];
  }, [bucketFor, formatBuckets, season, liveSeason, iconSize]);

  const selectorVariant = isMobile ? "mobile" : "desktop";
  const renderScopeFormat = (option: FilterOption) => {
    const icon = formatOptions.find((o) => o.value === option.value)?.icon;
    return (
      <span className="flex items-center gap-2 min-w-0">
        <span className="flex justify-center shrink-0" style={{ width: iconSize }}>
          {icon}
        </span>
        <span className="truncate">{option.label}</span>
      </span>
    );
  };
  const scopeValue = setCode
    ? boardWindow?.code ?? AXIS_ALL
    : allSeasons
      ? AXIS_ALL
      : bySetCode
        ? `${SCOPE_SET_PREFIX}${bySetCode}`
        : activeSet;
  const scopeSelector = scopeOptions.length > 1 ? (
    <SetFilterDropdown
      value={scopeValue}
      options={scopeOptions}
      onChange={setCode ? onSelectBoardScope : onSelectScope}
      variant={selectorVariant}
      triggerClassName={isMobile ? undefined : "!min-w-0"}
      searchable
    />
  ) : null;
  const formatSelector = formatOptions.length > 0 ? (
    <FilterDropdown
      value={format ?? AXIS_ALL}
      options={formatOptions}
      onChange={onSelectFormat}
      variant={selectorVariant}
      triggerClassName={isMobile ? undefined : "!min-w-0"}
      renderValue={renderScopeFormat}
      renderOption={renderScopeFormat}
    />
  ) : null;

  const cardDataHref = hasCardData(activeSet) ? `/pods/${activeSet}/data` : null;
  const cubeCobraHref = !allSeasons && !bySetCode ? cubeCobraUrl(activeSet) : null;

  // Under a cube filter each row already carries its own cube board code, so a name lands on that profile
  const profileSetFor = (row: LeaderboardTableRow) => {
    if (format === "cube") return row.setCode;
    return allSeasons ? homeCode : activeSet;
  };

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
            scopeSelector={scopeSelector}
            formatSelector={formatSelector}
            cardDataLink={cardDataHref ? <CardDataLink href={cardDataHref} variant="mobile" /> : undefined}
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
            allSeasons={allSeasons}
            bySet={!!bySetCode}
          />
        </>
      )}

      <main className="flex-1 lg:pl-5 lg:pr-8 lg:pb-10">
        <div className="grid grid-cols-1 lg:grid-cols-[3fr_2fr] gap-x-6 lg:gap-y-8">
          <section className="order-1 lg:order-2 min-w-0 flex flex-col">
            {showingMocks ? (
              <MockDraftsBlock events={mock} stacked={isMobile} />
            ) : isMobile ? (
              <MobileEventsBlock
                played={played}
                loading={events === undefined}
                nowMs={nowMs}
                activeSet={activeSet}
                cubeCobraHref={cubeCobraHref}
              />
            ) : (
              <>
                {showUpcoming && <UpcomingBlock />}
                {events === undefined ? (
                  <EventsLoadingBlock />
                ) : played.length > 0 ? (
                  <EventsBlock events={played} nowMs={nowMs} />
                ) : (
                  <div>
                    <SectionHeading label="EVENTS" count={0} unit="EVENTS" />
                    <EmptyHint>
                      {allSeasons ? "No pod drafts recorded yet" : `No pod drafts recorded yet for ${activeSet}`}
                    </EmptyHint>
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
              <StandingsHeading
                leaderboard={leaderboard}
                events={events}
                center={cardDataHref ? <CardDataLink href={cardDataHref} variant="center" /> : undefined}
                controls={
                  <div className="flex items-center gap-3 ml-4">
                    {scopeSelector}
                    {formatSelector}
                  </div>
                }
              />
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
              emptyMessage={allSeasons ? "No player stats yet." : `No player stats yet for ${activeSet}.`}
              playerHref={(row) => playerPath(row.slug, profileSetFor(row))}
            />
          </section>

          {isMobile && !showingMocks && mock.length > 0 && (
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
  controls,
  center,
  compact = false,
}: {
  leaderboard: PodLeaderboardRow[] | undefined;
  events: PodEventSummary[] | undefined;
  controls?: React.ReactNode;
  center?: React.ReactNode;
  compact?: boolean;
}) {
  return (
    <SectionHeading
      label="STANDINGS"
      count={leaderboard ? leaderboard.length : undefined}
      unit={(leaderboard?.length ?? 0) === 1 ? "PLAYER" : "PLAYERS"}
      controls={controls}
      center={center}
      compact={compact}
      padLeftClass="pl-5"
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


// A row's collapse is the reader's decision, so it outlives the tab switch that unmounts the row
function useRowDisclosure(defaultOpenId: string | undefined) {
  const [decisions, setDecisions] = useState<Record<string, boolean>>({});
  const isOpen = (id: string) => decisions[id] ?? id === defaultOpenId;
  const toggle = (id: string) => setDecisions((d) => ({ ...d, [id]: !isOpen(id) }));
  return { isOpen, toggle };
}

// Big pod lists render in batches, revealing more as a sentinel scrolls into view, so a busy season paints
// its first rows fast instead of mounting every EventRow at once
const EVENTS_INITIAL = 20;
const EVENTS_BATCH = 20;

function useIncrementalReveal(total: number) {
  const [count, setCount] = useState(EVENTS_INITIAL);
  const observerRef = useRef<IntersectionObserver | null>(null);
  useEffect(() => setCount(EVENTS_INITIAL), [total]);
  // Callback ref so the observer attaches whenever the sentinel mounts, including a tab switch that mounts
  // the list after the first render
  const sentinelRef = useCallback(
    (node: HTMLDivElement | null) => {
      observerRef.current?.disconnect();
      if (!node) return;
      observerRef.current = new IntersectionObserver(
        (entries) => {
          if (entries[0].isIntersecting) setCount((c) => Math.min(c + EVENTS_BATCH, total));
        },
        { rootMargin: "600px" },
      );
      observerRef.current.observe(node);
    },
    [total],
  );
  return { count, sentinelRef };
}

function EventsBlock({ events, nowMs }: { events: PodEventSummary[]; nowMs: number }) {
  const disclosure = useRowDisclosure(events[0]?.eventId);
  const { count, sentinelRef } = useIncrementalReveal(events.length);
  return (
    <div>
      <SectionHeading
        label="EVENTS"
        count={events.length}
        unit={events.length === 1 ? "EVENT" : "EVENTS"}
      />
      <div className="flex flex-col lg:gap-2">
        {events.slice(0, count).map((e, i) => (
          <EventRow
            key={e.eventId}
            event={e}
            index={i}
            nowMs={nowMs}
            open={disclosure.isOpen(e.eventId)}
            onToggle={() => disclosure.toggle(e.eventId)}
          />
        ))}
        {count < events.length && <div ref={sentinelRef} className="h-1" aria-hidden />}
      </div>
    </div>
  );
}

// The labelled grid needs room; below this the column is too narrow, so cells fall back to glyphs alone
const CALENDAR_LABEL_WIDTH = 1400;

function UpcomingBlock() {
  const iconsOnly = useIsMobile(CALENDAR_LABEL_WIDTH);
  return (
    <div>
      <SectionHeading label="UPCOMING" meta={<SlotSchedule />} />
      <div className="flex flex-col lg:gap-2">
        <PodActionRow />
        <UpcomingCalendar iconsOnly={iconsOnly} />
      </div>
    </div>
  );
}

const CALENDAR_WEEKDAYS = ["MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN"];

// The pod format calendar, weeks Mon-Sun through the week of the next rotation, resolved by the bot to
// match the Discord card. Today is outlined, a new set's arrival and the championship each fill their band.
// Mobile drops the codes to glyphs alone, where a labelled grid has no room.
const CALENDAR_COLLAPSED_WEEKS = 2;

function UpcomingCalendar({ iconsOnly = false, mobile = false }: { iconsOnly?: boolean; mobile?: boolean }) {
  const { data: rows } = usePodCalendar();
  const weeks = useMemo(() => chunkWeeks(rows), [rows]);
  const [expanded, setExpanded] = useState(false);
  if (weeks.length === 0) {
    return null;
  }
  const todayIso = new Date().toISOString().slice(0, 10);
  const todayColumn = (new Date().getDay() + 6) % 7;
  const canToggle = weeks.length > CALENDAR_COLLAPSED_WEEKS;
  const shown = expanded ? weeks : weeks.slice(0, CALENDAR_COLLAPSED_WEEKS);
  return (
    <div className="relative bg-surface border-b border-border px-3 pt-2 pb-3 lg:px-4 lg:pt-2.5 lg:pb-5">
      <div className="grid grid-cols-7 gap-1 mb-1">
        {CALENDAR_WEEKDAYS.map((name, i) => (
          <div
            key={name}
            className={cn(
              "text-center font-display tracking-[0.12em] leading-none text-[12px]",
              i === todayColumn ? "text-green" : "text-muted",
            )}
          >
            {name}
          </div>
        ))}
      </div>
      <div className="flex flex-col gap-1">
        {shown.map((week) => (
          <div key={week[0].day} className="grid grid-cols-7 gap-1">
            {week.map((day) => (
              <CalendarCell
                key={day.day}
                day={day}
                today={day.day === todayIso}
                past={day.day < todayIso}
                iconsOnly={iconsOnly}
              />
            ))}
          </div>
        ))}
      </div>
      {canToggle && (
        <Tooltip label={expanded ? "Collapse Calendar" : "Expand Calendar"} side="top" delayDuration={ROW_TOOLTIP_DELAY}>
          <button
            type="button"
            onClick={() => setExpanded((v) => !v)}
            aria-label={expanded ? "Collapse calendar" : "Expand calendar"}
            className={cn(
              "group absolute inset-x-0 bottom-0 flex items-end justify-center text-muted hover:text-green transition-colors",
              mobile ? "translate-y-1.5" : "translate-y-1",
            )}
          >
            <ChevronDown
              size={18}
              className={cn("transition-transform group-hover:translate-y-0.5", expanded && "rotate-180 group-hover:-translate-y-0.5")}
            />
          </button>
        </Tooltip>
      )}
    </div>
  );
}

function chunkWeeks(rows: PodCalendarDayRow[] | undefined): PodCalendarDayRow[][] {
  if (!rows) {
    return [];
  }
  const weeks: PodCalendarDayRow[][] = [];
  for (let i = 0; i < rows.length; i += 7) {
    weeks.push(rows.slice(i, i + 7));
  }
  return weeks;
}

const BAND_CLASS: Record<string, string> = {
  arrival: "bg-green/20 text-green",
  championship: "bg-gold/20 text-gold",
};

function CalendarCell({
  day,
  today,
  past,
  iconsOnly,
}: {
  day: PodCalendarDayRow;
  today: boolean;
  past: boolean;
  iconsOnly: boolean;
}) {
  const { month, day: dayNum } = parseMonthDay(day.day);
  const label = dayNum === 1 ? `${month} 1` : String(dayNum);
  const band = day.band ? BAND_CLASS[day.band] : past ? "bg-surface2/30 text-dim" : "bg-surface2/60 text-text";
  return (
    <div
      className={cn(
        "flex flex-col bg-bg border",
        iconsOnly ? "min-h-[58px]" : "min-h-[76px]",
        today ? "border-green" : "border-border",
      )}
    >
      <div
        className={cn(
          "text-center font-display tabular-nums tracking-[0.04em] leading-none py-1",
          iconsOnly ? "text-[13px]" : "text-[15px]",
          band,
        )}
      >
        {label}
      </div>
      <div className="flex-1 flex flex-col items-center justify-evenly px-1 py-0.5">
        {day.entries.map((entry, i) => (
          <CalendarEntryRow key={`${entry.label}-${i}`} entry={entry} past={past} iconsOnly={iconsOnly} />
        ))}
      </div>
    </div>
  );
}

const ROLE_CLASS: Record<PodCalendarEntry["role"], string> = {
  latest: "text-text",
  cube: "text-text",
  flashback: "text-blue",
  arrival: "text-green",
  championship: "text-gold",
};

function CalendarEntryRow({
  entry,
  past,
  iconsOnly,
}: {
  entry: PodCalendarEntry;
  past: boolean;
  iconsOnly: boolean;
}) {
  const glyph =
    entry.glyph === "FLASHBACK" ? "FLASHBACK" : setGlyphCode({ code: entry.glyph, custom: !!cubeCobraUrl(entry.glyph) });
  const glyphColor = past
    ? "text-dim"
    : entry.role === "championship"
      ? "text-gold"
      : entry.role === "flashback"
        ? "text-blue"
        : "text-white";
  return (
    <span className={cn("flex items-center gap-1.5 min-w-0 max-w-full", past && "opacity-60")}>
      <SetGlyph code={glyph} size={iconsOnly ? 26 : 22} className={cn("shrink-0", glyphColor)} />
      {!iconsOnly && (
        <span
          className={cn(
            "font-display tracking-[0.02em] leading-none text-[15px] truncate",
            past ? "text-dim" : ROLE_CLASS[entry.role],
          )}
        >
          {entry.label}
        </span>
      )}
    </span>
  );
}

function SlotSchedule() {
  const tz = viewerTimeZoneAbbr();
  return (
    <span className="flex items-center gap-3 whitespace-nowrap">
      <span
        className="flex items-center gap-2 font-display text-text tracking-[0.16em] leading-none"
        style={{ fontSize: 12 }}
      >
        <CalendarRange size={15} className="text-subtle" />
        EVERY DAY
      </span>
      {POD_SLOTS.map((slot) => (
        <span
          key={slot.label}
          className="flex items-baseline gap-2 border border-border2 bg-surface2/40 px-2.5 py-1.5"
        >
          <span className="font-display text-text tracking-[0.14em] leading-none" style={{ fontSize: 13 }}>
            {slot.label}
          </span>
          <span
            className="font-display text-green tabular-nums tracking-[0.04em] leading-none"
            style={{ fontSize: 13 }}
          >
            {easternHourInLocalTime(slot.easternHour)}
          </span>
          {tz && (
            <span className="font-display text-subtle tracking-[0.08em] leading-none" style={{ fontSize: 13 }}>
              {tz}
            </span>
          )}
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

const ROW_TOOLTIP_DELAY = 500;

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

// Leads every pod row so the format reads at a glance, hugging the title next to it
function PodSetTitle({
  event,
  stacked,
  children,
}: { event: PodEventSummary; stacked: boolean; children: React.ReactNode }) {
  const code = setGlyphCode({ code: event.setCode, custom: event.formatLabel != null });
  return (
    <span className={cn("flex items-center min-w-0 flex-1", stacked ? "gap-2" : "gap-2.5")}>
      <SetGlyph code={code} size={stacked ? 18 : 22} className="text-white shrink-0" />
      {children}
    </span>
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
          <PodSetTitle event={event} stacked={stacked}>
            <RowTitle stacked={stacked}>
              {highlightEventLabel(cleanPodEventName(event.name, event.setCode).toUpperCase())}
            </RowTitle>
          </PodSetTitle>
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
  const [titleHovered, setTitleHovered] = useState(false);
  const titleLinkTo = onToggle && !stacked ? `/pods/${event.slug}` : null;
  const headerClass = cn(
    "group flex-1 min-w-0 flex items-stretch text-left bg-transparent border-0 no-underline transition-colors",
    rowHeightClass(stacked),
    onToggle ? "cursor-pointer" : "cursor-default",
    open ? "bg-surface2/40" : "hover:bg-surface2/30",
  );
  const headerContent = (
    <>
      {!stacked && <DateRail date={event.eventDate} highlighted={open} />}
      <EventRowBody
        event={event}
        nowMs={nowMs}
        stacked={stacked}
        titleLinkTo={titleLinkTo}
        onTitleHover={setTitleHovered}
      />
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
          <div className={cn(headerClass, "relative")}>
            <Tooltip
              label={open ? "Hide Standings" : "Show Standings"}
              side="top"
              delayDuration={ROW_TOOLTIP_DELAY}
            >
              <button
                type="button"
                onClick={onToggle}
                aria-expanded={open}
                aria-label={open ? "Hide standings" : "Show standings"}
                className="absolute inset-0 bg-transparent border-0 cursor-pointer"
              />
            </Tooltip>
            <div className="relative flex-1 min-w-0 flex items-stretch pointer-events-none">
              {headerContent}
            </div>
          </div>
        ) : (
          <Link to={`/pods/${event.slug}`} className={headerClass}>
            {headerContent}
          </Link>
        )}
        {!stacked && <EventDetailsLink slug={event.slug} highlighted={titleHovered} />}
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
function EventDetailsLink({ slug, highlighted = false }: { slug: string; highlighted?: boolean }) {
  return (
    <Tooltip label="View Pod Breakdown" side="top" align="end" delayDuration={ROW_TOOLTIP_DELAY}>
      <Link
        to={`/pods/${slug}`}
        aria-label="View pod breakdown"
        className={cn(
          `group/details flex shrink-0 items-center justify-center gap-1.5 self-stretch pl-4 pr-2.5 bg-bg
            border-l border-border text-subtle no-underline transition-colors
            hover:border-green/60 hover:bg-green/10 hover:text-green`,
          highlighted && "border-green/60 bg-green/10 text-green",
        )}
      >
        <GiRoundTable size={22} className="shrink-0" />
        <ArrowRight
          size={13}
          className={cn(
            "shrink-0 transition-transform group-hover/details:translate-x-0.5",
            highlighted && "translate-x-0.5",
          )}
        />
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
  titleLinkTo = null,
  onTitleHover,
}: {
  event: PodEventSummary;
  nowMs: number;
  stacked?: boolean;
  titleLinkTo?: string | null;
  onTitleHover?: (hovered: boolean) => void;
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
  const titleText = <PodEventTitle event={event} />;
  const title = (
    <RowTitle stacked={stacked}>
      {titleLinkTo ? (
        <Tooltip label="View Pod Breakdown" side="top" align="start" delayDuration={ROW_TOOLTIP_DELAY}>
          <Link
            to={titleLinkTo}
            onMouseEnter={() => onTitleHover?.(true)}
            onMouseLeave={() => onTitleHover?.(false)}
            onFocus={() => onTitleHover?.(true)}
            onBlur={() => onTitleHover?.(false)}
            className="pointer-events-auto no-underline text-inherit transition-colors hover:text-green"
          >
            {titleText}
          </Link>
        </Tooltip>
      ) : (
        titleText
      )}
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
      <PodSetTitle event={event} stacked={stacked}>
        {title}
      </PodSetTitle>
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
  cubeCobraHref,
}: {
  played: PodEventSummary[];
  loading: boolean;
  nowMs: number;
  activeSet: string;
  cubeCobraHref: string | null;
}) {
  const [tab, setTab] = useState<EventsTab>("upcoming");
  const disclosure = useRowDisclosure(undefined);
  const { count, sentinelRef } = useIncrementalReveal(played.length);
  return (
    <div>
      <div className="flex border-b border-border">
        <TabButton active={tab === "upcoming"} onClick={() => setTab("upcoming")}>
          UPCOMING
        </TabButton>
        <TabButton active={tab === "all"} onClick={() => setTab("all")}>
          PAST EVENTS
        </TabButton>
      </div>
      {tab === "upcoming" ? (
        <>
          <PodActionRow />
          <div className="px-3 py-2.5 border-b border-border bg-surface flex justify-center">
            <SlotSchedule />
          </div>
          <UpcomingCalendar iconsOnly mobile />
          {(loading || played[0]) && (
            <SectionHeading
              label="LAST EVENT"
              compact
              meta={cubeCobraHref ? <CubeListLink href={cubeCobraHref} /> : undefined}
            />
          )}
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
          {played.slice(0, count).map((e, i) => (
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
          {count < played.length && <div ref={sentinelRef} className="h-1" aria-hidden />}
        </div>
      )}
    </div>
  );
}

function EmptyHint({ children }: { children: React.ReactNode }) {
  return (
    <div className="text-muted text-[13px] py-4 px-2 bg-surface border border-border">
      {children}
    </div>
  );
}

function MobileFilterBar({
  scopeSelector,
  formatSelector,
  cardDataLink,
}: {
  scopeSelector?: React.ReactNode;
  formatSelector?: React.ReactNode;
  cardDataLink?: React.ReactNode;
}) {
  if (!scopeSelector) {
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
  return (
    <div className="px-3 py-2 border-b border-border bg-surface flex items-stretch gap-2">
      <div className="flex-1 min-w-0 flex">{scopeSelector}</div>
      {formatSelector && <div className="flex-1 min-w-0 flex">{formatSelector}</div>}
      {cardDataLink && <div className="flex-1 min-w-0 flex">{cardDataLink}</div>}
    </div>
  );
}

// Compact CubeCobra link for the mobile LAST EVENT heading, where the hero label link has no home
function CubeListLink({ href }: { href: string }) {
  return (
    <a
      href={href}
      target="_blank"
      rel="noreferrer"
      className="inline-flex items-center gap-1.5 no-underline text-green transition-colors hover:text-green/70 font-display text-[12px] tracking-[0.14em] leading-none"
    >
      VIEW CUBECOBRA LIST
      <ArrowUpRight size={14} className="shrink-0" />
    </a>
  );
}

function CardDataLink({ href, variant }: { href: string; variant: "center" | "mobile" }) {
  if (variant === "mobile") {
    return (
      <Link
        to={href}
        className="w-full flex items-center justify-center gap-2 border border-green/40 text-green transition-colors hover:bg-green/10 no-underline font-display text-[13px] tracking-[0.14em] leading-none"
      >
        <TbListNumbers size={16} />
        VIEW CARD DATA
        <ArrowRight size={14} className="shrink-0" />
      </Link>
    );
  }
  return (
    <Link
      to={href}
      className="group inline-flex items-center gap-2 font-display text-[15px] tracking-[0.14em] leading-none text-subtle transition-colors hover:text-green"
    >
      VIEW CARD DATA
      <ArrowRight size={14} className="shrink-0 transition-transform group-hover:translate-x-0.5" />
    </Link>
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
  if (bucket === "mock") return <GiArcheryTarget size={Math.round(size * 1.15)} className={className} />;
  if (bucket === "set") {
    if (!seasonMeta) return <GiCardPick size={size} className={className} />;
    return <SetGlyph code={setGlyphCode(seasonMeta)} size={size} className={className} />;
  }
  if (bucket === "flashback") {
    return <SetGlyph code="FLASHBACK" size={Math.round(size * 1.22)} className={className} />;
  }
  return <SetGlyph code={CUBE_BASE} size={size} className={className} />;
}

function SetHero({
  activeSet,
  setMeta,
  sets,
  onSelectSet,
  range,
  isSeason,
  allSeasons,
  bySet,
}: {
  activeSet: string;
  setMeta: SetSummary | undefined;
  sets: SetSummary[];
  onSelectSet: (code: string) => void;
  range?: string | null;
  isSeason: boolean;
  allSeasons: boolean;
  bySet: boolean;
}) {
  const week = isSeason && !allSeasons ? weekOfSet(setMeta) : null;
  const isActive = !allSeasons && !bySet && (setMeta?.isActive ?? false);
  return (
    <div className="relative px-10 py-5 border-b border-border bg-surface flex items-center gap-6">
      {allSeasons ? (
        <GiRoundTable size={84} className="text-text" />
      ) : (
        <SetGlyph code={setMeta ? setGlyphCode(setMeta) : activeSet} size={84} />
      )}
      <div>
        <SectionLabel size={13} className={cn("text-green", !isActive && "invisible")}>LIVE</SectionLabel>
        <div className="flex items-baseline gap-3.5 mt-0.5">
          <span className="font-display tracking-[0.04em]" style={{ fontSize: 56, lineHeight: 0.9 }}>
            {allSeasons ? "POD DRAFTS" : activeSet}
          </span>
          <HeroFormatLabel
            label={allSeasons ? "ALL SEASONS" : (setMeta?.name?.toUpperCase() ?? "")}
            cubeHref={!allSeasons && !bySet ? cubeCobraUrl(activeSet) : null}
          />
        </div>
        <div className="font-mono text-[11px] text-muted mt-1 flex items-center justify-between gap-4 h-4">
          {!allSeasons && !bySet && (
            <>
              <span>{range || " "}</span>
              {week && <span>{week}</span>}
            </>
          )}
        </div>
      </div>
      <div className="flex-1" />
      {sets.length > 0 && (
        <SetSwitcherDesktop
          sets={sets}
          activeCode={allSeasons || bySet ? "" : activeSet}
          onChange={onSelectSet}
        />
      )}
    </div>
  );
}

// The format name beside the hero title. On a cube board it opens the CubeCobra card list, hovering green
// with an external-link mark; on a set board it stays plain text.
function HeroFormatLabel({ label, cubeHref }: { label: string; cubeHref: string | null }) {
  const className = "font-display text-[22px] text-muted tracking-[0.06em]";
  if (!cubeHref) {
    return <span className={className}>{label}</span>;
  }
  return (
    <Tooltip label="View in CubeCobra" side="top" delayDuration={ROW_TOOLTIP_DELAY}>
      <a
        href={cubeHref}
        target="_blank"
        rel="noreferrer"
        className={cn(className, "group inline-flex items-center gap-1 no-underline transition-colors hover:text-green")}
      >
        {label}
        <ArrowUpRight size={18} className="shrink-0 transition-transform group-hover:translate-x-0.5 group-hover:-translate-y-0.5" />
      </a>
    </Tooltip>
  );
}
