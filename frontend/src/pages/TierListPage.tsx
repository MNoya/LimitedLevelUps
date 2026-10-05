import { useEffect, useMemo, useRef, useState, type Ref } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { AppHeader } from "../components/AppHeader";
import { ExternalLink } from "../components/Icons";
import { setGlyphCode } from "../components/Brand";
import { FilterGroup, TierFilterBar } from "../components/TierFilterBar";
import { TierGrid } from "../components/TierGrid";
import { TierCardSearch } from "../components/TierCardSearch";
import { GradeGuideIcon, GradeGuideProvider, GradeGuideTrigger } from "../components/TierGuide";
import { SetGlyphDropdown } from "../components/SetGlyphDropdown";
import { Tooltip } from "../components/Tooltip";
import { SkeletonsModal } from "../components/SkeletonsModal";
import { skeletonsFor } from "../data/skeletons";
import { cardDataUrl } from "../data/cardStats";
import { useSets } from "../data/hooks";
import { relativeTime } from "../data/utils";
import { cn } from "../lib/utils";
import { useIsMobile } from "../lib/use-is-mobile";
import { useStickyScrollPadding } from "../lib/use-sticky-scroll-padding";
import { OPENED_IN_APP, useCloseModal } from "../lib/modal-history";
import { ACTIVE_SET_CODE, TIER_LIST_PREVIEW_SETS } from "../data/constants";
import {
  activeFilterCount,
  buildTierListSets,
  filtersFromParams,
  hasActiveFilters,
  resolveTierList,
  tierFilterOptions,
  useCardStats,
  useDataGradeView,
  useHideArt,
  TIER_LIST_MOBILE_BREAKPOINT,
  useTierList,
  withFilterParams,
  type TierFilters,
} from "../data/tierList";

