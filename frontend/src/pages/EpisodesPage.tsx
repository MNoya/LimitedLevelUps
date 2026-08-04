import { useEffect, useLayoutEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";
import { SiApplepodcasts, SiRss, SiSpotify, SiYoutube } from "react-icons/si";
import type { IconType } from "react-icons";
import {
  BarChart3,
  BookOpen,
  CalendarArrowDown,
  CalendarArrowUp,
  ChevronsLeft,
  GraduationCap,
  Headphones,
  Layers,
  LayoutGrid,
  Leaf,
  Library,
  ListOrdered,
  Mic,
  Package,
  Search,
  SearchX,
  SlidersHorizontal,
  X,
  Zap,
  type LucideIcon,
} from "lucide-react";
import { PageShell } from "../components/PageShell";
import { EpisodeCard } from "../components/EpisodeCard";
import { ShortCard } from "../components/ShortCard";
import { FilterDropdown, type FilterOption } from "../components/FilterDropdown";
import { GoToTopButton } from "../components/GoToTopButton";
import { SwipeableDrawer } from "../components/SwipeableDrawer";
import { Tooltip } from "../components/Tooltip";
import { CUT_CORNER_CHAMFER } from "../components/ChamferCta";
import { Crossfade } from "../components/Crossfade";
import { SetGlyph } from "../components/Brand";
import { useMediaFeed } from "../data/hooks";
import { EPISODE_CATEGORIES, categoryFromSlug, categorySlug, type Episode, type EpisodeCategory } from "../data/episodes";
import { LISTEN_ON } from "../data/site";
import { cn } from "../lib/utils";
import { useEpisodeGridColumns, useIsMobile } from "../lib/use-is-mobile";
import { TOGGLE_ACTIVE, TOGGLE_INACTIVE } from "../lib/toggle-styles";

const SORT_OPTIONS: { value: SortKey; label: string; icon: LucideIcon }[] = [
  { value: "newest", label: "Newest", icon: CalendarArrowDown },
  { value: "oldest", label: "Oldest", icon: CalendarArrowUp },
];

const renderSetValue = (option: FilterOption) => (
  <span className="flex min-w-0 items-center gap-2">
    <span className="hidden shrink-0 text-[11px] tracking-[0.22em] text-muted sm:inline">SET</span>
    <span className="hidden h-3.5 w-px shrink-0 bg-border2 sm:block" />
    {option.value ? (
      <span className="flex min-w-0 items-center gap-1.5 truncate text-green">
        <SetGlyph code={option.value} size={18} className="text-green" />
        {option.value}
      </span>
    ) : (
      <span className="truncate text-subtle">All sets</span>
    )}
  </span>
);

const CATEGORY_ICON: Record<EpisodeCategory, LucideIcon> = {
  "Set Review": BookOpen,
  Metagame: BarChart3,
  Draft: Layers,
  Sealed: Package,
  Rankings: ListOrdered,
  Coaching: GraduationCap,
  Guest: Mic,
  Evergreen: Leaf,
};

const LISTEN_ICONS: Record<string, IconType> = {
  Apple: SiApplepodcasts,
  Spotify: SiSpotify,
  YouTube: SiYoutube,
  RSS: SiRss,
};

type SortKey = "newest" | "oldest";

const PAGE_SIZE = 12;

const setCodeOf = (ep: Episode) => ep.setCode ?? null;
const setNameOf = (ep: Episode) => ep.setName ?? ep.setCode ?? "";
const setLandingPath = (code: string) => `/episodes/${code.toLowerCase()}`;

export function EpisodesPage() {
  const { data: episodes, isPending, isError, thumbnailsPending, setsReady } = useMediaFeed();
  const { categorySlug: slug } = useParams<{ categorySlug?: string }>();
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const [query, setQuery] = useState("");
  const [sort, setSort] = useState<SortKey>("newest");
  const [visible, setVisible] = useState(PAGE_SIZE);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [railCollapsed, setRailCollapsed] = useState(false);
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const isMobile = useIsMobile();
  const gridColumns = useEpisodeGridColumns();
  const sentinelRef = useRef<HTMLDivElement>(null);
  const contentTopRef = useRef<HTMLDivElement>(null);
  const searchWrapRef = useRef<HTMLDivElement>(null);
  const listRef = useRef<HTMLDivElement>(null);
  const [searchIndent, setSearchIndent] = useState(0);

  useLayoutEffect(() => {
    const measure = () => {
      const search = searchWrapRef.current;
      const list = listRef.current;
      if (!search || !list || window.innerWidth < 1024) {
        setSearchIndent(0);
        return;
      }
      const contentLeft = list.getBoundingClientRect().left + parseFloat(getComputedStyle(list).paddingLeft);
      setSearchIndent(Math.max(0, Math.round(search.getBoundingClientRect().left - contentLeft)));
    };
    measure();
    window.addEventListener("resize", measure);
    return () => window.removeEventListener("resize", measure);
  }, [railCollapsed]);

  const all = episodes ?? [];
  const setCodesBySlug = useMemo(() => {
    const map = new Map<string, string>();
    for (const ep of episodes ?? []) {
      if (ep.setCode) {
        map.set(ep.setCode.toLowerCase(), ep.setCode);
      }
    }
    return map;
  }, [episodes]);

  const slugLower = slug?.toLowerCase() ?? null;
  const shortsView = slugLower === "shorts";
  const audioView = slugLower === "audio";
  const activeCategory = slug ? categoryFromSlug(slug) : null;
  const pathSet = slugLower && !shortsView && !audioView && !activeCategory ? setCodesBySlug.get(slugLower) ?? null : null;
  const activeSet = pathSet ?? params.get("set");
  const awaitingSetSlug = !!slugLower && !shortsView && !audioView && !activeCategory && !setsReady;

  useEffect(() => {
    const legacyCategory = params.get("category");
    const legacyShorts = params.get("type") === "shorts";
    if (legacyCategory || legacyShorts) {
      const next = new URLSearchParams(params);
      next.delete("category");
      next.delete("type");
      const matched = EPISODE_CATEGORIES.find((category) => category === legacyCategory);
      const pathname = legacyShorts
        ? "/episodes/shorts"
        : matched
          ? `/episodes/${categorySlug(matched)}`
          : "/episodes";
      navigate({ pathname, search: next.toString() }, { replace: true });
      return;
    }
    if (!episodes) {
      return;
    }
    const querySet = params.get("set");
    if (!slug && querySet && setCodesBySlug.has(querySet.toLowerCase())) {
      const next = new URLSearchParams(params);
      next.delete("set");
      navigate({ pathname: setLandingPath(querySet), search: next.toString() }, { replace: true });
      return;
    }
    if (setsReady && slugLower && !shortsView && !audioView && !activeCategory && !setCodesBySlug.has(slugLower)) {
      navigate({ pathname: "/episodes", search: params.toString() }, { replace: true });
    }
  }, [params, slug, slugLower, navigate, episodes, setCodesBySlug, shortsView, audioView, activeCategory, setsReady]);

  const categoryPath = shortsView
    ? "/episodes/shorts"
    : audioView
      ? "/episodes/audio"
      : activeCategory
        ? `/episodes/${categorySlug(activeCategory)}`
        : null;

  const contentTopOffset = () => {
    const root = contentTopRef.current;
    return root ? root.getBoundingClientRect().top + window.scrollY : 0;
  };

  const navTo = (pathname: string, querySet: string | null) => {
    const next = new URLSearchParams(params);
    next.delete("set");
    if (querySet) {
      next.set("set", querySet);
    }
    navigate({ pathname, search: next.toString() });
    setVisible(PAGE_SIZE);
    const contentTop = contentTopOffset();
    if (window.scrollY > contentTop) {
      window.scrollTo({ top: contentTop });
    }
  };
  const setCategory = (category: EpisodeCategory | null) => {
    if (category) {
      navTo(`/episodes/${categorySlug(category)}`, activeSet);
    } else if (activeSet) {
      navTo(setLandingPath(activeSet), null);
    } else {
      navTo("/episodes", null);
    }
  };
  const chooseSet = (code: string | null) => {
    if (!code) {
      navTo(categoryPath ?? "/episodes", null);
    } else if (categoryPath) {
      navTo(categoryPath, code);
    } else {
      navTo(setLandingPath(code), null);
    }
  };
  const showShorts = () => navTo("/episodes/shorts", activeSet);
  const showAudio = () => navTo("/episodes/audio", activeSet);

  const longform = useMemo(() => all.filter((ep) => !ep.isShort), [all]);
  const shorts = useMemo(() => all.filter((ep) => ep.isShort), [all]);
  const withAudio = useMemo(() => longform.filter((ep) => Boolean(ep.audioUrl)), [longform]);
  const pool = shortsView ? shorts : audioView ? withAudio : longform;

  const longformInSet = useMemo(
    () => (activeSet ? longform.filter((ep) => setCodeOf(ep) === activeSet) : longform),
    [longform, activeSet],
  );
  const shortsInSet = useMemo(
    () => (activeSet ? shorts.filter((ep) => setCodeOf(ep) === activeSet) : shorts),
    [shorts, activeSet],
  );
  const audioInSet = useMemo(
    () => (activeSet ? withAudio.filter((ep) => setCodeOf(ep) === activeSet) : withAudio),
    [withAudio, activeSet],
  );

  const needle = query.trim().toLowerCase();
  const scopedLongform = useMemo(() => longformInSet.filter((ep) => matchesQuery(ep, needle)), [longformInSet, needle]);
  const scopedShorts = useMemo(() => shortsInSet.filter((ep) => matchesQuery(ep, needle)), [shortsInSet, needle]);
  const scopedAudio = useMemo(() => audioInSet.filter((ep) => matchesQuery(ep, needle)), [audioInSet, needle]);

  const counts = useMemo(() => {
    const map = new Map<EpisodeCategory, number>();
    for (const ep of scopedLongform) {
      map.set(ep.category, (map.get(ep.category) ?? 0) + 1);
    }
    return map;
  }, [scopedLongform]);

  const setMeta = useMemo(() => {
    const map = new Map<string, { name: string; count: number; released: string | null }>();
    for (const ep of pool) {
      const code = ep.setCode;
      if (!code) {
        continue;
      }
      const entry = map.get(code);
      if (entry) {
        entry.count += 1;
        entry.released = entry.released ?? ep.setReleasedAt ?? null;
      } else {
        map.set(code, { name: setNameOf(ep), count: 1, released: ep.setReleasedAt ?? null });
      }
    }
    return map;
  }, [pool]);

  const setFilterOptions = useMemo<FilterOption[]>(() => {
    const entries = [...setMeta.entries()].sort((a, b) => compareReleaseDesc(a[1].released, b[1].released));
    return [
      { value: "", label: "All sets" },
      ...entries.map(([code, meta]) => ({ value: code, label: meta.name })),
    ];
  }, [setMeta]);

  const renderSetOption = (option: FilterOption) => {
    const count = option.value ? setMeta.get(option.value)?.count : pool.length;
    return (
      <span className="flex w-full min-w-0 items-center gap-2.5">
        {option.value ? <SetGlyph code={option.value} size={20} /> : <span className="w-5 shrink-0" />}
        <span className="flex-1 truncate">{option.label}</span>
        {count != null && <span className="mono text-[12px] tabular-nums text-muted shrink-0">{count}</span>}
      </span>
    );
  };

  const setFilterDropdown = (
    <FilterDropdown
      value={activeSet ?? ""}
      options={setFilterOptions}
      onChange={(v) => chooseSet(v || null)}
      renderValue={renderSetValue}
      renderOption={renderSetOption}
      searchPlaceholder="Search sets or codes…"
      triggerClassName="!min-w-[124px] md:!min-w-[200px] !h-10 !py-0 hover:!bg-surface2"
      mobileCentered
    />
  );

  const filtered = useMemo(() => {
    const base = shortsView ? scopedShorts : audioView ? scopedAudio : scopedLongform;
    const rows = !shortsView && !audioView && activeCategory ? base.filter((ep) => ep.category === activeCategory) : base;
    return sortEpisodes(rows, sort);
  }, [shortsView, audioView, scopedShorts, scopedAudio, scopedLongform, activeCategory, sort]);

  useEffect(() => {
    setExpandedId(null);
  }, [slug, activeSet, audioView, shortsView, sort, query]);

  useEffect(() => {
    if (visible >= filtered.length) {
      return;
    }
    const sentinel = sentinelRef.current;
    if (!sentinel) {
      return;
    }
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries[0].isIntersecting) {
          setVisible((current) => Math.min(current + PAGE_SIZE, filtered.length));
        }
      },
      { rootMargin: "600px" },
    );
    observer.observe(sentinel);
    return () => observer.disconnect();
  }, [visible, filtered.length]);

  const chooseAll = () => {
    setCategory(null);
    setDrawerOpen(false);
  };
  const chooseCategory = (category: EpisodeCategory) => {
    setCategory(category);
    setDrawerOpen(false);
  };
  const chooseShorts = () => {
    showShorts();
    setDrawerOpen(false);
  };
  const chooseAudio = () => {
    showAudio();
    setDrawerOpen(false);
  };

  const mobileFilter = shortsView
    ? { label: "Shorts", icon: Zap }
    : audioView
      ? { label: "Audio", icon: Headphones }
      : activeCategory
        ? { label: activeCategory, icon: CATEGORY_ICON[activeCategory] }
        : null;

  const railProps = {
    allCount: scopedLongform.length,
    shortsCount: scopedShorts.length,
    shortsExist: shorts.length > 0,
    audioCount: scopedAudio.length,
    audioExist: withAudio.length > 0,
    counts,
    activeCategory,
    shortsView,
    audioView,
    onAll: chooseAll,
    onCategory: chooseCategory,
    onShorts: chooseShorts,
    onAudio: chooseAudio,
  };

  return (
    <PageShell subtitle="EPISODES" flushFooter>
      <div ref={contentTopRef} className="flex min-h-full flex-1">
        <aside
          className={cn(
            "hidden lg:block shrink-0 self-stretch",
            "border-r border-border bg-surface",
            "transition-[width] duration-300 ease-[cubic-bezier(0.22,1,0.36,1)]",
            railCollapsed ? "w-[57px]" : "w-[clamp(196px,18vw,244px)]",
          )}
        >
          <div className="sticky top-0 max-h-screen overflow-y-auto overflow-x-hidden">
            <CategoryRail
              {...railProps}
              collapsed={railCollapsed}
              onCollapse={() => setRailCollapsed(true)}
              onExpand={() => setRailCollapsed(false)}
            />
          </div>
        </aside>

        <div className="min-w-0 flex-1">
          <div className="sticky top-0 z-10 flex h-[60px] items-center gap-2.5 border-b border-border bg-surface px-4 md:px-6">
            <button
              type="button"
              onClick={() => setDrawerOpen(true)}
              className={cn(
                "lg:hidden shrink-0 flex h-10 items-center gap-2 border px-3 py-0 font-display text-[13px] tracking-[0.12em] transition-colors",
                mobileFilter ? TOGGLE_ACTIVE : "border-border2 text-text hover:bg-surface2",
              )}
            >
              {mobileFilter ? (
                <>
                  <mobileFilter.icon size={14} strokeWidth={2} className="shrink-0" />
                  <span className="uppercase">{mobileFilter.label}</span>
                </>
              ) : (
                <>
                  <SlidersHorizontal size={14} strokeWidth={2} className="shrink-0" />
                  <span>CATEGORIES</span>
                </>
              )}
            </button>
            {isMobile ? (
              <span className="shrink-0">{setFilterDropdown}</span>
            ) : (
              <Tooltip label="Filter by set" side="bottom">
                <span className="shrink-0">{setFilterDropdown}</span>
              </Tooltip>
            )}
            <div ref={searchWrapRef} className="relative min-w-0 flex-1">
              <Search
                size={15}
                strokeWidth={2}
                className={cn(
                  "pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 transition-colors",
                  query.trim() ? "text-green" : "text-dim",
                )}
              />
              <input
                value={query}
                onChange={(e) => {
                  setQuery(e.target.value);
                  setVisible(PAGE_SIZE);
                }}
                placeholder="Search"
                className={cn(
                  "w-full h-10 bg-bg border pl-9 pr-3.5 text-[14px] text-text placeholder:text-dim outline-none transition-colors focus:border-green",
                  query.trim() ? "border-green" : "border-border2",
                )}
              />
            </div>
            <SortControl value={sort} onChange={setSort} className="hidden sm:flex shrink-0" />
            <div className="ml-1 hidden xl:flex items-center gap-2.5">
              {LISTEN_ON.map(({ label, url }) => {
                const Icon = LISTEN_ICONS[label];
                return (
                  <Tooltip key={label} label={label} side="bottom">
                    <a
                      href={url}
                      target="_blank"
                      rel="noreferrer"
                      aria-label={label}
                      className="inline-flex h-10 w-10 items-center justify-center bg-surface2 text-subtle no-underline transition-colors hover:bg-border hover:text-green"
                      style={{ clipPath: CUT_CORNER_CHAMFER }}
                    >
                      {Icon ? <Icon className="text-[15px]" size={15} /> : label}
                    </a>
                  </Tooltip>
                );
              })}
            </div>
          </div>

          <div ref={listRef} className="px-4 md:px-6 pt-6 pb-4">
            {awaitingSetSlug || (isPending && filtered.length === 0) ? (
              <Grid>
                {Array.from({ length: 6 }).map((_, i) => (
                  <div key={i} className="aspect-video bg-surface border border-border animate-pulse" />
                ))}
              </Grid>
            ) : isError ? (
              <p className="text-muted text-[14px] py-8">Could not load episodes. Refresh to try again.</p>
            ) : filtered.length ? (
              <>
                <Crossfade transitionKey={`${slug ?? "all"}:${activeSet ?? ""}`}>
                  {shortsView ? (
                    <ShortGrid>
                      {filtered.slice(0, visible).map((ep) => (
                        <ShortCard key={ep.id} episode={ep} thumbnailPending={thumbnailsPending} />
                      ))}
                    </ShortGrid>
                  ) : (
                    <Grid>
                      {filtered.slice(0, visible).map((ep, index) => {
                        const isExpanded = expandedId === ep.id;
                        const column = index % gridColumns;
                        const colStart = column === gridColumns - 1 ? gridColumns - 1 : column + 1;
                        const rowStart = Math.floor(index / gridColumns) + 1;
                        const placed = isExpanded && gridColumns > 1;
                        return (
                          <EpisodeCard
                            key={ep.id}
                            episode={ep}
                            thumbnailPending={thumbnailsPending}
                            audioMode={audioView}
                            expanded={isExpanded}
                            colStart={placed ? colStart : undefined}
                            rowStart={placed ? rowStart : undefined}
                            onPlayingChange={(playing) => setExpandedId(playing ? ep.id : null)}
                          />
                        );
                      })}
                    </Grid>
                  )}
                </Crossfade>
                {visible < filtered.length ? (
                  <div ref={sentinelRef} className="h-10 flex items-center justify-center mt-10">
                    <span className="mono text-[11px] tracking-[0.16em] text-dim uppercase animate-pulse">Loading…</span>
                  </div>
                ) : null}
              </>
            ) : (
              <EmptyResults
                query={needle ? query.trim() : ""}
                noun={shortsView ? "shorts" : audioView ? "audio episodes" : "episodes"}
                category={activeCategory}
                set={activeSet}
                indent={searchIndent}
                onClear={() => {
                  setQuery("");
                  setVisible(PAGE_SIZE);
                }}
              />
            )}
          </div>
        </div>
      </div>

      <SwipeableDrawer open={drawerOpen} onOpenChange={setDrawerOpen} closeLabel="Close categories">
        <CategoryRail {...railProps} />
      </SwipeableDrawer>

      <GoToTopButton onClick={() => window.scrollTo({ top: contentTopOffset(), behavior: "smooth" })} />
    </PageShell>
  );
}

