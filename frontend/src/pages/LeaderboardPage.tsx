import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import React, { Fragment, useEffect, useMemo, useRef, useState } from "react";

import { AppHeader } from "../components/AppHeader";
import { useIsMobile } from "../lib/use-is-mobile";
import { SetGlyph, setGlyphCode, Trophy } from "../components/Brand";
import {
  ArrowRight,
  BsAsterisk,
  BsPaletteFill,
  ExternalLink,
} from "../components/Icons";
import { Footer } from "../components/Footer";
import { Pip, Pips } from "../components/ManaPips";
import { SetSwitcherDesktop, SetSwitcherMobile } from "../components/SetSwitcher";
import { TrophyLeaderboard } from "../components/TrophyLeaderboard";
import { MtgoSidebar } from "../components/MtgoSidebar";
import { FilterDropdown } from "../components/FilterDropdown";
import { SetFilterDropdown, setFilterOptionsFrom, type SetFilterOption } from "../components/SetFilterDropdown";
import { ColorsSwitcher } from "../components/ColorsSwitcher";
import { LeaderboardSidebar, LeaderboardInsightsStrip } from "../components/LeaderboardSidebar";
import { boardModeFor, DEFAULT_SORT, DEFAULT_SORT_NOSCORE, defaultSortFor, LeaderboardColumnHeader, LeaderboardTable, sortRows } from "../components/LeaderboardTable";
import type { SortDir, SortKey, SortState } from "../components/LeaderboardTable";
import { SectionLabel } from "../components/SectionLabel";
import { ChamferedButton } from "../components/ChamferedButton";
import { Record } from "../components/Record";
import { DonutChart } from "../components/DonutChart";
import { TrophyCount } from "../components/TrophyCount";
import { ArenaChampBadge, isArenaChampionshipFormat } from "../components/ArenaChampBadge";

import {
  useAvailableFormats,
  useColorChips,
  useColorsLeaderboard,
  useDraftEvents,
  useFormatColorsLeaderboard,
  useFormatLeaderboard,
  useLeaderboard,
  useOtherColorsLeaderboard,
  usePlayerProfile,
  usePlayerSlugByDiscordId,
  usePrefetchers,
  useSets,
  useCubeSeasons,
  useTrophyLeaderboard,
} from "../data/hooks";
import { isMtgoFlashbackCode, mtgoSetName, withMtgoSets, MTGO_BLOCK_GLYPHS } from "../data/mtgoSets";
import { useAuth } from "../auth/useAuth";
import { baseSetCode, canonicalSetCode, colorsOf, CUBE_BASE, CUBE_LIFETIME, cubeSeasonLabel, eventDate, fmtRange, fmtShortDate, isCubeCode, isCubeSeasonCode, isSoup, lastUpdated, leaderboardPath, playerPath, profileSearch, prettyFormat, relativeTime, sumEvents, weekOfSet, winPct } from "../data/utils";
import {
  cubeBoardCode, cubeBoardGlyphCode, cubeForBoard, isCubeBoardLive, ongoingCubeBoard,
  latestWindowFor, SEASONED_CUBE_VARIANT, setsWithCubeBoards,
} from "../data/cubeVariants";
import { CubeSeasonSelector, cubeBoardHasSeasons } from "../components/CubeSeasonSelector";
import { colorsDisplayName, FORMAT_LABEL_GROUPS, FORMAT_OPTIONS, matchesFormatFilter, MULTI, OTHER } from "../data/filters";
import { FMT_COLORS, FMT_DEFAULT_COLOR, renderFormatOption, shortFormat } from "../data/format-display";
import { guildLogoTransform, guildSvgUrl } from "../data/guild-art";
import { ACTIVE_SET_CODE } from "../data/constants";
import { cn } from "../lib/utils";
import type { CubeSeason, LeaderboardRow, PlayerDraftEvent, PlayerFormatBreakdown, SetSummary, TrophyLeaderboardRow } from "../types/leaderboard";
import type { LeaderboardTableRow } from "../components/LeaderboardTable";

// ─── Page entry ────────────────────────────────────────────────────────────

