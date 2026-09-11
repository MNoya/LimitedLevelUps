import {
  Fragment,
  useCallback,
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
  type CSSProperties,
  type KeyboardEvent as ReactKeyboardEvent,
  type MouseEvent as ReactMouseEvent,
  type ReactNode,
} from "react";
import { Link, useLocation, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { SiApplepodcasts, SiRss, SiSpotify, SiYoutube } from "react-icons/si";
import type { IconType } from "react-icons";
import {
  BarChart3,
  BookOpen,
  CalendarArrowDown,
  CalendarArrowUp,
  Captions,
  Check,
  ChevronDown,
  ChevronsLeft,
  ChevronsUpDown,
  Download,
  GraduationCap,
  Headphones,
  Layers,
  LayoutGrid,
  Leaf,
  Library,
  ListOrdered,
  Loader2,
  Mic,
  Package,
  Pencil,
  Search,
  SearchX,
  Settings,
  SlidersHorizontal,
  Trash2,
  X,
  Zap,
  type LucideIcon,
} from "lucide-react";
import { PageShell } from "../components/PageShell";
import { EpisodeCard } from "../components/EpisodeCard";
import { EpisodeEmbed } from "../components/PlayableThumbnail";
import { PodcastAudioPlayer, type AudioControls } from "../components/PodcastAudioPlayer";
import { ChevronRight } from "lucide-react";
import { EpisodeTag, CATEGORY_COLOR } from "../components/CategoryTag";
import { EpisodeThumbnail } from "../components/EpisodeThumbnail";
import { ToggleSwitch } from "../components/ToggleSwitch";
import { ShortCard } from "../components/ShortCard";
import { FilterDropdown, type FilterOption } from "../components/FilterDropdown";
import { GoToTopButton } from "../components/GoToTopButton";
import { SwipeableDrawer } from "../components/SwipeableDrawer";
import { Tooltip } from "../components/Tooltip";
import { RailHeader, RailRow } from "../components/Rail";
import { CUT_CORNER_CHAMFER } from "../components/ChamferCta";
import { Crossfade } from "../components/Crossfade";
import { SetGlyph } from "../components/Brand";
import { useMediaFeed, useEpisodeTranscript, useTranscriptIndex } from "../data/hooks";
import { useQueryClient } from "@tanstack/react-query";
import { useAuth } from "../auth/useAuth";
import { isPodOrganizer } from "../data/podOrganizers";
import { isAdmin } from "../data/admins";
import { saveTranscript } from "../data/adminApi";
import {
  TranscriptListSkeleton,
  TranscriptRow,
  TranscriptRowHeader,
  type TranscriptSort,
  type TranscriptSortKey,
} from "../components/TranscriptCard";
import { BsAsterisk } from "../components/Icons";
import { stripSpeakerTurns, transcriptToText, downloadTextFile } from "../lib/transcriptText";
import {
  EPISODE_CATEGORIES,
  categoryFromSlug,
  categorySlug,
  findEpisodeBySlug,
  type Episode,
  type EpisodeCategory,
} from "../data/episodes";
import { type TranscriptSegment } from "../data/transcript";
import {
  NONE_META,
  TIER_META,
  TIER_RANK,
  transcriptTier,
  type TranscriptIndex,
  type TranscriptStatus,
  type TranscriptTier,
} from "../data/transcriptStatus";
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

const AllSetsGlyph = ({ size = 18 }: { size?: number }) => (
  <span className="flex shrink-0 items-center justify-center" style={{ width: size, height: size }}>
    <BsAsterisk size={Math.round(size * 0.62)} />
  </span>
);

const renderSetValue = (option: FilterOption) =>
  option.value ? (
    <span className="flex min-w-0 items-center gap-1.5 truncate text-green">
      <SetGlyph code={option.value} size={18} className="text-green" />
      {option.value}
    </span>
  ) : (
    <span className="flex min-w-0 items-center gap-1.5 truncate text-subtle">
      <AllSetsGlyph />
      ALL SETS
    </span>
  );

// BookOpen's glyph mass sits high in its viewBox, so it reads as raised next to the row label; nudge it down.
const SetReviewIcon = ((props: { size?: number; strokeWidth?: number; className?: string }) => (
  <BookOpen {...props} className={cn("translate-y-[1px]", props.className)} />
)) as unknown as LucideIcon;

const CATEGORY_ICON: Record<EpisodeCategory, LucideIcon> = {
  "Set Review": SetReviewIcon,
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
  const { data: transcriptIndex } = useTranscriptIndex();
  const { user: authUser } = useAuth();
  const isTranscriptAdmin = isPodOrganizer(authUser?.discordId);
  const { categorySlug: slug, episodeSlug } = useParams<{ categorySlug?: string; episodeSlug?: string }>();
  const navigate = useNavigate();
  const location = useLocation();
  const [params] = useSearchParams();
  const [query, setQuery] = useState(() => params.get("q") ?? "");
  const [sort, setSort] = useState<SortKey>("newest");
  const [visible, setVisible] = useState(PAGE_SIZE);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [railCollapsed, setRailCollapsed] = useState(false);
  const [transcriptCategory, setTranscriptCategory] = useState<EpisodeCategory | "">(readStoredTranscriptCategory);
  const [transcriptTierFilter, setTranscriptTierFilter] = useState<TranscriptTier | "none" | "">(
    readStoredTranscriptTier,
  );
  const [transcriptSort, setTranscriptSort] = useState<TranscriptSort>({ key: "date", dir: "desc" });
  useEffect(() => {
    window.localStorage.setItem(TRANSCRIPT_CATEGORY_KEY, transcriptCategory);
  }, [transcriptCategory]);
  useEffect(() => {
    window.localStorage.setItem(TRANSCRIPT_TIER_KEY, transcriptTierFilter);
  }, [transcriptTierFilter]);
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
  const transcriptsView = slugLower === "transcripts";
  const sectionView = shortsView || audioView || transcriptsView;
  const activeCategory = slug ? categoryFromSlug(slug) : null;
  const pathSet = slugLower && !sectionView && !activeCategory ? setCodesBySlug.get(slugLower) ?? null : null;
  const activeSet = pathSet ?? params.get("set");
  const awaitingSetSlug = !!slugLower && !sectionView && !activeCategory && !setsReady;

  const openEpisode = useMemo(() => {
    if (!episodes) {
      return null;
    }
    if (episodeSlug) {
      return findEpisodeBySlug(episodes, episodeSlug.toLowerCase());
    }
    if (slugLower && !sectionView && !activeCategory && !setCodesBySlug.has(slugLower)) {
      return findEpisodeBySlug(episodes, slugLower);
    }
    return null;
  }, [episodes, episodeSlug, slugLower, sectionView, activeCategory, setCodesBySlug]);

  const looksLikeEpisodeTarget =
    Boolean(episodeSlug) ||
    Boolean(
      slugLower &&
        !sectionView &&
        !activeCategory &&
        !setCodesBySlug.has(slugLower) &&
        (slugLower.includes("-") || slugLower.length > 4),
    );

  const transcriptArticleView = transcriptsView && Boolean(openEpisode || (looksLikeEpisodeTarget && isPending));

  const openEpisodeId = openEpisode?.id;
  useEffect(() => {
    if (openEpisodeId) {
      window.scrollTo({ top: 0 });
    }
  }, [openEpisodeId]);

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
      setsReady && slugLower && !sectionView && !activeCategory && !setCodesBySlug.has(slugLower);
    if (unknownSlug && !episodeSlug && !findEpisodeBySlug(episodes, slugLower)) {
      navigate({ pathname: "/episodes", search: params.toString() }, { replace: true });
    }
  }, [params, slug, slugLower, episodeSlug, navigate, episodes, setCodesBySlug, sectionView, activeCategory, setsReady]);

  const categoryPath = shortsView
    ? "/episodes/shorts"
    : audioView
      ? "/episodes/audio"
      : transcriptsView
        ? "/episodes/transcripts"
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
  const railLink = (pathname: string, querySet: string | null) => {
    const next = new URLSearchParams(params);
    next.delete("set");
    if (querySet) {
      next.set("set", querySet);
    }
    const search = next.toString();
    return {
      href: search ? `${pathname}?${search}` : pathname,
      onClick: (event: ReactMouseEvent) => {
        if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey || event.button !== 0) {
          return;
        }
        event.preventDefault();
        navTo(pathname, querySet);
        setDrawerOpen(false);
      },
    };
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
  const chooseSet = (code: string | null) => {
    if (!code) {
      navTo(categoryPath ?? "/episodes", null);
    } else if (categoryPath) {
      navTo(categoryPath, code);
    } else {
      navTo(setLandingPath(code), null);
    }
  };

  const transcriptKey = (ep: Episode) => ep.youtubeId ?? ep.id;
  const statusOf = (ep: Episode) => transcriptIndex?.get(transcriptKey(ep));

  const longform = useMemo(() => all.filter((ep) => !ep.isShort), [all]);
  const shorts = useMemo(() => all.filter((ep) => ep.isShort), [all]);
  const withAudio = useMemo(() => longform.filter((ep) => Boolean(ep.audioUrl)), [longform]);
  // Admins review the whole catalogue (with per-episode status); everyone else sees only transcribed episodes.
  const withTranscript = useMemo(
    () => (isTranscriptAdmin ? longform : longform.filter((ep) => transcriptIndex?.has(transcriptKey(ep)))),
    [longform, transcriptIndex, isTranscriptAdmin],
  );
  const pool = shortsView ? shorts : audioView ? withAudio : transcriptsView ? withTranscript : longform;

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
  const transcriptsInSet = useMemo(
    () => (activeSet ? withTranscript.filter((ep) => setCodeOf(ep) === activeSet) : withTranscript),
    [withTranscript, activeSet],
  );

  const needle = query.trim().toLowerCase();
  const scopedLongform = useMemo(() => longformInSet.filter((ep) => matchesQuery(ep, needle)), [longformInSet, needle]);
  const scopedShorts = useMemo(() => shortsInSet.filter((ep) => matchesQuery(ep, needle)), [shortsInSet, needle]);
  const scopedAudio = useMemo(() => audioInSet.filter((ep) => matchesQuery(ep, needle)), [audioInSet, needle]);
  const scopedTranscript = useMemo(
    () => transcriptsInSet.filter((ep) => matchesQuery(ep, needle)),
    [transcriptsInSet, needle],
  );
  const transcriptCategoryCounts = useMemo(() => {
    const map = new Map<EpisodeCategory, number>();
    for (const ep of scopedTranscript) {
      map.set(ep.category, (map.get(ep.category) ?? 0) + 1);
    }
    return map;
  }, [scopedTranscript]);
  const filteredTranscript = useMemo(() => {
    let rows = scopedTranscript;
    if (transcriptCategory) {
      rows = rows.filter((ep) => ep.category === transcriptCategory);
    }
    if (isTranscriptAdmin && transcriptTierFilter) {
      rows = rows.filter((ep) => {
        const status = transcriptIndex?.get(ep.youtubeId ?? ep.id);
        if (transcriptTierFilter === "none") {
          return !status;
        }
        return status ? transcriptTier(status.source) === transcriptTierFilter : false;
      });
    }
    return rows;
  }, [scopedTranscript, transcriptCategory, transcriptTierFilter, isTranscriptAdmin, transcriptIndex]);

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
        {option.value ? <SetGlyph code={option.value} size={20} /> : <AllSetsGlyph size={20} />}
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
      triggerClassName="!min-w-[108px] md:!min-w-[132px] !h-10 !py-0 hover:!bg-surface2"
      mobileCentered
    />
  );

  const transcriptCategoryOptions = useMemo<FilterOption[]>(() => {
    const options: FilterOption[] = [{ value: "", label: "All categories" }];
    for (const category of EPISODE_CATEGORIES) {
      if (transcriptCategoryCounts.get(category)) {
        options.push({ value: category, label: category });
      }
    }
    return options;
  }, [transcriptCategoryCounts]);

  const renderCategoryValue = (option: FilterOption) => {
    const category = option.value as EpisodeCategory | "";
    const Icon = category ? CATEGORY_ICON[category] : SlidersHorizontal;
    return (
      <span className="flex min-w-0 items-center gap-2 truncate">
        <Icon size={15} strokeWidth={2} className={cn("shrink-0", category ? CATEGORY_COLOR[category] : "text-muted")} />
        <span className="truncate">{category ? option.label : "CATEGORY"}</span>
      </span>
    );
  };

  const renderCategoryOption = (option: FilterOption) => {
    const category = option.value as EpisodeCategory | "";
    const Icon = category ? CATEGORY_ICON[category] : null;
    const count = category ? transcriptCategoryCounts.get(category) : scopedTranscript.length;
    return (
      <span className="flex w-full min-w-0 items-center gap-2.5">
        {Icon ? (
          <Icon size={16} strokeWidth={2} className={cn("shrink-0", CATEGORY_COLOR[category as EpisodeCategory])} />
        ) : (
          <span className="w-4 shrink-0" />
        )}
        <span className="flex-1 truncate">{option.label}</span>
        {count != null && <span className="font-num text-[12px] tabular-nums text-muted shrink-0">{count}</span>}
      </span>
    );
  };

  const transcriptTierCounts = useMemo(() => {
    const base = transcriptCategory
      ? scopedTranscript.filter((ep) => ep.category === transcriptCategory)
      : scopedTranscript;
    const counts = { all: base.length, done: 0, youtube: 0, none: 0 };
    for (const ep of base) {
      const status = transcriptIndex?.get(ep.youtubeId ?? ep.id);
      if (!status) {
        counts.none += 1;
      } else {
        counts[transcriptTier(status.source)] += 1;
      }
    }
    return counts;
  }, [scopedTranscript, transcriptCategory, transcriptIndex]);

  const transcriptTierOptions: FilterOption[] = [
    { value: "", label: "All" },
    { value: "done", label: TIER_META.done.label },
    { value: "youtube", label: TIER_META.youtube.label },
    { value: "none", label: NONE_META.label },
  ];

  const tierDot = (value: string) => {
    if (!value) {
      return null;
    }
    return value === "none" ? NONE_META.dot : TIER_META[value as TranscriptTier].dot;
  };

  const renderTierValue = (option: FilterOption) => {
    if (!option.value) {
      return <span className="truncate text-subtle">STATUS</span>;
    }
    return (
      <span className="flex min-w-0 items-center gap-2 truncate">
        <span className={cn("h-2 w-2 shrink-0 rounded-full", tierDot(option.value))} />
        {option.label}
      </span>
    );
  };

  const renderTierOption = (option: FilterOption) => {
    const dot = tierDot(option.value);
    const key = (option.value || "all") as keyof typeof transcriptTierCounts;
    const count = transcriptTierCounts[key];
    return (
      <span className="flex w-full min-w-0 items-center gap-2.5">
        {dot ? <span className={cn("h-2 w-2 shrink-0 rounded-full", dot)} /> : <span className="w-2 shrink-0" />}
        <span className="flex-1 truncate">{option.label}</span>
        <span className="font-num text-[12px] tabular-nums text-muted shrink-0">{count > 0 ? count : "-"}</span>
      </span>
    );
  };

  const transcriptCategoryDropdown = (
    <FilterDropdown
      value={transcriptCategory}
      options={transcriptCategoryOptions}
      onChange={(v) => {
        setTranscriptCategory(v as EpisodeCategory | "");
        setVisible(PAGE_SIZE);
      }}
      renderValue={renderCategoryValue}
      renderOption={renderCategoryOption}
      searchable={false}
      triggerClassName="!min-w-[150px] !h-10 !py-0 hover:!bg-surface2"
      mobileCentered
    />
  );
  const transcriptStatusDropdown = (
    <FilterDropdown
      value={transcriptTierFilter}
      options={transcriptTierOptions}
      onChange={(v) => {
        setTranscriptTierFilter(v as TranscriptTier | "none" | "");
        setVisible(PAGE_SIZE);
      }}
      renderValue={renderTierValue}
      renderOption={renderTierOption}
      searchable={false}
      triggerClassName="!min-w-[120px] !h-10 !py-0 hover:!bg-surface2"
      mobileCentered
    />
  );
  const transcriptToolbarFilters = transcriptsView ? (
    <div className="hidden shrink-0 items-center gap-2 lg:flex">
      {transcriptCategoryDropdown}
      {isTranscriptAdmin ? transcriptStatusDropdown : null}
    </div>
  ) : null;

  const searchField = (
    <>
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
    </>
  );

  const onTranscriptSort = (key: TranscriptSortKey) => {
    setTranscriptSort((prev) => {
      if (prev.key === key) {
        return { key, dir: prev.dir === "asc" ? "desc" : "asc" };
      }
      const numericFirst = key === "date" || key === "words" || key === "status";
      return { key, dir: numericFirst ? "desc" : "asc" };
    });
    setVisible(PAGE_SIZE);
  };

  const filtered = useMemo(() => {
    const base = shortsView
      ? scopedShorts
      : audioView
        ? scopedAudio
        : transcriptsView
          ? filteredTranscript
          : scopedLongform;
    const rows = !sectionView && activeCategory ? base.filter((ep) => ep.category === activeCategory) : base;
    if (transcriptsView) {
      return sortTranscriptRows(rows, transcriptSort, transcriptIndex);
    }
    return sortEpisodes(rows, sort);
  }, [shortsView, audioView, transcriptsView, sectionView, scopedShorts, scopedAudio, filteredTranscript, scopedLongform, activeCategory, sort, transcriptSort, transcriptIndex]);

  useEffect(() => {
    if (visible >= filtered.length) {
      return;
    }
    const sentinel = sentinelRef.current;
    if (!sentinel) {
      return;
    }
    let queued = false;
    const check = () => {
      queued = false;
      if (sentinel.getBoundingClientRect().top < window.innerHeight + 600) {
        setVisible((current) => Math.min(current + PAGE_SIZE, filtered.length));
      }
    };
    const onScroll = () => {
      if (queued) {
        return;
      }
      queued = true;
      requestAnimationFrame(check);
    };
    check();
    const settle = setTimeout(check, 300);
    window.addEventListener("scroll", onScroll, { passive: true });
    window.addEventListener("resize", onScroll);
    return () => {
      clearTimeout(settle);
      window.removeEventListener("scroll", onScroll);
      window.removeEventListener("resize", onScroll);
    };
  }, [visible, filtered.length, openEpisodeId]);

  const mobileFilter = shortsView
    ? { label: "Shorts", icon: Zap }
    : audioView
      ? { label: "Audio", icon: Headphones }
      : transcriptsView
        ? { label: "Transcripts", icon: Captions }
        : activeCategory
          ? { label: activeCategory, icon: CATEGORY_ICON[activeCategory] }
          : null;

  const railProps = {
    allCount: scopedLongform.length,
    shortsCount: scopedShorts.length,
    shortsExist: isPending || shorts.length > 0,
    audioCount: scopedAudio.length,
    audioExist: isPending || withAudio.length > 0,
    transcriptsCount: scopedTranscript.filter((ep) => transcriptIndex?.has(transcriptKey(ep))).length,
    transcriptsExist: isPending || withTranscript.length > 0,
    counts,
    activeCategory,
    activeSet,
    shortsView,
    audioView,
    transcriptsView,
    link: railLink,
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
          <div className="sticky top-0 z-10 border-b border-border bg-surface">
            <div className="flex h-[60px] items-center gap-2.5 px-4 md:px-6">
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
              <Tooltip label="Filter by set" side="top">
                <span className="shrink-0">{setFilterDropdown}</span>
              </Tooltip>
            )}
            {transcriptsView ? <div className="min-w-0 flex-1 lg:hidden">{transcriptCategoryDropdown}</div> : null}
            {transcriptToolbarFilters}
            <div
              ref={searchWrapRef}
              className={cn("relative min-w-0 flex-1", transcriptsView && "hidden lg:block")}
            >
              {searchField}
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
            {transcriptsView ? (
              <div className="flex items-center gap-2.5 px-4 pb-3 md:px-6 lg:hidden">
                <div className="relative min-w-0 flex-1">{searchField}</div>
                {isTranscriptAdmin ? transcriptStatusDropdown : null}
              </div>
            ) : null}
          </div>
          )}

          <div
            ref={listRef}
            className={cn(
              "pb-4 pr-4 md:pr-6",
              openEpisode || transcriptArticleView ? "pl-2" : "pl-4 md:pl-6",
              transcriptArticleView ? "pt-0" : "pt-6",
            )}
          >
            {openEpisode && transcriptsView ? (
              <TranscriptArticle episode={openEpisode} />
            ) : openEpisode ? (
              <EpisodeDetail
                episode={openEpisode}
                audioMode={audioView}
                thumbnailPending={thumbnailsPending}
                siblings={episodes}
              />
            ) : looksLikeEpisodeTarget && isPending ? (
              transcriptsView ? <TranscriptArticleSkeleton /> : <EpisodeDetailSkeleton />
            ) : awaitingSetSlug || (isPending && filtered.length === 0) ? (
              transcriptsView ? (
                <div className="relative -top-6 -mr-4 md:-mr-6">
                  <TranscriptListSkeleton showStatus={isTranscriptAdmin} />
                </div>
              ) : (
                <Grid>
                  {Array.from({ length: 12 }).map((_, i) => (
                    <div key={i} className="aspect-video bg-surface border border-border animate-pulse" />
                  ))}
                </Grid>
              )
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
                  ) : transcriptsView ? (
                    <div className="relative -top-6 -mr-4 md:-mr-6">
                      <TranscriptRowHeader
                        sort={transcriptSort}
                        onSort={onTranscriptSort}
                        showStatus={isTranscriptAdmin}
                      />
                      <div className="divide-y divide-border">
                        {filtered.slice(0, visible).map((ep) => (
                          <TranscriptRow
                            key={ep.id}
                            episode={ep}
                            detailBase={detailBase}
                            status={statusOf(ep)}
                            showStatus={isTranscriptAdmin}
                          />
                        ))}
                      </div>
                    </div>
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
                noun={shortsView ? "shorts" : audioView ? "audio episodes" : transcriptsView ? "transcripts" : "episodes"}
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

const VIDEO_HEIGHT_KEY = "llu:episode-video-vh";
const VIDEO_HEIGHT_MIN = 18;
const VIDEO_HEIGHT_MAX = 92;
const VIDEO_HEIGHT_DEFAULT = 52;

const AUDIO_INTRO_OFFSET_SECONDS = 14;

function readStoredVideoHeight(): number {
  if (typeof window === "undefined") {
    return VIDEO_HEIGHT_DEFAULT;
  }
  const stored = Number(window.localStorage.getItem(VIDEO_HEIGHT_KEY));
  return stored >= VIDEO_HEIGHT_MIN && stored <= VIDEO_HEIGHT_MAX ? stored : VIDEO_HEIGHT_DEFAULT;
}

const TRANSCRIPT_WIDE_KEY = "llu:episode-transcript-wide";

function readStoredTranscriptWide(): boolean {
  if (typeof window === "undefined") {
    return false;
  }
  return window.localStorage.getItem(TRANSCRIPT_WIDE_KEY) === "1";
}

const ARTICLE_WIDE_KEY = "llu:transcript-article-wide";

function readStoredArticleWide(): boolean {
  if (typeof window === "undefined") {
    return true;
  }
  return window.localStorage.getItem(ARTICLE_WIDE_KEY) !== "0";
}

const TRANSCRIPT_CATEGORY_KEY = "llu:transcript-category";
const TRANSCRIPT_TIER_KEY = "llu:transcript-tier";

function readStoredTranscriptCategory(): EpisodeCategory | "" {
  const value = typeof window === "undefined" ? null : window.localStorage.getItem(TRANSCRIPT_CATEGORY_KEY);
  return value && (EPISODE_CATEGORIES as readonly string[]).includes(value) ? (value as EpisodeCategory) : "";
}

function readStoredTranscriptTier(): TranscriptTier | "none" | "" {
  const value = typeof window === "undefined" ? null : window.localStorage.getItem(TRANSCRIPT_TIER_KEY);
  return value === "done" || value === "youtube" || value === "none" ? value : "";
}

const READING_SETTINGS_KEY = "llu:transcript-reading";

type ReadingSettings = { highlight: boolean; autoScroll: boolean; textPx: number };

function readStoredReading(): ReadingSettings {
  const fallback: ReadingSettings = { highlight: true, autoScroll: false, textPx: 15 };
  if (typeof window === "undefined") {
    return fallback;
  }
  try {
    const raw = window.localStorage.getItem(READING_SETTINGS_KEY);
    return raw ? { ...fallback, ...(JSON.parse(raw) as Partial<ReadingSettings>) } : fallback;
  } catch {
    return fallback;
  }
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
  const transcriptEdit = useTranscriptEdit(episode.youtubeId ?? episode.id, transcript ?? []);
  const playerRef = useRef<HTMLIFrameElement>(null);
  const audioControlsRef = useRef<AudioControls>(null);
  const stickyRef = useRef<HTMLDivElement>(null);
  const rootRef = useRef<HTMLDivElement>(null);
  const [currentTime, setCurrentTime] = useState(0);
  const [headerHeight, setHeaderHeight] = useState(0);
  const [availableWidth, setAvailableWidth] = useState(0);
  const canGoWide = availableWidth > 1200;
  const [videoHeightVh, setVideoHeightVh] = useState<number>(readStoredVideoHeight);
  const [transcriptWide, setTranscriptWide] = useState<boolean>(readStoredTranscriptWide);
  const chapterRailReserve = 300 + 16;
  const boardWidth = Math.min(availableWidth || 1120, 1120);
  const videoMaxHeightPx = Math.max(0, Math.floor((boardWidth - chapterRailReserve) * 0.5625));
  const wideLayout = transcriptWide && canGoWide;
  const changeTranscriptWide = (wide: boolean) => {
    setTranscriptWide(wide);
    window.localStorage.setItem(TRANSCRIPT_WIDE_KEY, wide ? "1" : "0");
  };
  const isMobile = useIsMobile();
  const [reading, setReading] = useState<ReadingSettings>(() => readStoredReading());
  const changeReading = (next: ReadingSettings) => {
    setReading(next);
    window.localStorage.setItem(READING_SETTINGS_KEY, JSON.stringify(next));
  };
  const [resizing, setResizing] = useState(false);
  const [videoPlaying, setVideoPlaying] = useState(false);
  const [pointerOnVideo, setPointerOnVideo] = useState(false);
  const hideResizeTimer = useRef<number | null>(null);
  const resizeStart = useRef<{ y: number; vh: number } | null>(null);
  const showResizeHandle = pointerOnVideo || resizing || !videoPlaying;
  const enterVideo = () => {
    if (hideResizeTimer.current) {
      window.clearTimeout(hideResizeTimer.current);
      hideResizeTimer.current = null;
    }
    setPointerOnVideo(true);
  };
  const leaveVideo = () => {
    hideResizeTimer.current = window.setTimeout(() => setPointerOnVideo(false), 3000);
  };
  useEffect(() => () => window.clearTimeout(hideResizeTimer.current ?? undefined), []);
  const [readingHandleShown, setReadingHandleShown] = useState(false);
  const readingHideTimer = useRef<number | null>(null);
  const enterReadingHandle = () => {
    if (readingHideTimer.current) {
      window.clearTimeout(readingHideTimer.current);
      readingHideTimer.current = null;
    }
    setReadingHandleShown(true);
  };
  const leaveReadingHandle = () => {
    readingHideTimer.current = window.setTimeout(() => setReadingHandleShown(false), 3000);
  };
  useEffect(() => () => window.clearTimeout(readingHideTimer.current ?? undefined), []);
  const showReadingHandle = readingHandleShown || !videoPlaying;
  useLayoutEffect(() => {
    const el = stickyRef.current;
    if (!el) {
      return;
    }
    const measure = () => setHeaderHeight(el.getBoundingClientRect().height);
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(el);
    return () => observer.disconnect();
  }, []);
  useStickyScrollPadding(headerHeight);
  useLayoutEffect(() => {
    const parent = rootRef.current?.parentElement;
    if (!parent) {
      return;
    }
    const measure = () => {
      const style = getComputedStyle(parent);
      const pad = parseFloat(style.paddingLeft) + parseFloat(style.paddingRight);
      setAvailableWidth(parent.clientWidth - pad);
    };
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(parent);
    return () => observer.disconnect();
  }, []);
  const changeVideoHeight = (value: number) => {
    const clamped = Math.round(Math.min(VIDEO_HEIGHT_MAX, Math.max(VIDEO_HEIGHT_MIN, value)));
    setVideoHeightVh(clamped);
    window.localStorage.setItem(VIDEO_HEIGHT_KEY, String(clamped));
  };
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
      audioControlsRef.current?.seek(seconds + AUDIO_INTRO_OFFSET_SECONDS);
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
        if (data.event === "infoDelivery" && typeof data.info?.playerState === "number") {
          setVideoPlaying(data.info.playerState === 1 || data.info.playerState === 3);
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
  const richLayout = episode.hasTranscript || hasTranscript;
  const resizableVideo = richLayout && !usingAudioPlayer;
  const audioRich = richLayout && usingAudioPlayer;
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
      ref={rootRef}
      className={cn(
        "mx-auto w-full max-w-[1120px] lg:min-h-0",
        richLayout && transcriptWide && canGoWide && "lg:max-w-none lg:px-6",
        transcriptSettled ? "" : "min-h-[calc(100vh-9rem)]",
      )}
    >
      <div
        ref={stickyRef}
        className={cn(
          "z-30 -mx-4 -mt-6 bg-bg md:-mx-6 md:mt-0 md:px-6 md:py-2 lg:-mx-5 lg:-mt-6 lg:px-5 lg:pb-0 lg:pt-6",
          "sticky top-0",
        )}
      >
        <div
          className={cn("lg:flex lg:items-start lg:gap-4", wideLayout && "lg:justify-center")}
          style={
            resizableVideo
              ? ({ "--epv": `${videoHeightVh}vh`, "--epvmax": `${videoMaxHeightPx}px` } as CSSProperties)
              : undefined
          }
          onPointerEnter={richLayout ? enterReadingHandle : undefined}
          onPointerLeave={richLayout ? leaveReadingHandle : undefined}
        >
          <div
            className={cn("relative", richLayout && !usingAudioPlayer ? "lg:shrink-0" : "lg:min-w-0 lg:flex-1")}
            onPointerEnter={resizableVideo ? enterVideo : undefined}
            onPointerLeave={resizableVideo ? leaveVideo : undefined}
          >
            {usingAudioPlayer ? (
              <PodcastAudioPlayer
                ref={audioControlsRef}
                src={episode.audioUrl}
                title={episode.title}
                image={episode.image}
                pending={thumbnailPending}
                onTime={(seconds) => setCurrentTime(Math.max(0, seconds - AUDIO_INTRO_OFFSET_SECONDS))}
              />
            ) : (
              <div
                className={cn(
                  "relative aspect-video w-full overflow-hidden border-b border-border bg-surface md:mx-auto md:h-[36vh] md:w-auto md:rounded-lg md:border lg:mx-0 lg:rounded-none lg:border-0",
                  richLayout ? "lg:h-[var(--epv)] lg:max-h-[var(--epvmax)] lg:w-auto" : "lg:h-auto lg:w-full",
                )}
              >
                <EpisodeEmbed
                  episode={episode}
                  thumbnailPending={thumbnailPending}
                  audioMode={audioMode}
                  iframeRef={playerRef}
                  enableJsApi={!usingAudioPlayer}
                  audioControlsRef={audioControlsRef}
                />
                <div className="pointer-events-none absolute inset-0 z-10 hidden border-border lg:block lg:border" />
                {resizableVideo ? (
                  <Tooltip label="Drag to resize" side="top">
                  <div
                    role="separator"
                    aria-orientation="horizontal"
                    aria-label="Resize video"
                    onPointerDown={(e) => {
                      e.preventDefault();
                      setResizing(true);
                      resizeStart.current = { y: e.clientY, vh: videoHeightVh };
                      try {
                        e.currentTarget.setPointerCapture(e.pointerId);
                      } catch {
                        /* older browsers */
                      }
                    }}
                    onPointerMove={(e) => {
                      if (!resizeStart.current) {
                        return;
                      }
                      const dyVh = ((e.clientY - resizeStart.current.y) / window.innerHeight) * 100;
                      changeVideoHeight(resizeStart.current.vh + dyVh);
                    }}
                    onPointerUp={(e) => {
                      resizeStart.current = null;
                      setResizing(false);
                      try {
                        e.currentTarget.releasePointerCapture(e.pointerId);
                      } catch {
                        /* older browsers */
                      }
                    }}
                    onPointerCancel={() => {
                      resizeStart.current = null;
                      setResizing(false);
                    }}
                    className={cn(
                      "absolute bottom-2.5 left-1/2 z-20 hidden -translate-x-1/2 cursor-row-resize touch-none items-center justify-center gap-1.5 rounded-full border border-white/15 bg-black/55 px-3 py-1 text-white/85 backdrop-blur-sm transition-opacity duration-150 lg:flex",
                      showResizeHandle ? "opacity-100" : "pointer-events-none opacity-0",
                      resizing ? "border-green/70 text-green" : "hover:border-green/70 hover:text-green",
                    )}
                  >
                    <span className="h-px w-4 bg-current opacity-60" />
                    <ChevronsUpDown size={13} strokeWidth={2.25} className="shrink-0" />
                    <span className="h-px w-4 bg-current opacity-60" />
                  </div>
                </Tooltip>
                ) : null}
              </div>
            )}
          </div>
          {richLayout && !usingAudioPlayer && (hasTranscript || !transcriptSettled) ? (
            <aside className="relative hidden lg:flex lg:flex-col lg:w-[300px] lg:shrink-0 lg:h-[var(--epv)] lg:max-h-[var(--epvmax)]">
              {chapters.length > 0 || !transcriptSettled ? (
                <ChapterNav
                  className="lg:min-h-0 lg:shrink"
                  chapters={chapters}
                  activeT={activeChapterT}
                  onJump={jumpToChapter}
                  loading={chapters.length === 0}
                />
              ) : null}
              <div className="mt-auto flex items-center justify-between pt-2">
                <div
                  onPointerEnter={enterReadingHandle}
                  onPointerLeave={leaveReadingHandle}
                  className={cn(
                    "flex transition-opacity duration-200",
                    showReadingHandle ? "opacity-100" : "opacity-0",
                  )}
                >
                  <ReadingSettings
                    settings={reading}
                    onChange={changeReading}
                    wide={transcriptWide}
                    onWideChange={changeTranscriptWide}
                    isMobile={isMobile}
                    canGoWide={canGoWide}
                    panelUp
                    panelLeft
                    floating
                  />
                </div>
                <EditControls edit={transcriptEdit} floating />
              </div>
            </aside>
          ) : null}
        </div>
        <div className="pointer-events-none absolute inset-x-0 top-full hidden h-3 bg-gradient-to-b from-bg to-transparent lg:block" />
      </div>
      <div className={cn("w-full", audioRich && "lg:flex lg:items-start lg:gap-6")}>
        <div className={cn("min-w-0", audioRich && "lg:flex-1")}>
        <div className="mt-3 flex items-center justify-between gap-3 lg:mt-6">
          <h1 className="min-w-0 font-body text-text text-[16px] md:text-[20px] font-medium leading-snug">
            {episode.title}
          </h1>
          <div className="flex shrink-0 flex-col items-end gap-2">
            <EpisodeTag episode={episode} className={richLayout ? "hidden md:flex" : undefined} />
            {richLayout ? null : (
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
            currentTime={currentTime}
            collapsedChapters={collapsedChapters}
            onToggleChapter={toggleChapter}
            features={reading}
            topInset={headerHeight}
            edit={transcriptEdit}
            headerAction={
              isMobile ? (
                <ReadingSettings
                  settings={reading}
                  onChange={changeReading}
                  wide={transcriptWide}
                  onWideChange={changeTranscriptWide}
                  isMobile={isMobile}
                  canGoWide={canGoWide}
                />
              ) : undefined
            }
          />
        ) : !transcriptSettled && richLayout ? (
          <TranscriptBodySkeleton />
        ) : transcriptSettled && moreEpisodes.length > 0 ? (
          <MoreEpisodes episodes={moreEpisodes} />
        ) : null}
        </div>
        {audioRich && (chapters.length > 0 || !transcriptSettled) ? (
          <aside
            className="hidden lg:mt-6 lg:flex lg:flex-col lg:sticky lg:self-start lg:w-[300px] lg:shrink-0"
            style={{ top: headerHeight + 24 }}
          >
            <ChapterNav
              style={{ maxHeight: `calc(100vh - ${headerHeight + 84}px)` }}
              chapters={chapters}
              activeT={activeChapterT}
              onJump={jumpToChapter}
              loading={chapters.length === 0}
            />
            <div className="flex items-center justify-between pt-2">
              <ReadingSettings
                settings={reading}
                onChange={changeReading}
                wide={transcriptWide}
                onWideChange={changeTranscriptWide}
                isMobile={isMobile}
                canGoWide={canGoWide}
                panelUp
                panelLeft
              />
              <EditControls edit={transcriptEdit} />
            </div>
          </aside>
        ) : null}
      </div>
    </div>
  );
}

function ReadingSettings({
  settings,
  onChange,
  wide,
  onWideChange,
  isMobile,
  canGoWide,
  panelUp = false,
  panelLeft = false,
  floating = false,
  articleMode = false,
  block = false,
}: {
  settings: ReadingSettings;
  onChange: (next: ReadingSettings) => void;
  wide: boolean;
  onWideChange: (wide: boolean) => void;
  isMobile: boolean;
  canGoWide: boolean;
  panelUp?: boolean;
  panelLeft?: boolean;
  floating?: boolean;
  articleMode?: boolean;
  block?: boolean;
}) {
  const [open, setOpen] = useState(false);
  const body = (
    <div className="flex flex-col">
      <SettingRow label="Text Size">
        <div className="flex items-center gap-1.5">
          <span className="font-display text-[11px] leading-none text-muted">A</span>
          <input
            type="range"
            min={13}
            max={17}
            step={1}
            value={settings.textPx}
            onChange={(e) => onChange({ ...settings, textPx: Number(e.target.value) })}
            aria-label="Text size"
            className="h-1 w-16 cursor-pointer accent-green hover:accent-green-2"
          />
          <span className="font-display text-[15px] leading-none text-muted">A</span>
        </div>
      </SettingRow>
      {articleMode ? null : (
        <>
          <div className="my-1 h-px bg-border" />
          <ToggleRow
            label="Read Along"
            on={settings.highlight}
            onToggle={() => onChange({ ...settings, highlight: !settings.highlight })}
          />
          <ToggleRow
            label="Auto-Scroll"
            on={settings.autoScroll}
            onToggle={() => onChange({ ...settings, autoScroll: !settings.autoScroll })}
          />
        </>
      )}
      {canGoWide ? <ToggleRow label="Full Width" on={wide} onToggle={() => onWideChange(!wide)} /> : null}
    </div>
  );
  return (
    <div className={cn("relative", block && "w-full")}>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        aria-label="Reading options"
        className={cn(
          "flex h-8 cursor-pointer items-center border leading-none transition-colors",
          isMobile
            ? "w-8 justify-center"
            : block
              ? "w-full justify-center gap-1.5 px-2 font-display text-[13px] tracking-[0.02em]"
              : "gap-1.5 px-2.5 font-display text-[14px] tracking-[0.04em]",
          open ? "relative z-50" : "",
          floating && !open && "bg-surface/95 text-subtle shadow-[0_6px_18px_rgba(0,0,0,0.45)] backdrop-blur-sm",
          open
            ? "border-green bg-surface text-green"
            : cn("border-border2 hover:border-green hover:text-green", floating ? "" : "bg-transparent text-subtle"),
        )}
      >
        <Settings size={isMobile ? 16 : 14} strokeWidth={2} className="shrink-0" />
        {isMobile ? null : (
          <>
            <span className="whitespace-nowrap">{block ? "Options" : "Reading options"}</span>
            <ChevronDown
              size={14}
              strokeWidth={2.25}
              className={cn("shrink-0 transition-transform", open ? "rotate-180" : "")}
            />
          </>
        )}
      </button>
      {open ? (
        <>
          <button
            aria-hidden
            tabIndex={-1}
            onClick={() => setOpen(false)}
            className="fixed inset-0 z-40 cursor-default"
          />
          <div
            className={cn(
              "z-50 border border-border2 bg-surface shadow-[0_12px_34px_rgba(0,0,0,0.6)]",
              isMobile
                ? "fixed inset-x-0 bottom-0 border-x-0 border-b-0 px-4 pb-6 pt-4"
                : cn(
                    "absolute w-52 px-3 py-2",
                    panelUp ? "bottom-full mb-2" : "top-full mt-2",
                    panelLeft ? "left-0" : "right-0",
                  ),
            )}
          >
            {isMobile ? (
              <div className="mb-2 flex items-center justify-between">
                <span className="font-display text-[16px] tracking-[0.02em] text-text">Reading options</span>
                <button type="button" onClick={() => setOpen(false)} aria-label="Close" className="text-muted hover:text-green">
                  <X size={18} />
                </button>
              </div>
            ) : null}
            {body}
          </div>
        </>
      ) : null}
    </div>
  );
}

function SettingRow({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="-mx-1 flex items-center justify-between gap-4 rounded px-1 py-1.5 transition-colors hover:bg-white/[0.04]">
      <span className="font-num text-[12px] tracking-[0.01em] text-subtle">{label}</span>
      {children}
    </div>
  );
}

function ToggleRow({ label, on, onToggle }: { label: string; on: boolean; onToggle: () => void }) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={on}
      aria-label={label}
      onClick={onToggle}
      className="-mx-1 flex w-full cursor-pointer items-center justify-between gap-4 rounded px-1 py-1.5 text-left transition-colors hover:bg-white/[0.04]"
    >
      <span className="font-num text-[12px] tracking-[0.01em] text-subtle">{label}</span>
      <ToggleSwitch on={on} />
    </button>
  );
}

