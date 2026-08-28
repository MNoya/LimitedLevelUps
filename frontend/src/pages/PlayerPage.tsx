import React, { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { Link, useHref, useNavigate, useParams, useSearchParams } from "react-router-dom";

import { AppHeader } from "../components/AppHeader";
import { useAuth } from "../auth/useAuth";
import { isTrackerUser } from "../data/trackerUsers";
import { Collection } from "../components/tracker/Collection";
import { DraftLog, TRACKER_HEADER_H } from "../components/tracker/DraftLog";
import { TrackerStatsBlock } from "../components/tracker/TrackerStatsBlock";
import { RefreshButton } from "../components/tracker/RefreshButton";
import { AccountTabs, useTrackerAccounts } from "../components/tracker/AccountTabs";
import { useQuery } from "@tanstack/react-query";
import { fetchMyAccounts, type TrackerAccount } from "../data/trackerApi";
import { useIsMobile } from "../lib/use-is-mobile";
import { AAvatar, ALogo, SetGlyph, Trophy, fmtPts } from "../components/Brand";
import {
  ArrowRight,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  ChevronUp,
  ExternalLink,
  GiRoundTable,
  Info,
} from "../components/Icons";
import type { SortDir } from "../components/LeaderboardTable";
import { Pip, Pips } from "../components/ManaPips";
import { ImageIcon } from "../components/Icons";
import { DeckScreenshotModal } from "../components/pod/DeckScreenshotModal";
import { highlightEventLabel } from "../components/pod/EventLabel";
import { StatChip } from "../components/StatChip";
import { PointsBreakdown } from "../components/PointsBreakdown";
import { FilterDropdown } from "../components/FilterDropdown";
import { SectionLabel } from "../components/SectionLabel";
import { Record } from "../components/Record";
import { DonutChart } from "../components/DonutChart";
import { ErrorState } from "../components/ErrorState";
import { TrophyCount } from "../components/TrophyCount";
import { ArenaChampBadge, isArenaChampionshipFormat } from "../components/ArenaChampBadge";
import { LIFETIME_SET_CODE, SetCodeDropdown } from "../components/SetCodeDropdown";
import { MobilePageHeader } from "../components/PageNav";
import { RankBadge } from "../components/RankBadge";
import { ArenaRankIcon } from "../components/ArenaRankIcon";
import { GoToTopButton } from "../components/GoToTopButton";
import { Tooltip } from "../components/Tooltip";

import { useAvailableFormats, useColorChips, useDraftEvents, useLeaderboard, useLifetimeDraftEvents, usePlayerIdentity, usePlayerLifetimeProfile, usePlayerProfile, usePlayerSlugByDiscordId, useSets } from "../data/hooks";
import { withMtgoSets } from "../data/mtgoSets";
import { aggregate as scoreAggregate, computeScore, type ScoringStatRow } from "../data/scoring";
import { canonicalSetCode, colorsOf, eventDate, eventDisplayLabel, fmtShortDate, formatTag, isCubeCode, isFlashbackEvent, isSoup, lastUpdated, lcqCashPrize, leaderboardPath, mainColors, playerPath, prettyFormat, winPct } from "../data/utils";
import { ACTIVE_SET_CODE } from "../data/constants";
import {
  colorsDisplayName,
  deckColorParts,
  formatDeckColors,
  FORMAT_LABEL_GROUPS,
  FORMAT_OPTIONS,
  matchesFormatFilter,
  MULTI,
  OTHER,
  TWO_COLOR_CODES,
  type FilterOption,
} from "../data/filters";
import { FMT_COLORS, renderColorOption, renderFormatOption, shortFormat } from "../data/format-display";
import { cn } from "../lib/utils";
import type {
  PlayerDraftEvent,
  PlayerFormatBreakdown,
  PlayerIdentity,
  PlayerProfile,
  SelfReportedEvent,
  SetPlayed,
  SetSummary,
} from "../types/leaderboard";

// ─── Color palettes ────────────────────────────────────────────────────────

const COLOR_STROKES: Record<string, string> = {
  W: "#f0f2c0",
  U: "#b5cde3",
  B: "#aca29a",
  R: "#db8664",
  G: "#93b483",
};

const COLOR_KEYS: Array<"W" | "U" | "B" | "R" | "G"> = ["W", "U", "B", "R", "G"];

const COLOR_NAMES: Record<"W" | "U" | "B" | "R" | "G", string> = {
  W: "White",
  U: "Blue",
  B: "Black",
  R: "Red",
  G: "Green",
};

function comboColors(combo: string): string[] {
  const out: string[] = [];
  for (const c of combo) {
    const hex = COLOR_STROKES[c];
    if (hex) out.push(hex);
  }
  return out.length > 0 ? out : ["#7a8395"];
}

// ─── Page entry ────────────────────────────────────────────────────────────

export function PlayerPage() {
  const params = useParams<{ slug: string; setCode?: string }>();
  const slug = params.slug!.toLowerCase();
  const navigate = useNavigate();
  const { data: sets } = useSets();
  const dropdownSets = useMemo(() => withMtgoSets(sets), [sets]);
  const liveSetCode = sets?.find((s) => s.isActive)?.code;
  // Bare /player/<slug> is the set-agnostic lifetime view; a set in the path scopes to that set.
  const lifetime = !params.setCode;
  const setCode = (params.setCode ? canonicalSetCode(params.setCode, sets) : undefined) ?? liveSetCode ?? ACTIVE_SET_CODE;
  const { data: profile, isLoading, isFetching, error } = usePlayerProfile(slug, setCode, !lifetime);
  const { data: events, isFetching: isFetchingEvents } = useDraftEvents(slug, setCode, !lifetime);
  const [topSearchParams] = useSearchParams();
  const lifetimeFormat = topSearchParams.get("format") ?? "ALL";
  const lifetimeColors = topSearchParams.get("colors") ?? "ALL";
  const lifetimeProfile = usePlayerLifetimeProfile(slug, lifetime);
  const lifetimeEvents = useLifetimeDraftEvents(slug, lifetime, lifetimeFormat, lifetimeColors);
  const lifetimeRows = useMemo(
    () => (lifetimeEvents.data?.pages ?? []).flat(),
    [lifetimeEvents.data],
  );
  const { data: identity } = usePlayerIdentity(slug, !lifetime && !isLoading && !profile);
  const showLoadingBar = (isFetching || isFetchingEvents) && !isLoading;
  // Sibling navigation needs the leaderboard rows so we know who's adjacent
  // by rank. Cached behind TanStack Query — same fetch as the leaderboard
  // page, so navigating between profiles doesn't re-hit the network.
  const { data: leaderboardRows } = useLeaderboard(setCode);
  const isMobile = useIsMobile();

  useEffect(() => {
    window.scrollTo(0, 0);
  }, [slug, setCode, lifetime]);

  useEffect(() => {
    if (!params.setCode) return;
    if (setCode !== params.setCode) {
      navigate(
        { pathname: playerPath(slug, setCode), search: topSearchParams.toString() },
        { replace: true },
      );
    }
  }, [params.setCode, setCode, slug, navigate, topSearchParams]);

  const idx = leaderboardRows?.findIndex((r) => r.slug === slug) ?? -1;
  let prevSlug: string | null = null;
  let nextSlug: string | null = null;
  if (leaderboardRows && leaderboardRows.length > 0) {
    if (idx === -1) {
      // No data on this set, so the player sits off the board — bracket the ends
      prevSlug = leaderboardRows[leaderboardRows.length - 1].slug;
      nextSlug = leaderboardRows[0].slug;
    } else {
      prevSlug = idx > 0 ? leaderboardRows[idx - 1].slug : null;
      nextSlug = idx < leaderboardRows.length - 1 ? leaderboardRows[idx + 1].slug : null;
    }
  }
  const sibling: SiblingNav = { setCode, prevSlug, nextSlug };

  const topQs = topSearchParams.toString();
  const deckModalOpen = topSearchParams.has("deck");

  const onChangeSet = (newCode: string) => {
    const pathname = newCode === LIFETIME_SET_CODE ? `/player/${slug}` : playerPath(slug, newCode);
    navigate({ pathname, search: topQs });
  };

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (lifetime) return;
      if (e.metaKey || e.ctrlKey || e.altKey || e.shiftKey) return;
      if (deckModalOpen) return;
      const t = e.target;
      if (t instanceof HTMLElement) {
        if (t.tagName === "INPUT" || t.tagName === "TEXTAREA" || t.isContentEditable) return;
      }
      if (e.key === "ArrowLeft" && prevSlug) {
        e.preventDefault();
        navigate({ pathname: playerPath(prevSlug, setCode), search: topQs });
      } else if (e.key === "ArrowRight" && nextSlug) {
        e.preventDefault();
        navigate({ pathname: playerPath(nextSlug, setCode), search: topQs });
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [prevSlug, nextSlug, setCode, navigate, topQs, deckModalOpen, lifetime]);

  if (lifetime) {
    return (
      <LifetimePlayer
        profile={lifetimeProfile.data ?? null}
        isLoading={lifetimeProfile.isLoading}
        error={lifetimeProfile.error as Error | null}
        events={lifetimeRows}
        hasNextPage={!!lifetimeEvents.hasNextPage}
        isFetchingNextPage={lifetimeEvents.isFetchingNextPage}
        fetchNextPage={lifetimeEvents.fetchNextPage}
        sets={dropdownSets}
        isMobile={isMobile}
        onChangeSet={onChangeSet}
        navigate={navigate}
        qs={topQs}
      />
    );
  }

  if (error) {
    return (
      <div className="bg-bg text-text min-h-screen page-fade">
        {isMobile ? (
          <MobilePlayerHeader sibling={sibling} navigate={navigate} qs={topQs} />
        ) : (
          <AppHeader subtitle="PLAYER PROFILE" />
        )}
        <ErrorState error={error as Error} compact={isMobile} />
      </div>
    );
  }

  if (isLoading) {
    return (
      <div className="bg-bg text-text min-h-screen page-fade">
        {isMobile ? (
          <MobilePlayerHeader sibling={sibling} navigate={navigate} qs={topQs} />
        ) : (
          <AppHeader subtitle="PLAYER PROFILE" />
        )}
        {isMobile ? <MobileSkeleton /> : <DesktopSkeleton />}
      </div>
    );
  }

  if (!profile) {
    return (
      <NoSetData
        sets={dropdownSets}
        setCode={setCode}
        onChangeSet={onChangeSet}
        sibling={sibling}
        navigate={navigate}
        qs={topQs}
        isMobile={isMobile}
        identity={identity ?? null}
      />
    );
  }

  return (
    <>
      {showLoadingBar && <TopLoadingBar />}
      {isMobile ? (
        <Mobile profile={profile} events={events ?? []} sibling={sibling} sets={dropdownSets} onChangeSet={onChangeSet} />
      ) : (
        <Desktop profile={profile} events={events ?? []} sibling={sibling} sets={dropdownSets} onChangeSet={onChangeSet} />
      )}
    </>
  );
}

// ─── Lifetime (set-agnostic) profile ───────────────────────────────────────

function LifetimePlayer({
  profile,
  isLoading,
  error,
  events,
  hasNextPage,
  isFetchingNextPage,
  fetchNextPage,
  sets,
  isMobile,
  onChangeSet,
  navigate,
  qs,
}: {
  profile: PlayerProfile | null;
  isLoading: boolean;
  error: Error | null;
  events: PlayerDraftEvent[];
  hasNextPage: boolean;
  isFetchingNextPage: boolean;
  fetchNextPage: () => void;
  sets: SetSummary[] | undefined;
  isMobile: boolean;
  onChangeSet: (code: string) => void;
  navigate: ReturnType<typeof useNavigate>;
  qs: string;
}) {
  const toLeaderboard = () => navigate({ pathname: leaderboardPath(), search: qs });
  const [searchParams, setSearchParams] = useSearchParams();
  const [mobileTab, setMobileTab] = useState<"sets" | "events">("sets");
  const formatFilter = searchParams.get("format") ?? "ALL";
  const colorsFilter = searchParams.get("colors") ?? "ALL";
  const setParam = (key: "format" | "colors", v: string) => {
    setSearchParams((prev) => {
      const next = new URLSearchParams(prev);
      if (v === "ALL") next.delete(key);
      else next.set(key, v);
      return next;
    }, { replace: true });
  };
  const colorOptions = useMemo<FilterOption[]>(
    () => [
      { value: "ALL", label: "ALL COLORS" },
      ...TWO_COLOR_CODES.map((c) => ({ value: c, label: colorsDisplayName(c) })),
      { value: MULTI, label: "3+ COLORS" },
    ],
    [],
  );

  if (error) {
    return (
      <div className="bg-bg text-text min-h-screen page-fade">
        {isMobile ? <LifetimeMobileHeader onBack={toLeaderboard} /> : <AppHeader subtitle="PLAYER PROFILE" />}
        <ErrorState error={error} compact={isMobile} />
      </div>
    );
  }
  if (isLoading || !profile) {
    return (
      <div className="bg-bg text-text min-h-screen page-fade">
        {isMobile ? <LifetimeMobileHeader onBack={toLeaderboard} /> : <AppHeader subtitle="PLAYER PROFILE" />}
        {isLoading ? (
          isMobile ? <LifetimeMobileSkeleton /> : <LifetimeSkeleton />
        ) : (
          <div className="p-20 text-center text-muted font-display tracking-[0.2em]">PLAYER NOT FOUND</div>
        )}
      </div>
    );
  }

  const wp = winPct(profile.wins, profile.losses);
  const stats: StatStripStats = {
    trophies: profile.trophies,
    events: profile.events,
    wins: profile.wins,
    losses: profile.losses,
    score: 0,
  };
  const trophiesLabel = profile.selfReportedEvents.some((e) => e.isTrophy) ? "17L TROPHIES" : "TROPHIES";
  const setsPlayed = profile.setsPlayed ?? [];
  const updated = profile.lastCalculatedAt ? lastUpdated(profile.lastCalculatedAt) : null;

  if (isMobile) {
    return (
      <div className="bg-bg text-text min-h-screen page-fade">
        <LifetimeMobileHeader onBack={toLeaderboard} />
        <section
          className="px-[18px] pt-5 pb-4 border-b border-border"
          style={{ background: "linear-gradient(180deg, #14181f 0%, #0a0c10 100%)" }}
        >
          <div className="flex items-center">
            <AAvatar displayName={profile.displayName} avatarUrl={profile.avatarUrl} size={84} green />
            <div className="flex-1 min-w-0 ml-3 relative flex items-center min-h-[84px]">
              <h1
                className="font-display tracking-[0.03em] m-0 pl-[5px] line-clamp-2 break-words"
                style={{ fontSize: "clamp(20px, 7vw, 44px)", lineHeight: 0.95 }}
              >
                {profile.displayName.toUpperCase()}
              </h1>
              <ManualTrophiesBlock trophies={profile.selfReportedEvents} mobile className="absolute bottom-0 left-0" />
            </div>
            {sets ? (
              <SetCodeDropdown sets={sets} activeCode={LIFETIME_SET_CODE} onChange={onChangeSet} size="sm" chamfer={false} includeLifetime />
            ) : (
              <span className="shrink-0 font-display text-[16px] tracking-[0.18em] text-muted">ALL SETS</span>
            )}
          </div>
          {profile.events > 0 && (
            <div className="mt-[18px] grid gap-[5px] grid-cols-4">
              <StatChip
                label={trophiesLabel}
                value={
                  <span className="flex items-center gap-[3px]">
                    <Trophy size={12} color="#ffc63a" />
                    {stats.trophies}
                  </span>
                }
              />
              <StatChip label="EVENTS" value={stats.events} />
              <StatChip label="RECORD" value={`${stats.wins}–${stats.losses}`} />
              <StatChip label="WIN %" value={`${wp}%`} />
            </div>
          )}
        </section>
        <div className="flex items-stretch border-b border-border bg-surface h-11">
          <LeftPaneTab active={mobileTab === "sets"} onClick={() => setMobileTab("sets")} className="flex-1 justify-center">SET HISTORY</LeftPaneTab>
          <LeftPaneTab active={mobileTab === "events"} onClick={() => setMobileTab("events")} className="flex-1 justify-center">EVENT LOG</LeftPaneTab>
        </div>
        {mobileTab === "sets" ? (
          <LifetimeSetsPanel setsPlayed={setsPlayed} sets={sets} slug={profile.slug} isMobile />
        ) : (
          <LifetimeEventLog
            events={events}
            hasNextPage={hasNextPage}
            isFetchingNextPage={isFetchingNextPage}
            fetchNextPage={fetchNextPage}
            playerDisplayName={profile.displayName}
            slug={profile.slug}
            updated={updated}
            formatFilter={formatFilter}
            setFormatFilter={(v) => setParam("format", v)}
            colorsFilter={colorsFilter}
            setColorsFilter={(v) => setParam("colors", v)}
            colorOptions={colorOptions}
            isMobile
          />
        )}
      </div>
    );
  }

  return (
    <div className="bg-bg text-text min-h-screen page-fade">
      <AppHeader subtitle="PLAYER PROFILE" />
      <section
        className="px-8 pt-5 pb-7 border-b border-border"
        style={{ background: "linear-gradient(180deg, #14181f 0%, #0a0c10 100%)" }}
      >
        <div className="flex items-center justify-between mb-4">
          <BackButton onClick={toLeaderboard} inline />
        </div>
        <div className="flex items-end gap-7">
          <AAvatar displayName={profile.displayName} avatarUrl={profile.avatarUrl} size={120} green />
          <div className="shrink-0">
            <h1
              className="font-display tracking-[0.03em] m-0 whitespace-nowrap pl-[5px]"
              style={{ fontSize: "clamp(38px, 3.6vw, 64px)", lineHeight: 0.95 }}
            >
              {profile.displayName.toUpperCase()}
            </h1>
            <div className="mt-2 flex items-center gap-3 font-display tracking-[0.18em]">
              {sets ? (
                <SetCodeDropdown sets={sets} activeCode={LIFETIME_SET_CODE} onChange={onChangeSet} includeLifetime />
              ) : (
                <span className="text-muted text-[22px]">ALL SETS</span>
              )}
            </div>
          </div>
          <div className="ml-auto flex items-stretch gap-4 min-w-0">
            <ManualTrophiesBlock trophies={profile.selfReportedEvents} />
            {profile.events > 0 && (
              <StatStrip stats={stats} wp={wp} showPoints={false} trophiesLabel={trophiesLabel} />
            )}
          </div>
        </div>
      </section>
      <div className="grid" style={{ gridTemplateColumns: setsPlayed.length > 0 ? "clamp(360px, 32vw, 460px) minmax(0, 1fr)" : "minmax(0, 1fr)" }}>
        {setsPlayed.length > 0 && (
          <LifetimeSetsPanel setsPlayed={setsPlayed} sets={sets} slug={profile.slug} />
        )}
        <LifetimeEventLog
          events={events}
          hasNextPage={hasNextPage}
          isFetchingNextPage={isFetchingNextPage}
          fetchNextPage={fetchNextPage}
          playerDisplayName={profile.displayName}
          slug={profile.slug}
          updated={updated}
          formatFilter={formatFilter}
          setFormatFilter={(v) => setParam("format", v)}
          colorsFilter={colorsFilter}
          setColorsFilter={(v) => setParam("colors", v)}
          colorOptions={colorOptions}
        />
      </div>
    </div>
  );
}

function LifetimeMobileHeader({ onBack }: { onBack: () => void }) {
  return <MobilePageHeader backOnClick={onBack} prevTo={null} nextTo={null} />;
}

type SetSortKey = "release" | "set" | "trophies" | "events" | "winrate";

function FitText({ text, max = 15, min = 9, className }: { text: string; max?: number; min?: number; className?: string }) {
  const ref = useRef<HTMLSpanElement>(null);
  useLayoutEffect(() => {
    const el = ref.current;
    if (!el) return;
    const fit = () => {
      el.style.fontSize = `${max}px`;
      if (el.clientWidth > 0 && el.scrollWidth > el.clientWidth) {
        const scaled = (max * el.clientWidth) / el.scrollWidth;
        el.style.fontSize = `${Math.max(min, Math.floor(scaled * 10) / 10)}px`;
      }
    };
    fit();
    const observer = new ResizeObserver(fit);
    observer.observe(el);
    let cancelled = false;
    document.fonts?.ready.then(() => {
      if (!cancelled) fit();
    });
    return () => {
      cancelled = true;
      observer.disconnect();
    };
  }, [text, max, min]);
  return (
    <span ref={ref} className={cn("block min-w-0 flex-1 overflow-hidden whitespace-nowrap leading-none", className)}>
      {text}
    </span>
  );
}

function winRate(sp: SetPlayed): number {
  const games = sp.wins + sp.losses;
  return games > 0 ? sp.wins / games : 0;
}

const SET_SHORT_NAMES: Record<string, string> = {
  "Alchemy Horizons: Baldur's Gate": "Baldur's Gate",
};

function shortSetName(name: string): string {
  if (SET_SHORT_NAMES[name]) return SET_SHORT_NAMES[name];
  if (name.toLowerCase() === "peasant") return "Peasant Cube";
  return name;
}

function LifetimeSetsPanel({
  setsPlayed,
  sets,
  slug,
  isMobile = false,
}: {
  setsPlayed: SetPlayed[];
  sets: SetSummary[] | undefined;
  slug: string;
  isMobile?: boolean;
}) {
  const [sortKey, setSortKey] = useState<SetSortKey>("release");
  const [dir, setDir] = useState<SortDir>("desc");
  const nameFor = useCallback(
    (code: string) => sets?.find((s) => s.code === code)?.name ?? code,
    [sets],
  );
  const releaseFor = useCallback(
    (code: string) => sets?.find((s) => s.code === code)?.startDate ?? "",
    [sets],
  );
  const sorted = useMemo(() => {
    const arr = [...setsPlayed];
    arr.sort((a, b) => {
      let cmp: number;
      if (sortKey === "release") cmp = releaseFor(a.setCode).localeCompare(releaseFor(b.setCode));
      else if (sortKey === "set") cmp = nameFor(a.setCode).localeCompare(nameFor(b.setCode));
      else if (sortKey === "trophies") cmp = a.trophies - b.trophies;
      else if (sortKey === "events") cmp = a.events - b.events;
      else cmp = winRate(a) - winRate(b);
      return dir === "asc" ? cmp : -cmp;
    });
    return arr;
  }, [setsPlayed, sortKey, dir, nameFor, releaseFor]);
  if (setsPlayed.length === 0) return null;

  const onSort = (key: SetSortKey) => {
    const firstDir: SortDir = key === "set" ? "asc" : "desc";
    if (key !== sortKey) {
      setSortKey(key);
      setDir(firstDir);
      return;
    }
    if (dir === firstDir) {
      setDir(firstDir === "asc" ? "desc" : "asc");
    } else {
      setSortKey("release");
      setDir("desc");
    }
  };

  const grid = "minmax(0,1fr) 64px 52px 45px";

  return (
    <section className={cn(isMobile ? "pt-0 pb-5 px-[18px] border-b border-border" : "pb-6 px-5 border-r border-border")}>
      <div className="grid items-center h-[42px] gap-x-2 px-5 -mx-5 border-b border-border2" style={{ gridTemplateColumns: grid }}>
        <SetSortHeader label="SET NAME" active={sortKey === "set"} dir={dir} onClick={() => onSort("set")} align="left" primary />
        <SetSortHeader label="TROPHIES" active={sortKey === "trophies"} dir={dir} onClick={() => onSort("trophies")} align="right" />
        <SetSortHeader label="EVENTS" active={sortKey === "events"} dir={dir} onClick={() => onSort("events")} align="right" />
        <SetSortHeader label="WIN %" active={sortKey === "winrate"} dir={dir} onClick={() => onSort("winrate")} align="right" />
      </div>
      <div className="flex flex-col">
        {sorted.map((sp) => (
          <Link
            key={sp.setCode}
            to={playerPath(slug, sp.setCode)}
            className="grid items-center gap-x-2 min-h-[44px] px-2 -mx-2 no-underline text-inherit border-b border-border transition-colors hover:bg-surface2"
            style={{ gridTemplateColumns: grid }}
          >
            <span className="flex items-center gap-2 min-w-0">
              <SetGlyph code={sp.setCode} size={22} className="text-white/85 shrink-0" />
              <span className="flex items-baseline gap-2 min-w-0 flex-1">
                <span className="font-display text-[18px] leading-none tracking-[0.04em] shrink-0">{sp.setCode}</span>
                <FitText text={shortSetName(nameFor(sp.setCode))} className="font-display text-muted tracking-[0.03em]" max={12} min={9} />
              </span>
            </span>
            <TrophyCount count={sp.trophies} size="md" display fixedDigits={2} className="text-subtle justify-self-end" />
            <span className="font-display text-[17px] text-right text-subtle">{sp.events}</span>
            <span className="font-display text-[17px] text-right text-subtle">{winPct(sp.wins, sp.losses)}%</span>
          </Link>
        ))}
      </div>
    </section>
  );
}

function SetSortHeader({
  label,
  active,
  dir,
  onClick,
  align,
  primary = false,
}: {
  label: string;
  active: boolean;
  dir: SortDir;
  onClick: () => void;
  align: "left" | "right";
  primary?: boolean;
}) {
  const Icon = dir === "asc" ? ChevronUp : ChevronDown;
  return (
    <button
      type="button"
      onClick={onClick}
      aria-sort={active ? (dir === "asc" ? "ascending" : "descending") : "none"}
      className={cn(
        "flex items-center w-full h-full bg-transparent border-0 cursor-pointer font-display tracking-[0.2em] transition-colors whitespace-nowrap",
        primary ? "text-[14px]" : "text-[12px]",
        align === "right" ? "justify-end" : "justify-start",
        active ? "text-text" : "text-muted hover:text-text",
      )}
    >
      <span className="relative">
        {label}
        {active && (
          <Icon size={12} strokeWidth={2.5} className="absolute left-full top-1/2 -translate-y-1/2 ml-[-2px]" />
        )}
      </span>
    </button>
  );
}

function LifetimeEventLog({
  events,
  hasNextPage,
  isFetchingNextPage,
  fetchNextPage,
  playerDisplayName,
  slug,
  updated,
  formatFilter,
  setFormatFilter,
  colorsFilter,
  setColorsFilter,
  colorOptions,
  isMobile = false,
}: {
  events: PlayerDraftEvent[];
  hasNextPage: boolean;
  isFetchingNextPage: boolean;
  fetchNextPage: () => void;
  playerDisplayName: string;
  slug: string;
  updated: string | null;
  formatFilter: string;
  setFormatFilter: (v: string) => void;
  colorsFilter: string;
  setColorsFilter: (v: string) => void;
  colorOptions: FilterOption[];
  isMobile?: boolean;
}) {
  const compact = useIsMobile(1240);
  const sentinelRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const node = sentinelRef.current;
    if (!node || !hasNextPage) return;
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries[0]?.isIntersecting && hasNextPage && !isFetchingNextPage) fetchNextPage();
      },
      { rootMargin: "600px" },
    );
    observer.observe(node);
    return () => observer.disconnect();
  }, [hasNextPage, isFetchingNextPage, fetchNextPage]);

  const countLabel = `${events.length}${hasNextPage ? "+" : ""} EVENTS`;
  const loadMore = hasNextPage && (
    <div ref={sentinelRef} className="col-span-full flex justify-center py-6">
      <button
        type="button"
        onClick={() => fetchNextPage()}
        disabled={isFetchingNextPage}
        className="font-display text-[13px] tracking-[0.18em] text-muted hover:text-text transition-colors bg-transparent border border-border2 px-4 py-2 cursor-pointer disabled:opacity-50"
      >
        {isFetchingNextPage ? "LOADING…" : "LOAD MORE"}
      </button>
    </div>
  );
  const empty = events.length === 0 && (
    <div className="p-6 text-center text-muted font-display tracking-[0.2em] col-span-full">
      {formatFilter === "ALL" && colorsFilter === "ALL" ? "NO EVENTS RECORDED" : "NO EVENTS MATCH FILTER"}
    </div>
  );

  if (isMobile) {
    return (
      <section className="pt-2 pb-4 px-[18px]">
        <div className="flex items-baseline justify-between gap-2.5 mb-2">
          <div className="flex items-baseline gap-2.5">
            <SectionLabel size={14}>EVENT LOG</SectionLabel>
            {events.length > 0 && (
              <span className="font-display text-[13px] tracking-[0.14em] text-subtle whitespace-nowrap">{countLabel}</span>
            )}
          </div>
          {updated && (
            <span className="font-display text-[13px] tracking-[0.14em] text-muted shrink-0 whitespace-nowrap">UPDATED {updated}</span>
          )}
        </div>
        <div className="mb-2 grid grid-cols-2 gap-2">
          <FilterDropdown
            value={formatFilter}
            onChange={setFormatFilter}
            options={FORMAT_OPTIONS}
            renderValue={renderFormatOption}
            renderOption={renderFormatOption}
            className="w-full min-w-0"
            triggerClassName="w-full min-w-0"
          />
          <FilterDropdown
            value={colorsFilter}
            onChange={setColorsFilter}
            options={colorOptions}
            renderValue={renderColorOption}
            renderOption={renderColorOption}
            className="w-full min-w-0"
            triggerClassName="w-full min-w-0"
          />
        </div>
        <div className="flex flex-col border-t border-border2 -mx-[18px] px-[18px]">
          {events.map((e) => (
            <EventLogRow key={e.eventId} event={e} variant="mobile" playerDisplayName={playerDisplayName} setColumn setHref={playerPath(slug, e.setCode)} />
          ))}
        </div>
        {empty}
        {loadMore}
      </section>
    );
  }

  return (
    <section className="pb-6 px-5 min-w-0">
      <div className="flex items-center justify-between gap-3 h-[42px] px-5 -mx-5 border-b border-border2">
        <div className="flex items-baseline gap-2.5 shrink-0">
          <SectionLabel size={14}>EVENT LOG</SectionLabel>
          {events.length > 0 && (
            <span className="font-display text-[13px] tracking-[0.14em] text-subtle whitespace-nowrap">{countLabel}</span>
          )}
        </div>
        <div className="flex items-center gap-2 min-w-0">
          {updated && (
            <span className="font-display text-[13px] tracking-[0.14em] text-muted shrink-0 whitespace-nowrap mr-1">UPDATED {updated}</span>
          )}
          <FilterDropdown
            value={formatFilter}
            onChange={setFormatFilter}
            options={FORMAT_OPTIONS}
            renderValue={renderFormatOption}
            renderOption={renderFormatOption}
            className="min-w-0 max-w-[200px]"
            triggerClassName="min-w-0"
          />
          <FilterDropdown
            value={colorsFilter}
            onChange={setColorsFilter}
            options={colorOptions}
            renderValue={renderColorOption}
            renderOption={renderColorOption}
            className="min-w-0 max-w-[200px]"
            triggerClassName="min-w-0"
          />
        </div>
      </div>
      <div
        className="grid gap-x-2 items-stretch"
        style={{ gridTemplateColumns: "40px 22px 70px max-content 1fr 24px auto" }}
      >
        {events.map((e) => (
          <EventLogRow key={e.eventId} event={e} variant="desktop" playerDisplayName={playerDisplayName} setColumn setHref={playerPath(slug, e.setCode)} compact={compact} />
        ))}
        {empty}
        {loadMore}
      </div>
    </section>
  );
}