export function TierListPage({ skeletonsOpen = false }: { skeletonsOpen?: boolean }) {
  const { data: sets } = useSets();
  const isMobile = useIsMobile(TIER_LIST_MOBILE_BREAKPOINT);
  const { setCode, pair } = useParams();
  const [searchParams, setSearchParams] = useSearchParams();
  const filters = useMemo(() => filtersFromParams(searchParams), [searchParams]);
  const setFilters = (next: TierFilters) => {
    setSearchParams((params) => withFilterParams(params, next), { replace: true });
  };
  const [hideArt, setHideArt] = useHideArt();
  const [storedDataGrades, storeDataGrades] = useDataGradeView();
  const gradesParam = searchParams.get("grades");
  const dataGrades = gradesParam ? gradesParam === "17l" : storedDataGrades;
  const setDataGrades = (value: boolean) => {
    storeDataGrades(value);
    setSearchParams((params) => {
      const withGrades = withParam(params, "grades", value ? "17l" : "llu");
      return withParam(withGrades, "deck", value ? params.get("deck") : null);
    }, { replace: true });
  };
  const chosenDeck = searchParams.get("deck")?.toUpperCase() ?? null;
  const setDeck = (deck: string | null) => {
    if (deck) {
      storeDataGrades(true);
    }
    setSearchParams((params) => {
      const withDeck = withParam(params, "deck", deck?.toLowerCase() ?? null);
      return deck ? withParam(withDeck, "grades", "17l") : withDeck;
    }, { replace: true });
  };
  const [filtersOpen, setFiltersOpen] = useState(false);
  const [searchOpen, setSearchOpen] = useState(false);
  const [headerHeight, setHeaderHeight] = useState(0);
  const headerRef = useRef<HTMLDivElement>(null);

  const filterCount = activeFilterCount(filters);

  const liveSet = sets?.find((s) => s.isActive)?.code ?? ACTIVE_SET_CODE;
  const tierListSets = useMemo(() => buildTierListSets(sets), [sets]);
  const current = setCode?.toUpperCase() ?? tierListSets[0]?.code ?? liveSet;
  const setHref = (code: string) => `/tier-list/${code}`;
  const archetypesHref = `/tier-list/${current}/archetypes`;
  const closeSkeletons = useCloseModal(setHref(current));
  const setMeta = tierListSets.find((s) => s.code === current);
  const { uid, graders, comparison, effectiveUid } = resolveTierList(current);
  const glyphCode = setMeta ? setGlyphCode(setMeta) : current;
  const skeletons = useMemo(() => skeletonsFor(current), [current]);

  const { data: tierData, lastUpdated } = useTierList(effectiveUid);
  const cardStats = useCardStats(current);
  const placeByData = Boolean(cardStats?.hasGrades) && dataGrades;
  const decks = cardStats?.decks ?? [];
  const deck = placeByData && chosenDeck && decks.includes(chosenDeck) ? chosenDeck : null;
  const gradeToggle = cardStats?.hasGrades ? { dataGrades, setDataGrades, decks, deck, setDeck } : {};
  const dataSource = placeByData && cardStats ? { setCode: current, updatedAt: cardStats.updatedAt } : null;
  const statsUpdatedAt = cardStats?.hasGrades ? cardStats.updatedAt : undefined;
  const filterOptions = useMemo(() => tierFilterOptions(current, tierData), [current, tierData]);
  const filterBarLayout = useCenteredFilterBar(current, isMobile);

  useEffect(() => {
    window.scrollTo(0, 0);
  }, [setCode]);

  useEffect(() => {
    const hiddenColors = !isMobile && filters.colors.length > 0;
    const hiddenManaValues = isMobile && filters.manaValues.length > 0;
    if (hiddenColors || hiddenManaValues) {
      setFilters({
        ...filters,
        colors: hiddenColors ? [] : filters.colors,
        manaValues: hiddenManaValues ? [] : filters.manaValues,
      });
    }
  }, [isMobile, filters]);

  useEffect(() => {
    const header = headerRef.current;
    if (!header) return;
    const ro = new ResizeObserver(() => setHeaderHeight(header.offsetHeight));
    ro.observe(header);
    setHeaderHeight(header.offsetHeight);
    return () => ro.disconnect();
  }, []);

  const columnHeaderHeight = 40;
  useStickyScrollPadding(headerHeight + columnHeaderHeight);

  return (
    <GradeGuideProvider>
      <div className="bg-bg text-text min-h-screen flex flex-col page-fade">
        <AppHeader subtitle="TIER LIST" />
        <main className="flex flex-col w-full px-2 md:px-[15px] pb-10 overflow-x-clip">
          <div ref={headerRef} className="sticky top-0 z-20 bg-bg py-2 md:py-3">
            {isMobile ? (
              <>
                <div className="flex items-center gap-2">
                  <h1 className="font-display tracking-[0.12em] flex flex-1 items-center gap-2 leading-none min-w-0">
                    <SetGlyphDropdown
                      sets={tierListSets}
                      activeCode={current}
                      glyphCode={glyphCode}
                      label={setMeta?.name?.toUpperCase() ?? current}
                      isMobile
                      loading={!sets}
                      hrefFor={setHref}
                      triggerClassName="h-10 px-2.5"
                    />
                  </h1>

                  {skeletons.length > 0 && <SkeletonsButton href={archetypesHref} />}

                  {effectiveUid && (
                    <button
                      type="button"
                      onClick={() => setFiltersOpen((open) => !open)}
                      aria-expanded={filtersOpen}
                      aria-label="Filters"
                      className={cn(
                        "flex h-10 shrink-0 items-center gap-1.5 rounded border px-2 text-[12px] transition-colors",
                        filtersOpen || hasActiveFilters(filters)
                          ? "border-green text-text"
                          : "border-border2 text-subtle",
                      )}
                    >
                      <svg
                        width="17"
                        height="17"
                        viewBox="0 0 24 24"
                        fill="none"
                        stroke="currentColor"
                        strokeWidth="2"
                      >
                        <path
                          d="M3 5h18l-7 8v6l-4-2v-4z"
                          strokeLinejoin="round"
                        />
                      </svg>
                      <span className={cn(skeletons.length > 0 && "hidden min-[400px]:inline")}>Filters</span>
                      {filterCount > 0 && (
                        <span className="flex h-4 min-w-4 items-center justify-center rounded-full bg-green px-1 text-[10px] font-bold text-bg">
                          {filterCount}
                        </span>
                      )}
                      <span
                        className={cn(
                          "text-[10px] transition-transform",
                          filtersOpen && "rotate-180",
                        )}
                      >
                        ▾
                      </span>
                    </button>
                  )}
                </div>

                <ListMeta
                  lastUpdated={lastUpdated}
                  dataSource={dataSource}
                  statsUpdatedAt={statsUpdatedAt}
                  className="mt-1.5 whitespace-nowrap px-2 text-[clamp(8px,2.8vw,11px)]"
                />

                {effectiveUid && filtersOpen && (
                  <div className="pt-3">
                    <TierFilterBar
                      filters={filters}
                      setFilters={setFilters}
                      options={filterOptions}
                      setCode={glyphCode}
                      hideArt={hideArt}
                      setHideArt={setHideArt}
                      onSearch={() => setSearchOpen(true)}
                      {...gradeToggle}
                      stacked
                    />
                  </div>
                )}
              </>
            ) : (
              <div
                ref={filterBarLayout.rowRef}
                className={cn(
                  "grid items-end gap-x-[clamp(0.75rem,2.5vw,2.5rem)]",
                  filterBarLayout.twoRows && "grid-cols-[minmax(0,1fr)_max-content] gap-y-3",
                  !filterBarLayout.twoRows &&
                    (filterBarLayout.centered
                      ? "grid-cols-[minmax(0,1fr)_auto_minmax(0,1fr)]"
                      : "grid-cols-[minmax(0,max-content)_minmax(0,1fr)_max-content]"),
                )}
              >
                <div ref={filterBarLayout.headingRef} className="w-fit min-w-0 max-w-full">
                  <h1
                    className={cn(
                      "grid grid-cols-[minmax(0,auto)_auto] gap-x-1.5",
                      "font-display leading-none tracking-[0.12em]",
                    )}
                  >
                    <FilterGroup label="SET" stacked={false} className="invisible col-start-1 row-start-1">
                      <div className="h-10" />
                    </FilterGroup>
                    <div className="col-start-1 row-start-1 min-w-0">
                      <SetGlyphDropdown
                        sets={tierListSets}
                        activeCode={current}
                        glyphCode={glyphCode}
                        label={setMeta?.name?.toUpperCase() ?? current}
                        isMobile={false}
                        size="toolbar"
                        loading={!sets}
                        hrefFor={setHref}
                        labelRef={filterBarLayout.labelRef}
                      />
                    </div>
                    {skeletons.length > 0 && (
                      <div className="col-start-2 row-start-1 self-end">
                        <SkeletonsButton href={archetypesHref} />
                      </div>
                    )}
                  </h1>
                </div>

                {effectiveUid ? (
                  <div
                    ref={filterBarLayout.filterRef}
                    className={cn("justify-self-center", filterBarLayout.twoRows && "col-span-2 row-start-2")}
                  >
                    <TierFilterBar
                      filters={filters}
                      setFilters={setFilters}
                      options={filterOptions}
                      setCode={glyphCode}
                      hideArt={hideArt}
                      setHideArt={setHideArt}
                      onSearch={() => setSearchOpen(true)}
                      {...gradeToggle}
                      maxWidth={filterBarLayout.filterSpace}
                      onMinWidth={filterBarLayout.setMinFilterWidth}
                    />
                  </div>
                ) : (
                  <div />
                )}

                <ListMeta
                  rootRef={filterBarLayout.metaRef}
                  lastUpdated={lastUpdated}
                  dataSource={dataSource}
                  statsUpdatedAt={statsUpdatedAt}
                  alignEnd
                  className="w-auto flex-col items-end justify-self-end gap-y-1.5 whitespace-nowrap text-[11px]"
                />
              </div>
            )}
          </div>

          {effectiveUid ? (
            <TierGrid
              setCode={current}
              uid={effectiveUid}
              graders={graders}
              comparison={comparison}
              filters={filters}
              hideArt={hideArt}
              dataGrades={placeByData}
              deck={deck}
              stickyTop={headerHeight}
            />
          ) : (
            <div className="flex items-center justify-center border border-border bg-surface text-subtle text-[14px] min-h-[300px]">
              No tier list is available for {current} yet.
            </div>
          )}

          <div className="flex items-center justify-between gap-3 pt-2">
            <div className="flex flex-wrap items-center gap-x-4 gap-y-1">
              {graders.length > 0 && (
                <div className="flex items-center gap-x-2">
                  <span className="font-mono text-[10px] md:text-[12px] text-subtle">Set Reviews:</span>
                  <div className="flex items-center gap-x-3.5">
                    {graders.map((grader) => (
                      <SourceLink key={grader.uid} uid={grader.uid} label={`${grader.name}'s`} />
                    ))}
                  </div>
                </div>
              )}
              {uid && (
                <SourceLink uid={uid} label={graders.length > 0 ? "Live: LLU" : "Set Review List: LLU"} />
              )}
            </div>
            <a
              href="https://www.17lands.com/tier_lists"
              target="_blank"
              rel="noreferrer"
              className="font-mono text-[10px] md:text-[12px] text-subtle hover:text-green transition-colors no-underline whitespace-nowrap"
            >
              Powered by 17Lands
            </a>
          </div>
        </main>

        {searchOpen && (
          <TierCardSearch cards={tierData ?? []} setCode={current} onClose={() => setSearchOpen(false)} />
        )}

        {skeletonsOpen && skeletons.length > 0 && (
          <SkeletonsModal
            skeletons={skeletons}
            setCode={current}
            activePair={pair}
            pairHref={(colors) => `${archetypesHref}/${colors.toLowerCase()}`}
            onClose={closeSkeletons}
          />
        )}
      </div>
    </GradeGuideProvider>
  );
}