function ChapterNav({
  chapters,
  activeT,
  onJump,
  loading,
  className,
  style,
  hideTime = false,
  compact = false,
}: {
  chapters: { t: number; heading: string }[];
  activeT: number;
  onJump: (t: number) => void;
  loading: boolean;
  className?: string;
  style?: CSSProperties;
  hideTime?: boolean;
  compact?: boolean;
}) {
  return (
    <nav
      className={cn(
        "flex flex-col overflow-y-auto border border-border bg-surface/40",
        compact ? "items-stretch px-0 [scrollbar-width:none] [&::-webkit-scrollbar]:hidden" : "px-3",
        className,
      )}
      style={style}
    >
      {loading
        ? Array.from({ length: 9 }).map((_, i) => (
            <div
              key={i}
              className="flex items-center justify-between gap-3 border-t border-border/40 py-2.5 first:border-t-0"
            >
              <div className="h-3 flex-1 animate-pulse bg-border" style={{ maxWidth: `${70 - (i % 3) * 14}%` }} />
              <div className="h-3 w-8 animate-pulse bg-border" />
            </div>
          ))
        : chapters.map((chapter) => {
            const isActive = chapter.t === activeT;
            if (compact) {
              return (
                <button
                  key={chapter.t}
                  type="button"
                  onClick={() => onJump(chapter.t)}
                  title={chapter.heading}
                  className="group flex cursor-pointer items-center justify-center border-t border-border/40 py-2.5 leading-snug first:border-t-0"
                >
                  <span
                    className={cn(
                      "font-display text-[15px] uppercase leading-snug transition-colors group-hover:text-green",
                      isActive ? "text-green" : "text-subtle",
                    )}
                  >
                    {chapter.heading.trim().charAt(0)}
                  </span>
                </button>
              );
            }
            return (
              <button
                key={chapter.t}
                type="button"
                onClick={() => onJump(chapter.t)}
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
                {hideTime ? null : (
                  <span className="font-num shrink-0 text-[12px] text-green">{formatTimestamp(chapter.t)}</span>
                )}
              </button>
            );
          })}
    </nav>
  );
}