function TopLoadingBar() {
  return (
    <div
      aria-hidden="true"
      className="fixed top-0 left-0 right-0 h-[2px] z-[60] overflow-hidden pointer-events-none bg-border/30"
    >
      <div className="h-full w-1/3 bg-green animate-loadingBar" />
    </div>
  );
}

function useUrlFilters(): [
  string,
  (v: string) => void,
  string,
  (v: string) => void,
  string,
] {
  const [searchParams, setSearchParams] = useSearchParams();
  const formatFilter = searchParams.get("format") ?? "ALL";
  const colorsFilter = searchParams.get("colors") ?? "ALL";
  const update = (key: "format" | "colors", value: string) => {
    setSearchParams((prev) => {
      const next = new URLSearchParams(prev);
      if (value === "ALL") next.delete(key);
      else next.set(key, value);
      return next;
    }, { replace: true });
  };
  return [
    formatFilter,
    (v) => update("format", v),
    colorsFilter,
    (v) => update("colors", v),
    searchParams.toString(),
  ];
}

// The open deck modal is URL state (?deck=<sourceMessageId>) so a profile link opens straight to a
// deck. Opening pushes a history entry (browser Back closes the modal); closing replaces it away.
function useSharedDeck(
  selfReportedEvents: SelfReportedEvent[],
): [SelfReportedEvent | null, (trophy: SelfReportedEvent | null) => void] {
  const [searchParams, setSearchParams] = useSearchParams();
  const deckId = searchParams.get("deck");
  const shotTrophy = useMemo(() => {
    if (!deckId) return null;
    return selfReportedEvents.find((t) => t.sourceMessageId === deckId) ?? null;
  }, [deckId, selfReportedEvents]);
  const setShotTrophy = useCallback(
    (trophy: SelfReportedEvent | null) => {
      setSearchParams((prev) => {
        const next = new URLSearchParams(prev);
        if (trophy) next.set("deck", trophy.sourceMessageId);
        else next.delete("deck");
        return next;
      }, { replace: !trophy });
    },
    [setSearchParams],
  );
  return [shotTrophy, setShotTrophy];
}