export function LeaderboardPage() {
  const params = useParams<{ setCode?: string }>();
  const isMobile = useIsMobile();
  const navigate = useNavigate();
  const { data: sets } = useSets();
  const liveSetCode = sets?.find((s) => s.isActive)?.code;
  const requestedSet = params.setCode ? canonicalSetCode(params.setCode, sets) : undefined;
  const routeSet = requestedSet ?? liveSetCode ?? ACTIVE_SET_CODE;
  const { data: cubeSeasons } = useCubeSeasons();
  // Bare CUBE is not a board of its own: it opens whichever cube is running. The retired CUBE-ALL
  // lifetime sentinel now means the seasoned cube's own board, so old links keep landing somewhere.
  const cubeEntryBoard = ongoingCubeBoard(cubeSeasons);
  const cubeBoard = routeSet === CUBE_LIFETIME
    ? cubeBoardCode(SEASONED_CUBE_VARIANT.slug)
    : (routeSet === CUBE_BASE ? cubeEntryBoard : undefined);
  const activeSet = cubeBoard ?? routeSet;
  const setMeta = sets?.find((s) => s.code === baseSetCode(activeSet));
  // Every cube is its own entry here; `sets` keeps the real rows for route and metadata lookups
  const dropdownSets = useMemo(
    () => withMtgoSets(setsWithCubeBoards(sets, cubeSeasons)),
    [sets, cubeSeasons],
  );
  const isMtgo = isMtgoFlashbackCode(activeSet);
  const trophyLb = useTrophyLeaderboard(isMtgo ? activeSet : undefined);

  // Filters live in the URL as query params (?format=Premier or ?colors=WR).
  // Per spec they're mutually exclusive, so picking a non-ALL value in one
  // clears the other.
  const [searchParams, setSearchParams] = useSearchParams();
  useEffect(() => {
    if (!params.setCode) return;
    if (routeSet === liveSetCode) {
      navigate({ pathname: leaderboardPath(), search: searchParams.toString() }, { replace: true });
    } else if (cubeBoard) {
      navigate({ pathname: leaderboardPath(cubeBoard), search: searchParams.toString() }, { replace: true });
    } else if (routeSet !== params.setCode) {
      navigate({ pathname: leaderboardPath(routeSet), search: searchParams.toString() }, { replace: true });
    }
  }, [params.setCode, routeSet, liveSetCode, cubeBoard, navigate, searchParams]);
  const format = searchParams.get("format") ?? "ALL";
  const colors = searchParams.get("colors") ?? "ALL";
  const colorsMode = colors !== "ALL";
  const formatMode = format !== "ALL";
  const bothMode = colorsMode && formatMode;
  const formatOnlyMode = formatMode && !colorsMode;
  const colorsOnlyMode = colorsMode && !formatMode;

  const setFormat = (v: string) => {
    setSearchParams((prev) => {
      const next = new URLSearchParams(prev);
      if (v === "ALL") next.delete("format");
      else next.set("format", v);
      return next;
    });
  };
  const setColors = (v: string) => {
    setSearchParams((prev) => {
      const next = new URLSearchParams(prev);
      if (v === "ALL") next.delete("colors");
      else next.set("colors", v);
      return next;
    });
  };

  const { chips: colorChips, otherCombos, loading: colorChipsLoading } = useColorChips(activeSet);
  const { data: availableFormatLabels } = useAvailableFormats(activeSet);
  const formatOptions = useMemo(() => {
    if (!availableFormatLabels) return FORMAT_OPTIONS;
    const available = new Set(availableFormatLabels);
    return FORMAT_OPTIONS.filter((opt) => {
      if (opt.value === "ALL") return true;
      const labels = FORMAT_LABEL_GROUPS[opt.value] ?? [opt.value];
      return labels.some((l) => available.has(l));
    });
  }, [availableFormatLabels]);

  const otherMode = colorsOnlyMode && colors === OTHER;
  const namedColorsOnlyMode = colorsOnlyMode && colors !== OTHER;
  const bothOtherMode = bothMode && colors === OTHER;
  const bothNamedMode = bothMode && colors !== OTHER;

  const lb = useLeaderboard(colorsMode || formatMode ? undefined : activeSet);
  const fmtLb = useFormatLeaderboard(
    formatOnlyMode ? activeSet : undefined,
    formatOnlyMode ? format : undefined,
  );
  const colorsLb = useColorsLeaderboard(
    namedColorsOnlyMode ? activeSet : undefined,
    namedColorsOnlyMode ? colors : undefined,
  );
  const otherLb = useOtherColorsLeaderboard(
    otherMode || bothOtherMode ? activeSet : undefined,
    otherMode || bothOtherMode ? otherCombos : undefined,
    bothOtherMode ? format : undefined,
  );
  const bothLb = useFormatColorsLeaderboard(
    bothNamedMode ? activeSet : undefined,
    bothNamedMode ? format : undefined,
    bothNamedMode ? colors : undefined,
  );

  const active = bothNamedMode
    ? bothLb
    : otherMode || bothOtherMode
      ? otherLb
      : namedColorsOnlyMode
        ? colorsLb
        : formatOnlyMode
          ? fmtLb
          : lb;
  const baseRows: LeaderboardTableRow[] | undefined = active.data;
  const isLoading = active.isLoading;
  const error = active.error as Error | null;

  const boardMode = boardModeFor(format);
  const noScoreMode = format === "Pod" || boardMode === "direct";
  const effectiveDefaultSort: SortState = format === "Pod" ? DEFAULT_SORT_NOSCORE : defaultSortFor(boardMode);
  const rawSort = readSortFromParams(searchParams);
  const sort: SortState = noScoreMode && rawSort.key === "score" ? effectiveDefaultSort : rawSort;
  const rows = useMemo(
    () => (baseRows ? sortRows(baseRows, sort) : baseRows),
    [baseRows, sort.key, sort.dir],
  );

  const onSort = (key: SortKey) => {
    setSearchParams((prev) => {
      const next = new URLSearchParams(prev);
      const curKey = (next.get("sort") as SortKey | null) ?? effectiveDefaultSort.key;
      const curDir = (next.get("dir") as SortDir | null) ?? effectiveDefaultSort.dir;
      const dir: SortDir =
        curKey === key ? (curDir === "desc" ? "asc" : "desc") : "desc";
      if (key === effectiveDefaultSort.key && dir === effectiveDefaultSort.dir) {
        next.delete("sort");
        next.delete("dir");
      } else {
        next.set("sort", key);
        if (dir === "desc") next.delete("dir");
        else next.set("dir", dir);
      }
      return next;
    });
  };

  const updated = setMeta?.lastRefreshedAt ? lastUpdated(setMeta.lastRefreshedAt) : null;
  const filterProps: FilterRowProps = { format, setFormat, colors, setColors, colorChips, colorChipsLoading, formatOptions, updated };

  const { user } = useAuth();
  const { data: mySlug } = usePlayerSlugByDiscordId(user?.discordId);

  if (isMtgo) {
    return (
      <MtgoBoard
        activeSet={activeSet}
        sets={dropdownSets}
        rows={trophyLb.data}
        loading={trophyLb.isLoading}
        searchParams={searchParams}
        cubeEntryBoard={cubeEntryBoard}
        cubeSeasons={cubeSeasons}
      />
    );
  }

  return isMobile ? (
    <Mobile
      activeSet={activeSet}
      sets={dropdownSets}
      cubeSeasons={cubeSeasons}
      cubeEntryBoard={cubeEntryBoard}
      rows={rows}
      isLoading={isLoading}
      error={error}
      filters={filterProps}
      colorsMode={colorsMode}
      otherCombos={otherCombos}
      searchParams={searchParams}
      sort={sort}
      onSort={onSort}
      mySlug={mySlug ?? undefined}
    />
  ) : (
    <Desktop
      activeSet={activeSet}
      sets={dropdownSets}
      setMeta={setMeta}
      cubeSeasons={cubeSeasons}
      cubeEntryBoard={cubeEntryBoard}
      rows={rows}
      isLoading={isLoading}
      error={error}
      filters={filterProps}
      colorsMode={colorsMode}
      otherCombos={otherCombos}
      searchParams={searchParams}
      sort={sort}
      onSort={onSort}
      mySlug={mySlug ?? undefined}
    />
  );
}

const SORT_KEYS: ReadonlySet<SortKey> = new Set([
  "score",
  "trophies",
  "events",
  "record",
  "winPct",
  "earnings",
  "boxes",
]);

function readSortFromParams(searchParams: URLSearchParams): SortState {
  const rawKey = searchParams.get("sort");
  const rawDir = searchParams.get("dir");
  const key: SortKey = rawKey && SORT_KEYS.has(rawKey as SortKey) ? (rawKey as SortKey) : DEFAULT_SORT.key;
  const dir: SortDir = rawDir === "asc" ? "asc" : "desc";
  return { key, dir };
}

interface FilterRowProps {
  format: string;
  setFormat: (v: string) => void;
  colors: string;
  setColors: (v: string) => void;
  colorChips: string[];
  colorChipsLoading: boolean;
  formatOptions: typeof FORMAT_OPTIONS;
  updated: string | null;
}

// ─── MTGO flashback board ────────────────────────────────────────────────────
// Trophy-count board for MTGO-only sets: its own minimal chrome, no filters or scored columns.