function TranscriptArticle({ episode }: { episode: Episode }) {
  const { transcript, settled } = useEpisodeTranscript(episode);
  const transcriptEdit = useTranscriptEdit(episode.youtubeId ?? episode.id, transcript ?? []);
  const [collapsedChapters, setCollapsedChapters] = useState<ReadonlySet<number>>(() => new Set());
  const [reading, setReading] = useState<ReadingSettings>(readStoredReading);
  const changeReading = (next: ReadingSettings) => {
    setReading(next);
    window.localStorage.setItem(READING_SETTINGS_KEY, JSON.stringify(next));
  };
  const [wide, setWide] = useState<boolean>(readStoredArticleWide);
  const changeWide = (value: boolean) => {
    setWide(value);
    window.localStorage.setItem(ARTICLE_WIDE_KEY, value ? "1" : "0");
  };
  const [headerHeight, setHeaderHeight] = useState(0);
  const headerObserver = useRef<ResizeObserver | null>(null);
  const headerRef = useCallback((el: HTMLDivElement | null) => {
    headerObserver.current?.disconnect();
    if (!el) {
      return;
    }
    const measure = () => setHeaderHeight(el.getBoundingClientRect().height);
    measure();
    headerObserver.current = new ResizeObserver(measure);
    headerObserver.current.observe(el);
  }, []);
  useStickyScrollPadding(headerHeight);
  const chapters = useMemo(
    () => (transcript ?? []).filter((s) => s.heading).map((s) => ({ t: s.t, heading: s.heading as string })),
    [transcript],
  );
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
  const jumpToHeading = (t: number) => {
    setCollapsedChapters((prev) => {
      if (!prev.has(t)) {
        return prev;
      }
      const next = new Set(prev);
      next.delete(t);
      return next;
    });
    const target = document.getElementById(`ch-${t}`);
    if (!target) {
      return;
    }
    animateScrollTo(target.getBoundingClientRect().top + window.scrollY - headerHeight - 12);
  };
  const plainText = useMemo(
    () => (transcript ? transcriptToText(episode.title, transcript) : ""),
    [transcript, episode.title],
  );
  const hasBody = Boolean(transcript && transcript.length > 0);
  const hasChapters = chapters.length > 0;
  const download = () => downloadTextFile(`${episode.slug ?? "transcript"}.txt`, plainText);
  const [activeChapterT, setActiveChapterT] = useState(-1);
  useEffect(() => {
    if (!hasChapters) {
      return;
    }
    let queued = false;
    const update = () => {
      queued = false;
      const threshold = headerHeight + 28;
      let active = -1;
      for (const chapter of chapters) {
        const el = document.getElementById(`ch-${chapter.t}`);
        if (el && el.getBoundingClientRect().top <= threshold) {
          active = chapter.t;
        } else {
          break;
        }
      }
      setActiveChapterT(active);
    };
    const onScroll = () => {
      if (queued) {
        return;
      }
      queued = true;
      requestAnimationFrame(update);
    };
    update();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, [hasChapters, chapters, headerHeight]);
  const readingControl = (mobile: boolean, block = false) => (
    <ReadingSettings
      settings={reading}
      onChange={changeReading}
      wide={wide}
      onWideChange={changeWide}
      isMobile={mobile}
      canGoWide={!mobile}
      articleMode
      block={block}
      panelUp={false}
      panelLeft={false}
    />
  );

  return (
    <div className={cn("mx-auto w-full max-w-[1120px]", wide && "lg:max-w-none lg:px-6")}>
      {hasBody ? (
        <div className={cn("lg:flex lg:items-start lg:gap-10", wide && "lg:gap-6")}>
          <div className={cn("min-w-0 flex-1", wide ? "lg:max-w-none" : "lg:max-w-3xl")}>
            <div ref={headerRef} className="sticky top-0 z-20 bg-bg pt-3 pb-4 lg:pt-6 lg:pb-6">
              <div className="flex items-center justify-between gap-3">
                <h1 className="min-w-0 font-body text-text text-[16px] md:text-[20px] font-medium leading-snug">
                  {episode.title}
                </h1>
                <div className="flex shrink-0 items-center gap-3">
                  <span className="hidden font-num text-[12px] tracking-[0.06em] text-muted sm:inline">
                    {episode.publishedLabel.toUpperCase()}
                  </span>
                  <EpisodeTag episode={episode} />
                </div>
              </div>
            </div>
            <div className="border-t border-border">
              <EpisodeTranscript
                segments={transcript as TranscriptSegment[]}
                setCode={episode.setCode}
                currentTime={0}
                collapsedChapters={collapsedChapters}
                onToggleChapter={toggleChapter}
                features={{ articleMode: true, textPx: reading.textPx }}
                edit={transcriptEdit}
                headerAction={
                  <div className="flex items-center gap-2 lg:hidden">
                    {readingControl(true)}
                    <button
                      type="button"
                      onClick={download}
                      aria-label="Download transcript"
                      className="flex h-8 w-8 items-center justify-center border border-border2 text-subtle transition-colors hover:border-green hover:text-green"
                    >
                      <Download size={16} strokeWidth={2} />
                    </button>
                  </div>
                }
              />
            </div>
          </div>
          {hasChapters ? (
            <aside
              className="hidden lg:mt-6 lg:flex lg:flex-col lg:sticky lg:self-start lg:w-[300px] lg:shrink-0"
              style={{ top: 24 }}
            >
              <ChapterNav
                className="overflow-y-auto"
                style={{ maxHeight: "calc(100vh - 112px)" }}
                chapters={chapters}
                activeT={activeChapterT}
                onJump={jumpToHeading}
                loading={false}
                hideTime
              />
              <div className={cn("mt-3 grid gap-2", transcriptEdit.canEdit ? "grid-cols-3" : "grid-cols-2")}>
                <EditControls edit={transcriptEdit} block />
                <button
                  type="button"
                  onClick={download}
                  className="flex h-8 w-full items-center justify-center gap-1.5 border border-border2 px-2 font-display text-[13px] leading-none tracking-[0.02em] text-subtle transition-colors hover:border-green hover:text-green"
                >
                  <Download size={14} strokeWidth={2} className="shrink-0" />
                  <span className="leading-none">Download</span>
                </button>
                {readingControl(false, true)}
              </div>
            </aside>
          ) : null}
        </div>
      ) : settled ? (
        <div className="mx-auto max-w-3xl pt-6 lg:pt-10">
          <div className="flex items-center justify-between gap-3">
            <h1 className="min-w-0 font-body text-text text-[16px] md:text-[20px] font-medium leading-snug">
              {episode.title}
            </h1>
            <div className="flex shrink-0 items-center gap-3">
              <span className="hidden font-num text-[12px] tracking-[0.06em] text-muted sm:inline">
                {episode.publishedLabel.toUpperCase()}
              </span>
              <EpisodeTag episode={episode} />
            </div>
          </div>
          <p className="mt-6 text-[14px] text-muted">No transcript available</p>
          {(episode.youtubeId || episode.audioUrl) && episode.slug ? (
            <div className="mt-4 flex flex-wrap items-center gap-x-5 gap-y-2">
              {episode.youtubeId ? (
                <Link
                  to={`/episodes/${categorySlug(episode.category)}/${episode.slug}`}
                  className="inline-flex items-center gap-1.5 text-[14px] text-subtle transition-colors hover:text-green"
                >
                  <SiYoutube size={15} className="shrink-0" />
                  Watch this episode
                </Link>
              ) : null}
              {episode.audioUrl ? (
                <Link
                  to={`/episodes/audio/${episode.slug}`}
                  className="inline-flex items-center gap-1.5 text-[14px] text-subtle transition-colors hover:text-green"
                >
                  <Headphones size={15} strokeWidth={2} className="shrink-0" />
                  Listen to this episode
                </Link>
              ) : null}
            </div>
          ) : null}
        </div>
      ) : (
        <TranscriptContentSkeleton />
      )}
    </div>
  );
}

function TranscriptContentSkeleton() {
  const wide = readStoredArticleWide();
  return (
    <div className={cn("lg:flex lg:items-start lg:gap-10", wide && "lg:gap-6")}>
      <div className={cn("min-w-0 flex-1", wide ? "lg:max-w-none" : "lg:max-w-3xl")}>
        <div className="flex items-center justify-between gap-3 pt-3 pb-4 lg:pt-6 lg:pb-6">
          <div className="h-6 w-2/3 max-w-xl animate-pulse rounded bg-surface md:h-7" />
          <div className="h-5 w-20 shrink-0 animate-pulse rounded bg-surface" />
        </div>
        <div className="border-t border-border pt-2 lg:pt-4">
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
      </div>
      <aside className="hidden lg:mt-6 lg:block lg:w-[300px] lg:shrink-0">
        <ChapterNav className="lg:max-h-[70vh]" chapters={[]} activeT={-1} onJump={() => {}} loading hideTime />
        <div className="mt-3 grid grid-cols-2 gap-2">
          <div className="h-8 animate-pulse bg-surface" />
          <div className="h-8 animate-pulse bg-surface" />
        </div>
      </aside>
    </div>
  );
}

function TranscriptArticleSkeleton() {
  const wide = readStoredArticleWide();
  return (
    <div className={cn("mx-auto w-full max-w-[1120px]", wide && "lg:max-w-none lg:px-6")}>
      <TranscriptContentSkeleton />
    </div>
  );
}

function EpisodeDetailSkeleton() {
  return (
    <div className="mx-auto w-full max-w-[1120px]">
      <div
        className="-mx-4 -mt-6 md:-mx-6 md:mt-0 md:px-6 lg:-mx-5 lg:px-5 lg:flex lg:items-start lg:gap-4"
        style={{ "--epv": `${VIDEO_HEIGHT_DEFAULT}vh` } as CSSProperties}
      >
        <div className="relative aspect-video w-full animate-pulse border-b border-border bg-surface md:mx-auto md:h-[36vh] md:w-auto md:rounded-lg md:border lg:mx-0 lg:h-[var(--epv)] lg:max-h-[calc((min(100vw,1120px)_-_316px)*0.5625)] lg:w-auto lg:shrink-0 lg:rounded-none lg:border-0" />
        <ChapterNav
          className="hidden lg:flex lg:w-[300px] lg:shrink-0 lg:max-h-[var(--epv,40vh)]"
          chapters={[]}
          activeT={-1}
          onJump={() => {}}
          loading
        />
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

type ParaLine = { t: number; text: string; speaker?: string; showName?: boolean; lane?: number };
type TranscriptItem =
  | { kind: "chapter"; t: number; heading: string }
  | { kind: "section"; t: number; title: string; paras: ParaLine[] }
  | { kind: "para"; t: number; text: string; speaker?: string; showName?: boolean; lane?: number };

const SPEAKER_LANES = [
  { border: "border-[#2ee85c]", name: "text-[#2ee85c]" },
  { border: "border-[#5ab0ff]", name: "text-[#5ab0ff]" },
  { border: "border-[#f0b74a]", name: "text-[#f0b74a]" },
  { border: "border-[#f087c0]", name: "text-[#f087c0]" },
];

function annotateSpeakers(items: TranscriptItem[]): void {
  const laneOf = new Map<string, number>();
  let named = new Set<string>();
  const mark = (para: ParaLine) => {
    if (!para.speaker) {
      return;
    }
    if (!laneOf.has(para.speaker)) {
      laneOf.set(para.speaker, laneOf.size);
    }
    para.lane = laneOf.get(para.speaker);
    if (!named.has(para.speaker)) {
      para.showName = true;
      named.add(para.speaker);
    }
  };
  for (const item of items) {
    if (item.kind === "chapter") {
      named = new Set();
    } else if (item.kind === "para") {
      mark(item);
    } else if (item.kind === "section") {
      item.paras.forEach(mark);
    }
  }
}

function escapeRegExp(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

const chapterSlug = (heading: string) =>
  heading
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");

function useStickyScrollPadding(headerHeight: number): void {
  useEffect(() => {
    const root = document.documentElement;
    root.style.scrollPaddingTop = headerHeight ? `${headerHeight + 12}px` : "";
    return () => {
      root.style.scrollPaddingTop = "";
    };
  }, [headerHeight]);
}

const PATREON_URL = "https://www.patreon.com/limitedlevelups";
const PATREON_PHRASE = /patreon(?:\.com|\s+dot\s+com)?\s*(?:\/|\s+slash\s+)\s*limited[-\s]*level[-\s]*ups/gi;
const DOMAIN_LINK = /\b(?:https?:\/\/)?(?:www\.)?(17lands\.com|limitedlevelups\.com)(\/[^\s)]*)?/gi;


type TranscriptFeatures = {
  highlight?: boolean;
  autoScroll?: boolean;
  textPx?: number;
  articleMode?: boolean;
};

type SaveStatus = "idle" | "saving" | "saved" | "error";

interface TranscriptEdit {
  canEdit: boolean;
  editing: boolean;
  working: TranscriptSegment[];
  saving: boolean;
  status: SaveStatus;
  message: string | null;
  canSave: boolean;
  enterEdit: () => void;
  discard: () => void;
  save: () => void;
  dismiss: () => void;
  markInput: () => void;
  editBlock: (index: number, field: "text" | "heading" | "subheading", value: string) => void;
  dropSubheading: (index: number) => void;
}

function useTranscriptEdit(episodeKey: string | undefined, segments: TranscriptSegment[]): TranscriptEdit {
  const { user } = useAuth();
  const queryClient = useQueryClient();
  const canEdit = Boolean(episodeKey) && isAdmin(user?.discordId);
  const [editing, setEditing] = useState(false);
  const [working, setWorking] = useState<TranscriptSegment[]>(segments);
  const [status, setStatus] = useState<SaveStatus>("idle");
  const [message, setMessage] = useState<string | null>(null);
  const [touched, setTouched] = useState(false);
  const saving = status === "saving";

  const enterEdit = () => {
    setWorking(structuredClone(segments));
    setStatus("idle");
    setMessage(null);
    setTouched(false);
    setEditing(true);
  };
  const discard = () => {
    setEditing(false);
    setStatus("idle");
    setMessage(null);
    setTouched(false);
  };
  const markInput = () => setTouched(true);
  const editBlock = (index: number, field: "text" | "heading" | "subheading", value: string) => {
    setTouched(false);
    setWorking((prev) => {
      const next = prev.slice();
      const segment = { ...next[index] };
      if (field === "text") {
        segment.text = value;
      } else {
        const trimmed = value.trim();
        if (trimmed) {
          segment[field] = trimmed;
        } else {
          delete segment[field];
        }
      }
      next[index] = segment;
      return next;
    });
  };
  const dropSubheading = (index: number) => {
    setWorking((prev) => {
      const next = prev.slice();
      const segment = { ...next[index] };
      delete segment.subheading;
      next[index] = segment;
      return next;
    });
  };

  const dirty = useMemo(() => JSON.stringify(working) !== JSON.stringify(segments), [working, segments]);
  const hasEmptyParagraph = useMemo(() => working.some((segment) => !segment.text.trim()), [working]);
  const canSave = (dirty || touched) && !hasEmptyParagraph && !saving;

  const save = async () => {
    if (!episodeKey || !canSave) {
      return;
    }
    setStatus("saving");
    setMessage(null);
    try {
      const saved = await saveTranscript(episodeKey, working);
      queryClient.setQueryData(["episode-transcript", episodeKey], saved);
      setEditing(false);
      setStatus("saved");
      window.setTimeout(() => setStatus((prev) => (prev === "saved" ? "idle" : prev)), 2500);
    } catch (err) {
      setStatus("error");
      setMessage(err instanceof Error ? err.message : "Save failed");
      window.setTimeout(() => setStatus((prev) => (prev === "error" ? "idle" : prev)), 6000);
    }
  };
  const dismiss = () => {
    setStatus("idle");
    setMessage(null);
  };

  return {
    canEdit, editing, working, saving, status, message, canSave,
    enterEdit, discard, save, dismiss, markInput, editBlock, dropSubheading,
  };
}

function EditControls({
  edit,
  floating = false,
  block = false,
}: {
  edit: TranscriptEdit;
  floating?: boolean;
  block?: boolean;
}) {
  if (!edit.canEdit) {
    return null;
  }
  const buttonBase =
    "flex h-8 items-center justify-center gap-1.5 border px-2.5 font-display text-[13px] leading-none tracking-[0.02em] transition-colors";
  const chrome = floating ? "bg-surface/95 shadow-[0_6px_18px_rgba(0,0,0,0.45)] backdrop-blur-sm" : "";
  if (!edit.editing) {
    return (
      <button
        type="button"
        onClick={edit.enterEdit}
        className={cn(buttonBase, chrome, block && "w-full", "border-border2 text-subtle hover:border-green hover:text-green")}
      >
        <Pencil size={14} strokeWidth={2} className="shrink-0" />
        <span className="leading-none">Edit</span>
      </button>
    );
  }
  const discardButton = (
    <button
      type="button"
      onClick={edit.discard}
      aria-label="Discard"
      className={cn(
        "flex h-8 w-8 shrink-0 items-center justify-center border transition-colors",
        chrome,
        "border-border2 text-subtle hover:border-text hover:text-text",
      )}
    >
      <X size={16} strokeWidth={2} />
    </button>
  );
  const saveButton = (
    <button
      type="button"
      onClick={edit.save}
      disabled={!edit.canSave}
      className={cn(
        buttonBase,
        chrome,
        block && "flex-1 px-1.5",
        "border-green text-green hover:bg-green/10",
        "disabled:cursor-not-allowed disabled:border-border2 disabled:text-dim disabled:hover:bg-transparent",
      )}
    >
      {edit.saving ? (
        <>
          <Loader2 size={14} strokeWidth={2} className="shrink-0 animate-spin" />
          <span className="leading-none">Saving</span>
        </>
      ) : (
        "Save"
      )}
    </button>
  );
  if (block) {
    return (
      <div className="flex gap-1.5">
        {discardButton}
        {saveButton}
      </div>
    );
  }
  return (
    <div className="flex items-center gap-2">
      {discardButton}
      {saveButton}
    </div>
  );
}

function EpisodeTranscript({
  segments,
  setCode,
  onSeek,
  currentTime,
  collapsedChapters,
  onToggleChapter,
  features,
  topInset = 0,
  headerAction,
  edit,
}: {
  segments: TranscriptSegment[];
  setCode?: string | null;
  onSeek?: (seconds: number) => void;
  currentTime: number;
  collapsedChapters: ReadonlySet<number>;
  onToggleChapter: (t: number) => void;
  features?: TranscriptFeatures;
  topInset?: number;
  headerAction?: ReactNode;
  edit?: TranscriptEdit;
}) {
  const articleMode = features?.articleMode ?? false;
  const highlight = (features?.highlight ?? true) && !articleMode;
  const autoScroll = (features?.autoScroll ?? false) && !articleMode;
  const textPx = features?.textPx ?? 15;
  const bodyRef = useRef<HTMLDivElement>(null);
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
      const text = stripSpeakerTurns(segment.text);
      const speaker = segment.speaker;
      if (segment.heading) {
        section = null;
        out.push({ kind: "chapter", t: segment.t, heading: segment.heading });
        out.push({ kind: "para", t: segment.t, text, speaker });
      } else if (segment.subheading) {
        section = { kind: "section", t: segment.t, title: segment.subheading, paras: [{ t: segment.t, text, speaker }] };
        out.push(section);
      } else if (section) {
        section.paras.push({ t: segment.t, text, speaker });
      } else {
        const prev = out[out.length - 1];
        if (speaker && prev && prev.kind === "para" && prev.speaker === speaker) {
          prev.text = `${prev.text}\n\n${text}`;
        } else {
          out.push({ kind: "para", t: segment.t, text, speaker });
        }
      }
    }
    annotateSpeakers(out);
    return out;
  }, [segments]);

  const firstChapterIndex = items.findIndex((item) => item.kind === "chapter");

  const hashLocation = useLocation();
  const handledHash = useRef("");
  useEffect(() => {
    const raw = decodeURIComponent(hashLocation.hash.replace(/^#/, "")).trim();
    if (!raw || items.length === 0 || handledHash.current === raw) {
      return;
    }
    let target: number | null = null;
    const tsMatch = raw.match(/^ch-(\d+)$/i);
    if (tsMatch) {
      target = Number(tsMatch[1]);
    } else {
      const wanted = raw.toLowerCase();
      for (const item of items) {
        if (item.kind === "chapter" && chapterSlug(item.heading) === wanted) {
          target = item.t;
          break;
        }
      }
    }
    if (target === null) {
      return;
    }
    handledHash.current = raw;
    if (collapsedChapters.has(target)) {
      onToggleChapter(target);
    }
    const t = target;
    window.setTimeout(() => {
      document.getElementById(`ch-${t}`)?.scrollIntoView({ behavior: "smooth", block: "start" });
    }, 80);
  }, [hashLocation.hash, items, collapsedChapters, onToggleChapter]);

  const activeParaT = useMemo(() => {
    if (!(currentTime > 0)) {
      return -1;
    }
    let best = -1;
    const consider = (t: number) => {
      if (t <= currentTime + 0.5 && t > best) {
        best = t;
      }
    };
    for (const item of items) {
      if (item.kind === "para") {
        consider(item.t);
      } else if (item.kind === "section") {
        item.paras.forEach((para) => consider(para.t));
      }
    }
    return best;
  }, [items, currentTime]);

  useEffect(() => {
    if (!autoScroll || !highlight) {
      return;
    }
    const active = bodyRef.current?.querySelector<HTMLElement>('[data-active="true"]');
    if (!active) {
      return;
    }
    const rect = active.getBoundingClientRect();
    const safeTop = topInset + 16;
    const safeBottom = window.innerHeight - 16;
    let delta = 0;
    if (rect.top < safeTop) {
      delta = rect.top - safeTop;
    } else if (rect.bottom > safeBottom) {
      delta = rect.bottom - safeBottom;
    }
    if (delta !== 0) {
      window.scrollBy({ top: delta, behavior: "smooth" });
    }
  }, [activeParaT, autoScroll, highlight, topInset]);

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
        item.paras.forEach((para, paraIndex) => map.set(`${index}:${paraIndex}`, allow(para.text)));
      } else {
        map.set(`${index}:0`, allow(item.text));
      }
    });
    return map;
  }, [items, cardNames]);

  const renderCards = (text: string, allowed: Set<string> | undefined, linkedHere: Set<string>): ReactNode => {
    if (cardNames.length === 0) {
      return text;
    }
    const pattern = new RegExp(`(${cardNames.map(escapeRegExp).join("|")})`, "g");
    return text.split(pattern).map((part, index) => {
      if (!cardNameSet.has(part)) {
        return part;
      }
      if (allowed?.has(part) && !linkedHere.has(part)) {
        linkedHere.add(part);
        return <TranscriptCardLink key={index} name={part} set={setCode ?? undefined} cardImages={cardImages} />;
      }
      return (
        <em key={index} className="text-subtle/90 italic">
          {part}
        </em>
      );
    });
  };

  const renderText = (text: string, allowed: Set<string> | undefined): ReactNode => {
    const linkedHere = new Set<string>();
    const linkClass = "text-green underline transition-colors hover:text-green/70";
    const hits: { start: number; end: number; node: ReactNode }[] = [];
    PATREON_PHRASE.lastIndex = 0;
    for (let match: RegExpExecArray | null; (match = PATREON_PHRASE.exec(text)) !== null; ) {
      hits.push({
        start: match.index,
        end: match.index + match[0].length,
        node: (
          <a href={PATREON_URL} target="_blank" rel="noreferrer" className={linkClass}>
            patreon.com/limitedlevelups
          </a>
        ),
      });
    }
    DOMAIN_LINK.lastIndex = 0;
    for (let match: RegExpExecArray | null; (match = DOMAIN_LINK.exec(text)) !== null; ) {
      const shown = match[0];
      const href = `https://${match[1]}${match[2] ?? ""}`;
      hits.push({
        start: match.index,
        end: match.index + shown.length,
        node: (
          <a href={href} target="_blank" rel="noreferrer" className={linkClass}>
            {shown}
          </a>
        ),
      });
    }
    if (hits.length === 0) {
      return renderCards(text, allowed, linkedHere);
    }
    hits.sort((a, b) => a.start - b.start);
    const nodes: ReactNode[] = [];
    let last = 0;
    let key = 0;
    for (const hit of hits) {
      if (hit.start < last) {
        continue;
      }
      if (hit.start > last) {
        nodes.push(<Fragment key={key++}>{renderCards(text.slice(last, hit.start), allowed, linkedHere)}</Fragment>);
      }
      nodes.push(<Fragment key={key++}>{hit.node}</Fragment>);
      last = hit.end;
    }
    if (last < text.length) {
      nodes.push(<Fragment key={key++}>{renderCards(text.slice(last), allowed, linkedHere)}</Fragment>);
    }
    return nodes;
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
    <div className={cn(articleMode ? "pt-2 lg:pt-4" : "mt-4 border-t border-border pt-4 lg:mt-6")}>
      {edit && edit.status !== "idle" ? (
        <button
          type="button"
          onClick={edit.dismiss}
          aria-label="Dismiss"
          className={cn(
            "fixed bottom-6 left-1/2 z-50 flex -translate-x-1/2 cursor-pointer items-center gap-2 rounded-md border px-3 py-2",
            "bg-surface/95 text-[13px] shadow-lg shadow-black/50 backdrop-blur-sm transition-colors hover:bg-surface",
            edit.status === "error"
              ? "border-red-400/60 text-red-400"
              : edit.status === "saved"
                ? "border-green/60 text-green"
                : "border-border2 text-subtle",
          )}
        >
          {edit.status === "saving" ? <Loader2 size={14} className="shrink-0 animate-spin" /> : null}
          {edit.status === "saved" ? <Check size={14} className="shrink-0" /> : null}
          {edit.status === "error" ? <X size={14} className="shrink-0" /> : null}
          <span>{edit.status === "saving" ? "Saving…" : edit.status === "saved" ? "Saved" : edit.message}</span>
        </button>
      ) : null}
      {edit?.editing ? (
        <div className="w-full" style={{ ["--tsize" as string]: `${textPx}px` }}>
          {edit.working.map((segment, index) => (
            <EditableSegment
              key={index}
              index={index}
              segment={segment}
              onEdit={edit.editBlock}
              onInput={edit.markInput}
              onDropSubheading={edit.dropSubheading}
            />
          ))}
        </div>
      ) : (
      <div ref={bodyRef} className="w-full" style={{ ["--tsize" as string]: `${textPx}px` }}>
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
                className={cn(
                  "mb-1.5 flex items-center gap-2 scroll-mt-[calc(56vw+1rem)] lg:scroll-mt-4",
                  index === firstChapterIndex ? "mt-0" : "mt-8",
                )}
              >
                <button
                  type="button"
                  onClick={() => {
                    const slug = chapterSlug(item.heading);
                    handledHash.current = slug;
                    window.history.replaceState(null, "", `#${slug}`);
                    onToggleChapter(item.t);
                  }}
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
                {articleMode ? null : onSeek ? (
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
                {headerAction && index === firstChapterIndex ? <div className="ml-auto">{headerAction}</div> : null}
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
                  {articleMode ? null : onSeek ? (
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
                  : item.paras.map((para, paraIndex) => {
                      const active = highlight && para.t === activeParaT;
                      return (
                        <p
                          key={paraIndex}
                          data-active={active}
                          className={cn(
                            "text-[length:var(--tsize,15px)] leading-[1.6] mt-2 transition-colors",
                            active ? "-ml-4 border-l-2 border-green pl-4 text-text" : "text-subtle",
                          )}
                        >
                          {renderText(para.text, linkable.get(`${index}:${paraIndex}`))}
                        </p>
                      );
                    })}
              </div>
            );
          }
          const isActive = highlight && item.t === activeParaT;
          if (item.speaker) {
            const lane = SPEAKER_LANES[(item.lane ?? 0) % SPEAKER_LANES.length];
            const linked = linkable.get(`${index}:0`);
            return (
              <div key={index} className="mt-5">
                {item.showName ? (
                  <span className={cn("mb-1.5 block font-display text-[14px] tracking-[0.1em] leading-none", lane.name)}>
                    {item.speaker}
                  </span>
                ) : null}
                <div className={cn("border-l-2 pl-4", lane.border)}>
                  {item.text.split("\n\n").map((para, paraIndex) => (
                    <p
                      key={paraIndex}
                      data-active={isActive && paraIndex === 0}
                      className="text-[length:var(--tsize,15px)] leading-[1.6] mt-2 first:mt-0 text-subtle"
                    >
                      {renderText(para, linked)}
                    </p>
                  ))}
                </div>
              </div>
            );
          }
          return (
            <p
              key={index}
              data-active={isActive}
              className={cn(
                "text-[length:var(--tsize,15px)] leading-[1.6] mt-2 transition-colors",
                isActive ? "-ml-4 border-l-2 border-green pl-4 text-text" : "text-subtle",
              )}
            >
              {renderText(item.text, linkable.get(`${index}:0`))}
            </p>
          );
        })}
      </div>
      )}
    </div>
  );
}