function CategoryRail({
  allCount,
  shortsCount,
  shortsExist,
  audioCount,
  audioExist,
  counts,
  activeCategory,
  shortsView,
  audioView,
  onAll,
  onCategory,
  onShorts,
  onAudio,
  collapsed = false,
  onCollapse,
  onExpand,
}: {
  allCount: number;
  shortsCount: number;
  shortsExist: boolean;
  audioCount: number;
  audioExist: boolean;
  counts: Map<EpisodeCategory, number>;
  activeCategory: EpisodeCategory | null;
  shortsView: boolean;
  audioView: boolean;
  onAll: () => void;
  onCategory: (category: EpisodeCategory) => void;
  onShorts: () => void;
  onAudio: () => void;
  collapsed?: boolean;
  onCollapse?: () => void;
  onExpand?: () => void;
}) {
  return (
    <nav>
      {collapsed ? (
        <Tooltip label="View Categories" side="bottom">
          <button
            type="button"
            onClick={onExpand}
            aria-label="View Categories"
            className="flex h-[60px] w-full items-center justify-center border-b border-border text-muted transition-colors hover:text-green"
          >
            <Library size={22} strokeWidth={2} />
          </button>
        </Tooltip>
      ) : onCollapse ? (
        <Tooltip label="Collapse Library" side="bottom" align="end">
          <button
            type="button"
            onClick={onCollapse}
            aria-label="Collapse Library"
            className="group flex h-[60px] w-full items-center gap-2.5 border-b border-border px-4 text-left transition-colors"
          >
            <Library size={22} strokeWidth={2} className="shrink-0 text-green" />
            <span className="font-display text-[25px] leading-none tracking-[0.12em] text-text transition-colors group-hover:text-green">
              LIBRARY
            </span>
            <ChevronsLeft
              size={20}
              strokeWidth={2}
              className="ml-auto -mr-1 shrink-0 text-muted transition-colors group-hover:text-green"
            />
          </button>
        </Tooltip>
      ) : (
        <div className="flex h-[60px] items-center gap-2.5 border-b border-border px-4">
          <Library size={22} strokeWidth={2} className="shrink-0 text-green" />
          <span className="font-display text-[25px] leading-none tracking-[0.12em] text-text">LIBRARY</span>
        </div>
      )}
      <div>
        <RailRow
          label="All"
          icon={LayoutGrid}
          count={allCount}
          active={!shortsView && !audioView && !activeCategory}
          collapsed={collapsed}
          onClick={onAll}
        />
        <div>
          <RailRow
            label="Evergreen"
            icon={CATEGORY_ICON.Evergreen}
            count={counts.get("Evergreen") ?? 0}
            active={!shortsView && activeCategory === "Evergreen"}
            collapsed={collapsed}
            onClick={() => onCategory("Evergreen")}
          />
          {EPISODE_CATEGORIES.filter((category) => category !== "Evergreen").map((category) => (
            <RailRow
              key={category}
              label={category}
              icon={CATEGORY_ICON[category]}
              count={counts.get(category) ?? 0}
              active={!shortsView && activeCategory === category}
              collapsed={collapsed}
              onClick={() => onCategory(category)}
            />
          ))}
        </div>
        {shortsExist || audioExist ? <div className="mx-4 my-2 border-t border-border" /> : null}
        {shortsExist ? (
          <RailRow
            label="Shorts"
            icon={Zap}
            count={shortsCount}
            active={shortsView}
            collapsed={collapsed}
            onClick={onShorts}
          />
        ) : null}
        {audioExist ? (
          <RailRow
            label="Audio"
            icon={Headphones}
            count={audioCount}
            active={audioView}
            collapsed={collapsed}
            onClick={onAudio}
          />
        ) : null}
      </div>
    </nav>
  );
}