function MobilePlayerHeader({
  sibling,
  navigate,
  qs = "",
}: {
  sibling: SiblingNav;
  navigate: ReturnType<typeof useNavigate>;
  qs?: string;
}) {
  const toFor = (s: string | null) =>
    s ? { pathname: playerPath(s, sibling.setCode), search: qs } : null;
  return (
    <MobilePageHeader
      backOnClick={() => navigate({ pathname: leaderboardPath(sibling.setCode), search: qs })}
      prevTo={toFor(sibling.prevSlug)}
      nextTo={toFor(sibling.nextSlug)}
      prevAriaLabel="Previous player"
      nextAriaLabel="Next player"
    />
  );
}

function NoSetData({
  sets,
  setCode,
  onChangeSet,
  sibling,
  navigate,
  qs,
  isMobile,
  identity,
}: {
  sets: SetSummary[] | undefined;
  setCode: string;
  onChangeSet: (code: string) => void;
  sibling: SiblingNav;
  navigate: ReturnType<typeof useNavigate>;
  qs: string;
  isMobile: boolean;
  identity: PlayerIdentity | null;
}) {
  const setSwitcher = sets ? (
    <SetCodeDropdown sets={sets} activeCode={setCode} onChange={onChangeSet} size={isMobile ? "sm" : "md"} chamfer={!isMobile} includeLifetime />
  ) : (
    <span className="text-[22px]">{setCode}</span>
  );
  return (
    <div className="bg-bg text-text min-h-screen page-fade">
      {isMobile ? (
        <MobilePlayerHeader sibling={sibling} navigate={navigate} qs={qs} />
      ) : (
        <AppHeader subtitle="PLAYER PROFILE" />
      )}
      <section
        className={cn("border-b border-border", isMobile ? "px-[18px] pt-4 pb-8" : "px-8 pt-5 pb-7")}
        style={{ background: "linear-gradient(180deg, #14181f 0%, #0a0c10 100%)" }}
      >
        {!isMobile && (
          <div className="flex items-center justify-between mb-4">
            <BackButton onClick={() => navigate({ pathname: leaderboardPath(setCode), search: qs })} inline />
            <SiblingNavButtons sibling={sibling} qs={qs} />
          </div>
        )}
        {isMobile ? (
          <div className="flex items-center justify-between gap-4">
            <div className="flex items-center gap-4 min-w-0">
              {identity && (
                <AAvatar displayName={identity.displayName} avatarUrl={identity.avatarUrl} size={64} green />
              )}
              {identity && (
                <h1
                  className="font-display tracking-[0.03em] m-0 truncate pl-[5px]"
                  style={{ fontSize: "clamp(20px, 7vw, 44px)", lineHeight: 0.95 }}
                >
                  {identity.displayName.toUpperCase()}
                </h1>
              )}
            </div>
            <div className="shrink-0 flex items-center gap-3 font-display tracking-[0.18em]">{setSwitcher}</div>
          </div>
        ) : (
          <div className="flex items-end gap-7">
            {identity && (
              <AAvatar displayName={identity.displayName} avatarUrl={identity.avatarUrl} size={120} green />
            )}
            <div className="shrink-0">
              {identity && (
                <h1
                  className="font-display tracking-[0.03em] m-0 whitespace-nowrap pl-[5px]"
                  style={{ fontSize: 64, lineHeight: 0.95 }}
                >
                  {identity.displayName.toUpperCase()}
                </h1>
              )}
              <div className={cn("flex items-center gap-3 font-display tracking-[0.18em]", identity && "mt-2")}>
                {setSwitcher}
              </div>
            </div>
          </div>
        )}
      </section>
      <div className="p-20 text-center text-muted font-display tracking-[0.2em]">
        NO {setCode} EVENTS RECORDED
      </div>
    </div>
  );
}

function SkeletonBox({ className }: { className?: string }) {
  return <div className={cn("bg-surface2 animate-pulse", className)} />;
}

function MobileSkeleton() {
  return (
    <>
      <section
        className="px-[18px] pt-5 pb-4 border-b border-border"
        style={{ background: "linear-gradient(180deg, #14181f 0%, #0a0c10 100%)" }}
      >
        <div className="flex items-center">
          <SkeletonBox className="w-[84px] h-[84px] rounded-full shrink-0" />
          <div className="flex-1 min-w-0 ml-3 flex items-center min-h-[84px]">
            <SkeletonBox className="w-40 h-9" />
          </div>
          <div className="flex flex-col items-end gap-1.5 shrink-0">
            <SkeletonBox className="w-[51px] h-[38px]" />
            <SkeletonBox className="w-[92px] h-[38px]" />
          </div>
        </div>
        <div className="mt-[18px] grid grid-cols-5 gap-[5px]">
          {[0, 1, 2, 3, 4].map((i) => (
            <SkeletonBox key={i} className="h-12" />
          ))}
        </div>
      </section>

      <section className="border-b border-border">
        <div className="flex border-b border-border">
          {[0, 1, 2].map((i) => (
            <div key={i} className="flex-1 py-2.5 px-1.5 flex justify-center">
              <SkeletonBox className="w-3/4 h-3" />
            </div>
          ))}
        </div>
        <div className="px-[18px] py-4 flex items-center gap-3.5">
          <SkeletonBox className="w-[108px] h-[108px] rounded-full" />
          <div className="flex-1 flex flex-col gap-1.5">
            {[0, 1, 2, 3, 4].map((i) => (
              <SkeletonBox key={i} className="h-5" />
            ))}
          </div>
        </div>
      </section>

      <section className="py-4 px-[18px]">
        <SkeletonBox className="w-32 h-3 mb-3" />
        {[0, 1, 2, 3, 4, 5].map((i) => (
          <div
            key={i}
            className="grid gap-2.5 py-2.5 border-b border-border items-center"
            style={{ gridTemplateColumns: "20px 1fr auto" }}
          >
            <SkeletonBox className="w-4 h-4" />
            <div className="flex flex-col gap-1.5">
              <SkeletonBox className="w-28 h-3" />
              <SkeletonBox className="w-20 h-2" />
            </div>
            <SkeletonBox className="w-10 h-3.5" />
          </div>
        ))}
      </section>
    </>
  );
}

function DesktopSkeleton() {
  return (
    <>
      <section
        className="px-8 pt-5 pb-7 border-b border-border"
        style={{ background: "linear-gradient(180deg, #14181f 0%, #0a0c10 100%)" }}
      >
        <div className="flex items-center justify-between mb-4">
          <SkeletonBox className="w-48 h-5" />
          <SkeletonBox className="w-28 h-5" />
        </div>
        <div className="flex items-end gap-7">
          <SkeletonBox className="w-[120px] h-[120px] rounded-full" />
          <div className="shrink-0 flex flex-col gap-3">
            <SkeletonBox className="w-72 h-12" />
            <SkeletonBox className="w-44 h-9" />
          </div>
          <div
            className="ml-auto self-end grid border border-border2"
            style={{ flex: "0 1 601px", height: "106px", gridTemplateColumns: "1fr 1fr 1.3fr 1fr 0.9fr" }}
          >
            {[0, 1, 2, 3, 4].map((i) => (
              <div
                key={i}
                className={cn(
                  "px-3 flex flex-col items-center justify-center gap-3",
                  i < 4 && "border-r border-border2",
                )}
              >
                <SkeletonBox className="w-12 h-2.5" />
                <SkeletonBox className="w-16 h-10" />
              </div>
            ))}
          </div>
        </div>
      </section>

      <div className="grid" style={{ gridTemplateColumns: "clamp(360px, 32vw, 460px) minmax(0, 1fr)" }}>
        <section className="py-5 pr-8 pl-6 min-[1360px]:pl-10 border-r border-border">
          {[0, 1, 2].map((s) => (
            <div key={s} className={s > 0 ? "mt-6" : undefined}>
              <div className="flex justify-center mb-3.5" style={{ width: 148 }}>
                <SkeletonBox className="w-28 h-4" />
              </div>
              <div className="flex items-center gap-5">
                <SkeletonBox className="w-[148px] h-[148px] rounded-full shrink-0" />
                <div className="flex-1 flex flex-col gap-2">
                  {[0, 1, 2, 3, 4].map((i) => (
                    <SkeletonBox key={i} className="h-5" />
                  ))}
                </div>
              </div>
            </div>
          ))}
        </section>

        <section className="pb-6 px-5 min-w-0">
          <div className="h-[42px] flex items-center justify-between px-5 -mx-5 border-b border-border2">
            <SkeletonBox className="w-40 h-3" />
            <div className="flex gap-2">
              <SkeletonBox className="w-36 h-8" />
              <SkeletonBox className="w-36 h-8" />
            </div>
          </div>
          {Array.from({ length: 13 }).map((_, i) => (
            <div
              key={i}
              className="grid items-center gap-x-2 min-h-[44px] px-2 -mx-2 border-b border-border"
              style={{ gridTemplateColumns: "22px 70px max-content 1fr 24px auto" }}
            >
              <span />
              <SkeletonBox className="w-12 h-3" />
              <SkeletonBox className="w-24 h-3.5" />
              <SkeletonBox className="w-16 h-3" />
              <span />
              <SkeletonBox className="w-10 h-4 justify-self-end" />
            </div>
          ))}
        </section>
      </div>
    </>
  );
}

function LifetimeSkeleton() {
  return (
    <>
      <section
        className="px-8 pt-5 pb-7 border-b border-border"
        style={{ background: "linear-gradient(180deg, #14181f 0%, #0a0c10 100%)" }}
      >
        <div className="mb-4"><SkeletonBox className="w-48 h-5" /></div>
        <div className="flex items-end gap-7">
          <SkeletonBox className="w-[120px] h-[120px] rounded-full" />
          <div className="flex flex-col gap-3">
            <SkeletonBox className="w-72 h-12" />
            <SkeletonBox className="w-40 h-9" />
          </div>
          <div
            className="ml-auto self-end grid border border-border2"
            style={{ flex: "0 1 596px", height: "106px", gridTemplateColumns: "1fr 1fr 1.3fr 1fr" }}
          >
            {[0, 1, 2, 3].map((i) => (
              <div key={i} className={cn("px-3 flex flex-col items-center justify-center gap-3", i < 3 && "border-r border-border2")}>
                <SkeletonBox className="w-12 h-2.5" />
                <SkeletonBox className="w-16 h-10" />
              </div>
            ))}
          </div>
        </div>
      </section>
      <div className="grid" style={{ gridTemplateColumns: "clamp(360px, 32vw, 460px) minmax(0, 1fr)" }}>
        <section className="pb-6 px-5 border-r border-border">
          <div className="h-[42px] flex items-center px-5 -mx-5 border-b border-border2"><SkeletonBox className="w-20 h-3" /></div>
          {Array.from({ length: 13 }).map((_, i) => (
            <div key={i} className="grid items-center gap-x-2 min-h-[44px] px-2 -mx-2 border-b border-border" style={{ gridTemplateColumns: "minmax(0,1fr) 64px 52px 45px" }}>
              <span className="flex items-center gap-2"><SkeletonBox className="w-[22px] h-[22px] rounded-full" /><SkeletonBox className="w-28 h-3" /></span>
              <SkeletonBox className="w-8 h-3 justify-self-end" />
              <SkeletonBox className="w-6 h-3 justify-self-end" />
              <SkeletonBox className="w-9 h-3 justify-self-end" />
            </div>
          ))}
        </section>
        <section className="pb-6 px-5 min-w-0">
          <div className="h-[42px] flex items-center justify-between px-5 -mx-5 border-b border-border2">
            <SkeletonBox className="w-40 h-3" />
            <div className="flex gap-2"><SkeletonBox className="w-36 h-8" /><SkeletonBox className="w-36 h-8" /></div>
          </div>
          {Array.from({ length: 13 }).map((_, i) => (
            <div key={i} className="grid items-center gap-x-2 min-h-[44px] px-2 -mx-2 border-b border-border" style={{ gridTemplateColumns: "40px 22px 70px max-content 1fr 24px auto" }}>
              <SkeletonBox className="w-[18px] h-[18px] mx-auto" />
              <span />
              <SkeletonBox className="w-12 h-3" />
              <SkeletonBox className="w-24 h-3.5" />
              <SkeletonBox className="w-16 h-3" />
              <span />
              <SkeletonBox className="w-10 h-4 justify-self-end" />
            </div>
          ))}
        </section>
      </div>
    </>
  );
}

