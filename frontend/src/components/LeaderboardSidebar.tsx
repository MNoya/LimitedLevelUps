import { useEffect, useRef, useState, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { BsAsterisk, BsPaletteFill, ChevronDown, ExternalLink } from "./Icons";
import { cn } from "../lib/utils";

import { Trophy } from "./Brand";
import { Pips } from "./ManaPips";
import { SectionLabel } from "./SectionLabel";
import { SurfaceCard } from "./SurfaceCard";
import { TrophyCount } from "./TrophyCount";
import { Record } from "./Record";

import { ArenaRankIcon } from "./ArenaRankIcon";
import { FilterDropdown, type FilterOption } from "./FilterDropdown";
import { useAllRecentTrophies, useColorsSummary, useFormatScopedTrophies, useRecentTrophies } from "../data/hooks";
import { boardOffersSoup } from "../data/cubeVariants";
import { lcqDraft2Earnings } from "../data/scoring";
import { formatsForBucket } from "../data/format-buckets";
import { colorsOf, isCubeCode, isSoup, mainColors, playerPath, profileSearch, relativeTime } from "../data/utils";
import { FMT_COLORS, FMT_DEFAULT_COLOR, shortFormat } from "../data/format-display";
import { colorsDisplayName, MULTI, OTHER } from "../data/filters";
import type { ColorsSummary, RecentTrophy } from "../types/leaderboard";

interface InsightsParams {
  setCode: string;
  playerSetCode?: string;
  colors?: string;
  format?: string;
  rank?: string;
  otherCombos?: string[];
  maxRecent?: number;
}

export function LeaderboardSidebar({
  setCode,
  playerSetCode,
  colors = "ALL",
  format = "ALL",
  otherCombos = [],
  onColorsSelect,
  searchParams,
  stats,
  updated,
  maxColors = 5,
  maxRecent = 10,
}: InsightsParams & {
  onColorsSelect?: (code: string) => void;
  searchParams?: URLSearchParams;
  stats?: { players: number; events: string };
  updated?: string | null;
  maxColors?: number;
}) {
  const [rank, setRank] = useState("ALL");
  const filterActive = format !== "ALL" || colors !== "ALL" || rank !== "ALL";
  const [recentLimit, setRecentLimit] = useState(maxRecent);
  const d = useInsightsData({ setCode, playerSetCode, colors, format, rank, otherCombos, maxRecent: recentLimit }, searchParams);
  const canShowMoreRecent = Boolean(d.recentScoped && d.recentScoped.length >= recentLimit);

  return (
    <aside className="flex flex-col gap-4">
      <SurfaceCard>
        <div className="mb-1 flex items-center gap-1.5">
          <Trophy size={16} color="#ffc63a" />
          <SectionLabel
            size={16}
            letterSpacing={d.lcqScope ? "0.14em" : undefined}
            className="text-subtle whitespace-nowrap"
          >
            {d.topColorsTitle}
          </SectionLabel>
          <FilterDropdown
            value={rank}
            onChange={setRank}
            options={RANK_OPTIONS}
            renderOption={renderRankOption}
            align="right"
            className="ml-auto shrink-0"
            renderTrigger={({ open, selected, toggle }) => (
              <button
                type="button"
                onClick={toggle}
                aria-expanded={open}
                className={cn(
                  "relative flex h-7 items-center justify-center border bg-transparent pl-2.5 pr-6 font-display tracking-[0.06em] text-[12px] leading-none cursor-pointer transition-colors",
                  open ? "border-green text-green" : "border-border2 text-text hover:border-green hover:text-green",
                )}
              >
                <span key={selected.value} className="animate-fadeIn flex items-center gap-1.5 whitespace-nowrap">
                  {selected.value !== "ALL" && (
                    <ArenaRankIcon
                      endRank={selected.value === "Mythic" ? "Mythic" : `${selected.value}-1`}
                      size={15}
                      title={selected.label}
                    />
                  )}
                  {selected.value === "ALL" ? "ALL RANKS" : selected.label}
                </span>
                <ChevronDown
                  size={14}
                  strokeWidth={2.5}
                  className={cn("absolute right-1 transition-transform", open && "rotate-180")}
                />
              </button>
            )}
          />
        </div>
        <TopColorsRows
          topColors={d.topColors}
          maxColors={maxColors}
          colors={colors}
          onColorsSelect={onColorsSelect}
          lcqScope={d.lcqScope}
        />
      </SurfaceCard>

      <SurfaceCard>
        <div className="mb-1 flex items-center gap-1.5">
          <Trophy size={16} color="#ffc63a" />
          <SectionLabel size={16} className="text-subtle">{d.recentTitle}</SectionLabel>
          {!filterActive && updated && (
            <span className="ml-auto mono text-[11px] text-muted whitespace-nowrap">UPDATED {updated}</span>
          )}
          {d.namedScope && (
            <span className="ml-auto inline-flex items-center">
              <Pips colors={colors} size={12} />
            </span>
          )}
          {colors === MULTI && <BsPaletteFill size={13} className="ml-auto" aria-hidden="true" />}
          {colors === OTHER && <BsAsterisk size={12} className="ml-auto" aria-hidden="true" />}
        </div>
        <RecentTrophyRows
          recentScoped={d.recentScoped}
          recentEmpty={d.recentEmpty}
          cube={d.cube}
          showRowPips={d.showRowPips}
          linkSetCode={d.linkSetCode}
          qs={d.qs}
        />
        {canShowMoreRecent && (
          <button
            type="button"
            onClick={() => setRecentLimit((n) => n + maxRecent)}
            className="-mb-3.5 mt-0.5 flex w-full items-center justify-center gap-1.5 border-t border-border bg-transparent py-2 font-display text-[12px] tracking-[0.18em] text-muted transition-colors hover:text-text"
          >
            SHOW MORE
            <ChevronDown size={15} strokeWidth={2.5} />
          </button>
        )}
      </SurfaceCard>
      {stats && (
        <div className="mono text-[11px] text-muted -mt-2 flex justify-between px-12">
          <span>{stats.players} PLAYERS</span>
          <span>{stats.events} EVENTS</span>
        </div>
      )}
    </aside>
  );
}

export function LeaderboardInsightsStrip({
  setCode,
  playerSetCode,
  colors = "ALL",
  format = "ALL",
  otherCombos = [],
  onColorsSelect,
  searchParams,
  maxColors = 12,
  maxRecent = 25,
}: InsightsParams & {
  onColorsSelect?: (code: string) => void;
  searchParams?: URLSearchParams;
  maxColors?: number;
}) {
  const d = useInsightsData({ setCode, playerSetCode, colors, format, otherCombos, maxRecent }, searchParams);
  const [open, setOpen] = useState<"colors" | "recent" | null>(null);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) {
      return;
    }
    const onClickOutside = (e: MouseEvent) => {
      if (!ref.current?.contains(e.target as Node)) setOpen(null);
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(null);
    };
    document.addEventListener("mousedown", onClickOutside);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onClickOutside);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  return (
    <div ref={ref} className="relative border-b border-border bg-bg">
      <div className="grid grid-cols-2">
        <StripToggle open={open === "colors"} onClick={() => setOpen((o) => (o === "colors" ? null : "colors"))}>
          TOP COLORS
        </StripToggle>
        <StripToggle
          open={open === "recent"}
          onClick={() => setOpen((o) => (o === "recent" ? null : "recent"))}
          className="border-l border-border"
        >
          <Trophy size={13} color="#ffc63a" />
          RECENT
        </StripToggle>
      </div>
      {open && (
        <div className="menu-scrollbar absolute inset-x-0 top-full z-20 max-h-[min(62vh,460px)] overflow-y-auto border-b border-border bg-surface px-3 py-1.5 shadow-lg">
          {open === "colors" ? (
            <TopColorsRows
              topColors={d.topColors}
              maxColors={maxColors}
              colors={colors}
              onColorsSelect={
                onColorsSelect && ((code) => {
                  onColorsSelect(code);
                  setOpen(null);
                })
              }
              lcqScope={d.lcqScope}
            />
          ) : (
            <RecentTrophyRows
              recentScoped={d.recentScoped}
              recentEmpty={d.recentEmpty}
              cube={d.cube}
              showRowPips={d.showRowPips}
              linkSetCode={d.linkSetCode}
              qs={d.qs}
            />
          )}
        </div>
      )}
    </div>
  );
}