function RailRow({
  label,
  icon: Icon,
  count,
  active,
  collapsed = false,
  onClick,
}: {
  label: string;
  icon: LucideIcon;
  count: number;
  active: boolean;
  collapsed?: boolean;
  onClick: () => void;
}) {
  const button = (
    <button
      type="button"
      onClick={onClick}
      aria-label={collapsed ? label : undefined}
      className={cn(
        "group relative flex w-full items-center text-left transition-colors",
        collapsed ? "justify-center py-3.5" : "gap-3 px-4 py-3.5",
        active ? "bg-surface2" : "hover:bg-bg/40",
      )}
    >
      <span
        className={cn(
          "absolute left-0 top-0 h-full w-[3px] origin-center bg-green transition-all duration-200",
          active ? "opacity-100" : "opacity-0 scale-y-50 group-hover:opacity-100 group-hover:scale-y-100",
        )}
      />
      <Icon
        size={18}
        strokeWidth={2}
        className={cn(
          "shrink-0 transition-colors",
          active ? "text-green" : "text-muted group-hover:text-green",
        )}
      />
      {collapsed ? null : (
        <>
          <span
            className={cn(
              "flex-1 font-display uppercase tracking-[0.08em] text-[16px] transition-colors",
              active ? "text-green" : "text-text group-hover:text-green",
            )}
          >
            {label}
          </span>
          <span
            className={cn(
              "mono text-[13px] tabular-nums transition-colors",
              active ? "text-green" : "text-muted group-hover:text-green",
            )}
          >
            {count || "–"}
          </span>
        </>
      )}
    </button>
  );

  if (collapsed) {
    return (
      <Tooltip label={`${label} (${count || "–"})`} side="right">
        {button}
      </Tooltip>
    );
  }
  return button;
}