function LifetimeMobileSkeleton() {
  return (
    <>
      <section className="px-[18px] pt-5 pb-4 border-b border-border" style={{ background: "linear-gradient(180deg, #14181f 0%, #0a0c10 100%)" }}>
        <div className="flex items-center">
          <SkeletonBox className="w-[84px] h-[84px] rounded-full shrink-0" />
          <div className="flex-1 min-w-0 ml-3 flex items-center min-h-[84px]"><SkeletonBox className="w-40 h-9" /></div>
          <SkeletonBox className="w-[92px] h-[38px] shrink-0" />
        </div>
        <div className="mt-[18px] grid grid-cols-4 gap-[5px]">
          {[0, 1, 2, 3].map((i) => <SkeletonBox key={i} className="h-12" />)}
        </div>
      </section>
      <div className="flex items-stretch border-b border-border bg-surface h-11">
        {[0, 1].map((i) => (
          <div key={i} className="flex-1 flex items-center justify-center"><SkeletonBox className="w-24 h-3" /></div>
        ))}
      </div>
      <section className="pt-0 pb-5 px-[18px]">
        <div className="grid items-center h-[42px] gap-x-2 px-5 -mx-5 border-b border-border2" style={{ gridTemplateColumns: "minmax(0,1fr) 64px 52px 45px" }}>
          <SkeletonBox className="w-20 h-3" />
          <SkeletonBox className="w-12 h-3 justify-self-end" />
          <SkeletonBox className="w-10 h-3 justify-self-end" />
          <SkeletonBox className="w-9 h-3 justify-self-end" />
        </div>
        {Array.from({ length: 11 }).map((_, i) => (
          <div key={i} className="grid items-center gap-x-2 min-h-[44px] px-2 -mx-2 border-b border-border" style={{ gridTemplateColumns: "minmax(0,1fr) 64px 52px 45px" }}>
            <span className="flex items-center gap-2"><SkeletonBox className="w-[22px] h-[22px] rounded-full" /><SkeletonBox className="w-24 h-3" /></span>
            <SkeletonBox className="w-7 h-3 justify-self-end" />
            <SkeletonBox className="w-5 h-3 justify-self-end" />
            <SkeletonBox className="w-8 h-3 justify-self-end" />
          </div>
        ))}
      </section>
    </>
  );
}

interface SiblingNav {
  setCode: string;
  prevSlug: string | null;
  nextSlug: string | null;
}

// ─── Aggregation ───────────────────────────────────────────────────────────

interface PlayerAggregates {
  colorCount: Record<"W" | "U" | "B" | "R" | "G", number>;
  comboCount: Record<string, number>;
  comboTrophies: Record<string, number>;
}

interface StatStripStats {
  trophies: number;
  events: number;
  wins: number;
  losses: number;
  score: number;
}

function statsFromEvents(events: PlayerDraftEvent[]): StatStripStats {
  let trophies = 0;
  let wins = 0;
  let losses = 0;
  let countedEvents = 0;
  const rows: ScoringStatRow[] = [];
  for (const e of events) {
    if (e.format.startsWith("MidWeek")) continue;
    if (e.isTrophy) trophies += 1;
    wins += e.wins;
    losses += e.losses;
    countedEvents += 1;
    rows.push({ format: e.format, wins: e.wins, losses: e.losses, trophies: e.isTrophy ? 1 : 0, events: 1 });
  }
  return { trophies, events: countedEvents, wins, losses, score: computeScore(rows) };
}

function aggregate(
  events: PlayerDraftEvent[],
  selfReported: readonly SelfReportedEvent[] = [],
): PlayerAggregates {
  const colorCount: PlayerAggregates["colorCount"] = { W: 0, U: 0, B: 0, R: 0, G: 0 };
  const comboCount: Record<string, number> = {};
  const comboTrophies: Record<string, number> = {};
  for (const e of [...events, ...selfReported]) {
    const main = mainColors(e.colors);
    for (const c of main) {
      if (c in colorCount) colorCount[c as keyof typeof colorCount]++;
    }
    const combo = colorsOf(e.colors);
    if (combo.length === 0) continue;
    comboCount[combo] = (comboCount[combo] ?? 0) + 1;
    if (e.isTrophy) comboTrophies[combo] = (comboTrophies[combo] ?? 0) + 1;
  }
  return { colorCount, comboCount, comboTrophies };
}

// ─── Desktop ───────────────────────────────────────────────────────────────

function Desktop({
  profile,
  events,
  sibling,
  sets,
  onChangeSet,
}: {
  profile: PlayerProfile;
  events: PlayerDraftEvent[];
  sibling: SiblingNav;
  sets: SetSummary[] | undefined;
  onChangeSet: (code: string) => void;
}) {
  const navigate = useNavigate();

  const [formatFilter, setFormatFilter, colorsFilter, setColorsFilter, qs] =
    useUrlFilters();

  const { chips: colorChips, otherCombos } = useColorChips(profile.setCode);
  const cube = isCubeCode(profile.setCode);
  const colorOptions = useMemo<FilterOption[]>(() => {
    const opts: FilterOption[] = [{ value: "ALL", label: "ALL COLORS" }];
    for (const c of colorChips) {
      if (c === MULTI) opts.push({ value: MULTI, label: "SOUP" });
      else if (c === OTHER) opts.push({ value: OTHER, label: "OTHER" });
      else opts.push({ value: c, label: colorsDisplayName(c) });
    }
    return opts;
  }, [colorChips]);
  const { data: availableFormatLabels } = useAvailableFormats(profile.setCode);
  const formatOptions = useMemo(() => {
    const available = new Set(availableFormatLabels ?? []);
    const base = !availableFormatLabels
      ? FORMAT_OPTIONS
      : FORMAT_OPTIONS.filter((opt) => {
          if (opt.value === "ALL") return true;
          const labels = FORMAT_LABEL_GROUPS[opt.value] ?? [opt.value];
          return labels.some((l) => available.has(l));
        });
    const platforms = Array.from(new Set(profile.selfReportedEvents.map((t) => t.platform)));
    return [...base, ...platforms.map((p) => ({ value: p, label: p.toUpperCase() }))];
  }, [availableFormatLabels, profile.selfReportedEvents]);
  const otherSet = useMemo(() => new Set(otherCombos), [otherCombos]);

  const matchesFilters = useCallback(
    (colors: string, format: string) => {
      if (formatFilter !== "ALL" && !matchesFormatFilter(format, formatFilter)) return false;
      if (colorsFilter !== "ALL") {
        if (colorsFilter === MULTI) {
          if (!isSoup(colors, cube)) return false;
        } else if (colorsFilter === OTHER) {
          if (isSoup(colors, cube)) return false;
          if (!otherSet.has(colorsOf(colors))) return false;
        } else if (colorsOf(colors) !== colorsFilter) return false;
      }
      return true;
    },
    [formatFilter, colorsFilter, otherSet, cube]
  );

  // filtered = real 17lands events, the basis for the scored stat strip. displayRows adds the
  // self-reported trophies as synthetic rows for the log only, so counts/score stay untouched.
  const filtered = useMemo(
    () => events.filter((e) => matchesFilters(e.colors, e.format)),
    [events, matchesFilters]
  );
  const displayRows = useMemo(() => mergeTrophyRows(filtered, profile, matchesFilters), [filtered, profile, matchesFilters]);
  const [shotTrophy, setShotTrophy] = useSharedDeck(profile.selfReportedEvents);

  const filtersActive = formatFilter !== "ALL" || colorsFilter !== "ALL";
  // The headline points and its breakdown popover follow the format filter only, selecting the
  // canonical per-format contributions (already carrying the player-wide confidence, and the flat
  // Pod row) rather than rescoring the filtered events — which would shrink confidence per-format
  // and drop pod points. Colors narrow the event log and counts, not the points.
  const popoverBreakdown = useMemo(() => {
    if (formatFilter === "ALL") return profile.formatBreakdown;
    const labels = new Set(FORMAT_LABEL_GROUPS[formatFilter] ?? [formatFilter]);
    return profile.formatBreakdown.filter((b) => labels.has(b.formatLabel));
  }, [profile.formatBreakdown, formatFilter]);
  const fullConfidence = useMemo(
    () =>
      scoreAggregate(
        profile.formatBreakdown
          .filter((b) => b.formatLabel !== "Pod")
          .map((b) => ({ label: b.formatLabel, events: b.events, wins: b.wins, losses: b.losses, trophies: b.trophies })),
      ).confidence,
    [profile.formatBreakdown],
  );
  const pointsTotal =
    formatFilter === "ALL"
      ? profile.score
      : Math.round(popoverBreakdown.reduce((s, b) => s + b.scoreContribution, 0) * 100) / 100;
  const lockedFormats =
    formatFilter !== "ALL" && popoverBreakdown.length > 0 ? popoverBreakdown.map((b) => b.formatLabel) : null;
  const stats: StatStripStats = useMemo(() => {
    if (!filtersActive) {
      return { trophies: profile.trophies, events: profile.events, wins: profile.wins, losses: profile.losses, score: profile.score };
    }
    const counts = statsFromEvents(filtered);
    const filteredTrophyCount = displayRows.length - filtered.length;
    return { trophies: counts.trophies + filteredTrophyCount, events: counts.events, wins: counts.wins, losses: counts.losses, score: pointsTotal };
  }, [filtersActive, filtered, displayRows, pointsTotal, profile.trophies, profile.events, profile.wins, profile.losses, profile.score]);
  const wp = winPct(stats.wins, stats.losses);
  const ranked = profile.rank > 0;
  const hasBreakdown = profile.events > 0 || profile.selfReportedEvents.length > 0;
  const trackerMode = useOwnTrackerProfile(profile.slug);
  const [leftPane, setLeftPane] = useState<"breakdown" | "collection">("collection");
  const { accounts: trackerAccounts, accountId: trackerAccount, setAccountId: setTrackerAccount } =
    useTrackerAccounts(trackerMode);
  const [pointsModalOpen, setPointsModalOpen] = useState(false);
  const pointsBtnRef = useRef<HTMLButtonElement>(null);

  return (
    <div className="bg-bg text-text min-h-screen page-fade">
      <AppHeader subtitle="PLAYER PROFILE" />

      <section
        className="px-8 pt-5 pb-7 border-b border-border"
        style={{ background: "linear-gradient(180deg, #14181f 0%, #0a0c10 100%)" }}
      >
        <div className="flex items-center justify-between mb-4">
          <BackButton onClick={() => navigate({ pathname: leaderboardPath(profile.setCode), search: qs })} inline />
          <SiblingNavButtons sibling={sibling} qs={qs} />
        </div>
        <div className="flex items-end gap-7">
          <AAvatar displayName={profile.displayName} avatarUrl={profile.avatarUrl} size={120} green />
          <div className="shrink-0">
            <h1
              className="font-display tracking-[0.03em] m-0 whitespace-nowrap pl-[5px]"
              style={{ fontSize: "clamp(38px, 3.6vw, 64px)", lineHeight: 0.95 }}
            >
              {profile.displayName.toUpperCase()}
            </h1>
            <div className="mt-2 flex items-center gap-3 font-display tracking-[0.18em]">
              {sets ? (
                <SetCodeDropdown sets={sets} activeCode={profile.setCode} onChange={onChangeSet} includeLifetime />
              ) : (
                <span className="text-[22px]">{profile.setCode}</span>
              )}
              {ranked && <RankBadge rank={profile.rank} size="lg" />}
            </div>
          </div>
          <div className="ml-auto flex items-stretch gap-4 min-w-0">
            {trackerMode && (
              <TrackerStatsBlock slug={profile.slug} setCode={profile.setCode} accountId={trackerAccount} />
            )}
            <ManualTrophiesBlock trophies={profile.selfReportedEvents} />
            {profile.linked17lands && profile.events > 0 && (
              <StatStrip
                stats={stats}
                wp={wp}
                showPoints={ranked}
                onPointsClick={() => setPointsModalOpen((o) => !o)}
                pointsBtnRef={pointsBtnRef}
                trophiesLabel={profile.selfReportedEvents.some((e) => e.isTrophy) ? "17L TROPHIES" : "TROPHIES"}
              />
            )}
          </div>
        </div>
      </section>

      <div
        className={cn("grid", trackerMode && "grid-cols-1 min-[1128px]:grid-cols-[480px_minmax(0,1fr)]")}
        style={trackerMode ? undefined : { gridTemplateColumns: hasBreakdown ? "clamp(360px, 32vw, 460px) minmax(0, 1fr)" : "minmax(0, 1fr)" }}
      >
        {trackerMode ? (
          <div className="border-b border-border min-[1128px]:border-b-0 min-[1128px]:border-r">
            <div className={cn("flex items-center gap-2 border-b border-border bg-surface pl-8 pr-4",
                               TRACKER_HEADER_H)}>
              <LeftPaneTab active={leftPane === "breakdown"} onClick={() => setLeftPane("breakdown")}>
                BREAKDOWN
              </LeftPaneTab>
              <LeftPaneTab active={leftPane === "collection"} onClick={() => setLeftPane("collection")}>
                COLLECTION
              </LeftPaneTab>
              <AccountTabs
                accounts={trackerAccounts}
                active={trackerAccount}
                onChange={setTrackerAccount}
                className="ml-auto"
              />
              <RefreshButton setCode={profile.setCode} className="ml-auto" />
            </div>
            {leftPane === "collection" ? (
              <Collection slug={profile.slug} setCode={profile.setCode} accountId={trackerAccount} narrow />
            ) : (
              <BreakdownPanel breakdown={profile.formatBreakdown} totalScore={profile.score} events={events} selfReported={profile.selfReportedEvents} showPoints={ranked} lockedFormats={lockedFormats} bordered={false} />
            )}
          </div>
        ) : hasBreakdown && (
          <BreakdownPanel breakdown={profile.formatBreakdown} totalScore={profile.score} events={events} selfReported={profile.selfReportedEvents} showPoints={ranked} lockedFormats={lockedFormats} />
        )}
        {trackerMode ? (
          <DraftLog slug={profile.slug} setCode={profile.setCode} accountId={trackerAccount} />
        ) : (
        <DraftLogDesktop
          events={events}
          filtered={filtered}
          rows={displayRows}
          summary={eventLogSummaryParts(events.length, profile.selfReportedEvents, displayRows.length, filtersActive)}
          onOpenTrophy={setShotTrophy}
          formatFilter={formatFilter}
          setFormatFilter={setFormatFilter}
          colorsFilter={colorsFilter}
          setColorsFilter={setColorsFilter}
          colorOptions={colorOptions}
          formatOptions={formatOptions}
          setEndDate={sets?.find((s) => s.code === profile.setCode)?.endDate ?? null}
          playerDisplayName={profile.displayName}
          updated={profile.lastCalculatedAt ? lastUpdated(profile.lastCalculatedAt) : null}
        />
        )}
      </div>

      <PointsBreakdown
        open={pointsModalOpen}
        onClose={() => setPointsModalOpen(false)}
        breakdown={popoverBreakdown}
        confidenceOverride={formatFilter !== "ALL" ? fullConfidence : undefined}
        events={events}
        anchorRef={pointsBtnRef}
      />
      {shotTrophy && (
        <TrophyDeckModal
          trophy={shotTrophy}
          trophies={profile.selfReportedEvents}
          displayName={profile.displayName}
          onSelect={setShotTrophy}
          onClose={() => setShotTrophy(null)}
        />
      )}
    </div>
  );
}

function LeftPaneTab({
  active, onClick, children, className,
}: { active: boolean; onClick: () => void; children: React.ReactNode; className?: string }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "font-display text-[14px] tracking-[0.18em] px-4 h-full inline-flex items-center border-b-2 -mb-px",
        active ? "text-green border-green" : "text-muted border-transparent hover:text-text",
        className,
      )}
    >
      {children}
    </button>
  );
}

/** The tracker is private, so it only ever opens on the allowlisted user's own profile */
function useOwnTrackerProfile(slug: string): boolean {
  const { user } = useAuth();
  const { data: ownSlug } = usePlayerSlugByDiscordId(user?.discordId);
  return isTrackerUser(user?.discordId) && ownSlug === slug;
}

// A self-reported trophy rendered inline in the event log as a synthetic event. Carries the
// trophy for the deck-screenshot modal; never counted toward the scored stat strip.
type LogEntry = PlayerDraftEvent & { trophy?: SelfReportedEvent };

// Fallback label for trophies logged before the format field existed: a 7-win run reads Premier,
// anything shorter Traditional. Rows with a stored format use that instead.
function trophyFormatLabel(record: string): string {
  const wins = Number(record.split("-")[0]) || 0;
  return wins >= 7 ? "Premier Draft" : "Trad Draft";
}