function withParam(params: URLSearchParams, key: string, value: string | null): URLSearchParams {
  const next = new URLSearchParams(params);
  if (value) {
    next.set(key, value);
  } else {
    next.delete(key);
  }
  return next;
}

function useCenteredFilterBar(setCode: string, isMobile: boolean) {
  const rowRef = useRef<HTMLDivElement>(null);
  const headingRef = useRef<HTMLDivElement>(null);
  const labelRef = useRef<HTMLSpanElement>(null);
  const filterRef = useRef<HTMLDivElement>(null);
  const metaRef = useRef<HTMLDivElement>(null);
  const [centered, setCentered] = useState(false);
  const [filterSpace, setFilterSpace] = useState<number | undefined>(undefined);
  const [minFilterWidth, setMinFilterWidth] = useState(0);
  const [twoRows, setTwoRows] = useState(false);

  useEffect(() => {
    const row = rowRef.current;
    const heading = headingRef.current;
    if (!row || !heading) {
      return;
    }
    const measure = () => {
      const label = labelRef.current;
      const truncatedWidth = label ? label.scrollWidth - label.clientWidth : 0;
      const fullHeadingWidth = heading.offsetWidth + truncatedWidth;
      const filterWidth = filterRef.current?.offsetWidth ?? 0;
      const gap = parseFloat(getComputedStyle(row).columnGap) || 0;
      const metaWidth = metaRef.current?.offsetWidth ?? 0;
      const besideSpace = row.clientWidth - fullHeadingWidth - metaWidth - 2 * gap;
      const stacked = minFilterWidth > besideSpace;
      setTwoRows(stacked);
      setCentered(!stacked && 2 * (fullHeadingWidth + gap) + filterWidth <= row.clientWidth);
      setFilterSpace(stacked ? row.clientWidth : besideSpace);
    };
    const observer = new ResizeObserver(measure);
    for (const element of [row, heading, filterRef.current, metaRef.current]) {
      if (element) {
        observer.observe(element);
      }
    }
    document.fonts.ready.then(measure);
    return () => observer.disconnect();
  }, [setCode, isMobile, minFilterWidth]);

  return {
    rowRef,
    headingRef,
    labelRef,
    filterRef,
    metaRef,
    centered,
    twoRows,
    filterSpace,
    setMinFilterWidth,
  };
}