function MtgoBoard({
  activeSet,
  sets,
  rows,
  loading,
  searchParams,
  cubeEntryBoard,
  cubeSeasons,
}: {
  activeSet: string;
  sets: SetSummary[] | undefined;
  rows: TrophyLeaderboardRow[] | undefined;
  loading: boolean;
  searchParams: URLSearchParams;
  cubeEntryBoard?: string;
  cubeSeasons?: CubeSeason[];
}) {
  const navigate = useNavigate();
  const isMobile = useIsMobile();
  const onSelectSet = (c: string) => goToSet(navigate, c, sets, searchParams, cubeEntryBoard, cubeSeasons);
  const releaseDate = sets?.find((s) => s.code === activeSet)?.startDate;
  const blockGlyphs = MTGO_BLOCK_GLYPHS[activeSet];
  return (
    <div className="bg-bg text-text min-h-screen flex flex-col page-fade">
      <AppHeader subtitle="LEADERBOARD" />
      <div className="relative px-5 md:px-10 py-5 border-b border-border bg-surface flex items-center gap-3 md:gap-4">
        {blockGlyphs ? (
          <div className="flex items-center gap-2 md:gap-2.5 shrink-0">
            <i
              className={`ss ss-${blockGlyphs[0]} text-white`}
              style={{ fontSize: isMobile ? 52 : 84, lineHeight: 1 }}
              aria-hidden="true"
            />
            <div className="flex flex-col items-center gap-1.5 md:gap-2">
              {blockGlyphs.slice(1).map((glyph) => (
                <i
                  key={glyph}
                  className={`ss ss-${glyph} text-white`}
                  style={{ fontSize: isMobile ? 24 : 38, lineHeight: 1 }}
                  aria-hidden="true"
                />
              ))}
            </div>
          </div>
        ) : (
          <SetGlyph code={activeSet} size={isMobile ? 52 : 84} />
        )}
        <div className="min-w-0">
          <div className="flex items-baseline gap-3">
            <span
              className="font-display tracking-[0.04em]"
              style={{ fontSize: isMobile ? 32 : 56, lineHeight: 0.9 }}
            >
              {activeSet}
            </span>
            <span className="font-display text-[15px] md:text-[22px] text-muted tracking-[0.06em] truncate">
              {mtgoSetName(activeSet).toUpperCase()}
            </span>
          </div>
          {releaseDate && (
            <div className="mono text-[11px] text-muted mt-1 tracking-[0.04em]">{fmtShortDate(releaseDate)}</div>
          )}
        </div>
        <div className="flex-1" />
        {sets && (
          isMobile ? (
            <div className="w-[150px] shrink-0">
              <SetSwitcherMobile sets={sets} activeCode={activeSet} onChange={onSelectSet} />
            </div>
          ) : (
            <SetSwitcherDesktop sets={sets} activeCode={activeSet} onChange={onSelectSet} />
          )
        )}
      </div>
      <div className="px-5 md:px-10 py-4 grid gap-6 lg:grid-cols-[1fr_320px]">
        <TrophyLeaderboard rows={rows} loading={loading} />
        <div className="lg:pt-4">
          <MtgoSidebar rows={rows} setCode={activeSet} />
        </div>
      </div>
      <Footer className="mt-auto px-10 pt-5 pb-3" />
    </div>
  );
}

// ─── Desktop ───────────────────────────────────────────────────────────────

function Desktop({
  activeSet,
  sets,
  setMeta,
  cubeSeasons,
  cubeEntryBoard,
  rows,
  isLoading,
  error,
  filters,
  colorsMode: _colorsMode,
  otherCombos,
  searchParams,
  sort,
  onSort,
  mySlug,
}: {
  activeSet: string;
  sets: SetSummary[] | undefined;
  setMeta: SetSummary | undefined;
  cubeSeasons: CubeSeason[] | undefined;
  cubeEntryBoard: string | undefined;
  rows: LeaderboardTableRow[] | undefined;
  isLoading: boolean;
  error: Error | null;
  filters: FilterRowProps;
  colorsMode: boolean;
  otherCombos: string[];
  searchParams: URLSearchParams;
  sort: SortState;
  onSort: (key: SortKey) => void;
  mySlug?: string;
}) {
  const navigate = useNavigate();
  const { prefetchSet, prefetchPlayer } = usePrefetchers();
  const profileSet = baseSetCode(activeSet);
  return (
    <div className="bg-bg text-text min-h-screen flex flex-col page-fade">
      <AppHeader subtitle="LEADERBOARD" />
      <SetHero
        activeSet={activeSet}
        setMeta={setMeta}
        sets={sets}
        cubeSeasons={cubeSeasons}
        onSelectSet={(c) => goToSet(navigate, c, sets, searchParams, cubeEntryBoard, cubeSeasons)}
        onSelectSeason={(c) => navigate({ pathname: leaderboardPath(c), search: searchParams.toString() })}
        onPrefetchSet={prefetchSet}
        format={filters.format}
        colors={filters.colors}
      />
      <FilterRow {...filters} />

      <div className="pl-5 pr-8 grid gap-6" style={{ gridTemplateColumns: "1fr 320px" }}>
        <LeaderboardTable
          rows={rows}
          variant="desktop"
          loading={isLoading}
          error={error}
          mode={boardModeFor(filters.format)}
          sort={sort}
          onSort={onSort}
          onRowPrefetch={(r) => prefetchPlayer(r.slug, profileSet)}
          highlightSlug={mySlug}
          playerHref={(r) => playerHrefFor(r, profileSet, searchParams)}
          rowExpandable={(r) => r.events > 0}
          renderExpanded={(r) => (
            <DesktopExpandedRow
              row={r}
              to={playerHrefFor(r, profileSet, searchParams)}
              activeFormat={filters.format}
              activeColors={filters.colors}
              otherCombos={otherCombos}
            />
          )}
        />
        <div className="pt-4">
          <LeaderboardSidebar
            setCode={activeSet}
            playerSetCode={profileSet}
            colors={filters.colors}
            format={filters.format}
            otherCombos={otherCombos}
            onColorsSelect={filters.setColors}
            searchParams={searchParams}
            updated={filters.updated}
            stats={{
              players: rows?.length ?? 0,
              events: sumEvents(rows),
            }}
          />
        </div>
      </div>
      <Footer className="mt-auto px-10 pt-5 pb-3" />
    </div>
  );
}