function selfTrophyToEntry(trophy: SelfReportedEvent, fallbackSet: string): LogEntry {
  const [w, l] = trophy.record.split("-");
  return {
    slug: "",
    setCode: trophy.setCode || fallbackSet,
    eventId: `selftrophy-${trophy.sourceMessageId}`,
    // The platform doubles as the filterable format value so the format dropdown can filter to it;
    // the row's visible label comes from trophy.format (or the record-derived fallback).
    format: trophy.platform,
    expansion: trophy.setCode || fallbackSet,
    wins: Number(w) || 0,
    losses: Number(l) || 0,
    isTrophy: trophy.isTrophy,
    colors: trophy.colors,
    startedAt: trophy.reportedAt,
    finishedAt: trophy.reportedAt,
    externalUrl: null,
    eventName: null,
    podEventSlug: null,
    trophy,
  };
}

// Real events plus the self-reported trophy rows that pass the active filters, newest first.
function mergeTrophyRows(
  filteredEvents: PlayerDraftEvent[],
  profile: PlayerProfile,
  matches: (colors: string, format: string) => boolean,
): LogEntry[] {
  const trophyRows = profile.selfReportedEvents
    .map((t) => selfTrophyToEntry(t, profile.setCode))
    .filter((e) => matches(e.colors, e.format));
  return [...filteredEvents, ...trophyRows].sort((a, b) =>
    eventDate(a) < eventDate(b) ? 1 : eventDate(a) > eventDate(b) ? -1 : 0,
  );
}

function TrophyDeckModal({
  trophy,
  trophies,
  displayName,
  onSelect,
  onClose,
}: {
  trophy: SelfReportedEvent;
  trophies: SelfReportedEvent[];
  displayName: string;
  onSelect: (trophy: SelfReportedEvent) => void;
  onClose: () => void;
}) {
  const index = trophies.findIndex((t) => t.sourceMessageId === trophy.sourceMessageId);
  const canCycle = trophies.length > 1;
  const prev = canCycle ? trophies[(index - 1 + trophies.length) % trophies.length] : null;
  const next = canCycle ? trophies[(index + 1) % trophies.length] : null;
  return (
    <DeckScreenshotModal
      participant={{
        displayName,
        deckColors: trophy.colors,
        deckScreenshotUrl: trophy.screenshotUrl,
        deckScreenshotCaption: trophy.caption,
        deckSourceUrl: trophy.sourceUrl,
        record: trophy.record,
        screenshotChannelId: trophy.sourceChannelId,
        screenshotMessageId: trophy.sourceMessageId,
        mainboard: null,
      }}
      hideDraftLog
      onClose={onClose}
      onPrev={prev ? () => onSelect(prev) : undefined}
      onNext={next ? () => onSelect(next) : undefined}
    />
  );
}

function StatStrip({
  stats,
  wp,
  showPoints = true,
  onPointsClick,
  pointsBtnRef,
  trophiesLabel = "TROPHIES",
}: {
  stats: StatStripStats;
  wp: string;
  showPoints?: boolean;
  onPointsClick?: () => void;
  pointsBtnRef?: React.RefObject<HTMLButtonElement>;
  trophiesLabel?: string;
}) {
  const valueCls = "font-display leading-none text-[clamp(26px,3vw,44px)]";
  const tiles: Array<{
    label: string;
    value: React.ReactNode;
    accent?: boolean;
    onClick?: () => void;
    btnRef?: React.RefObject<HTMLButtonElement>;
  }> = [
    {
      label: trophiesLabel,
      value: (
        <span className="flex items-center gap-1.5">
          <Trophy size={26} color="#ffc63a" />
          <span className={valueCls}>{stats.trophies}</span>
        </span>
      ),
    },
    {
      label: "EVENTS",
      value: <span className={valueCls}>{stats.events}</span>,
    },
    {
      label: "RECORD",
      value: (
        <Record
          mono
          wins={stats.wins}
          losses={stats.losses}
          separatorMargin={4}
          className={valueCls}
        />
      ),
    },
    {
      label: "WIN %",
      value: (
        <span className={valueCls}>
          {wp}
          <span className="text-[clamp(14px,1.5vw,22px)] text-muted">%</span>
        </span>
      ),
    },
    ...(showPoints
      ? [
          {
            label: "POINTS",
            value: <span className={cn(valueCls, "text-green")}>{fmtPts(stats.score)}</span>,
            accent: true,
            onClick: onPointsClick,
            btnRef: pointsBtnRef,
          },
        ]
      : []),
  ];
  return (
    <div
      className="grid border border-border2 bg-bg self-stretch min-w-0 ml-auto"
      style={{
        flex: "0 1 720px",
        gridTemplateColumns: showPoints ? "1fr 1fr 1.3fr 1fr 1.05fr" : "1fr 1fr 1.3fr 1fr",
      }}
    >
      {tiles.map((t, i) => {
        const tileCls = cn(
          "py-3.5 px-3 flex flex-col items-center text-center min-w-0",
          i < tiles.length - 1 && "border-r border-border2",
        );
        const label = (
          <SectionLabel size={14}>
            {t.onClick ? (
              <span className="relative inline-block leading-none">
                {t.label}
                <span
                  aria-hidden="true"
                  className="absolute top-1/2 -translate-y-1/2 ml-[3px] leading-none"
                  style={{ left: "100%" }}
                >
                  <Info size={14} className="text-muted" />
                </span>
              </span>
            ) : (
              t.label
            )}
          </SectionLabel>
        );
        const body = (
          <>
            {label}
            <div className="flex-1 flex items-center justify-center">{t.value}</div>
          </>
        );
        if (t.onClick) {
          return (
            <Tooltip key={t.label} label="View Points Breakdown">
              <button
                type="button"
                ref={t.btnRef}
                onClick={t.onClick}
                aria-label={`Show ${t.label.toLowerCase()} breakdown`}
                className={cn(tileCls, "bg-transparent cursor-pointer hover:bg-surface2/40 transition-colors")}
              >
                {body}
              </button>
            </Tooltip>
          );
        }
        return (
          <div key={t.label} className={tileCls}>
            {body}
          </div>
        );
      })}
    </div>
  );
}

const PANEL_TITLE_COLOR = "#e6ecf5";

function BreakdownPanel({
  breakdown,
  totalScore,
  events,
  selfReported,
  showPoints,
  lockedFormats,
  bordered = true,
}: {
  breakdown: PlayerFormatBreakdown[];
  totalScore: number;
  events: PlayerDraftEvent[];
  selfReported: SelfReportedEvent[];
  showPoints: boolean;
  lockedFormats?: string[] | null;
  bordered?: boolean;
}) {
  const formatBreakdown = useMemo(
    () => [...breakdown].sort((a, b) => b.scoreContribution - a.scoreContribution),
    [breakdown],
  );
  const total = formatBreakdown.reduce((s, f) => s + f.scoreContribution, 0) || 1;
  const { colorCount, comboCount, comboTrophies } = aggregate(events, selfReported);
  const comboEntries = Object.entries(comboCount).sort((a, b) => b[1] - a[1]);
  const comboTotal = comboEntries.reduce((s, [, n]) => s + n, 0) || 1;
  const colorTotal = Object.values(colorCount).reduce((a, b) => a + b, 0) || 1;

  const [fmtHover, setFmtHover] = useState<string | null>(null);
  const activeFmt = fmtHover ?? lockedFormats ?? null;
  const [deckHover, setDeckHover] = useState<string | null>(null);
  const [colorHover, setColorHover] = useState<string | null>(null);

  const deckRowRefs = useRef<Record<string, HTMLDivElement | null>>({});
  useEffect(() => {
    if (deckHover) {
      deckRowRefs.current[deckHover]?.scrollIntoView({ block: "nearest", behavior: "smooth" });
    }
  }, [deckHover]);

  return (
    <section className={cn("py-5 pr-8 pl-6 min-[1360px]:pl-10", bordered && "border-r border-border")}>
      {showPoints && formatBreakdown.length > 0 && (
        <>
          <SectionLabel size={15} letterSpacing="0.18em" color={PANEL_TITLE_COLOR} className="mb-3.5 text-center whitespace-nowrap" style={{ width: 148 }}>POINTS BY FORMAT</SectionLabel>
          <div className="flex items-center gap-5 mb-4">
            <DonutChart
              pieHole={0.5}
              entries={formatBreakdown.map((f) => ({
                key: f.formatLabel,
                value: f.scoreContribution / total,
                color: FMT_COLORS[f.formatLabel] ?? "#5c8aff",
              }))}
              radius={56}
              strokeWidth={18}
              size={148}
              activeKey={activeFmt}
              onHoverEntry={setFmtHover}
            />
            <FormatLegend
              breakdown={formatBreakdown}
              totalScore={totalScore}
              hoveredKey={activeFmt}
              onHover={setFmtHover}
            />
          </div>
        </>
      )}

      <SectionLabel size={15} letterSpacing="0.18em" color={PANEL_TITLE_COLOR} className={cn("mb-3 text-center whitespace-nowrap", showPoints && formatBreakdown.length > 0 && "mt-6")} style={{ width: 148 }}>DECK COLORS</SectionLabel>
      <div className="flex items-center gap-5">
        <DonutChart
          pieHole={0.5}
          entries={comboEntries.map(([k, v]) => ({
            key: k,
            value: v,
            colors: comboColors(k),
          }))}
          radius={56}
          strokeWidth={18}
          size={148}
          activeKey={deckHover}
          onHoverEntry={setDeckHover}
        />
        <div
          className="flex-1 flex flex-col gap-1 max-h-[148px] overflow-y-auto overflow-x-hidden pr-2 [&::-webkit-scrollbar]:w-1 [&::-webkit-scrollbar-track]:bg-transparent [&::-webkit-scrollbar-thumb]:bg-border2 [&::-webkit-scrollbar-thumb]:rounded-full"
          style={{ scrollbarWidth: "thin", scrollbarColor: "#3b4458 transparent" }}
        >
          {comboEntries.map(([code, count]) => (
            <div
              key={code}
              ref={(el) => {
                deckRowRefs.current[code] = el;
              }}
              onMouseEnter={() => setDeckHover(code)}
              onMouseLeave={() => setDeckHover(null)}
              className={cn(
                "grid gap-2 items-center px-1.5 rounded transition-colors cursor-default",
                deckHover === code && "bg-surface2",
              )}
              style={{ gridTemplateColumns: "auto 1fr 44px 40px" }}
            >
              <Pips colors={code} size={14} />
              <span className="font-display text-[15px] tracking-[0.06em]">
                {colorsDisplayName(code)}
              </span>
              <TrophyCount
                count={comboTrophies[code] ?? 0}
                size="md"
                display
                fixedDigits={2}
                className="text-subtle justify-self-end"
              />
              <span className="mono text-[15px] text-subtle text-right">
                ×{count}
              </span>
            </div>
          ))}
        </div>
      </div>

      <SectionLabel size={15} letterSpacing="0.18em" color={PANEL_TITLE_COLOR} className="mt-6 mb-3 text-center whitespace-nowrap" style={{ width: 148 }}>COLORS PLAYED</SectionLabel>
      <div className="flex items-center gap-5">
        <DonutChart
          pieHole={0.5}
          entries={Object.entries(colorCount)
            .filter(([, v]) => v > 0)
            .map(([k, v]) => ({ key: k, value: v, color: COLOR_STROKES[k] }))}
          radius={56}
          strokeWidth={18}
          size={148}
          activeKey={colorHover}
          onHoverEntry={setColorHover}
        />
        <div className="flex-1 flex flex-col gap-1 pr-4">
          {COLOR_KEYS.map((c) => {
            const pct = (colorCount[c] / colorTotal) * 100;
            return (
              <div
                key={c}
                onMouseEnter={() => setColorHover(c)}
                onMouseLeave={() => setColorHover(null)}
                className={cn(
                  "grid gap-2 items-center px-1.5 -mx-1.5 rounded transition-colors cursor-default",
                  colorHover === c && "bg-surface2",
                )}
                style={{ gridTemplateColumns: "auto 1fr 48px" }}
              >
                <Pip c={c} size={14} />
                <span className="font-display text-[15px] tracking-[0.06em]">
                  {COLOR_NAMES[c]}
                </span>
                <span className="mono text-[15px] text-subtle text-right">
                  {pct.toFixed(0)}%
                </span>
              </div>
            );
          })}
        </div>
      </div>
    </section>
  );
}

function FormatLegend({
  breakdown,
  totalScore,
  hoveredKey,
  onHover,
}: {
  breakdown: PlayerFormatBreakdown[];
  totalScore: number;
  hoveredKey?: string | string[] | null;
  onHover?: (key: string | null) => void;
}) {
  const isHighlighted = (label: string) =>
    Array.isArray(hoveredKey) ? hoveredKey.includes(label) : hoveredKey === label;
  return (
    <div className="flex-1 flex flex-col">
      {breakdown.map((f, i) => {
        const pct = totalScore ? (f.scoreContribution / totalScore) * 100 : 0;
        return (
          <div
            key={f.formatLabel}
            onMouseEnter={onHover ? () => onHover(f.formatLabel) : undefined}
            onMouseLeave={onHover ? () => onHover(null) : undefined}
            className={cn(
              "grid items-center py-[5px] gap-2.5 px-1.5 -mx-1.5 rounded transition-colors cursor-default",
              isHighlighted(f.formatLabel) && "bg-surface2",
            )}
            style={{ gridTemplateColumns: "1fr 44px 68px 48px" }}
          >
            <span
              className="font-display text-[15px] tracking-[0.06em]"
              style={{ color: FMT_COLORS[f.formatLabel] ?? "#5c8aff" }}
            >
              {shortFormat(f.formatLabel)}
            </span>
            <TrophyCount
              count={f.trophies}
              size="md"
              display
              fixedDigits={2}
              className="text-subtle justify-self-end"
            />
            <Record
              mono
              wins={f.wins}
              losses={f.losses}
              className="mono text-[13px] text-right text-subtle"
            />
            <span
              className={cn(
                "font-display text-[17px] text-right",
                pct > 0 ? "text-green" : "text-muted",
              )}
            >
              {fmtPts(f.scoreContribution)}
            </span>
          </div>
        );
      })}
    </div>
  );
}