function EmptyResults({
  query,
  noun,
  category,
  set,
  indent,
  onClear,
}: {
  query: string;
  noun: string;
  category: string | null;
  set: string | null;
  indent: number;
  onClear: () => void;
}) {
  const searching = query.length > 0;
  const forSet = set ? ` for ${set}` : "";
  const nounPhrase = category ? `${category} ${noun}` : noun;
  return (
    <div
      className="flex animate-fadeIn flex-col items-center py-12 text-center md:py-16 lg:flex-row lg:items-center lg:gap-6 lg:text-left"
      style={{ marginLeft: indent }}
    >
      <div
        className="relative mb-6 flex h-20 w-20 shrink-0 items-center justify-center border border-border2 bg-surface lg:mb-0"
        style={{ clipPath: CUT_CORNER_CHAMFER }}
      >
        <SearchX size={32} strokeWidth={1.5} className="text-dim" />
        <span className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_center,rgba(46,232,92,0.10),transparent_70%)]" />
      </div>
      <div className="flex flex-col">
        <h3 className="font-display text-[22px] leading-none tracking-[0.06em] text-text md:text-[26px]">
          {searching ? "No matches found" : `No ${nounPhrase} yet`}
        </h3>
        <p className="mono mt-3 text-[12px] leading-relaxed text-muted">
          {searching ? (
            <>
              Nothing matches <span className="text-green">“{query}”</span>
              {forSet}.
              <br />
              Try a different title or set.
            </>
          ) : (
            <>No {nounPhrase}{forSet} have been posted yet.</>
          )}
        </p>
      </div>
      {searching ? (
        <button
          type="button"
          onClick={onClear}
          className="mt-7 inline-flex h-10 items-center gap-2 border border-border2 px-4 font-display text-[13px] tracking-[0.12em] text-text transition-colors hover:border-green hover:text-green lg:mt-0 lg:ml-2"
        >
          <X size={14} strokeWidth={2} className="shrink-0" />
          CLEAR SEARCH
        </button>
      ) : null}
    </div>
  );
}