function EditableSegment({
  index,
  segment,
  onEdit,
  onInput,
  onDropSubheading,
}: {
  index: number;
  segment: TranscriptSegment;
  onEdit: (index: number, field: "text" | "heading" | "subheading", value: string) => void;
  onInput: () => void;
  onDropSubheading: (index: number) => void;
}) {
  const box =
    "-mx-1 min-h-[1.2em] cursor-text rounded-sm px-1 outline-none transition-colors hover:bg-green/5 focus:bg-green/10 focus:ring-1 focus:ring-green/40";
  const commitOnShiftEnter = (e: ReactKeyboardEvent<HTMLDivElement>) => {
    if (e.key === "Enter" && e.shiftKey) {
      e.preventDefault();
      e.currentTarget.blur();
    }
  };
  const commitOnEnter = (e: ReactKeyboardEvent<HTMLDivElement>) => {
    if (e.key === "Enter") {
      e.preventDefault();
      e.currentTarget.blur();
    }
  };
  return (
    <div className="mt-3 first:mt-0">
      {segment.heading !== undefined ? (
        <div
          id={`ch-${segment.t}`}
          contentEditable
          suppressContentEditableWarning
          data-idx={index}
          data-field="heading"
          onKeyDown={commitOnEnter}
          onInput={onInput}
          onBlur={(e) => onEdit(index, "heading", e.currentTarget.innerText)}
          className={cn(
            "mb-1 scroll-mt-[calc(56vw+1rem)] font-display text-text text-[19px] tracking-[0.02em] lg:scroll-mt-4",
            box,
          )}
        >
          {segment.heading}
        </div>
      ) : null}
      {segment.subheading !== undefined ? (
        <div className="mb-1 flex items-center gap-2">
          <Tooltip label="Remove subtopic" side="top">
            <button
              type="button"
              onClick={() => onDropSubheading(index)}
              aria-label="Remove subtopic"
              className="shrink-0 -translate-y-[1px] text-dim transition-colors hover:text-green"
            >
              <Trash2 size={16} strokeWidth={2} />
            </button>
          </Tooltip>
          <div
            contentEditable
            suppressContentEditableWarning
            data-idx={index}
            data-field="subheading"
            onKeyDown={commitOnEnter}
            onInput={onInput}
            onBlur={(e) => onEdit(index, "subheading", e.currentTarget.innerText)}
            className={cn("flex-1 font-display text-text/90 text-[17px] tracking-[0.02em]", box)}
          >
            {segment.subheading}
          </div>
        </div>
      ) : null}
      <div
        contentEditable
        suppressContentEditableWarning
        data-idx={index}
        data-field="text"
        onKeyDown={commitOnShiftEnter}
        onInput={onInput}
        onBlur={(e) => onEdit(index, "text", e.currentTarget.innerText)}
        className={cn("text-[length:var(--tsize,15px)] leading-[1.6] text-subtle", box)}
      >
        {segment.text}
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
  transcriptsCount,
  transcriptsExist,
  counts,
  activeCategory,
  activeSet,
  shortsView,
  audioView,
  transcriptsView,
  link,
  collapsed = false,
  onCollapse,
  onExpand,
}: {
  allCount: number;
  shortsCount: number;
  shortsExist: boolean;
  audioCount: number;
  audioExist: boolean;
  transcriptsCount: number;
  transcriptsExist: boolean;
  counts: Map<EpisodeCategory, number>;
  activeCategory: EpisodeCategory | null;
  activeSet: string | null;
  shortsView: boolean;
  audioView: boolean;
  transcriptsView: boolean;
  link: (pathname: string, querySet: string | null) => { href: string; onClick: (event: ReactMouseEvent) => void };
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
          active={!shortsView && !audioView && !transcriptsView && !activeCategory}
          collapsed={collapsed}
          {...link(activeSet ? setLandingPath(activeSet) : "/episodes", null)}
        />
        <div>
          <RailRow
            label="Evergreen"
            icon={CATEGORY_ICON.Evergreen}
            count={counts.get("Evergreen") ?? 0}
            active={!shortsView && activeCategory === "Evergreen"}
            collapsed={collapsed}
            {...link(`/episodes/${categorySlug("Evergreen")}`, activeSet)}
          />
          {EPISODE_CATEGORIES.filter((category) => category !== "Evergreen").map((category) => (
            <RailRow
              key={category}
              label={category}
              icon={CATEGORY_ICON[category]}
              count={counts.get(category) ?? 0}
              active={!shortsView && activeCategory === category}
              collapsed={collapsed}
              {...link(`/episodes/${categorySlug(category)}`, activeSet)}
            />
          ))}
        </div>
        {shortsExist || audioExist || transcriptsExist ? (
          <div className="mx-4 my-2 border-t border-border" />
        ) : null}
        {shortsExist ? (
          <RailRow
            label="Shorts"
            icon={Zap}
            count={shortsCount}
            active={shortsView}
            collapsed={collapsed}
            {...link("/episodes/shorts", activeSet)}
          />
        ) : null}
        {audioExist ? (
          <RailRow
            label="Audio"
            icon={Headphones}
            count={audioCount}
            active={audioView}
            collapsed={collapsed}
            {...link("/episodes/audio", activeSet)}
          />
        ) : null}
        {transcriptsExist ? (
          <RailRow
            label="Transcripts"
            icon={Captions}
            count={transcriptsCount}
            active={transcriptsView}
            collapsed={collapsed}
            {...link("/episodes/transcripts", activeSet)}
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
  const haystack = [ep.title, ep.setName ?? "", ep.setCode ?? ""].join(" ").toLowerCase();
  return needle.split(/\s+/).every((token) => haystack.includes(token));
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

function tierRankOf(status: TranscriptStatus | undefined): number {
  return status ? TIER_RANK[transcriptTier(status.source)] : 0;
}

function structureRankOf(status: TranscriptStatus | undefined): number {
  return status ? status.sections + status.subsections : -1;
}

function sortTranscriptRows(rows: Episode[], sort: TranscriptSort, index?: TranscriptIndex): Episode[] {
  const dir = sort.dir === "asc" ? 1 : -1;
  const statusOf = (ep: Episode) => index?.get(ep.youtubeId ?? ep.id);
  const compare = (a: Episode, b: Episode): number => {
    switch (sort.key) {
      case "title":
        return a.title.localeCompare(b.title);
      case "set":
        return (a.setCode ?? "").localeCompare(b.setCode ?? "");
      case "category":
        return a.category.localeCompare(b.category);
      case "words":
        return (statusOf(a)?.wordCount ?? 0) - (statusOf(b)?.wordCount ?? 0);
      case "status":
        return tierRankOf(statusOf(a)) - tierRankOf(statusOf(b));
      case "structure":
        return structureRankOf(statusOf(a)) - structureRankOf(statusOf(b));
      case "date":
      default:
        return new Date(a.pubDate).getTime() - new Date(b.pubDate).getTime();
    }
  };
  return [...rows].sort((a, b) => {
    const primary = compare(a, b) * dir;
    if (primary !== 0) {
      return primary;
    }
    return new Date(b.pubDate).getTime() - new Date(a.pubDate).getTime();
  });
}