function DraftLogDesktop({
  events,
  filtered,
  rows,
  summary,
  onOpenTrophy,
  formatFilter,
  setFormatFilter,
  colorsFilter,
  setColorsFilter,
  colorOptions,
  formatOptions,
  setEndDate,
  playerDisplayName,
  updated,
}: {
  events: PlayerDraftEvent[];
  filtered: PlayerDraftEvent[];
  rows: LogEntry[];
  summary: string[];
  onOpenTrophy: (t: SelfReportedEvent) => void;
  formatFilter: string;
  setFormatFilter: (v: string) => void;
  colorsFilter: string;
  setColorsFilter: (v: string) => void;
  colorOptions: FilterOption[];
  formatOptions: FilterOption[];
  setEndDate: string | null;
  playerDisplayName: string;
  updated: string | null;
}) {
  const compact = useIsMobile(1240);
  const sectionRef = useRef<HTMLElement>(null);
  const scrollToTop = () =>
    sectionRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });

  return (
    <section ref={sectionRef} className="pb-6 px-5 min-w-0">
      <div className="flex justify-between items-center gap-3 h-[42px] px-5 -mx-5 border-b border-border2">
        <div className="flex items-baseline gap-2.5 shrink-0">
          <SectionLabel size={14}>EVENT LOG</SectionLabel>
          {summary.length > 0 && (
            <span className="inline-flex items-baseline gap-x-3 font-display text-[13px] tracking-[0.14em] text-subtle whitespace-nowrap">
              {summary.map((part) => (
                <span key={part}>{part}</span>
              ))}
            </span>
          )}
        </div>
        {updated && (
          <span className="font-display text-[13px] tracking-[0.14em] text-muted shrink-0 whitespace-nowrap">
            UPDATED {updated}
          </span>
        )}
        <div className="flex gap-2 min-w-0 shrink justify-end">
          <FilterDropdown
            value={formatFilter}
            onChange={setFormatFilter}
            options={formatOptions}
            renderValue={renderFormatOption}
            renderOption={renderFormatOption}
            className="min-w-0 max-w-[200px]"
            triggerClassName="min-w-0"
          />
          <FilterDropdown
            value={colorsFilter}
            onChange={setColorsFilter}
            options={colorOptions}
            renderValue={renderColorOption}
            renderOption={renderColorOption}
            className="min-w-0 max-w-[200px]"
            triggerClassName="min-w-0"
          />
        </div>
      </div>

      <div
        className="grid gap-x-2 items-stretch"
        style={{ gridTemplateColumns: "22px 70px max-content 1fr 24px auto" }}
      >
        {rows.map((e, i) => {
          const isFB = isFlashbackEvent(e.finishedAt, setEndDate);
          const prev = rows[i - 1];
          const next = rows[i + 1];
          const showBoundary = !isFB && !!prev && isFlashbackEvent(prev.finishedAt, setEndDate);
          const hideBottomBorder =
            isFB && !!next && !isFlashbackEvent(next.finishedAt, setEndDate);
          return (
            <React.Fragment key={e.eventId}>
              {showBoundary && <FlashbackDivider variant="desktop" />}
              <EventLogRow event={e} variant="desktop" hideBottomBorder={hideBottomBorder} playerDisplayName={playerDisplayName} onOpenTrophy={onOpenTrophy} compact={compact} />
            </React.Fragment>
          );
        })}
        {rows.length === 0 && (
          <div className="p-6 text-center text-muted font-display tracking-[0.2em] col-span-full">
            NO EVENTS MATCH FILTER
          </div>
        )}
        <GoToTopButton onClick={scrollToTop} />
      </div>
    </section>
  );
}

function FormatTagPill({ tag }: { tag: { label: string; tone: "midweek" | "open" | "alchemy" } }) {
  if (tag.tone === "alchemy") {
    return (
      <img
        src={`${import.meta.env.BASE_URL}alchemy.png`}
        alt={tag.label}
        className="h-6 w-auto object-contain"
      />
    );
  }
  const toneCls =
    tag.tone === "midweek"
      ? "border-[#a86bff] text-[#a86bff]"
      : "border-[#ffc63a] text-[#ffc63a]";
  return (
    <span
      className={cn(
        "inline-flex items-center px-2 py-0.5 bg-bg border font-display text-[11px] tracking-[0.2em] leading-none uppercase whitespace-nowrap",
        toneCls,
      )}
    >
      {tag.label}
    </span>
  );
}

function CashPrizePill({ amount, className }: { amount: string; className?: string }) {
  return (
    <span
      className={cn(
        "inline-flex items-center px-2 py-1 bg-[#ff8c3a] border border-[#ff8c3a] text-bg font-mono font-bold text-[13px] tracking-[0.08em] leading-none whitespace-nowrap",
        className,
      )}
    >
      {amount}
    </span>
  );
}

function FlashbackDivider({ variant }: { variant: "desktop" | "mobile" }) {
  const mxClass = variant === "mobile" ? "-mx-[18px]" : "-mx-2";
  const spanCls = variant === "desktop" ? "col-span-full" : "";
  return (
    <div className={cn("relative my-1 border-t border-teal", mxClass, spanCls)}>
      <span className="absolute left-1/2 -translate-x-1/2 -top-[9px] px-2 py-0.5 bg-bg border border-teal text-teal font-display text-[11px] tracking-[0.2em] leading-none">
        FLASHBACK
      </span>
    </div>
  );
}

function PodEventButton({ size = "md" }: { size?: "sm" | "md" }) {
  const isSm = size === "sm";
  const chamfer = "polygon(4px 0, 100% 0, calc(100% - 4px) 100%, 0 100%)";
  return (
    <span
      className="inline-block bg-transparent transition-colors group-hover:[animation:pod-border-pulse_1.4s_ease-in-out_infinite]"
      style={{ clipPath: chamfer, padding: 1 }}
    >
      <span
        className={cn(
          "inline-flex items-center gap-1.5 leading-none font-display text-text bg-surface2 whitespace-nowrap",
          isSm
            ? "text-[11px] tracking-[0.14em] py-[5px] pl-[8px] pr-[10px]"
            : "text-[13px] tracking-[0.14em] py-[6px] pl-[10px] pr-[12px]",
        )}
        style={{ clipPath: chamfer }}
      >
        <GiRoundTable size={isSm ? 14 : 16} className="text-green shrink-0" />
        <span className={isSm ? "inline" : "hidden xl:inline"}>VIEW EVENT</span>
        <ArrowRight size={isSm ? 10 : 12} className={isSm ? "inline-block" : "hidden xl:inline-block"} />
      </span>
    </span>
  );
}

const PLATFORM_BUCKETS = ["MTGA", "MTGO", "PAPER", "OTHER"] as const;

const PLATFORM_ICONS: Record<string, string> = {
  MTGA: `${import.meta.env.BASE_URL}platforms/mtga.png`,
  MTGO: `${import.meta.env.BASE_URL}platforms/mtgo.png`,
  PAPER: `${import.meta.env.BASE_URL}platforms/cardback.png`,
};

function platformBucket(platform: string): (typeof PLATFORM_BUCKETS)[number] {
  const p = platform.toLowerCase();
  if (p.includes("mtgo") || p.includes("online")) return "MTGO";
  if (p.includes("mtga") || p.includes("arena")) return "MTGA";
  if (p.includes("paper") || p.includes("pre")) return "PAPER";
  return "OTHER";
}

function platformCounts(trophies: SelfReportedEvent[]): Array<{ bucket: string; count: number }> {
  const counts = new Map<string, number>();
  for (const t of trophies) {
    const bucket = platformBucket(t.platform);
    counts.set(bucket, (counts.get(bucket) ?? 0) + 1);
  }
  return PLATFORM_BUCKETS.filter((b) => counts.has(b)).map((b) => ({ bucket: b, count: counts.get(b)! }));
}

// Event-log header summary parts, rendered space-separated: ["88 EVENTS"] when it's all 17lands,
// ["88 17LANDS", "1 MTGO", "1 MTGA", "1 PAPER"] when manual trophies are mixed in, the platforms alone
// for a manual-only player, [] when empty. While filtered, the visible-of-total count.
function eventLogSummaryParts(
  events17L: number,
  trophies: SelfReportedEvent[],
  visibleRows: number,
  isFiltered: boolean,
): string[] {
  if (events17L === 0 && trophies.length === 0) return [];
  if (isFiltered) return [`${visibleRows} OF ${events17L + trophies.length}`];
  if (trophies.length === 0) return [`${events17L} EVENTS`];
  const parts = events17L > 0 ? [`${events17L} 17LANDS`] : [];
  for (const { bucket, count } of platformCounts(trophies)) parts.push(`${count} ${bucket}`);
  return parts;
}

// Player-logged trophies — separate from the automated 17L count, one icon + tally per source.
// Desktop: a bordered tile beside the 17L stat. Mobile: a compact inline row under the player name
// (no label). The platform doubles as the event-log row's format value, so the dropdown can filter it.
function ManualTrophiesBlock({
  trophies,
  mobile = false,
  className,
}: {
  trophies: SelfReportedEvent[];
  mobile?: boolean;
  className?: string;
}) {
  const wins = trophies.filter((t) => t.isTrophy);
  if (wins.length === 0) return null;
  const counts = platformCounts(wins);
  const iconSize = mobile ? 18 : 24;
  const numCls = mobile ? "text-[16px]" : "text-[clamp(22px,2.4vw,32px)]";
  const pairs = counts.map(({ bucket, count }) => (
    <span key={bucket} className={cn("inline-flex items-center", mobile ? "gap-1" : "gap-1.5")}>
      {PLATFORM_ICONS[bucket] ? (
        <img src={PLATFORM_ICONS[bucket]} alt={bucket} style={{ height: iconSize }} className="w-auto shrink-0" draggable={false} />
      ) : (
        <span className="font-display text-muted text-[12px] tracking-[0.12em]">{bucket}</span>
      )}
      <span className={cn("font-display leading-none tabular-nums", numCls)}>{count}</span>
    </span>
  ));
  if (mobile) {
    return (
      <div className={cn("pl-[5px] flex items-center flex-wrap gap-x-2 gap-y-1", className)}>
        <Trophy size={iconSize} color="#ffc63a" />
        {pairs}
      </div>
    );
  }
  return (
    <div className="border border-border2 bg-bg px-4 py-3.5 flex flex-col items-center justify-center text-center gap-2 self-stretch shrink-0 min-w-[120px]">
      <div className="flex items-center gap-1.5">
        <SectionLabel size={13}>MANUAL</SectionLabel>
        <Trophy size={18} color="#ffc63a" />
      </div>
      <div className="flex items-center justify-center flex-wrap gap-4">{pairs}</div>
    </div>
  );
}

// Marks an event-log row as a player-reported result, naming where it was played.
// Border/text take the platform's palette color (red MTGO/MTGA, brown Paper), grey for write-ins.
function PlatformTag({ platform, label = platform }: { platform: string; label?: string }) {
  const color = FMT_COLORS[platform];
  return (
    <span
      className={cn(
        "inline-flex items-center px-2 py-1 bg-bg border font-display text-[13px] tracking-[0.18em] leading-none uppercase whitespace-nowrap",
        color ? "" : "border-border text-muted",
      )}
      style={color ? { borderColor: color, color } : undefined}
    >
      {label}
    </span>
  );
}

function EventLogRow({
  event: e,
  variant,
  hideBottomBorder = false,
  playerDisplayName,
  onOpenTrophy,
  setColumn = false,
  setHref,
  compact = false,
}: {
  event: LogEntry;
  variant: "desktop" | "mobile";
  hideBottomBorder?: boolean;
  playerDisplayName?: string;
  onOpenTrophy?: (t: SelfReportedEvent) => void;
  setColumn?: boolean;
  setHref?: string;
  compact?: boolean;
}) {
  const trophy = e.trophy ?? null;
  const href = e.externalUrl ?? null;
  const isPod = e.format === "PodDraft";
  const podSlug = isPod ? e.podEventSlug ?? null : null;
  const podLinkTo = podSlug
    ? `/pods/${podSlug}${playerDisplayName ? `?player=${encodeURIComponent(playerDisplayName)}` : ""}`
    : null;
  const podFullHref = useHref(podLinkTo ?? "/");
  const podNewTabHref = podLinkTo ? podFullHref : null;
  const rowInternal = isPod && !!podSlug;
  const rowExternal = !isPod && !!href;
  const linkClass = (rowInternal || rowExternal || trophy) ? "group cursor-pointer transition-colors hover:bg-surface2 no-underline text-inherit" : "";
  const podWithoutDeck = isPod && !e.colors;
  const formatLabel = trophy
    ? (trophy.format ?? trophyFormatLabel(trophy.record)).toUpperCase()
    : eventDisplayLabel(e).toUpperCase();
  const tag = isPod || trophy ? null : formatTag(e.format, e.expansion);
  const cashPrize = lcqCashPrize(e);
  const recordColor = cashPrize ? "#ff8c3a" : e.isTrophy ? "#2ee85c" : "#e6ecf5";
  const borderCls = hideBottomBorder ? "" : "border-b border-border";

  if (variant === "desktop") {
    const { name: deckName, splash: deckSplash } = !podWithoutDeck
      ? deckColorParts(e.colors)
      : { name: "", splash: "" };
    const deckContent = compact ? (
      <span className="flex items-center">
        <Pips colors={e.colors} size={14} />
      </span>
    ) : (
      <span className="grid items-center gap-x-2" style={{ gridTemplateColumns: "100px 96px 1fr" }}>
        <Pips colors={e.colors} size={14} />
        <span
          className="text-[13px] text-muted whitespace-nowrap"
          style={deckSplash ? undefined : { gridColumn: "span 2" }}
        >
          {deckName}
        </span>
        {deckSplash && <span className="text-[13px] text-muted">{deckSplash}</span>}
      </span>
    );
    const inner = (
      <>
        {setColumn && (
          <span className="flex items-center justify-center">
            <SetGlyph code={e.setCode} size={18} className="text-white/85" />
          </span>
        )}
        <span className="text-right pr-1">
          {e.isTrophy && <Trophy size={18} color="#ffc63a" />}
        </span>
        <span className="text-[13px] text-muted text-center">{fmtShortDate(eventDate(e))}</span>
        <span className="flex items-center gap-2 min-w-0 pr-4">
          <span className="font-display text-[16px] tracking-[0.08em] whitespace-nowrap">{highlightEventLabel(formatLabel)}</span>
          {e.isTrophy && isArenaChampionshipFormat(e.format) && <ArenaChampBadge size={36} box={22} />}
          <span className="flex-1 flex items-center justify-center">
            {cashPrize && <CashPrizePill amount={cashPrize} />}
          </span>
          {tag && <FormatTagPill tag={tag} />}
        </span>
        {isPod ? (
          compact ? (
            <span className="flex items-center gap-2 min-w-0">
              {!podWithoutDeck && <Pips colors={e.colors} size={14} />}
              {podSlug && <PodEventButton />}
            </span>
          ) : (
          <span className="grid items-center gap-x-2 min-w-0" style={{ gridTemplateColumns: "100px 96px minmax(0, 100px) auto 1fr" }}>
            {podWithoutDeck ? (
              <span className="text-[13px] text-muted" style={{ gridColumn: "1 / 4" }}>
                Deck not submitted
              </span>
            ) : (
              <>
                <Pips colors={e.colors} size={14} />
                <span
                  className="text-[13px] text-muted whitespace-nowrap"
                  style={deckSplash ? undefined : { gridColumn: "span 2" }}
                >
                  {deckName}
                </span>
                {deckSplash && <span className="text-[13px] text-muted">{deckSplash}</span>}
              </>
            )}
            {podSlug && <PodEventButton />}
          </span>
          )
        ) : (
          deckContent
        )}
        <span className="flex items-center justify-center">
          <ArenaRankIcon endRank={e.endRank} size={22} />
        </span>
        {trophy ? (
          <span className="inline-flex items-center justify-end gap-3 text-dim group-hover:text-text transition-colors">
            <PlatformTag platform={trophy.platform} />
            <ImageIcon size={18} aria-hidden="true" />
            <Record
              mono
              wins={e.wins}
              losses={e.losses}
              color={recordColor}
              className="text-right font-display text-[22px]"
            />
          </span>
        ) : isPod ? (
          podNewTabHref ? (
            <Tooltip label="Open in new tab">
              <button
                type="button"
                onClick={(ev) => {
                  ev.preventDefault();
                  ev.stopPropagation();
                  window.open(podNewTabHref, "_blank", "noopener,noreferrer");
                }}
                aria-label="Open event in new tab"
                className="inline-flex items-center justify-end gap-3 text-dim group-hover:text-text transition-colors bg-transparent border-none p-0 cursor-pointer"
              >
                <Record
                  mono
                  wins={e.wins}
                  losses={e.losses}
                  color={recordColor}
                  className="text-right font-display text-[22px]"
                />
                <ExternalLink size={18} aria-hidden="true" />
              </button>
            </Tooltip>
          ) : (
            <span className="inline-flex items-center justify-end">
              <Record
                mono
                wins={e.wins}
                losses={e.losses}
                color={recordColor}
                className="text-right font-display text-[22px]"
              />
            </span>
          )
        ) : (
          <Tooltip label="View deck in 17lands">
            <span className="inline-flex items-center justify-end gap-3 text-dim group-hover:text-text transition-colors">
              <Record
                mono
                wins={e.wins}
                losses={e.losses}
                color={recordColor}
                className="text-right font-display text-[22px]"
              />
              {href && <ExternalLink size={18} aria-hidden="true" />}
            </span>
          </Tooltip>
        )}
      </>
    );
    const cls = cn(
      "grid gap-x-3 py-[6px] px-2 -mx-2 items-center col-span-full",
      borderCls,
      linkClass,
    );
    const style = { gridTemplateColumns: "subgrid" };
    if (trophy) {
      return (
        <button
          type="button"
          onClick={() => onOpenTrophy?.(trophy)}
          className={cn("text-left w-full bg-transparent border-0", cls)}
          style={style}
        >
          {inner}
        </button>
      );
    }
    if (rowInternal && podLinkTo) {
      return <Link to={podLinkTo} className={cls} style={style}>{inner}</Link>;
    }
    if (rowExternal) {
      return (
        <a href={href!} target="_blank" rel="noopener noreferrer" className={cls} style={style}>
          {inner}
        </a>
      );
    }
    if (setHref) {
      return <Link to={setHref} className={cls} style={style}>{inner}</Link>;
    }
    return <div className={cls} style={style}>{inner}</div>;
  }

  // mobile
  const inner = (
    <>
      <span>
        {e.isTrophy && <Trophy size={16} color="#ffc63a" />}
      </span>
      <div>
        <div className="flex items-center gap-1.5 flex-wrap">
          {setColumn && <SetGlyph code={e.setCode} size={13} className="text-white/85" />}
          {!podWithoutDeck && <Pips colors={e.colors} size={11} />}
          <span className="font-display text-[13px] tracking-[0.08em]">
            {highlightEventLabel(formatLabel)}
          </span>
          {e.isTrophy && isArenaChampionshipFormat(e.format) && <ArenaChampBadge size={28} box={16} />}
          {cashPrize && <CashPrizePill amount={cashPrize} className="mx-1.5" />}
          {tag && <FormatTagPill tag={tag} />}
        </div>
        <div className="mt-0.5">
          <span className="text-[11px] text-muted">
            {[
              podWithoutDeck ? "Deck not submitted" : formatDeckColors(e.colors),
              fmtShortDate(eventDate(e)),
            ].filter(Boolean).join(" · ")}
          </span>
        </div>
      </div>
      {trophy ? (
        <span className="inline-flex items-center gap-1.5 text-dim group-hover:text-text transition-colors">
          <PlatformTag platform={trophy.platform} label={platformBucket(trophy.platform)} />
          <ImageIcon size={16} aria-hidden="true" />
          <Record
            mono
            wins={e.wins}
            losses={e.losses}
            color={recordColor}
            className="font-display text-[22px]"
          />
        </span>
      ) : isPod ? (
        <span className="inline-flex items-center gap-2.5">
          {podSlug && <PodEventButton size="sm" />}
          {podNewTabHref ? (
            <Tooltip label="Open in new tab">
              <button
                type="button"
                onClick={(ev) => {
                  ev.preventDefault();
                  ev.stopPropagation();
                  window.open(podNewTabHref, "_blank", "noopener,noreferrer");
                }}
                aria-label="Open event in new tab"
                className="inline-flex items-center gap-1.5 text-dim group-hover:text-text transition-colors bg-transparent border-none p-0 cursor-pointer"
              >
                <Record
                  mono
                  wins={e.wins}
                  losses={e.losses}
                  color={recordColor}
                  className="font-display text-[22px]"
                />
                <ExternalLink size={16} aria-hidden="true" />
              </button>
            </Tooltip>
          ) : (
            <Record
              mono
              wins={e.wins}
              losses={e.losses}
              color={recordColor}
              className="font-display text-[22px]"
            />
          )}
        </span>
      ) : (
        <Tooltip label="View deck in 17lands">
          <span className="inline-flex items-center gap-1.5 text-dim group-hover:text-text transition-colors">
            <ArenaRankIcon endRank={e.endRank} size={18} className="mr-0.5" />
            <Record
              mono
              wins={e.wins}
              losses={e.losses}
              color={recordColor}
              className="font-display text-[22px]"
            />
            {href && <ExternalLink size={16} aria-hidden="true" />}
          </span>
        </Tooltip>
      )}
    </>
  );
  const cls = cn(
    "grid gap-2.5 py-2.5 px-[18px] -mx-[18px] items-center",
    borderCls,
    linkClass,
  );
  const style = { gridTemplateColumns: "20px 1fr auto" };
  if (trophy) {
    return (
      <button
        type="button"
        onClick={() => onOpenTrophy?.(trophy)}
        className={cn("text-left bg-transparent border-0 w-[calc(100%+36px)]", cls)}
        style={style}
      >
        {inner}
      </button>
    );
  }
  if (rowInternal && podLinkTo) {
    return (
      <Link to={podLinkTo} className={cls} style={style}>
        {inner}
      </Link>
    );
  }
  if (rowExternal) {
    return (
      <a href={href!} target="_blank" rel="noopener noreferrer" className={cls} style={style}>
        {inner}
      </a>
    );
  }
  return <div className={cls} style={style}>{inner}</div>;
}