function SkeletonsButton({ href }: { href: string }) {
  return (
    <Link
      to={href}
      state={OPENED_IN_APP}
      className="flex h-10 shrink-0 items-center rounded border border-border2 px-2 font-display text-[14px] leading-none tracking-[0.14em] text-text transition-colors no-underline hover:border-green hover:text-green md:px-2.5"
    >
      <span className="-translate-y-px">ARCHETYPES</span>
    </Link>
  );
}

function SourceLink({ uid, label }: { uid: string; label: string }) {
  return (
    <Tooltip label="View on 17Lands" side="top">
      <a
        href={`https://www.17lands.com/tier_list/${uid}`}
        target="_blank"
        rel="noreferrer"
        className="font-mono flex items-center gap-1 text-[10px] md:text-[12px] text-subtle hover:text-green transition-colors no-underline"
      >
        {label}
        <ExternalLink size={11} />
      </a>
    </Tooltip>
  );
}

function ListMeta({
  lastUpdated,
  dataSource,
  statsUpdatedAt,
  alignEnd = false,
  rootRef,
  className,
}: {
  lastUpdated: string | null;
  dataSource: { setCode: string; updatedAt: string } | null;
  statsUpdatedAt?: string;
  alignEnd?: boolean;
  rootRef?: Ref<HTMLDivElement>;
  className?: string;
}) {
  const listUpdated = lastUpdated ? lastUpdatedLabel(lastUpdated) : null;
  const statsUpdated = statsUpdatedAt ? lastUpdatedLabel(statsUpdatedAt) : null;
  const updated = dataSource ? statsUpdated : listUpdated;
  const otherUpdated = dataSource ? listUpdated : statsUpdated;
  const dataLabel = (
    <>
      17LANDS DATA
      <ExternalLink size={11} />
    </>
  );
  const reviewLabel = (
    <>
      SET REVIEW GRADES
      <GradeGuideIcon className="ml-1.5" />
    </>
  );
  return (
    <div
      ref={rootRef}
      className={cn("font-mono flex w-full items-center justify-between gap-x-4 text-subtle", className)}
    >
      <span className={cn("grid [&>*]:col-start-1 [&>*]:row-start-1", alignEnd && "justify-items-end")}>
        {dataSource ? (
          <a
            href={cardDataUrl(dataSource.setCode)}
            target="_blank"
            rel="noreferrer"
            className={cn(
              "flex items-center gap-1.5 tracking-[0.16em] text-subtle no-underline",
              "transition-colors hover:text-green",
            )}
          >
            {dataLabel}
          </a>
        ) : (
          <GradeGuideTrigger className="tracking-[0.16em]">{reviewLabel}</GradeGuideTrigger>
        )}
        <span aria-hidden className={cn("invisible flex items-center tracking-[0.16em]", !dataSource && "gap-1.5")}>
          {dataSource ? reviewLabel : dataLabel}
        </span>
      </span>
      <span
        className={cn("grid tracking-[0.06em] [&>*]:col-start-1 [&>*]:row-start-1", alignEnd && "justify-items-end")}
      >
        <span className={cn(!updated && "invisible")}>{updated ?? "Last updated"}</span>
        {otherUpdated && (
          <span aria-hidden className="invisible">
            {otherUpdated}
          </span>
        )}
      </span>
    </div>
  );
}

// Relative time while fresh; absolute "JUN 3" once a week old ("JUN 3 '25" across years)
function lastUpdatedLabel(iso: string): string {
  const updated = new Date(iso);
  const now = new Date();
  const ageDays = (now.getTime() - updated.getTime()) / 86_400_000;
  if (ageDays < 7) {
    const rel = relativeTime(iso, now);
    return rel === "now" ? "Updated just now" : `Last updated ${rel} ago`;
  }
  const monthDay = updated.toLocaleDateString("en-US", { month: "short", day: "numeric" });
  const shortYear = ` '${String(updated.getFullYear() % 100).padStart(2, "0")}`;
  const sameYear = updated.getFullYear() === now.getFullYear();
  return `Last updated ${monthDay}${sameYear ? "" : shortYear}`;
}