function Grid({ children }: { children: ReactNode }) {
  return (
    <div className="grid grid-flow-row-dense grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-4 gap-x-4 gap-y-7">
      {children}
    </div>
  );
}

function ShortGrid({ children }: { children: ReactNode }) {
  return (
    <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6 gap-x-4 gap-y-8">
      {children}
    </div>
  );
}

function SortControl({
  value,
  onChange,
  className,
}: {
  value: SortKey;
  onChange: (value: SortKey) => void;
  className?: string;
}) {
  return (
    <div className={cn("flex h-10 border border-border divide-x divide-border", className)}>
      {SORT_OPTIONS.map((option) => {
        const active = option.value === value;
        const Icon = option.icon;
        return (
          <Tooltip key={option.value} label={`Sort by ${option.label}`} side="bottom">
            <button
              type="button"
              onClick={() => onChange(option.value)}
              className={cn(
                "flex items-center gap-1.5 px-3 font-display tracking-[0.06em] text-[14px] transition-colors md:px-3.5",
                active ? TOGGLE_ACTIVE : TOGGLE_INACTIVE,
              )}
            >
              <Icon size={15} strokeWidth={2} className="shrink-0" />
              {option.label}
            </button>
          </Tooltip>
        );
      })}
    </div>
  );
}

function matchesQuery(ep: Episode, needle: string): boolean {
  if (!needle) {
    return true;
  }
  return (
    ep.title.toLowerCase().includes(needle) ||
    (ep.setName?.toLowerCase().includes(needle) ?? false) ||
    (ep.setCode?.toLowerCase().includes(needle) ?? false)
  );
}

function compareReleaseDesc(a: string | null, b: string | null): number {
  if (a === b) {
    return 0;
  }
  if (!a) {
    return -1;
  }
  if (!b) {
    return 1;
  }
  return a < b ? 1 : -1;
}

function sortEpisodes(rows: Episode[], sort: SortKey): Episode[] {
  const sorted = [...rows];
  sorted.sort((a, b) => new Date(b.pubDate).getTime() - new Date(a.pubDate).getTime());
  if (sort === "oldest") {
    sorted.reverse();
  }
  return sorted;
}