// ─── Mobile ────────────────────────────────────────────────────────────────

function Mobile({
  profile,
  events,
  sibling,
  sets,
  onChangeSet,
}: {
  profile: PlayerProfile;
  events: PlayerDraftEvent[];
  sibling: SiblingNav;
  sets: SetSummary[] | undefined;
  onChangeSet: (code: string) => void;
}) {
  const navigate = useNavigate();

  const [formatFilter, setFormatFilter, colorsFilter, setColorsFilter, qs] =
    useUrlFilters();

  const { chips: colorChips, otherCombos } = useColorChips(profile.setCode);
  const cube = isCubeCode(profile.setCode);
  const colorOptions = useMemo<FilterOption[]>(() => {
    const opts: FilterOption[] = [{ value: "ALL", label: "ALL COLORS" }];
    for (const c of colorChips) {
      if (c === MULTI) opts.push({ value: MULTI, label: "SOUP" });
      else if (c === OTHER) opts.push({ value: OTHER, label: "OTHER" });
      else opts.push({ value: c, label: colorsDisplayName(c) });
    }
    return opts;
  }, [colorChips]);
  const { data: availableFormatLabels } = useAvailableFormats(profile.setCode);
  const formatOptions = useMemo(() => {
    const available = new Set(availableFormatLabels ?? []);
    const base = !availableFormatLabels
      ? FORMAT_OPTIONS
      : FORMAT_OPTIONS.filter((opt) => {
          if (opt.value === "ALL") return true;
          const labels = FORMAT_LABEL_GROUPS[opt.value] ?? [opt.value];
          return labels.some((l) => available.has(l));
        });
    const platforms = Array.from(new Set(profile.selfReportedEvents.map((t) => t.platform)));
    return [...base, ...platforms.map((p) => ({ value: p, label: p.toUpperCase() }))];
  }, [availableFormatLabels, profile.selfReportedEvents]);
  const otherSet = useMemo(() => new Set(otherCombos), [otherCombos]);

  const matchesFilters = useCallback(
    (colors: string, format: string) => {
      if (formatFilter !== "ALL" && !matchesFormatFilter(format, formatFilter)) return false;
      if (colorsFilter !== "ALL") {
        if (colorsFilter === MULTI) {
          if (!isSoup(colors, cube)) return false;
        } else if (colorsFilter === OTHER) {
          if (isSoup(colors, cube)) return false;
          if (!otherSet.has(colorsOf(colors))) return false;
        } else if (colorsOf(colors) !== colorsFilter) return false;
      }
      return true;
    },
    [formatFilter, colorsFilter, otherSet, cube]
  );

  // filtered = real 17lands events, the basis for the scored stat strip. displayRows adds the
  // self-reported trophies as synthetic rows for the log only, so counts/score stay untouched.
  const filtered = useMemo(
    () => events.filter((e) => matchesFilters(e.colors, e.format)),
    [events, matchesFilters]
  );
  const displayRows = useMemo(() => mergeTrophyRows(filtered, profile, matchesFilters), [filtered, profile, matchesFilters]);
  const [shotTrophy, setShotTrophy] = useSharedDeck(profile.selfReportedEvents);

  const filtersActive = formatFilter !== "ALL" || colorsFilter !== "ALL";
  // The headline points and its breakdown popover follow the format filter only, selecting the
  // canonical per-format contributions (already carrying the player-wide confidence, and the flat
  // Pod row) rather than rescoring the filtered events — which would shrink confidence per-format
  // and drop pod points. Colors narrow the event log and counts, not the points.
  const popoverBreakdown = useMemo(() => {
    if (formatFilter === "ALL") return profile.formatBreakdown;
    const labels = new Set(FORMAT_LABEL_GROUPS[formatFilter] ?? [formatFilter]);
    return profile.formatBreakdown.filter((b) => labels.has(b.formatLabel));
  }, [profile.formatBreakdown, formatFilter]);
  const fullConfidence = useMemo(
    () =>
      scoreAggregate(
        profile.formatBreakdown
          .filter((b) => b.formatLabel !== "Pod")
          .map((b) => ({ label: b.formatLabel, events: b.events, wins: b.wins, losses: b.losses, trophies: b.trophies })),
      ).confidence,
    [profile.formatBreakdown],
  );
  const pointsTotal =
    formatFilter === "ALL"
      ? profile.score
      : Math.round(popoverBreakdown.reduce((s, b) => s + b.scoreContribution, 0) * 100) / 100;
  const lockedFormats =
    formatFilter !== "ALL" && popoverBreakdown.length > 0 ? popoverBreakdown.map((b) => b.formatLabel) : null;
  const stats: StatStripStats = useMemo(() => {
    if (!filtersActive) {
      return { trophies: profile.trophies, events: profile.events, wins: profile.wins, losses: profile.losses, score: profile.score };
    }
    const counts = statsFromEvents(filtered);
    const filteredTrophyCount = displayRows.length - filtered.length;
    return { trophies: counts.trophies + filteredTrophyCount, events: counts.events, wins: counts.wins, losses: counts.losses, score: pointsTotal };
  }, [filtersActive, filtered, displayRows, pointsTotal, profile.trophies, profile.events, profile.wins, profile.losses, profile.score]);
  const wp = winPct(stats.wins, stats.losses);
  const ranked = profile.rank > 0;
  const hasBreakdown = profile.events > 0 || profile.selfReportedEvents.length > 0;
  const trackerMode = useOwnTrackerProfile(profile.slug);
  const { accounts: trackerAccounts, accountId: trackerAccount, setAccountId: setTrackerAccount } =
    useTrackerAccounts(trackerMode);
  const [pointsModalOpen, setPointsModalOpen] = useState(false);
  const pointsBtnRef = useRef<HTMLButtonElement>(null);

  const eventLogRef = useRef<HTMLElement>(null);
  const scrollToTop = () =>
    eventLogRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });

  return (
    <div className="bg-bg text-text min-h-screen page-fade">
      <MobilePlayerHeader sibling={sibling} navigate={navigate} qs={qs} />

      <section
        className="px-[18px] pt-5 pb-4 border-b border-border"
        style={{ background: "linear-gradient(180deg, #14181f 0%, #0a0c10 100%)" }}
      >
        <div className="flex items-center">
          <AAvatar displayName={profile.displayName} avatarUrl={profile.avatarUrl} size={84} green />
          <div className="flex-1 min-w-0 ml-3 relative flex items-center min-h-[84px]">
            <h1
              className="font-display tracking-[0.03em] m-0 pl-[5px] line-clamp-2 break-words"
              style={{ fontSize: "clamp(20px, 7vw, 44px)", lineHeight: 0.95 }}
            >
              {profile.displayName.toUpperCase()}
            </h1>
            <ManualTrophiesBlock
              trophies={profile.selfReportedEvents}
              mobile
              className="absolute bottom-0 left-0"
            />
          </div>
          <div className="flex flex-col items-end gap-1.5 font-display tracking-[0.18em] shrink-0">
            {ranked && (
              <span className="flex items-center gap-2" style={{ marginRight: -8 }}>
                <RankBadge rank={profile.rank} size="md" />
              </span>
            )}
            {sets ? (
              <SetCodeDropdown sets={sets} activeCode={profile.setCode} onChange={onChangeSet} size="sm" chamfer={false} includeLifetime />
            ) : (
              <span className="text-[18px]">{profile.setCode}</span>
            )}
          </div>
        </div>

        {profile.linked17lands && profile.events > 0 && (
        <div className={cn("mt-[18px] grid gap-[5px]", ranked ? "grid-cols-5" : "grid-cols-4")}>
          <StatChip
            label={profile.selfReportedEvents.some((e) => e.isTrophy) ? "17L TROPHIES" : "TROPHIES"}
            value={
              <span className="flex items-center gap-[3px]">
                <Trophy size={12} color="#ffc63a" />
                {stats.trophies}
              </span>
            }
          />
          <StatChip label="EVENTS" value={stats.events} />
          <StatChip label="RECORD" value={`${stats.wins}–${stats.losses}`} />
          <StatChip label="WIN %" value={`${wp}%`} />
          {ranked && (
            <StatChip
              label="POINTS"
              value={fmtPts(stats.score)}
              accent
              onClick={() => setPointsModalOpen((o) => !o)}
              buttonRef={pointsBtnRef}
            />
          )}
        </div>
        )}
      </section>

      {(hasBreakdown || trackerMode) && (
        <MobileBreakdown
          breakdown={profile.formatBreakdown}
          events={events}
          selfReported={profile.selfReportedEvents}
          showPoints={ranked}
          lockedFormats={lockedFormats}
          tracker={
            trackerMode
              ? {
                  slug: profile.slug,
                  setCode: profile.setCode,
                  updatedAt: profile.lastCalculatedAt ?? null,
                  accounts: trackerAccounts,
                  accountId: trackerAccount,
                  onChangeAccount: setTrackerAccount,
                }
              : null
          }
        />
      )}

      {!trackerMode && (
      <section ref={eventLogRef} className="py-4 px-[18px]">
        <div className="flex items-center justify-between mb-2.5 gap-2">
          <div className="flex items-baseline gap-2">
            <SectionLabel size={12}>EVENT LOG</SectionLabel>
            <span className="inline-flex items-baseline gap-x-2.5 font-display text-[11px] tracking-[0.12em] text-dim">
              {eventLogSummaryParts(events.length, profile.selfReportedEvents, displayRows.length, filtersActive).map(
                (part) => (
                  <span key={part}>{part}</span>
                ),
              )}
            </span>
          </div>
          {profile.lastCalculatedAt && (
            <span className="font-display text-[11px] tracking-[0.12em] text-muted">UPDATED {lastUpdated(profile.lastCalculatedAt)}</span>
          )}
        </div>
        <div className="flex items-stretch gap-2 mb-3">
          <div className="flex-1 min-w-0 flex">
            <FilterDropdown
              value={formatFilter}
              onChange={setFormatFilter}
              options={formatOptions}
              variant="mobile"
              renderValue={renderFormatOption}
              renderOption={renderFormatOption}
            />
          </div>
          <div className="flex-1 min-w-0 flex">
            <FilterDropdown
              value={colorsFilter}
              onChange={setColorsFilter}
              options={colorOptions}
              variant="mobile"
              renderValue={renderColorOption}
              renderOption={renderColorOption}
            />
          </div>
        </div>
        {(() => {
          const mobileEndDate = sets?.find((s) => s.code === profile.setCode)?.endDate ?? null;
          return displayRows.map((e, i) => {
            const isFB = isFlashbackEvent(e.finishedAt, mobileEndDate);
            const prev = displayRows[i - 1];
            const next = displayRows[i + 1];
            const showBoundary = !isFB && !!prev && isFlashbackEvent(prev.finishedAt, mobileEndDate);
            const hideBottomBorder =
              isFB && !!next && !isFlashbackEvent(next.finishedAt, mobileEndDate);
            return (
              <React.Fragment key={e.eventId}>
                {showBoundary && <FlashbackDivider variant="mobile" />}
                <EventLogRow event={e} variant="mobile" hideBottomBorder={hideBottomBorder} playerDisplayName={profile.displayName} onOpenTrophy={setShotTrophy} />
              </React.Fragment>
            );
          });
        })()}
        {displayRows.length === 0 && (
          <div className="p-6 text-center text-muted font-display tracking-[0.2em] text-[13px]">
            NO EVENTS MATCH FILTER
          </div>
        )}
        <GoToTopButton onClick={scrollToTop} compact />
      </section>
      )}

      <PointsBreakdown
        open={pointsModalOpen}
        onClose={() => setPointsModalOpen(false)}
        breakdown={popoverBreakdown}
        confidenceOverride={formatFilter !== "ALL" ? fullConfidence : undefined}
        events={events}
        anchorRef={pointsBtnRef}
      />
      {shotTrophy && (
        <TrophyDeckModal
          trophy={shotTrophy}
          trophies={profile.selfReportedEvents}
          displayName={profile.displayName}
          onSelect={setShotTrophy}
          onClose={() => setShotTrophy(null)}
        />
      )}
    </div>
  );
}

