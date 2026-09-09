import { Fragment, useEffect, useLayoutEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { Link, useLocation, useNavigate, useParams, useSearchParams } from "react-router-dom";
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
import { EpisodeEmbed } from "../components/PlayableThumbnail";
import type { AudioControls } from "../components/PodcastAudioPlayer";
import { ChevronRight } from "lucide-react";
import { EpisodeTag } from "../components/CategoryTag";
import { EpisodeThumbnail } from "../components/EpisodeThumbnail";
import { ShortCard } from "../components/ShortCard";
import { FilterDropdown, type FilterOption } from "../components/FilterDropdown";
import { GoToTopButton } from "../components/GoToTopButton";
import { SwipeableDrawer } from "../components/SwipeableDrawer";
import { Tooltip } from "../components/Tooltip";
import { RailHeader, RailRow } from "../components/Rail";
import { CUT_CORNER_CHAMFER } from "../components/ChamferCta";
import { Crossfade } from "../components/Crossfade";
import { SetGlyph } from "../components/Brand";
import { useMediaFeed, useEpisodeTranscript } from "../data/hooks";
import {
  EPISODE_CATEGORIES,
  categoryFromSlug,
  categorySlug,
  findEpisodeBySlug,
  type Episode,
  type EpisodeCategory,
} from "../data/episodes";
import type { TranscriptSegment } from "../data/transcript";
import { useCardImageMap } from "../data/cardImages";
import { TranscriptCardLink } from "../components/TranscriptCardLink";
import { LISTEN_ON } from "../data/site";
import { cn } from "../lib/utils";
import { useIsMobile } from "../lib/use-is-mobile";
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
  const { categorySlug: slug, episodeSlug } = useParams<{ categorySlug?: string; episodeSlug?: string }>();
  const navigate = useNavigate();
  const location = useLocation();
  const [params] = useSearchParams();
  const [query, setQuery] = useState(() => params.get("q") ?? "");
  const [sort, setSort] = useState<SortKey>("newest");
  const [visible, setVisible] = useState(PAGE_SIZE);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [railCollapsed, setRailCollapsed] = useState(false);
  const isMobile = useIsMobile();
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

  const openEpisode = useMemo(() => {
    if (!episodes) {
      return null;
    }
    if (episodeSlug) {
      return findEpisodeBySlug(episodes, episodeSlug.toLowerCase());
    }
    if (slugLower && !shortsView && !audioView && !activeCategory && !setCodesBySlug.has(slugLower)) {
      return findEpisodeBySlug(episodes, slugLower);
    }
    return null;
  }, [episodes, episodeSlug, slugLower, shortsView, audioView, activeCategory, setCodesBySlug]);

  const looksLikeEpisodeTarget =
    Boolean(episodeSlug) ||
    Boolean(
      slugLower &&
        !shortsView &&
        !audioView &&
        !activeCategory &&
        !setCodesBySlug.has(slugLower) &&
        (slugLower.includes("-") || slugLower.length > 4),
    );

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
    if (episodeSlug && !findEpisodeBySlug(episodes, episodeSlug.toLowerCase())) {
      navigate({ pathname: `/episodes/${slug ?? ""}`.replace(/\/$/, ""), search: params.toString() }, { replace: true });
      return;
    }
    const unknownSlug =
      setsReady && slugLower && !shortsView && !audioView && !activeCategory && !setCodesBySlug.has(slugLower);
    if (unknownSlug && !episodeSlug && !findEpisodeBySlug(episodes, slugLower)) {
      navigate({ pathname: "/episodes", search: params.toString() }, { replace: true });
    }
  }, [params, slug, slugLower, episodeSlug, navigate, episodes, setCodesBySlug, shortsView, audioView, activeCategory, setsReady]);

  const categoryPath = shortsView
    ? "/episodes/shorts"
    : audioView
      ? "/episodes/audio"
      : activeCategory
        ? `/episodes/${categorySlug(activeCategory)}`
        : null;
  const detailBase = categoryPath ?? (pathSet ? setLandingPath(pathSet) : "/episodes");

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
  const updateQuery = (value: string) => {
    setQuery(value);
    setVisible(PAGE_SIZE);
    const next = new URLSearchParams(params);
    if (value.trim()) {
      next.set("q", value);
    } else {
      next.delete("q");
    }
    navigate({ pathname: location.pathname, search: next.toString() }, { replace: true });
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
        {count != null && <span className="font-num text-[12px] tabular-nums text-muted shrink-0">{count}</span>}
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
    <PageShell subtitle="EPISODES">
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
          {openEpisode || (looksLikeEpisodeTarget && isPending) ? null : (
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
                onChange={(e) => updateQuery(e.target.value)}
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
          )}

          <div ref={listRef} className="px-4 md:px-6 pt-6 pb-4">
            {openEpisode ? (
              <EpisodeDetail
                episode={openEpisode}
                audioMode={audioView}
                thumbnailPending={thumbnailsPending}
                siblings={episodes}
              />
            ) : looksLikeEpisodeTarget && isPending ? (
              <EpisodeDetailSkeleton />
            ) : awaitingSetSlug || (isPending && filtered.length === 0) ? (
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
                      {filtered.slice(0, visible).map((ep) => (
                        <EpisodeCard
                          key={ep.id}
                          episode={ep}
                          thumbnailPending={thumbnailsPending}
                          audioMode={audioView}
                          detailBase={detailBase}
                        />
                      ))}
                    </Grid>
                  )}
                </Crossfade>
                {visible < filtered.length ? (
                  <div ref={sentinelRef} className="h-10 flex items-center justify-center mt-10">
                    <span className="font-mono text-[11px] tracking-[0.16em] text-dim uppercase animate-pulse">Loading…</span>
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
                onClear={() => updateQuery("")}
              />
            )}
          </div>
        </div>
      </div>

      <SwipeableDrawer open={drawerOpen} onOpenChange={setDrawerOpen} closeLabel="Close categories">
        <CategoryRail {...railProps} />
      </SwipeableDrawer>

      <GoToTopButton
        onClick={() => window.scrollTo({ top: contentTopOffset(), behavior: "smooth" })}
        dimmed={Boolean(openEpisode)}
        className={openEpisode ? "lg:hidden" : undefined}
      />
    </PageShell>
  );
}