function SetHero({
  activeSet,
  setMeta,
  sets,
  cubeSeasons,
  onSelectSet,
  onSelectSeason,
  onPrefetchSet,
  format,
  colors,
}: {
  activeSet: string;
  setMeta: SetSummary | undefined;
  sets: SetSummary[] | undefined;
  cubeSeasons: CubeSeason[] | undefined;
  onSelectSet: (code: string) => void;
  onSelectSeason: (code: string) => void;
  onPrefetchSet?: (code: string) => void;
  format: string;
  colors: string;
}) {
  const base = baseSetCode(activeSet);
  const isCube = base === CUBE_BASE;
  const week = weekOfSet(setMeta);
  const filterActive = format !== "ALL" || colors !== "ALL";
  const tightHero = useIsMobile(1400);
  const seasonLabel = cubeSeasonLabel(activeSet);
  const seasonSet = seasonLabel ? sets?.find((s) => s.code === seasonLabel) : undefined;
  const cubeSeason = isCube ? cubeSeasons?.find((s) => s.setCode === activeSet) : undefined;
  // Start at the actual cube burst (cube opens after release); end at the set's planned rotation
  // date rather than the latest event, so a live season doesn't read "— <today>". EOE is the
  // exception — its cube ran after the set already rotated — so never end before the last event.
  // A cube board with no row yet shows no range at all: the CUBE set's own open-ended window spans
  // every cube and belongs to no board.
  let seasonRange: string | null = null;
  if (cubeSeason) {
    const setEnd = seasonSet?.endDate;
    const end = setEnd && setEnd >= cubeSeason.lastEvent ? setEnd : cubeSeason.lastEvent;
    seasonRange = fmtRange(cubeSeason.firstEvent, end);
  } else if (!isCube && setMeta) {
    seasonRange = fmtRange(setMeta.startDate, setMeta.endDate);
  }
  // One marker across every board: LIVE means the thing you are looking at is the one running now,
  // the same signal the set list already shows against its live row.
  const isActive = isCube ? isCubeBoardLive(activeSet) : (setMeta?.isActive ?? false);
  // A cube board is named for the cube it scores, so a season reads as the cube that ran it
  const heroName = isCube
    ? (cubeForBoard(activeSet) ?? SEASONED_CUBE_VARIANT).name
    : (setMeta?.name ?? "");
  return (
    <div className="relative px-10 py-5 border-b border-border bg-surface flex items-center gap-6">
      <SetGlyph code={base} size={84} />
      <div>
        <SectionLabel size={13} className={cn("text-green", !isActive && "invisible")}>LIVE</SectionLabel>
        <div className="flex items-baseline gap-3.5 mt-0.5">
          <span className="font-display tracking-[0.04em]" style={{ fontSize: 56, lineHeight: 0.9 }}>
            {base}
          </span>
          <span className="font-display text-[22px] text-muted tracking-[0.06em]">
            {heroName.toUpperCase()}
          </span>
        </div>
        {isCube ? (
          // Every cube prints its own run here, never the shared CUBE row's open-ended window. Height
          // comes from the same text-[11px] element a normal set uses, so the hero matches exactly.
          <div className="mono text-[11px] text-muted mt-1 tracking-[0.04em] flex items-center gap-6">
            {/* Zero height holds the hero to a normal set's while the selector keeps its width */}
            {cubeBoardHasSeasons(activeSet) && (
              <div className="h-0 shrink-0 flex items-center">
                <CubeSeasonSelector activeSet={activeSet} seasons={cubeSeasons} onSelect={onSelectSeason} />
              </div>
            )}
            {/* Nudged onto the selector's baseline: the two sit in one line box at 11px and 20px, so
                box alignment leaves the smaller text riding high. Transform, so the hero keeps its height. */}
            <span className="whitespace-nowrap ml-auto self-end translate-y-[4px]">{seasonRange || " "}</span>
          </div>
        ) : (
          <div className="mono text-[11px] text-muted mt-1 flex justify-between gap-4">
            {setMeta && <span>{fmtRange(setMeta.startDate, setMeta.endDate)}</span>}
            {week && <span>{week}</span>}
          </div>
        )}
      </div>
      {filterActive ? <FilterHero format={format} colors={colors} /> : <div className="flex-1" />}
      {sets && (
        <SetSwitcherDesktop
          sets={sets}
          activeCode={isCubeCode(activeSet) ? cubeBoardGlyphCode(activeSet) : base}
          onChange={onSelectSet}
          onPrefetch={onPrefetchSet}
          extraHide={filterActive ? (tightHero ? 3 : 2) : 0}
        />
      )}
    </div>
  );
}

function ColorsHeroGlyph({ code }: { code: string }) {
  return (
    <span
      className="shrink-0 inline-flex items-center justify-center"
      style={{ width: 48, height: 48 }}
    >
      <ColorsHeroGlyphInner code={code} />
    </span>
  );
}

function ColorsHeroGlyphInner({ code }: { code: string }) {
  if (code === MULTI) {
    return <BsPaletteFill size={36} aria-hidden="true" />;
  }
  if (code === OTHER) {
    return <BsAsterisk size={32} aria-hidden="true" />;
  }
  const url = guildSvgUrl(code);
  if (url) {
    return (
      <img
        key={url}
        src={url}
        alt=""
        aria-hidden="true"
        className="block"
        style={{ height: 44, width: 44, transform: guildLogoTransform(code) }}
      />
    );
  }
  if (code.length === 1 && "WUBRG".includes(code)) {
    return <Pip c={code as "W" | "U" | "B" | "R" | "G"} size={32} />;
  }
  const isTri = code.length === 3 && [...code].every((c) => "WUBRG".includes(c));
  if (isTri) {
    const [top, left, right] = [...code] as Array<"W" | "U" | "B" | "R" | "G">;
    return (
      <span className="inline-flex flex-col items-center" style={{ gap: 2 }}>
        <Pip c={top} size={20} />
        <span className="inline-flex" style={{ gap: 2 }}>
          <Pip c={left} size={20} />
          <Pip c={right} size={20} />
        </span>
      </span>
    );
  }
  return <Pips colors={code} size={22} />;
}