// ─── Mobile breakdown (tabbed) ─────────────────────────────────────────────

type BreakdownTab = "format" | "deckColors" | "manaPips" | "collection" | "games";

const BREAKDOWN_TAB_STORAGE_KEY = "player-breakdown-tab";

function isBreakdownTab(v: unknown): v is BreakdownTab {
  return v === "format" || v === "deckColors" || v === "manaPips" || v === "collection" || v === "games";
}

interface MobileTracker {
  slug: string;
  setCode: string;
  updatedAt: string | null;
  accounts: TrackerAccount[];
  accountId: number | null;
  onChangeAccount: (id: number) => void;
}

function MobileBreakdown({
  breakdown,
  events,
  selfReported,
  showPoints,
  lockedFormats,
  tracker,
}: {
  breakdown: PlayerFormatBreakdown[];
  events: PlayerDraftEvent[];
  selfReported: SelfReportedEvent[];
  showPoints: boolean;
  lockedFormats?: string[] | null;
  /** null on every profile but the tracker owner's own */
  tracker: MobileTracker | null;
}) {
  const [tab, setTab] = useState<BreakdownTab>(() => {
    if (typeof window === "undefined") return "deckColors";
    const stored = window.localStorage.getItem(BREAKDOWN_TAB_STORAGE_KEY);
    return isBreakdownTab(stored) ? stored : "deckColors";
  });
  useEffect(() => {
    window.localStorage.setItem(BREAKDOWN_TAB_STORAGE_KEY, tab);
  }, [tab]);
  const offered = (t: BreakdownTab) =>
    t === "format" ? showPoints : t === "collection" || t === "games" ? !!tracker : true;
  const activeTab = offered(tab) ? tab : "deckColors";
  const sectionRef = useRef<HTMLElement>(null);
  return (
    <section ref={sectionRef} className="border-b border-border">
      <div className="flex border-b border-border">
        {tracker && (
          <BreakdownTabButton active={activeTab === "collection"} onClick={() => setTab("collection")}>
            COLLECTION
          </BreakdownTabButton>
        )}
        {tracker && (
          <BreakdownTabButton active={activeTab === "games"} onClick={() => setTab("games")}>
            GAMES
          </BreakdownTabButton>
        )}
        {showPoints && (
          <BreakdownTabButton active={activeTab === "format"} onClick={() => setTab("format")}>
            {tracker ? "POINTS" : "POINTS BY FORMAT"}
          </BreakdownTabButton>
        )}
        <BreakdownTabButton active={activeTab === "deckColors"} onClick={() => setTab("deckColors")}>
          {tracker ? "DECKS" : "DECK COLORS"}
        </BreakdownTabButton>
        <BreakdownTabButton active={activeTab === "manaPips"} onClick={() => setTab("manaPips")}>
          {tracker ? "COLORS" : "COLORS PLAYED"}
        </BreakdownTabButton>
      </div>
      {activeTab === "collection" && tracker && <MobileCollectionTab tracker={tracker} />}
      {activeTab !== "collection" && activeTab !== "games" && (
        <div className="px-[18px] py-4">
          {activeTab === "format" && <MobileFormatTab breakdown={breakdown} lockedFormats={lockedFormats} />}
          {activeTab === "deckColors" && <MobileDeckColorsTab events={events} selfReported={selfReported} />}
          {activeTab === "manaPips" && <MobileManaPipsTab events={events} selfReported={selfReported} />}
        </div>
      )}
      {/* The collection tab is long enough on its own, so the log sits under every other tab */}
      {tracker && activeTab !== "collection" && (
        <div className="pt-2 border-t border-border">
          <DraftLog slug={tracker.slug} setCode={tracker.setCode} accountId={tracker.accountId}
                    updatedAt={tracker.updatedAt} />
          <GoToTopButton
            onClick={() => sectionRef.current?.scrollIntoView({ behavior: "smooth", block: "start" })}
            compact
          />
        </div>
      )}
    </section>
  );
}

// Carries the controls the desktop left column puts beside its tabs, where there is no room here
function MobileCollectionTab({ tracker }: { tracker: MobileTracker }) {
  const { slug, setCode, accounts, accountId, onChangeAccount } = tracker;
  return (
    <>
      <div className="flex items-center gap-2 px-4 pt-3">
        <AccountTabs accounts={accounts} active={accountId} onChange={onChangeAccount} />
        <RefreshButton setCode={setCode} className="ml-auto" />
      </div>
      <TrackerStatsBlock slug={slug} setCode={setCode} accountId={accountId} className="mx-4 mt-3" />
      <Collection slug={slug} setCode={setCode} accountId={accountId} />
    </>
  );
}

function BreakdownTabButton({
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
        "flex-1 py-2.5 px-1.5 bg-transparent cursor-pointer font-display text-[11px] tracking-[0.16em] transition-colors border-b-2 border-solid",
        active ? "text-text border-green" : "text-muted border-transparent",
      )}
      style={active ? { marginBottom: -1 } : undefined}
    >
      {children}
    </button>
  );
}

function MobileFormatTab({ breakdown, lockedFormats }: { breakdown: PlayerFormatBreakdown[]; lockedFormats?: string[] | null }) {
  const formatBreakdown = useMemo(
    () => [...breakdown].sort((a, b) => b.scoreContribution - a.scoreContribution),
    [breakdown],
  );
  const total = formatBreakdown.reduce((s, f) => s + f.scoreContribution, 0) || 1;
  const [hover, setHover] = useState<string | null>(null);
  const activeFmt = hover ?? lockedFormats ?? null;
  const isActiveFmt = (label: string) =>
    Array.isArray(activeFmt) ? activeFmt.includes(label) : activeFmt === label;
  return (
    <div className="flex items-center gap-3.5 min-h-[140px]">
      <DonutChart
        pieHole={0.5}
        entries={formatBreakdown.map((f) => ({
          key: f.formatLabel,
          value: f.scoreContribution / total,
          color: FMT_COLORS[f.formatLabel] ?? "#5c8aff",
        }))}
        radius={42}
        strokeWidth={14}
        size={108}
        activeKey={activeFmt}
        onHoverEntry={setHover}
      />
      <div className="flex-1 flex flex-col">
        {formatBreakdown.map((f, i) => (
          <div
            key={f.formatLabel}
            onMouseEnter={() => setHover(f.formatLabel)}
            onMouseLeave={() => setHover(null)}
            className={cn(
              "grid items-center py-[5px] gap-2 px-1.5 -mx-1.5 rounded transition-colors cursor-default",
              isActiveFmt(f.formatLabel) && "bg-surface2",
            )}
            style={{ gridTemplateColumns: "1fr 36px 56px 36px" }}
          >
            <span
              className="font-display text-[11px] tracking-[0.06em]"
              style={{ color: FMT_COLORS[f.formatLabel] ?? "#5c8aff" }}
            >
              {shortFormat(f.formatLabel)}
            </span>
            <TrophyCount
              count={f.trophies}
              size="sm"
              fixedDigits={2}
              className="text-muted justify-self-end"
            />
            <Record
              mono
              wins={f.wins}
              losses={f.losses}
              className="mono text-[13px] text-right text-muted"
            />
            <span
              className={cn(
                "font-display text-[13px] text-right",
                f.scoreContribution > 0 ? "text-green" : "text-muted",
              )}
            >
              {fmtPts(f.scoreContribution)}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}

function MobileDeckColorsTab({ events, selfReported }: { events: PlayerDraftEvent[]; selfReported: SelfReportedEvent[] }) {
  const { comboCount, comboTrophies } = aggregate(events, selfReported);
  const comboEntries = Object.entries(comboCount).sort((a, b) => b[1] - a[1]);
  const comboTotal = comboEntries.reduce((s, [, n]) => s + n, 0) || 1;
  const [hover, setHover] = useState<string | null>(null);
  const rowRefs = useRef<Record<string, HTMLDivElement | null>>({});
  useEffect(() => {
    if (hover) {
      rowRefs.current[hover]?.scrollIntoView({ block: "nearest", behavior: "smooth" });
    }
  }, [hover]);
  if (comboEntries.length === 0) {
    return <div className="font-display text-[13px] text-muted py-3 min-h-[140px]">NO EVENTS YET</div>;
  }
  return (
    <div className="flex items-center gap-3.5 min-h-[140px]">
      <DonutChart
        pieHole={0.5}
        entries={comboEntries.map(([k, v]) => ({
          key: k,
          value: v,
          colors: comboColors(k),
        }))}
        radius={42}
        strokeWidth={14}
        size={108}
        activeKey={hover}
        onHoverEntry={setHover}
      />
      <div
        className="flex-1 flex flex-col gap-1 max-h-[126px] overflow-y-auto overflow-x-hidden pr-2 [&::-webkit-scrollbar]:w-1 [&::-webkit-scrollbar-track]:bg-transparent [&::-webkit-scrollbar-thumb]:bg-border2 [&::-webkit-scrollbar-thumb]:rounded-full"
        style={{ scrollbarWidth: "thin", scrollbarColor: "#3b4458 transparent" }}
      >
        {comboEntries.map(([code, count]) => (
          <div
            key={code}
            ref={(el) => {
              rowRefs.current[code] = el;
            }}
            onMouseEnter={() => setHover(code)}
            onMouseLeave={() => setHover(null)}
            className={cn(
              "grid gap-2 items-center px-1.5 rounded transition-colors cursor-default min-h-[22px]",
              hover === code && "bg-surface2",
            )}
            style={{ gridTemplateColumns: "auto 1fr 38px 36px" }}
          >
            <Pips colors={code} size={11} />
            <span className="font-display text-[13px] tracking-[0.06em]">
              {colorsDisplayName(code)}
            </span>
            <TrophyCount
              count={comboTrophies[code] ?? 0}
              size="sm"
              fixedDigits={2}
              className="text-muted justify-self-end"
            />
            <span className="mono text-[13px] text-muted text-right">
              ×{count}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}

function MobileManaPipsTab({ events, selfReported }: { events: PlayerDraftEvent[]; selfReported: SelfReportedEvent[] }) {
  const { colorCount } = aggregate(events, selfReported);
  const colorTotal = Object.values(colorCount).reduce((a, b) => a + b, 0) || 1;
  const [hover, setHover] = useState<string | null>(null);
  return (
    <div className="flex flex-col gap-3.5">
      <div className="flex items-center gap-6 min-h-[140px]">
        <DonutChart
          pieHole={0.5}
          entries={Object.entries(colorCount)
            .filter(([, v]) => v > 0)
            .map(([k, v]) => ({ key: k, value: v, color: COLOR_STROKES[k] }))}
          radius={42}
          strokeWidth={14}
          size={108}
          activeKey={hover}
          onHoverEntry={setHover}
        />
        <div className="flex-1 flex flex-col gap-1 pr-4">
          {COLOR_KEYS.map((c) => {
            const pct = (colorCount[c] / colorTotal) * 100;
            return (
              <div
                key={c}
                onMouseEnter={() => setHover(c)}
                onMouseLeave={() => setHover(null)}
                className={cn(
                  "grid gap-2 items-center px-1.5 -mx-1.5 rounded transition-colors cursor-default min-h-[22px]",
                  hover === c && "bg-surface2",
                )}
                style={{ gridTemplateColumns: "auto 1fr 40px" }}
              >
                <Pip c={c} size={11} />
                <span className="font-display text-[13px] tracking-[0.06em]">
                  {COLOR_NAMES[c]}
                </span>
                <span className="mono text-[13px] text-muted text-right">
                  {pct.toFixed(0)}%
                </span>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}

// ─── Helpers ───────────────────────────────────────────────────────────────

function BackButton({
  onClick,
  compact = false,
  inline = false,
}: {
  onClick: () => void;
  compact?: boolean;
  /** When true, drop the bottom margin so the button can sit in a flex row alongside other controls. */
  inline?: boolean;
}) {
  return (
    <button
      onClick={onClick}
      className={cn(
        "bg-transparent border-none text-muted font-display leading-none cursor-pointer flex items-center transition-colors hover:text-text",
        compact ? "text-[13px] tracking-[0.15em] gap-1.5" : "text-[14px] tracking-[0.18em] gap-1.5",
        !compact && !inline && "mb-3.5",
      )}
    >
      <ChevronLeft size={compact ? 14 : 16} className="shrink-0" /> {compact ? "BACK" : "BACK TO LEADERBOARD"}
    </button>
  );
}

function SiblingNavButtons({
  sibling,
  qs = "",
  compact = false,
}: {
  sibling: SiblingNav;
  qs?: string;
  compact?: boolean;
}) {
  const baseCls = cn(
    "bg-transparent border-none font-display tracking-[0.15em] leading-none flex items-center gap-1.5 transition-colors",
    compact ? "text-[13px]" : "text-[14px]",
    "cursor-pointer hover:text-text no-underline text-muted",
  );
  const disabledCls = "opacity-30 cursor-default pointer-events-none text-muted";
  const toFor = (s: string | null) =>
    s ? { pathname: playerPath(s, sibling.setCode), search: qs } : null;
  const prevTo = toFor(sibling.prevSlug);
  const nextTo = toFor(sibling.nextSlug);
  return (
    <div
      data-popover-keep-open
      className={cn("flex items-center", compact ? "gap-3" : "gap-5")}
    >
      {prevTo ? (
        <Link to={prevTo} className={baseCls} aria-label="Previous player">
          <ChevronLeft size={16} className="shrink-0" /> PREV
        </Link>
      ) : (
        <span className={cn(baseCls, disabledCls)} aria-disabled="true">
          <ChevronLeft size={16} className="shrink-0" /> PREV
        </span>
      )}
      {nextTo ? (
        <Link to={nextTo} className={baseCls} aria-label="Next player">
          NEXT <ChevronRight size={16} className="shrink-0" />
        </Link>
      ) : (
        <span className={cn(baseCls, disabledCls)} aria-disabled="true">
          NEXT <ChevronRight size={16} className="shrink-0" />
        </span>
      )}
    </div>
  );
}