function StripToggle({
  open,
  onClick,
  className,
  children,
}: {
  open: boolean;
  onClick: () => void;
  className?: string;
  children: ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-expanded={open}
      className={cn(
        "flex items-center justify-center gap-1.5 py-2 bg-transparent font-display text-[12px] tracking-[0.2em] text-subtle transition-colors hover:bg-surface",
        open && "bg-surface text-text",
        className,
      )}
    >
      {children}
      <ChevronDown size={15} strokeWidth={2.5} className={cn("text-muted transition-transform", open && "rotate-180")} />
    </button>
  );
}

function TopColorsRows({
  topColors,
  maxColors,
  colors,
  onColorsSelect,
  lcqScope,
}: {
  topColors: ColorsSummary[] | undefined;
  maxColors: number;
  colors: string;
  onColorsSelect?: (code: string) => void;
  lcqScope: boolean;
}) {
  const [limit, setLimit] = useState(maxColors);
  if (!topColors) {
    return <div className="mono text-[11px] text-muted py-2">LOADING…</div>;
  }
  if (topColors.length === 0) {
    return <div className="mono text-[11px] text-muted py-2">NO TROPHIES YET</div>;
  }
  const canShowMore = topColors.length > limit;
  return (
    <>
      {topColors.slice(0, limit).map((row, i) => {
        const isActive = row.colors === colors;
        const cls =
          (lcqScope
            ? "grid grid-cols-[24px_28px_1fr_auto_auto] "
            : "grid grid-cols-[24px_28px_1fr_auto] ") +
          "gap-2 items-center py-2 -mx-1 px-1 text-left transition-colors " +
          (i ? "border-t border-border" : "") +
          (isActive ? " text-green" : "") +
          (onColorsSelect ? " cursor-pointer hover:bg-surface2" : "");
        const inner = (
          <>
            <span className="mono text-[11px] text-muted">{i + 1}</span>
            <span className="flex justify-center">
              {row.colors === MULTI ? (
                <BsPaletteFill size={18} className="shrink-0 block -my-1" aria-hidden="true" />
              ) : (
                <Pips colors={row.colors} size={12} />
              )}
            </span>
            <span className="font-display text-[14px] tracking-[0.05em] pl-1.5">
              {colorsDisplayName(row.colors)}
            </span>
            {lcqScope && (
              <span className="font-display text-[14px] tracking-[0.02em] tabular-nums text-right text-green mr-2">
                {row.earnings ? `$${row.earnings / 1000}K` : ""}
              </span>
            )}
            <TrophyCount count={row.trophies} size="compact" className="text-muted" />
          </>
        );
        return onColorsSelect ? (
          <button
            key={row.colors}
            type="button"
            onClick={() => onColorsSelect(isActive ? "ALL" : row.colors)}
            aria-pressed={isActive}
            className={cls + " bg-transparent border-0 w-full"}
          >
            {inner}
          </button>
        ) : (
          <div key={row.colors} className={cls}>
            {inner}
          </div>
        );
      })}
      {canShowMore && (
        <button
          type="button"
          onClick={() => setLimit((n) => n + maxColors)}
          className="-mb-3.5 mt-0.5 flex w-full items-center justify-center gap-1.5 border-t border-border bg-transparent py-2 font-display text-[12px] tracking-[0.18em] text-muted transition-colors hover:text-text"
        >
          SHOW MORE
          <ChevronDown size={15} strokeWidth={2.5} />
        </button>
      )}
    </>
  );
}