function FilterHero({ format, colors }: { format: string; colors: string }) {
  const colorsActive = colors !== "ALL";
  const formatActive = format !== "ALL";
  const opt = FORMAT_OPTIONS.find((o) => o.value === format);
  const formatLabel = opt?.label ?? format.toUpperCase();
  const formatColor = FMT_COLORS[format] ?? FMT_DEFAULT_COLOR;
  const colorsName = colorsActive ? colorsDisplayName(colors) : "";

  if (colorsActive && formatActive) {
    return (
      <div className="flex-1 min-w-0 flex flex-col items-center justify-center pointer-events-none gap-2.5">
        <span
          className="font-display tracking-[0.06em] whitespace-nowrap max-w-full overflow-hidden text-ellipsis"
          style={{ fontSize: 26, lineHeight: 1, color: formatColor }}
        >
          {formatLabel}
        </span>
        <span
          className="relative whitespace-nowrap font-display tracking-[0.06em]"
          style={{ fontSize: 32, lineHeight: 1 }}
        >
          <span className="absolute right-full top-1/2 -translate-y-1/2 pr-3 flex items-center">
            <ColorsHeroGlyph code={colors} />
          </span>
          {colorsName}
        </span>
      </div>
    );
  }

  if (colorsActive) {
    return (
      <div className="flex-1 min-w-0 flex items-center justify-center pointer-events-none">
        <span
          className="relative whitespace-nowrap font-display tracking-[0.06em]"
          style={{ fontSize: 36, lineHeight: 1 }}
        >
          <span className="absolute right-full top-1/2 -translate-y-1/2 pr-3 flex items-center">
            <ColorsHeroGlyph code={colors} />
          </span>
          {colorsName}
        </span>
      </div>
    );
  }
  return (
    <div className="flex-1 min-w-0 flex items-center justify-center pointer-events-none">
      <span
        className="font-display tracking-[0.06em] whitespace-nowrap max-w-full overflow-hidden text-ellipsis"
        style={{ fontSize: 36, lineHeight: 1, color: formatColor }}
      >
        {formatLabel}
      </span>
    </div>
  );
}

function FilterRow({
  format,
  setFormat,
  colors,
  setColors,
  colorChips,
  colorChipsLoading,
  formatOptions,
}: FilterRowProps) {
  return (
    <div className="px-10 py-3 border-b border-border flex items-center gap-4 flex-wrap">
      <FilterDropdown
        value={format}
        options={formatOptions}
        onChange={setFormat}
        renderValue={renderFormatOption}
        renderOption={renderFormatOption}
      />
      <SectionLabel size={11}>COLORS</SectionLabel>
      <ColorsSwitcher activeCode={colors} onChange={setColors} chips={colorChips} loading={colorChipsLoading} />
      <Link
        to="/leaderboard/about"
        className="ml-auto inline-flex items-center gap-1.5 font-display text-[15px] leading-none tracking-[0.08em] text-green hover:text-green-2 transition-colors no-underline whitespace-nowrap"
      >
        ABOUT THE LEADERBOARD
        <ArrowRight size={15} />
      </Link>
    </div>
  );
}

// ─── Mobile ────────────────────────────────────────────────────────────────