function EpisodeDetail({
  episode,
  audioMode,
  thumbnailPending,
  siblings,
}: {
  episode: Episode;
  audioMode: boolean;
  thumbnailPending: boolean;
  siblings?: Episode[];
}) {
  const { transcript, settled: transcriptSettled } = useEpisodeTranscript(episode);
  const playerRef = useRef<HTMLIFrameElement>(null);
  const audioControlsRef = useRef<AudioControls>(null);
  const stickyRef = useRef<HTMLDivElement>(null);
  const [currentTime, setCurrentTime] = useState(0);
  const [collapsedChapters, setCollapsedChapters] = useState<ReadonlySet<number>>(() => new Set());
  const toggleChapter = (t: number) =>
    setCollapsedChapters((prev) => {
      const next = new Set(prev);
      if (next.has(t)) {
        next.delete(t);
      } else {
        next.add(t);
      }
      return next;
    });
  const usingAudioPlayer = audioMode || !episode.youtubeId;
  const canSeek = usingAudioPlayer ? Boolean(episode.audioUrl) : Boolean(episode.youtubeId);
  const seek = (seconds: number) => {
    if (usingAudioPlayer) {
      audioControlsRef.current?.seek(seconds);
      return;
    }
    const command = (func: string, args: unknown[]) =>
      playerRef.current?.contentWindow?.postMessage(
        JSON.stringify({ event: "command", func, args }),
        "https://www.youtube.com",
      );
    command("seekTo", [seconds, true]);
    command("playVideo", []);
  };
  useEffect(() => {
    if (usingAudioPlayer) {
      return;
    }
    const hideCaptions = () => {
      const message = JSON.stringify({ event: "command", func: "setOption", args: ["captions", "track", {}] });
      playerRef.current?.contentWindow?.postMessage(message, "https://www.youtube.com");
    };
    const timers = [800, 1600, 2800].map((delay) => window.setTimeout(hideCaptions, delay));
    return () => timers.forEach(window.clearTimeout);
  }, [usingAudioPlayer, episode.youtubeId]);
  useEffect(() => {
    if (usingAudioPlayer) {
      return;
    }
    const listen = () =>
      playerRef.current?.contentWindow?.postMessage(
        JSON.stringify({ event: "listening", id: 1, channel: "widget" }),
        "https://www.youtube.com",
      );
    const timers = [500, 1200, 2500].map((delay) => window.setTimeout(listen, delay));
    const onMessage = (event: MessageEvent) => {
      if (event.origin !== "https://www.youtube.com") {
        return;
      }
      try {
        const data = JSON.parse(event.data);
        if (data.event === "infoDelivery" && typeof data.info?.currentTime === "number") {
          setCurrentTime(data.info.currentTime);
        }
      } catch {
        return;
      }
    };
    window.addEventListener("message", onMessage);
    return () => {
      timers.forEach(window.clearTimeout);
      window.removeEventListener("message", onMessage);
    };
  }, [usingAudioPlayer, episode.youtubeId]);
  const chapters = useMemo(
    () => (transcript ?? []).filter((s) => s.heading).map((s) => ({ t: s.t, heading: s.heading as string })),
    [transcript],
  );
  const hasTranscript = Boolean(transcript && transcript.length > 0);
  const expectTranscript = !audioMode && (episode.hasTranscript || hasTranscript);
  const moreEpisodes = useMemo(() => {
    const others = (siblings ?? []).filter((e) => e.id !== episode.id && !e.isShort);
    const sameCategory = others.filter((e) => e.category === episode.category);
    const rest = others.filter((e) => e.category !== episode.category);
    return [...sameCategory, ...rest].slice(0, 12);
  }, [siblings, episode.id, episode.category]);
  const activeChapterT = useMemo(() => {
    let active = -1;
    for (const chapter of chapters) {
      if (chapter.t <= currentTime + 0.5) {
        active = chapter.t;
      } else {
        break;
      }
    }
    return active;
  }, [chapters, currentTime]);
  const jumpToChapter = (seconds: number) => {
    setCollapsedChapters((prev) => {
      if (!prev.has(seconds)) {
        return prev;
      }
      const next = new Set(prev);
      next.delete(seconds);
      return next;
    });
    if (canSeek) {
      seek(seconds);
    }
    const target = document.getElementById(`ch-${seconds}`);
    if (!target) {
      return;
    }
    const offset = (stickyRef.current?.offsetHeight ?? 0) + 12;
    animateScrollTo(target.getBoundingClientRect().top + window.scrollY - offset);
  };
  return (
    <div
      className={cn(
        "mx-auto w-full max-w-[1120px] lg:min-h-0",
        transcriptSettled ? "" : "min-h-[calc(100vh-9rem)]",
      )}
    >
      <div
        ref={stickyRef}
        className="sticky top-0 z-30 -mx-4 -mt-6 bg-bg md:-mx-6 md:mt-0 md:px-6 md:py-2 lg:mx-0 lg:-mt-6 lg:px-0 lg:pb-0 lg:pt-6"
      >
        <div className="lg:flex lg:items-stretch lg:gap-4">
          <div className="lg:min-w-0 lg:flex-1">
            <div className="relative aspect-video w-full overflow-hidden border-b border-border bg-surface md:mx-auto md:h-[36vh] md:w-auto md:rounded-lg md:border lg:mx-0 lg:h-auto lg:w-full lg:rounded-none lg:border-0">
              <EpisodeEmbed
                episode={episode}
                thumbnailPending={thumbnailPending}
                audioMode={audioMode}
                iframeRef={playerRef}
                enableJsApi={!usingAudioPlayer}
                audioControlsRef={audioControlsRef}
              />
              <div className="pointer-events-none absolute inset-0 z-10 hidden border-border lg:block lg:border" />
            </div>
          </div>
          {expectTranscript ? (
            <aside className="relative hidden lg:block lg:w-[300px] lg:shrink-0">
              <nav className="absolute inset-0 flex flex-col overflow-y-auto border border-border bg-surface/40 px-3 py-1">
                {chapters.length > 0
                  ? chapters.map((chapter) => {
                      const isActive = chapter.t === activeChapterT;
                      return (
                        <button
                          key={chapter.t}
                          type="button"
                          onClick={() => jumpToChapter(chapter.t)}
                          className="group flex cursor-pointer items-baseline justify-between gap-3 border-t border-border/40 py-2.5 text-left first:border-t-0"
                        >
                          <span
                            className={cn(
                              "font-display text-[15px] uppercase tracking-[0.02em] leading-snug transition-colors group-hover:text-green",
                              isActive ? "text-green" : "text-subtle",
                            )}
                          >
                            {chapter.heading}
                          </span>
                          <span className="font-num shrink-0 text-[12px] text-green">
                            {formatTimestamp(chapter.t)}
                          </span>
                        </button>
                      );
                    })
                  : Array.from({ length: 9 }).map((_, i) => (
                      <div
                        key={i}
                        className="flex items-center justify-between gap-3 border-t border-border/40 py-2.5 first:border-t-0"
                      >
                        <div className="h-3 flex-1 animate-pulse bg-border" style={{ maxWidth: `${70 - (i % 3) * 14}%` }} />
                        <div className="h-3 w-8 animate-pulse bg-border" />
                      </div>
                    ))}
              </nav>
            </aside>
          ) : null}
        </div>
        <div className="pointer-events-none absolute inset-x-0 top-full hidden h-3 bg-gradient-to-b from-bg to-transparent lg:block" />
      </div>
      <div className="mt-3 flex items-center justify-between gap-3 lg:mt-6">
        <h1 className="min-w-0 font-body text-text text-[16px] md:text-[20px] font-medium leading-snug">
          {episode.title}
        </h1>
        <div className="flex shrink-0 flex-col items-end gap-2">
          <EpisodeTag episode={episode} className={expectTranscript ? "hidden md:flex" : undefined} />
          {expectTranscript ? null : (
            <div className="flex items-center gap-2 font-num text-[12px] tabular-nums text-muted">
              <span>{episode.publishedLabel}</span>
              {episode.number ? (
                <>
                  <span aria-hidden className="h-3 w-px bg-border2" />
                  <span>EP {episode.number}</span>
                </>
              ) : null}
            </div>
          )}
        </div>
      </div>
      {hasTranscript ? (
        <EpisodeTranscript
          segments={transcript as TranscriptSegment[]}
          setCode={episode.setCode}
          onSeek={canSeek ? seek : undefined}
          collapsedChapters={collapsedChapters}
          onToggleChapter={toggleChapter}
        />
      ) : !transcriptSettled && expectTranscript ? (
        <TranscriptBodySkeleton />
      ) : transcriptSettled && moreEpisodes.length > 0 ? (
        <MoreEpisodes episodes={moreEpisodes} />
      ) : null}
    </div>
  );
}