function RecentTrophyRows({
  recentScoped,
  recentEmpty,
  cube,
  showRowPips,
  linkSetCode,
  qs,
}: {
  recentScoped: RecentTrophy[] | undefined;
  recentEmpty: string;
  cube: boolean;
  showRowPips: boolean;
  linkSetCode: string;
  qs: string;
}) {
  if (!recentScoped) {
    return <div className="mono text-[11px] text-muted py-2">LOADING…</div>;
  }
  if (recentScoped.length === 0) {
    return <div className="mono text-[11px] text-muted py-2">{recentEmpty}</div>;
  }
  return (
    <>
      {recentScoped.map((t, i) => {
        const isExternal = Boolean(t.seventeenlandsEventId);
        const cls =
          "group grid gap-2 items-center py-[7px] no-underline text-inherit transition-colors hover:bg-surface2 -mx-1 px-1 animate-fadeUpIn " +
          (showRowPips ? "grid-cols-[auto_1fr_28px_96px] " : "grid-cols-[1fr_28px_96px] ") +
          (i ? "border-t border-border" : "");
        const inner = (
          <>
            {showRowPips &&
              (isSoup(t.colors, cube) ? (
                <span className="inline-flex items-center gap-px shrink-0">
                  <Pips colors={mainColors(t.colors).slice(0, 3)} size={10} />
                  <BsPaletteFill size={12} aria-hidden="true" />
                </span>
              ) : (
                <Pips colors={t.colors} size={10} />
              ))}
            <span className="font-display text-[15px] leading-none tracking-[0.04em] whitespace-nowrap overflow-hidden text-ellipsis min-w-0">
              {t.displayName.toUpperCase()}
            </span>
            <Record
              wins={t.wins}
              losses={t.losses}
              mono
              color={lcqCashForRow(t) > 0 ? "#2ee85c" : undefined}
              className="mono text-[13px] text-subtle text-right"
            />
            <span className="grid grid-cols-[1fr_auto] items-center gap-1 mono text-dim">
              <span
                className="text-[11px] text-text justify-self-center text-center leading-[1.15]"
                style={LCQ_DRAFT_2_FORMATS.includes(t.format) ? { color: FMT_COLORS.LCQ } : undefined}
              >
                {shortFormat(t.format)}
              </span>
              <span className="flex items-center gap-1">
                <span className="text-[11px] tabular-nums transition-colors group-hover:text-text">
                  {relativeTime(t.finishedAt)}
                </span>
                {isExternal && (
                  <ExternalLink size={13} className="transition-colors group-hover:text-text" aria-hidden="true" />
                )}
              </span>
            </span>
          </>
        );
        const key = `${t.slug}-${t.finishedAt}`;
        return isExternal ? (
          <a
            key={key}
            href={`https://www.17lands.com/deck/${t.seventeenlandsEventId}`}
            target="_blank"
            rel="noopener noreferrer"
            className={cls}
          >
            {inner}
          </a>
        ) : (
          <Link key={key} to={{ pathname: playerPath(t.slug, linkSetCode), search: qs }} className={cls}>
            {inner}
          </Link>
        );
      })}
    </>
  );
}

