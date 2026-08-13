import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { AppHeader } from "../components/AppHeader";
import { ExternalLink } from "../components/Icons";
import { setGlyphCode } from "../components/Brand";
import { TierFilterBar } from "../components/TierFilterBar";
import { TierGrid } from "../components/TierGrid";
import { GradeGuideIcon, GradeGuideProvider, GradeGuideTrigger } from "../components/TierGuide";
import { TierSetDropdown } from "../components/TierSetDropdown";
import { Tooltip } from "../components/Tooltip";
import { SkeletonsModal } from "../components/SkeletonsModal";
import { skeletonsFor } from "../data/skeletons";
import { useSets } from "../data/hooks";
import { relativeTime } from "../data/utils";
import { cn } from "../lib/utils";
import { useIsMobile } from "../lib/use-is-mobile";
import { ACTIVE_SET_CODE, TIER_LIST_PREVIEW_SETS } from "../data/constants";
import {
  activeFilterCount,
  buildTierListSets,
  EMPTY_FILTERS,
  hasActiveFilters,
  resolveTierList,
  tierFilterOptions,
  useHideArt,
  useTierList,
  type TierFilters,
} from "../data/tierList";

export function TierListPage({ skeletonsOpen = false }: { skeletonsOpen?: boolean }) {
  const { data: sets } = useSets();
  const isMobile = useIsMobile();
  const navigate = useNavigate();
  const { setCode } = useParams();
  const [filters, setFilters] = useState<TierFilters>(EMPTY_FILTERS);
  const [hideArt, setHideArt] = useHideArt();
  const [filtersOpen, setFiltersOpen] = useState(false);
  const [headerHeight, setHeaderHeight] = useState(0);
  const headerRef = useRef<HTMLDivElement>(null);

  const filterCount = activeFilterCount(filters);

  const liveSet = sets?.find((s) => s.isActive)?.code ?? ACTIVE_SET_CODE;
  const tierListSets = useMemo(() => buildTierListSets(sets), [sets]);
  const current = setCode?.toUpperCase() ?? tierListSets[0]?.code ?? liveSet;
  const pickSet = (code: string) => navigate(`/tier-list/${code}`);
  const setMeta = tierListSets.find((s) => s.code === current);
  const { uid, graders, comparison, effectiveUid } = resolveTierList(current);
  const glyphCode = setMeta ? setGlyphCode(setMeta) : current;
  const skeletons = useMemo(() => skeletonsFor(current), [current]);

  const { data: tierData, lastUpdated } = useTierList(effectiveUid);
  const filterOptions = useMemo(
    () => tierFilterOptions(tierData ?? []),
    [tierData],
  );
  const filtersReady = Boolean(tierData?.length);

  useEffect(() => {
    setFilters(EMPTY_FILTERS);
  }, [effectiveUid]);

  useEffect(() => {
    if (!isMobile) {
      setFilters((prev) => (prev.colors.length > 0 ? { ...prev, colors: [] } : prev));
    }
  }, [isMobile]);

  useEffect(() => {
    const header = headerRef.current;
    if (!header) return;
    const ro = new ResizeObserver(() => setHeaderHeight(header.offsetHeight));
    ro.observe(header);
    setHeaderHeight(header.offsetHeight);
    return () => ro.disconnect();
  }, []);

  return (
    <GradeGuideProvider>
      <div className="bg-bg text-text min-h-screen flex flex-col animate-fadeIn">
        <AppHeader subtitle="TIER LIST" />
        <main className="flex flex-col w-full px-2 md:px-[15px] pb-4 overflow-x-clip">
          <div ref={headerRef} className="sticky top-0 z-20 bg-bg py-2 md:py-3">
            {isMobile ? (
              <>
                <div className="flex items-center gap-2">
                  <h1 className="font-display tracking-[0.12em] flex flex-1 items-center gap-2 leading-none min-w-0">
                    <TierSetDropdown
                      sets={tierListSets}
                      activeCode={current}
                      glyphCode={glyphCode}
                      label={setMeta?.name?.toUpperCase() ?? current}
                      isMobile
                      loading={!sets}
                      onChange={pickSet}
                      triggerClassName="h-10 px-2.5"
                    />
                  </h1>

                  {skeletons.length > 0 && <SkeletonsButton onClick={() => navigate(`/tier-list/${current}/archetypes`)} />}

                  {effectiveUid && (
                    <button
                      type="button"
                      onClick={() => setFiltersOpen((open) => !open)}
                      aria-expanded={filtersOpen}
                      aria-label="Filters"
                      disabled={!filtersReady}
                      className={cn(
                        "flex h-10 shrink-0 items-center gap-1.5 rounded border px-2 text-[12px] transition-colors",
                        filtersOpen || hasActiveFilters(filters)
                          ? "border-green text-text"
                          : "border-border2 text-muted",
                        !filtersReady && "opacity-50",
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
                  className="mt-1.5 whitespace-nowrap text-[clamp(8px,2.8vw,11px)]"
                />

                {effectiveUid && filtersReady && filtersOpen && (
                  <div className="pt-3">
                    <TierFilterBar
                      filters={filters}
                      setFilters={setFilters}
                      options={filterOptions}
                      setCode={glyphCode}
                      hideArt={hideArt}
                      setHideArt={setHideArt}
                      stacked
                    />
                  </div>
                )}
              </>
            ) : (
              <div className="grid items-center gap-x-[clamp(0.75rem,2.5vw,2.5rem)] grid-cols-[minmax(0,1fr)_auto] min-[1500px]:grid-cols-[minmax(0,1fr)_auto_minmax(0,1fr)]">
                <div className="w-fit min-w-0 max-w-full">
                  <h1 className="font-display tracking-[0.12em] flex items-center gap-3 leading-none min-w-0">
                    <TierSetDropdown
                      sets={tierListSets}
                      activeCode={current}
                      glyphCode={glyphCode}
                      label={setMeta?.name?.toUpperCase() ?? current}
                      isMobile={false}
                      loading={!sets}
                      onChange={pickSet}
                    />
                    {skeletons.length > 0 && (
                      <SkeletonsButton onClick={() => navigate(`/tier-list/${current}/archetypes`)} />
                    )}
                  </h1>
                  <ListMeta lastUpdated={lastUpdated} className="mt-1 pl-[2px] text-[11px]" />
                </div>

                {effectiveUid && filtersReady ? (
                  <div className="justify-self-center -translate-y-1">
                    <TierFilterBar
                      filters={filters}
                      setFilters={setFilters}
                      options={filterOptions}
                      setCode={glyphCode}
                      hideArt={hideArt}
                      setHideArt={setHideArt}
                    />
                  </div>
                ) : (
                  <div />
                )}

                <div className="hidden min-[1500px]:block" />
              </div>
            )}
          </div>

          {effectiveUid ? (
            <TierGrid
              uid={effectiveUid}
              graders={graders}
              comparison={comparison}
              filters={filters}
              hideArt={hideArt}
              stickyTop={headerHeight}
            />
          ) : (
            <div className="flex items-center justify-center border border-border bg-surface text-muted text-[14px] min-h-[300px]">
              No tier list is available for {current} yet.
            </div>
          )}

          <div className="flex items-center justify-between gap-3 pt-2">
            <div className="flex flex-wrap items-center gap-x-4 gap-y-1">
              {graders.length > 0 && (
                <div className="flex items-center gap-x-2">
                  <span className="mono text-[10px] md:text-[12px] text-muted">Set Reviews:</span>
                  <div className="flex items-center gap-x-3.5">
                    {graders.map((grader) => (
                      <SourceLink key={grader.uid} uid={grader.uid} label={`${grader.name}'s`} />
                    ))}
                  </div>
                </div>
              )}
              {uid && (
                <div className="flex items-center gap-x-2">
                  <span className="mono text-[10px] md:text-[12px] text-muted">
                    {graders.length > 0 ? "Live:" : "Set Review List:"}
                  </span>
                  <SourceLink uid={uid} label="LLU" />
                </div>
              )}
            </div>
            <a
              href={`https://www.17lands.com/tier_list/${effectiveUid ?? ""}`}
              target="_blank"
              rel="noreferrer"
              className="mono text-[10px] md:text-[12px] text-muted hover:text-green transition-colors no-underline whitespace-nowrap"
            >
              Powered by 17Lands
            </a>
          </div>
        </main>

        {skeletonsOpen && skeletons.length > 0 && (
          <SkeletonsModal
            skeletons={skeletons}
            setCode={current}
            onClose={() => navigate(`/tier-list/${current}`)}
          />
        )}
      </div>
    </GradeGuideProvider>
  );
}

function SkeletonsButton({ onClick }: { onClick: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="relative flex h-10 shrink-0 items-center rounded border border-border2 px-2 font-display text-[14px] leading-none tracking-[0.14em] text-text transition-colors hover:border-green hover:text-green md:h-9 md:px-2.5"
    >
      <span className="-translate-y-px">ARCHETYPES</span>
      <span className="absolute -right-1.5 -top-2.5 z-10 rounded-full border border-green bg-green px-1.5 py-0.5 font-sans text-[9px] font-bold leading-none tracking-wide text-bg">
        NEW
      </span>
    </button>
  );
}

function SourceLink({ uid, label }: { uid: string; label: string }) {
  return (
    <Tooltip label="View on 17Lands" side="top">
      <a
        href={`https://www.17lands.com/tier_list/${uid}`}
        target="_blank"
        rel="noreferrer"
        className="mono flex items-center gap-1 text-[10px] md:text-[12px] text-muted hover:text-green transition-colors no-underline"
      >
        {label}
        <ExternalLink size={11} />
      </a>
    </Tooltip>
  );
}

function ListMeta({
  lastUpdated,
  className,
}: {
  lastUpdated: string | null;
  className?: string;
}) {
  const updated = lastUpdated ? lastUpdatedLabel(lastUpdated) : null;
  return (
    <div className={cn("mono flex w-full items-center justify-between gap-x-4 text-muted", className)}>
      <GradeGuideTrigger className="tracking-[0.16em]">
        SET REVIEW GRADES
        <GradeGuideIcon className="ml-1.5" />
      </GradeGuideTrigger>
      {updated && <span className="tracking-[0.06em]">{updated}</span>}
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