function EpisodeDetailSkeleton() {
  return (
    <div className="mx-auto w-full max-w-[1120px]">
      <div className="-mx-4 -mt-6 md:mx-0 md:mt-0">
        <div className="aspect-video w-full animate-pulse border-b border-border bg-surface md:mx-auto md:h-[36vh] md:w-auto md:aspect-auto md:rounded-lg md:border lg:mx-0 lg:h-auto lg:w-full lg:aspect-video lg:rounded-none lg:border-0" />
      </div>
      <div className="mt-3 h-6 w-3/4 animate-pulse bg-surface md:h-7 lg:mt-6" />
      <TranscriptBodySkeleton />
    </div>
  );
}

function TranscriptBodySkeleton() {
  return (
    <div className="mt-4 border-t border-border pt-4 lg:mt-6">
      {Array.from({ length: 3 }).map((_, group) => (
        <div key={group} className={group === 0 ? "" : "mt-8"}>
          <div className="mb-3 h-5 w-1/3 animate-pulse bg-surface" />
          <div className="space-y-2.5">
            {Array.from({ length: 4 }).map((_, line) => (
              <div key={line} className="h-4 animate-pulse bg-surface" style={{ width: `${96 - (line % 4) * 9}%` }} />
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}

function MoreEpisodes({ episodes }: { episodes: Episode[] }) {
  return (
    <div className="mt-8 border-t border-border pt-6">
      <h2 className="mb-4 font-display text-text text-[16px] tracking-[0.02em]">More episodes</h2>
      <div className="flex flex-col gap-3">
        {episodes.map((episode) => (
          <MoreEpisodeRow key={episode.id} episode={episode} />
        ))}
      </div>
    </div>
  );
}

function MoreEpisodeRow({ episode }: { episode: Episode }) {
  const href = episode.slug ? `/episodes/${categorySlug(episode.category)}/${episode.slug}` : null;
  const meta = [episode.publishedLabel.toUpperCase(), episode.number ? `EP ${episode.number}` : null]
    .filter(Boolean)
    .join(" · ");
  const body = (
    <>
      <div className="relative aspect-video w-36 shrink-0 overflow-hidden rounded-md border border-border bg-surface sm:w-44">
        <EpisodeThumbnail
          src={episode.image}
          className="transition-transform duration-300 group-hover/row:scale-[1.06]"
        />
      </div>
      <div className="min-w-0 flex-1">
        <div className="flex items-start justify-between gap-2">
          <span className="font-num text-[11px] tracking-[0.06em] text-muted">{meta}</span>
          <EpisodeTag episode={episode} className="mt-0.5" />
        </div>
        <span className="mt-1 block font-body text-text text-[14px] md:text-[15px] font-medium leading-snug line-clamp-2 transition-colors group-hover/row:text-green">
          {episode.title}
        </span>
      </div>
    </>
  );
  if (href) {
    return (
      <Link to={href} className="group/row flex gap-3 no-underline">
        {body}
      </Link>
    );
  }
  return (
    <a href={episode.link} target="_blank" rel="noreferrer" className="group/row flex gap-3 no-underline">
      {body}
    </a>
  );
}

type TranscriptItem =
  | { kind: "chapter"; t: number; heading: string }
  | { kind: "section"; t: number; title: string; paras: string[] }
  | { kind: "para"; text: string };

function escapeRegExp(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

function EpisodeTranscript({
  segments,
  setCode,
  onSeek,
  collapsedChapters,
  onToggleChapter,
}: {
  segments: TranscriptSegment[];
  setCode?: string | null;
  onSeek?: (seconds: number) => void;
  collapsedChapters: ReadonlySet<number>;
  onToggleChapter: (t: number) => void;
}) {
  const cardNames = useMemo(() => {
    const names = new Set<string>();
    for (const segment of segments) {
      for (const card of segment.cards ?? []) {
        names.add(card.name);
      }
    }
    return [...names].sort((a, b) => b.length - a.length);
  }, [segments]);
  const cardNameSet = useMemo(() => new Set(cardNames), [cardNames]);

  const cardItems = useMemo(
    () => (setCode ? cardNames.map((name) => ({ name, set: setCode })) : []),
    [cardNames, setCode],
  );
  const cardImages = useCardImageMap(cardItems);

  const items = useMemo<TranscriptItem[]>(() => {
    const out: TranscriptItem[] = [];
    let section: Extract<TranscriptItem, { kind: "section" }> | null = null;
    for (const segment of segments) {
      if (segment.heading) {
        section = null;
        out.push({ kind: "chapter", t: segment.t, heading: segment.heading });
        out.push({ kind: "para", text: segment.text });
      } else if (segment.subheading) {
        section = { kind: "section", t: segment.t, title: segment.subheading, paras: [segment.text] };
        out.push(section);
      } else if (section) {
        section.paras.push(segment.text);
      } else {
        out.push({ kind: "para", text: segment.text });
      }
    }
    return out;
  }, [segments]);

  const linkable = useMemo(() => {
    const map = new Map<string, Set<string>>();
    let seen = new Set<string>();
    const allow = (text: string) => {
      const names = new Set<string>();
      for (const name of cardNames) {
        if (!seen.has(name) && text.includes(name)) {
          names.add(name);
          seen.add(name);
        }
      }
      return names;
    };
    items.forEach((item, index) => {
      if (item.kind === "chapter") {
        seen = new Set();
      } else if (item.kind === "section") {
        seen = new Set();
        item.paras.forEach((para, paraIndex) => map.set(`${index}:${paraIndex}`, allow(para)));
      } else {
        map.set(`${index}:0`, allow(item.text));
      }
    });
    return map;
  }, [items, cardNames]);

  const renderText = (text: string, allowed: Set<string> | undefined): ReactNode => {
    if (!setCode || cardNames.length === 0) {
      return text;
    }
    const pattern = new RegExp(`(${cardNames.map(escapeRegExp).join("|")})`, "g");
    const linkedHere = new Set<string>();
    return text.split(pattern).map((part, index) => {
      if (!cardNameSet.has(part)) {
        return part;
      }
      if (allowed?.has(part) && !linkedHere.has(part)) {
        linkedHere.add(part);
        return <TranscriptCardLink key={index} name={part} set={setCode} cardImages={cardImages} />;
      }
      return (
        <em key={index} className="text-subtle/90 italic">
          {part}
        </em>
      );
    });
  };

  const [collapsed, setCollapsed] = useState<ReadonlySet<number>>(() => new Set());
  const toggle = (index: number) =>
    setCollapsed((prev) => {
      const next = new Set(prev);
      if (next.has(index)) {
        next.delete(index);
      } else {
        next.add(index);
      }
      return next;
    });
  const chapterOf = useMemo(() => {
    const map = new Map<number, number>();
    let currentT = -1;
    items.forEach((item, itemIndex) => {
      if (item.kind === "chapter") {
        currentT = item.t;
      } else {
        map.set(itemIndex, currentT);
      }
    });
    return map;
  }, [items]);

  return (
    <div className="mt-4 border-t border-border pt-4 lg:mt-6">
      <div className="w-full">
        {items.map((item, index) => {
          if (item.kind !== "chapter") {
            const parent = chapterOf.get(index);
            if (parent !== undefined && parent >= 0 && collapsedChapters.has(parent)) {
              return null;
            }
          }
          if (item.kind === "chapter") {
            const isChapterCollapsed = collapsedChapters.has(item.t);
            return (
              <div
                key={index}
                id={`ch-${item.t}`}
                className="mt-8 mb-1.5 flex items-center gap-2 scroll-mt-[calc(56vw+1rem)] first:mt-0 lg:scroll-mt-4"
              >
                <button
                  type="button"
                  onClick={() => onToggleChapter(item.t)}
                  aria-expanded={!isChapterCollapsed}
                  className="group flex items-center gap-2 text-left"
                >
                  <ChevronRight
                    size={18}
                    strokeWidth={2.5}
                    className={cn("shrink-0 text-green transition-transform", isChapterCollapsed ? "" : "rotate-90")}
                  />
                  <h3 className="font-display text-text text-[19px] tracking-[0.02em] leading-none transition-colors group-hover:text-green">
                    {item.heading}
                  </h3>
                </button>
                {onSeek ? (
                  <button
                    type="button"
                    onClick={() => onSeek(item.t)}
                    className="font-num shrink-0 text-[14px] leading-none text-green transition-colors hover:text-green/70"
                  >
                    {formatTimestamp(item.t)}
                  </button>
                ) : (
                  <span className="font-num shrink-0 text-[14px] leading-none text-dim">{formatTimestamp(item.t)}</span>
                )}
              </div>
            );
          }
          if (item.kind === "section") {
            const isCollapsed = collapsed.has(index);
            return (
              <div key={index} className="pt-4 first:pt-0">
                <div className="mb-1 flex items-center gap-1.5">
                  <button
                    type="button"
                    onClick={() => toggle(index)}
                    aria-expanded={!isCollapsed}
                    className="group flex items-center gap-1.5 text-left"
                  >
                    <ChevronRight
                      size={15}
                      strokeWidth={2.5}
                      className={cn("shrink-0 text-green transition-transform", isCollapsed ? "" : "rotate-90")}
                    />
                    <span className="font-display text-text/90 text-[17px] tracking-[0.02em] leading-none transition-colors group-hover:text-green">
                      {item.title}
                    </span>
                  </button>
                  {onSeek ? (
                    <button
                      type="button"
                      onClick={() => onSeek(item.t)}
                      className="font-num ml-1 shrink-0 text-[14px] leading-none text-green transition-colors hover:text-green/70"
                    >
                      {formatTimestamp(item.t)}
                    </button>
                  ) : (
                    <span className="font-num ml-1 shrink-0 text-[14px] leading-none text-dim">
                      {formatTimestamp(item.t)}
                    </span>
                  )}
                </div>
                {isCollapsed
                  ? null
                  : item.paras.map((para, paraIndex) => (
                      <p key={paraIndex} className="text-subtle text-[15px] leading-[1.6] mt-2">
                        {renderText(para, linkable.get(`${index}:${paraIndex}`))}
                      </p>
                    ))}
              </div>
            );
          }
          return (
            <p key={index} className="text-subtle text-[15px] leading-[1.6] mt-2">
              {renderText(item.text, linkable.get(`${index}:0`))}
            </p>
          );
        })}
      </div>
    </div>
  );
}

function animateScrollTo(top: number, duration = 240) {
  const start = window.scrollY;
  const distance = top - start;
  if (Math.abs(distance) < 4) {
    window.scrollTo({ top });
    return;
  }
  const startTime = performance.now();
  const step = (now: number) => {
    const progress = Math.min(1, (now - startTime) / duration);
    const eased = 1 - Math.pow(1 - progress, 3);
    window.scrollTo({ top: start + distance * eased });
    if (progress < 1) {
      requestAnimationFrame(step);
    }
  };
  requestAnimationFrame(step);
}

function formatTimestamp(seconds: number): string {
  const hours = Math.floor(seconds / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  const secs = seconds % 60;
  const mm = hours ? String(minutes).padStart(2, "0") : String(minutes);
  return `${hours ? `${hours}:` : ""}${mm}:${String(secs).padStart(2, "0")}`;
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
        <RailHeader icon={Library} label="LIBRARY" />
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
        <p className="font-mono mt-3 text-[12px] leading-relaxed text-muted">
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