const RECENT_POOL = 100;

function useInsightsData(
  { setCode, playerSetCode, colors = "ALL", format = "ALL", rank = "ALL", otherCombos = [], maxRecent = 10 }: InsightsParams,
  searchParams?: URLSearchParams,
) {
  const linkSetCode = playerSetCode ?? setCode;
  const cube = isCubeCode(setCode);
  const qs = profileSearch(searchParams);
  const colorsScoped = colors !== "ALL";
  const formatScoped = !colorsScoped && format !== "ALL";
  const rankScoped = rank !== "ALL";

  const { data: topColorsAll } = useColorsSummary(formatScoped || rankScoped ? undefined : setCode);
  const { data: formatTrophies } = useFormatScopedTrophies(
    formatScoped ? setCode : undefined,
    formatScoped ? format : undefined,
  );
  const { data: allTrophies } = useAllRecentTrophies(rankScoped && !formatScoped ? setCode : undefined);
  const { data: recentAll } = useRecentTrophies(formatScoped || rankScoped ? undefined : setCode, RECENT_POOL);

  const trophyPool = formatScoped ? formatTrophies : rankScoped ? allTrophies : recentAll;
  const rankFiltered = rankScoped
    ? trophyPool?.filter((t) => rankTierOf(t.endRank) === rank)
    : trophyPool;

  // A board that offers no Soup chip does not rank Soup either — it would top the list and say nothing
  const ranksSoup = boardOffersSoup(setCode);
  const topColors: ColorsSummary[] | undefined = formatScoped || rankScoped
    ? rankFiltered && topColorsFromTrophies(setCode, rankFiltered)
    : topColorsAll?.filter((r) => r.trophies > 0 && (ranksSoup || r.colors !== MULTI));

  const recentSource: RecentTrophy[] | undefined = rankFiltered;
  const recentScoped = !colorsScoped
    ? recentSource
      ? recentSource.slice(0, maxRecent)
      : undefined
    : (recentSource ?? [])
        .filter((t) => {
          if (colors === MULTI) return isSoup(t.colors, cube);
          if (colors === OTHER) return otherCombos.includes(colorsOf(t.colors));
          return colorsOf(t.colors) === colors;
        })
        .slice(0, maxRecent);

  const scopeLabel = colorsScoped ? colorsDisplayName(colors) : formatScoped ? shortFormat(format) : "";
  const scoped = colorsScoped || formatScoped;
  const formatColor = formatScoped ? (FMT_COLORS[format] ?? FMT_DEFAULT_COLOR) : null;
  const scopeChip = colorsScoped ? (
    <span className="text-green">{scopeLabel}</span>
  ) : formatScoped ? (
    <span style={{ color: formatColor! }}>{scopeLabel}</span>
  ) : null;
  const lcqScope = formatScoped && format === "LCQ";
  const recentNoun = lcqScope ? "TROPHIES & DAY 2" : "TROPHIES";
  const recentTitle = scoped ? <>RECENT {scopeChip} {recentNoun}</> : "RECENT TROPHIES";
  const recentEmpty = scoped || rankScoped
    ? ["NO RECENT", rankScoped ? rank.toUpperCase() : "", scopeLabel, recentNoun].filter(Boolean).join(" ")
    : "NO TROPHIES YET";
  const topColorsTitle = formatScoped ? (
    <>TOP COLORS {scopeChip} {lcqScope ? "TROPHIES & CASH" : "TROPHIES"}</>
  ) : (
    "TOP COLORS"
  );
  const namedScope = colorsScoped && colors !== MULTI && colors !== OTHER;
  const showRowPips = !namedScope;

  return {
    topColors,
    recentScoped,
    cube,
    qs,
    linkSetCode,
    lcqScope,
    namedScope,
    showRowPips,
    scopeChip,
    recentTitle,
    recentEmpty,
    topColorsTitle,
  };
}