function Mobile({
  activeSet,
  sets,
  cubeSeasons,
  cubeEntryBoard,
  rows,
  isLoading,
  error,
  filters,
  colorsMode: _colorsMode,
  otherCombos,
  searchParams,
  sort,
  onSort,
  mySlug,
}: {
  activeSet: string;
  sets: SetSummary[] | undefined;
  cubeSeasons: CubeSeason[] | undefined;
  cubeEntryBoard: string | undefined;
  rows: LeaderboardTableRow[] | undefined;
  isLoading: boolean;
  otherCombos: string[];
  error: Error | null;
  filters: FilterRowProps;
  colorsMode: boolean;
  mySlug?: string;
  searchParams: URLSearchParams;
  sort: SortState;
  onSort: (key: SortKey) => void;
}) {
  const navigate = useNavigate();
  const { prefetchPlayer } = usePrefetchers();
  const profileSet = baseSetCode(activeSet);
  const setMeta = sets?.find((s) => s.code === profileSet);
  const updated = setMeta?.lastRefreshedAt ? lastUpdated(setMeta.lastRefreshedAt) : null;
  const isCube = profileSet === CUBE_BASE;
  const setOptions = useMemo<SetFilterOption[]>(() => (sets ? setFilterOptionsFrom(sets) : []), [sets]);

  const chromeRef = useRef<HTMLDivElement>(null);
  const [chromeHeight, setChromeHeight] = useState(0);
  useEffect(() => {
    const el = chromeRef.current;
    if (!el) {
      return;
    }
    const measure = () => setChromeHeight(el.getBoundingClientRect().height);
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  return (
    <div className="bg-bg text-text min-h-screen flex flex-col overflow-x-clip page-fade">
      <div ref={chromeRef} className="page-chrome sticky top-0 z-10 bg-bg">
        <AppHeader subtitle="LEADERBOARD" />

        <div className="px-3 py-2 border-b border-border bg-surface flex items-stretch gap-2">
          <div className="basis-1/2 min-w-0 flex">
            <FilterDropdown
              value={filters.format}
              options={filters.formatOptions}
              onChange={filters.setFormat}
              variant="mobile"
              renderValue={renderFormatOption}
              renderOption={renderFormatOption}
              triggerClassName="py-2"
            />
          </div>
          {sets && (
            <div className="basis-1/2 min-w-0 flex">
              <SetFilterDropdown
                value={isCubeCode(activeSet) ? cubeBoardGlyphCode(activeSet) : profileSet}
                options={setOptions}
                onChange={(code) => goToSet(navigate, code, sets, searchParams, cubeEntryBoard, cubeSeasons)}
                variant="mobile"
                align="right"
                searchable
                subtext={updated ?? undefined}
              />
            </div>
          )}
        </div>
        {isCube && cubeBoardHasSeasons(activeSet) && (
          <div className="px-3 py-1.5 border-b border-border bg-surface flex">
            <CubeSeasonSelector
              activeSet={activeSet}
              seasons={cubeSeasons}
              onSelect={(c) => navigate({ pathname: leaderboardPath(c), search: searchParams.toString() })}
              variant="mobile"
            />
          </div>
        )}
        <div className="px-3 py-1.5 border-b border-border bg-bg">
          <ColorsSwitcher
            activeCode={filters.colors}
            onChange={filters.setColors}
            chips={filters.colorChips}
            loading={filters.colorChipsLoading}
            variant="mobile"
          />
        </div>
        <LeaderboardInsightsStrip
          setCode={activeSet}
          playerSetCode={profileSet}
          colors={filters.colors}
          format={filters.format}
          otherCombos={otherCombos}
          onColorsSelect={filters.setColors}
          searchParams={searchParams}
        />
        {/* Column header is part of the sticky chrome so it stays pinned with the
            rest of the page chrome as rows scroll under it. */}
        <LeaderboardColumnHeader variant="mobile" mode={boardModeFor(filters.format)} sort={sort} onSort={onSort} />
      </div>

      <LeaderboardTable
        rows={rows}
        variant="mobile"
        loading={isLoading}
        error={error}
        showHeader={false}
        mode={boardModeFor(filters.format)}
        onRowPrefetch={(r) => prefetchPlayer(r.slug, profileSet)}
        highlightSlug={mySlug}
        stickyTop={chromeHeight}
        playerHref={(r) => playerHrefFor(r, profileSet, searchParams)}
        rowExpandable={(r) => r.events > 0}
        renderExpanded={(r) => (
          <MobileExpandedRow
            row={r}
            to={playerHrefFor(r, profileSet, searchParams)}
            activeFormat={filters.format}
            activeColors={filters.colors}
            otherCombos={otherCombos}
          />
        )}
      />
      <Footer className="mt-auto px-4 py-4" />
    </div>
  );
}

// ─── Expanded rows ─────────────────────────────────────────────────────────

const PANEL_MIN_HEIGHT = 88;

// Debug aid — bump above 0 (e.g. 3000) to keep skeleton visible after data lands
const SKELETON_DEBUG_DELAY_MS: number = 0;

function useDelayedExpandedData(slug: string, setCode: string) {
  const profileQ = usePlayerProfile(slug, setCode);
  const eventsQ = useDraftEvents(slug, setCode);
  const [released, setReleased] = useState(SKELETON_DEBUG_DELAY_MS === 0);
  useEffect(() => {
    if (SKELETON_DEBUG_DELAY_MS === 0) return;
    const t = setTimeout(() => setReleased(true), SKELETON_DEBUG_DELAY_MS);
    return () => clearTimeout(t);
  }, []);
  return {
    profile: released ? profileQ.data : undefined,
    events: released ? eventsQ.data : undefined,
  };
}

type PlayerLinkTo = string | { pathname: string; search: string };

function playerHrefFor(row: LeaderboardTableRow, setCode: string, params: URLSearchParams): string {
  const qs = profileSearch(params);
  const path = playerPath(row.slug, setCode);
  return qs ? `${path}?${qs}` : path;
}

function DesktopExpandedRow({
  row,
  to,
  activeFormat,
  activeColors,
  otherCombos,
}: {
  row: LeaderboardTableRow;
  to: PlayerLinkTo;
  activeFormat: string;
  activeColors: string;
  otherCombos: string[];
}) {
  const { profile, events } = useDelayedExpandedData(row.slug, row.setCode);
  const { lastTrophies, biggestStreak } = useHighlights(events);
  const filtersActive = activeFormat !== "ALL" || activeColors !== "ALL";
  const cube = isCubeCode(row.setCode);
  const filteredTrophies = useMemo(
    () => filterTrophyEvents(events, activeFormat, activeColors, otherCombos, cube).slice(0, 3),
    [events, activeFormat, activeColors, otherCombos, cube],
  );
  const trophiesToShow = filtersActive ? filteredTrophies : lastTrophies;
  const scopedDecks = useMemo(
    () => trophiesToShow.length === 0 && events
      ? filterScopedEvents(events, activeFormat, activeColors, otherCombos, cube).slice(0, 3)
      : [],
    [trophiesToShow.length, events, activeFormat, activeColors, otherCombos, cube],
  );

  return (
    <Link
      to={to}
      aria-label={`View ${row.displayName}'s profile`}
      className="pt-3 pb-2 pr-4 pl-[76px] border-t border-dashed border-border2 flex items-start gap-6 cursor-pointer transition-colors hover:bg-green/5 no-underline text-inherit"
    >
      <div className="flex-1 min-w-0 overflow-hidden"><FormatBreakdownPreview breakdown={profile?.formatBreakdown} /></div>
      <div className="flex-1 min-w-0 overflow-hidden"><MostPlayedDecks events={events} /></div>
      <div className="flex-1 min-w-0 overflow-hidden"><LastTrophyPanel data={trophiesToShow} decks={scopedDecks} loading={!events} activeFormat={activeFormat} activeColors={activeColors} /></div>
      <div className="flex-[0.4] min-w-0 overflow-hidden self-stretch -ml-6"><BiggestStreakPanel data={biggestStreak} loading={!events} /></div>
      <ChamferedButton className="!pt-[10px] !pb-[10px] self-center">
        <span className="inline-flex items-center gap-2">
          VIEW PROFILE
          <ArrowRight size={12} />
        </span>
      </ChamferedButton>
    </Link>
  );
}

function FormatBreakdownPreview({
  breakdown,
}: {
  breakdown: PlayerFormatBreakdown[] | undefined;
}) {
  const sorted = useMemo(
    () =>
      breakdown
        ? [...breakdown]
            .filter((f) => f.events > 0)
            .sort((a, b) => b.events - a.events)
        : [],
    [breakdown],
  );
  const ready = sorted.length > 0;
  const total = ready ? Math.max(1, sorted.reduce((s, f) => s + f.events, 0)) : 1;
  const dense = sorted.length >= 4;
  const labelCls = dense ? "text-[11px]" : "text-[13px]";
  const swatchCls = dense ? "w-[11px] h-[11px]" : "w-[13px] h-[13px]";
  const numCls = dense ? "text-[11px]" : "text-[12px]";
  return (
    <div style={{ minHeight: PANEL_MIN_HEIGHT }}>
      <SectionLabel size={13} className="text-subtle">FORMAT BREAKDOWN</SectionLabel>
      <div className="flex items-center gap-2.5 mt-2 min-w-0">
        <div className="shrink-0">
          <DonutChart
            entries={sorted.map((f) => ({
              key: f.formatLabel,
              value: f.events / total,
              color: FMT_COLORS[f.formatLabel] ?? FMT_DEFAULT_COLOR,
            }))}
            radius={28}
            strokeWidth={10}
            size={76}
            pieHole={0.5}
          />
        </div>
        <div
          className="grid items-center gap-x-2 gap-y-0.5 min-w-0"
          style={{ gridTemplateColumns: "auto minmax(0, 1fr) auto" }}
        >
          {ready
            ? sorted.map((f) => {
                const color = FMT_COLORS[f.formatLabel] ?? FMT_DEFAULT_COLOR;
                return (
                  <Fragment key={f.formatLabel}>
                    <span className={cn(swatchCls, "shrink-0")} style={{ background: color }} />
                    <span className={cn("font-display tracking-[0.08em] truncate", labelCls)}>
                      {shortFormat(f.formatLabel)}
                    </span>
                    <span className={cn("mono text-muted tabular-nums justify-self-end", numCls)}>
                      {f.events}
                    </span>
                  </Fragment>
                );
              })
            : SKELETON_FORMAT_ROWS.map((w, i) => (
                <Fragment key={i}>
                  <span className="w-2 h-2 bg-surface2 shrink-0" />
                  <span className="h-2.5 bg-surface2" style={{ width: w }} />
                  <span className="h-2.5 bg-surface2 justify-self-end" style={{ width: 18 }} />
                </Fragment>
              ))}
        </div>
      </div>
    </div>
  );
}

const SKELETON_FORMAT_ROWS = [70, 56, 64, 48];

function MostPlayedDecks({ events }: { events: PlayerDraftEvent[] | undefined }) {
  const top = useMemo(() => {
    if (!events || events.length === 0) return [];
    const count: Record<string, number> = {};
    const trophies: Record<string, number> = {};
    for (const e of events) {
      const c = colorsOf(e.colors);
      if (c.length === 0) continue;
      count[c] = (count[c] ?? 0) + 1;
      if (e.isTrophy) trophies[c] = (trophies[c] ?? 0) + 1;
    }
    return Object.entries(count)
      .sort((a, b) => b[1] - a[1])
      .slice(0, 3)
      .map(([code, n]) => ({ code, count: n, trophies: trophies[code] ?? 0 }));
  }, [events]);

  return (
    <div style={{ minHeight: PANEL_MIN_HEIGHT }}>
      <SectionLabel size={13} className="text-subtle">MOST PLAYED DECKS</SectionLabel>
      <div
        className="grid items-center gap-x-3 gap-y-1 mt-2 w-fit"
        style={{ gridTemplateColumns: "auto 64px auto" }}
      >
        {top.length > 0
          ? top.map((d) => (
              <Fragment key={d.code}>
                <Pips colors={d.code} size={11} />
                <span className="font-display text-[13px] tracking-[0.06em]">
                  {colorsDisplayName(d.code)}
                </span>
                <TrophyCount count={d.trophies} size="compact" className="text-muted" />
              </Fragment>
            ))
          : [50, 60, 44].map((w, i) => (
              <Fragment key={i}>
                <span className="w-[26px] h-3 bg-surface2 shrink-0" />
                <span className="h-3 bg-surface2" style={{ width: w }} />
                <span className="h-2.5 bg-surface2" style={{ width: 22 }} />
              </Fragment>
            ))}
      </div>
    </div>
  );
}

function filterTrophyEvents(
  events: PlayerDraftEvent[] | undefined,
  activeFormat: string,
  activeColors: string,
  otherCombos: string[],
  cube: boolean,
): PlayerDraftEvent[] {
  if (!events) return [];
  const otherSet = new Set(otherCombos);
  const matches = events.filter((e) => {
    if (!e.isTrophy) return false;
    if (!matchesFormatFilter(e.format, activeFormat)) return false;
    if (activeColors !== "ALL") {
      if (activeColors === MULTI) {
        if (!isSoup(e.colors, cube)) return false;
      } else if (activeColors === OTHER) {
        if (isSoup(e.colors, cube)) return false;
        if (!otherSet.has(colorsOf(e.colors))) return false;
      } else if (colorsOf(e.colors) !== activeColors) return false;
    }
    return true;
  });
  return matches.sort((a, b) => (b.finishedAt ?? "").localeCompare(a.finishedAt ?? ""));
}

function filterScopedEvents(
  events: PlayerDraftEvent[] | undefined,
  activeFormat: string,
  activeColors: string,
  otherCombos: string[],
  cube: boolean,
): PlayerDraftEvent[] {
  if (!events) return [];
  const otherSet = new Set(otherCombos);
  const matches = events.filter((e) => {
    if (!matchesFormatFilter(e.format, activeFormat)) return false;
    if (activeColors !== "ALL") {
      if (activeColors === MULTI) {
        if (!isSoup(e.colors, cube)) return false;
      } else if (activeColors === OTHER) {
        if (isSoup(e.colors, cube)) return false;
        if (!otherSet.has(colorsOf(e.colors))) return false;
      } else if (colorsOf(e.colors) !== activeColors) return false;
    }
    return true;
  });
  return matches.sort((a, b) => (b.finishedAt ?? "").localeCompare(a.finishedAt ?? ""));
}

interface StreakData { count: number; format: string }

function useHighlights(events: PlayerDraftEvent[] | undefined): {
  lastTrophies: PlayerDraftEvent[];
  biggestStreak: StreakData | null;
} {
  return useMemo(() => {
    if (!events || events.length === 0) return { lastTrophies: [], biggestStreak: null };
    const sorted = [...events].sort((a, b) =>
      (a.finishedAt ?? "").localeCompare(b.finishedAt ?? ""),
    );
    const lastTrophies: PlayerDraftEvent[] = [];
    for (let i = sorted.length - 1; i >= 0 && lastTrophies.length < 3; i--) {
      if (sorted[i].isTrophy) lastTrophies.push(sorted[i]);
    }
    let max = 0, cur = 0;
    let streakFormat = "";
    for (const e of sorted) {
      if (e.isTrophy) {
        cur += 1;
        if (cur > max) { max = cur; streakFormat = e.format; }
      } else {
        cur = 0;
      }
    }
    return {
      lastTrophies,
      biggestStreak: max >= 2 ? { count: max, format: streakFormat } : null,
    };
  }, [events]);
}

function LastTrophyPanel({
  data,
  decks = [],
  loading,
  activeFormat,
  activeColors,
}: {
  data: PlayerDraftEvent[];
  decks?: PlayerDraftEvent[];
  loading: boolean;
  activeFormat: string;
  activeColors: string;
}) {
  const colorsActive = activeColors !== "ALL";
  const formatActive = !colorsActive && activeFormat !== "ALL";
  const filterLabel = colorsActive
    ? colorsDisplayName(activeColors)
    : formatActive
      ? activeFormat.toUpperCase()
      : null;
  const filterStyle = formatActive
    ? { color: FMT_COLORS[activeFormat] ?? FMT_DEFAULT_COLOR }
    : undefined;
  const showDecks = !loading && data.length === 0 && decks.length > 0;
  const rows = showDecks ? decks : data;
  const headerNoun = showDecks ? "DECKS" : "TROPHIES";
  return (
    <div style={{ minHeight: PANEL_MIN_HEIGHT }}>
      <SectionLabel size={13} className="text-subtle">
        LAST{filterLabel && (
          <>
            {" "}
            <span className={colorsActive ? "text-green" : ""} style={filterStyle}>
              {filterLabel}
            </span>
          </>
        )} {headerNoun}
      </SectionLabel>
      <div className="flex flex-col gap-1 mt-2.5 min-w-0">
        {loading ? (
          [0, 1, 2].map((i) => (
            <div
              key={i}
              className="grid items-center gap-x-3 w-fit"
              style={{ gridTemplateColumns: "auto auto auto auto 12px" }}
            >
              <span className="w-[26px] h-3 bg-surface2 shrink-0" />
              <span className="h-3 bg-surface2" style={{ width: 50 }} />
              <span className="h-3 bg-surface2" style={{ width: 36 }} />
              <span className="h-3 bg-surface2" style={{ width: 24 }} />
              <span />
            </div>
          ))
        ) : rows.length > 0 ? (
          rows.map((e) => {
            const href = e.seventeenlandsEventId
              ? `https://www.17lands.com/deck/${e.seventeenlandsEventId}`
              : null;
            const onClick = href
              ? (ev: React.MouseEvent) => {
                  ev.preventDefault();
                  ev.stopPropagation();
                  window.open(href, "_blank", "noopener,noreferrer");
                }
              : undefined;
            return (
              <div
                key={e.eventId}
                onClick={onClick}
                role={href ? "link" : undefined}
                title={href ? "Open deck on 17lands" : undefined}
                className={cn(
                  "grid items-center gap-x-3 px-1.5 -mx-1.5 rounded transition-colors w-fit",
                  href && "hover:bg-surface2 cursor-pointer",
                )}
                style={{ gridTemplateColumns: "auto auto auto auto 12px" }}
              >
                <Pips colors={e.colors} size={11} />
                <span className="font-display text-[13px] tracking-[0.06em] text-muted truncate">
                  {shortFormat(e.format)}
                </span>
                <Record
                  wins={e.wins}
                  losses={e.losses}
                  mono
                  className="mono text-[12px] text-muted text-right justify-self-end"
                />
                <span className="mono text-[12px] text-dim">{relativeTime(eventDate(e))}</span>
                <span className="flex justify-center text-subtle">
                  {href && <ExternalLink size={10} aria-hidden="true" />}
                </span>
              </div>
            );
          })
        ) : (
          <div className="mono text-[12px] text-muted">NONE YET</div>
        )}
      </div>
    </div>
  );
}

function BiggestStreakPanel({
  data,
  loading,
}: {
  data: StreakData | null;
  loading: boolean;
}) {
  return (
    <div className="flex flex-col items-center justify-center h-full" style={{ minHeight: PANEL_MIN_HEIGHT }}>
      <SectionLabel size={13} className="text-subtle text-center">MAX TROPHY</SectionLabel>
      {loading ? (
        <span className="block h-5 w-12 bg-surface2 mt-1" />
      ) : data ? (
        <>
          <span className="flex items-center gap-1.5 my-0.5">
            <Trophy size={14} color="#ffc63a" />
            <span className="font-display text-[18px] leading-none tracking-[0.04em]">
              ×{data.count}
            </span>
          </span>
          <SectionLabel size={13} className="text-subtle text-center">STREAK</SectionLabel>
        </>
      ) : (
        <div className="mono text-[12px] text-muted text-center mt-1">—</div>
      )}
    </div>
  );
}

function MobileExpandedRow({
  row,
  to,
  activeFormat,
  activeColors,
  otherCombos,
}: {
  row: LeaderboardTableRow;
  to: PlayerLinkTo;
  activeFormat: string;
  activeColors: string;
  otherCombos: string[];
}) {
  const { events } = useDelayedExpandedData(row.slug, row.setCode);
  const cube = isCubeCode(row.setCode);
  // events are DESC-sorted by finishedAt — first matching trophy is the most recent
  const lastTrophy = useMemo(() => {
    if (!events) return null;
    const filtersActive = activeFormat !== "ALL" || activeColors !== "ALL";
    if (!filtersActive) {
      for (const e of events) if (e.isTrophy) return e;
      return null;
    }
    return filterTrophyEvents(events, activeFormat, activeColors, otherCombos, cube)[0] ?? null;
  }, [events, activeFormat, activeColors, otherCombos, cube]);
  const lastDeck = useMemo(() => {
    if (!events || lastTrophy) return null;
    return filterScopedEvents(events, activeFormat, activeColors, otherCombos, cube)[0] ?? null;
  }, [events, lastTrophy, activeFormat, activeColors, otherCombos, cube]);

  return (
    <Link
      to={to}
      aria-label={`View ${row.displayName}'s profile`}
      className="pt-2 pb-3 pr-3.5 pl-9 flex items-center gap-3 border-t border-dashed border-border2 cursor-pointer transition-colors hover:bg-green/5 no-underline text-inherit"
    >
      <div className="flex-1 min-w-0 flex flex-col gap-1.5">
        <span className="font-display text-[12px] tracking-[0.12em] text-muted tabular-nums">
          {row.events} EVENTS · <Record wins={row.wins} losses={row.losses} /> · {winPct(row.wins, row.losses)}%
        </span>
        <div className="flex items-center gap-1.5 min-h-[14px]">
          {!events ? (
            <span className="block h-3 w-40 bg-surface2" />
          ) : lastTrophy ? (
            <>
              <SectionLabel size={11} letterSpacing="0.18em">LAST TROPHY</SectionLabel>
              <Trophy size={12} color="#ffc63a" />
              <Pips colors={lastTrophy.colors} size={12} />
              <span className="text-dim text-[11px]">·</span>
              <span className="font-display text-[11px] tracking-[0.08em] text-muted">
                {prettyFormat(lastTrophy.format).toUpperCase()}
              </span>
              {isArenaChampionshipFormat(lastTrophy.format) && <ArenaChampBadge size={22} box={14} />}
              <span className="text-dim text-[11px]">·</span>
              <span className="font-display text-[11px] tracking-[0.08em] text-dim tabular-nums">{relativeTime(eventDate(lastTrophy))}</span>
            </>
          ) : lastDeck ? (
            <>
              <SectionLabel size={11} letterSpacing="0.18em">LAST DECK</SectionLabel>
              <Pips colors={lastDeck.colors} size={12} />
              <span className="text-dim text-[11px]">·</span>
              <span className="font-display text-[11px] tracking-[0.08em] text-muted">
                {prettyFormat(lastDeck.format).toUpperCase()}
              </span>
              <span className="text-dim text-[11px]">·</span>
              <span className="font-display text-[11px] tracking-[0.08em] text-dim tabular-nums">{relativeTime(eventDate(lastDeck))}</span>
            </>
          ) : null}
        </div>
      </div>
      <span className="font-display text-[12px] leading-none tracking-[0.18em] text-green inline-flex items-center gap-1.5 shrink-0">
        VIEW PROFILE
        <ArrowRight size={12} />
      </span>
    </Link>
  );
}

// ─── Helpers ───────────────────────────────────────────────────────────────

// The one CUBE row now covers every cube Arena has run, so its set name reads too narrow in a picker
function goToSet(
  navigate: ReturnType<typeof useNavigate>,
  code: string,
  sets: SetSummary[] | undefined,
  searchParams: URLSearchParams,
  cubeEntryBoard?: string,
  cubeSeasons?: CubeSeason[],
) {
  // The CUBE chip drops into the newest season; LIFETIME (CUBE-ALL) is reached
  // only from the in-header season selector.
  if (code === CUBE_BASE && cubeEntryBoard) code = cubeEntryBoard;
  code = latestWindowFor(code, cubeSeasons);
  const activeCode = sets?.find((s) => s.isActive)?.code;
  navigate({
    pathname: code === activeCode ? leaderboardPath() : leaderboardPath(code),
    search: searchParams.toString(),
  });
}