function topColorsFromTrophies(setCode: string, trophies: RecentTrophy[]): ColorsSummary[] {
  const cube = isCubeCode(setCode);
  const counts = new Map<string, { trophies: number; earnings: number; players: Set<string> }>();
  for (const t of trophies) {
    const isTrophy = t.isTrophy !== false;
    const cash = lcqCashForRow(t);
    if (!isTrophy && cash === 0) continue;
    const keys: string[] = [];
    const main = colorsOf(t.colors);
    if (main) keys.push(main);
    if (isSoup(t.colors, cube)) keys.push(MULTI);
    for (const key of keys) {
      const cur = counts.get(key) ?? { trophies: 0, earnings: 0, players: new Set<string>() };
      if (isTrophy) cur.trophies += 1;
      cur.earnings += cash;
      cur.players.add(t.slug);
      counts.set(key, cur);
    }
  }
  return [...counts.entries()]
    .map(([colors, v]) => ({
      setCode,
      colors,
      trophies: v.trophies,
      events: v.trophies,
      players: v.players.size,
      earnings: v.earnings,
    }))
    .sort((a, b) => b.trophies - a.trophies || b.earnings - a.earnings);
}

const LCQ_DRAFT_2_FORMATS = formatsForBucket("LCQ Draft 2");

function lcqCashForRow(t: RecentTrophy): number {
  return LCQ_DRAFT_2_FORMATS.includes(t.format) ? lcqDraft2Earnings(t.wins) : 0;
}

const RANK_OPTIONS: FilterOption[] = [
  { value: "ALL", label: "ALL RANKS" },
  ...["Mythic", "Diamond", "Platinum", "Gold", "Silver", "Bronze"].map((tier) => ({
    value: tier,
    label: tier.toUpperCase(),
  })),
];

const renderRankOption = (opt: FilterOption) =>
  opt.value === "ALL" ? (
    <span>{opt.label}</span>
  ) : (
    <span className="flex items-center gap-2">
      <ArenaRankIcon endRank={opt.value === "Mythic" ? "Mythic" : `${opt.value}-1`} size={16} />
      <span>{opt.label}</span>
    </span>
  );

function rankTierOf(endRank: string | null | undefined): string | undefined {
  return endRank?.split("-")[0];
}
