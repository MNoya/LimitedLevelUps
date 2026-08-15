import React, { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { ChevronDown, ChevronUp } from "lucide-react";
import { AAvatar, Trophy, fmtPts } from "./Brand";
import { Record } from "./Record";
import { ErrorState } from "./ErrorState";
import { ScoringInfoButton } from "./ScoringInfoButton";
import { winPct } from "../data/utils";
import { cn } from "../lib/utils";

// Shared table powering the set leaderboard and the per-archetype board, on
// both desktop and mobile. Owns the expanded-row state internally; expanded
// content is rendered by the caller.

export interface LeaderboardTableRow {
  setCode: string;
  slug: string;
  displayName: string;
  avatarUrl: string | null;
  rank: number;
  score?: number;
  trophies: number;
  events: number;
  wins: number;
  losses: number;
  lastCalculatedAt: string;
  boxes?: number;
  earnings?: number;
}

// points = standard score board; lcq adds a $ column; pod swaps score for
// events+record (PodDraftsPage); direct swaps score for boxes won. The main
// leaderboard's Pod filter keeps the points layout — its score is pod points.
export type BoardMode = "points" | "lcq" | "pod" | "direct";

export function boardModeFor(format: string): BoardMode {
  if (format === "Direct") return "direct";
  if (format === "LCQ") return "lcq";
  return "points";
}

export type SortKey = "score" | "trophies" | "events" | "record" | "winPct" | "earnings" | "boxes";
export type SortDir = "asc" | "desc";
export interface SortState {
  key: SortKey;
  dir: SortDir;
}

export const DEFAULT_SORT: SortState = { key: "score", dir: "desc" };
export const DEFAULT_SORT_NOSCORE: SortState = { key: "trophies", dir: "desc" };
export const DEFAULT_SORT_DIRECT: SortState = { key: "boxes", dir: "desc" };

export function defaultSortFor(mode: BoardMode): SortState {
  if (mode === "direct") return DEFAULT_SORT_DIRECT;
  return DEFAULT_SORT;
}

const SORT_VALUE: Record<SortKey, (r: LeaderboardTableRow) => number> = {
  score: (r) => r.score ?? 0,
  trophies: (r) => r.trophies,
  events: (r) => r.events,
  record: (r) => r.wins,
  winPct: (r) => r.wins / Math.max(1, r.wins + r.losses),
  earnings: (r) => r.earnings ?? 0,
  boxes: (r) => r.boxes ?? 0,
};

export function sortRows<T extends LeaderboardTableRow>(
  rows: T[],
  { key, dir }: SortState,
): T[] {
  const get = SORT_VALUE[key];
  const sign = dir === "desc" ? -1 : 1;
  return [...rows].sort((a, b) => {
    const av = get(a);
    const bv = get(b);
    if (av !== bv) return sign * (av < bv ? -1 : 1);
    const as = a.score ?? 0;
    const bs = b.score ?? 0;
    if (as !== bs) return bs - as;
    if (as === 0 && a.trophies !== b.trophies) return b.trophies - a.trophies;
    return a.rank - b.rank;
  });
}

// A metric track holds a short number under a long heading, so its width is mostly padding. Both
// bounds are given so a narrow desktop spends that padding first and the name keeps its floor.
const NAME_COL = "minmax(175px, 1fr)";
const METRIC_COLS =
  "minmax(62px, 70px) minmax(44px, 100px) minmax(52px, 110px) minmax(44px, 90px) minmax(44px, 90px)";

const COLS_DESKTOP: Record<BoardMode, string> = {
  points: `44px ${NAME_COL} ${METRIC_COLS}`,
  lcq: `44px ${NAME_COL} 44px ${METRIC_COLS}`,
  pod: `44px ${NAME_COL} ${METRIC_COLS}`,
  direct: `44px ${NAME_COL} ${METRIC_COLS}`,
};
const COLS_MOBILE: Record<BoardMode, string> = {
  points: "20px 1fr 44px 50px",
  lcq: "20px 1fr 44px 40px 50px",
  pod: "20px 1fr 40px 44px 56px",
  direct: "20px 1fr 40px 56px 44px",
};

export function LeaderboardTable<T extends LeaderboardTableRow>({
  rows,
  variant,
  loading = false,
  error,
  emptyMessage,
  renderExpanded,
  /** When false, the caller renders LeaderboardColumnHeader separately (e.g. inside a
   *  page-level sticky chrome). Defaults to true so the table is self-contained. */
  showHeader = true,
  mode = "points",
  sort,
  onSort,
  playerHref,
  rowExpandable,
  onRowPrefetch,
  highlightSlug,
  stickyTop = 0,
}: {
  rows: T[] | undefined;
  variant: "desktop" | "mobile";
  loading?: boolean;
  error?: Error | null;
  emptyMessage?: React.ReactNode;
  renderExpanded?: (row: T) => React.ReactNode;
  showHeader?: boolean;
  mode?: BoardMode;
  sort?: SortState;
  onSort?: (key: SortKey) => void;
  playerHref?: (row: T) => string | null;
  /** When it returns false, the row links to the player instead of expanding (nothing to show). */
  rowExpandable?: (row: T) => boolean;
  /** Fired on row hover/focus to warm that player's cache on intent. */
  onRowPrefetch?: (row: T) => void;
  /** Slug of the signed-in viewer's own row, rendered with an accent highlight. */
  highlightSlug?: string;
  /** Viewport offset (px) below which the floating own-row pins — clears a sticky page header. */
  stickyTop?: number;
}) {
  const [openSlug, setOpenSlug] = useState<string | null>(null);
  const [renderedSlug, setRenderedSlug] = useState<string | null>(null);
  useEffect(() => {
    if (openSlug) {
      setRenderedSlug(openSlug);
      return;
    }
    if (renderedSlug == null) return;
    const t = setTimeout(() => setRenderedSlug(null), 220);
    return () => clearTimeout(t);
  }, [openSlug, renderedSlug]);
  const isMobile = variant === "mobile";

  const [myRowEl, setMyRowEl] = useState<HTMLDivElement | null>(null);
  const [myRowVisible, setMyRowVisible] = useState(true);
  useEffect(() => {
    if (!myRowEl) {
      setMyRowVisible(true);
      return;
    }
    const observer = new IntersectionObserver(
      ([entry]) => setMyRowVisible(entry.isIntersecting),
      { rootMargin: `${-stickyTop}px 0px 0px 0px`, threshold: 0 },
    );
    observer.observe(myRowEl);
    return () => observer.disconnect();
  }, [myRowEl, stickyTop]);

  if (error) return <ErrorState error={error} compact={isMobile} />;
  if (loading) return <LoadingRows variant={variant} />;
  if (!rows || rows.length === 0) return <EmptyState>{emptyMessage}</EmptyState>;

  return (
    <div>
      {showHeader && (
        <LeaderboardColumnHeader variant={variant} mode={mode} sort={sort} onSort={onSort} />
      )}
      <div className={cn("flex flex-col", isMobile ? "gap-0" : "gap-[1px]")}>
        <FloatingOwnRow
          row={highlightSlug ? rows.find((r) => r.slug === highlightSlug) : undefined}
          mode={mode}
          variant={variant}
          stickyTop={stickyTop}
          hidden={myRowVisible}
          onScrollToRow={() => myRowEl?.scrollIntoView({ behavior: "smooth", block: "center" })}
        />
        {rows.map((r) => {
          const open = openSlug === r.slug;
          const expandable = !!renderExpanded && (rowExpandable?.(r) ?? true);
          const href = playerHref?.(r) ?? null;
          const mine = !!highlightSlug && r.slug === highlightSlug;
          return (
            <div
              key={r.slug}
              ref={mine ? setMyRowEl : undefined}
              onMouseEnter={onRowPrefetch ? () => onRowPrefetch(r) : undefined}
              onFocus={onRowPrefetch ? () => onRowPrefetch(r) : undefined}
              className={cn(
                "transition-colors",
                isMobile && "border-b border-border",
                open ? "bg-surface2" : isMobile ? "bg-transparent" : "bg-surface",
                (expandable || href) && !isMobile && "hover:bg-surface2",
                mine && !open && "bg-green/[0.07]",
                mine && "shadow-[inset_3px_0_0_0_#2ee85c,inset_-3px_0_0_0_#2ee85c]",
              )}
            >
              {isMobile ? (
                <MobileRow
                  row={r}
                  mode={mode}
                  href={href}
                  onToggle={expandable ? () => setOpenSlug(open ? null : r.slug) : undefined}
                />
              ) : (
                <DesktopRow
                  row={r}
                  mode={mode}
                  href={href}
                  onToggle={expandable ? () => setOpenSlug(open ? null : r.slug) : undefined}
                />
              )}
              {renderExpanded && expandable && (
                <div
                  className={cn(
                    "grid transition-[grid-template-rows] duration-200 ease-out",
                    open ? "grid-rows-[1fr]" : "grid-rows-[0fr]",
                  )}
                  aria-hidden={!open}
                >
                  <div className="overflow-hidden">
                    {renderedSlug === r.slug && renderExpanded(r)}
                  </div>
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

// The signed-in viewer's own standing, pinned to the top of the table while their
// real row is scrolled out of view, so they never lose sight of their rank. Sticky
// within the rows column so it inherits the table width rather than the viewport's.
function FloatingOwnRow({
  row,
  mode,
  variant,
  stickyTop,
  hidden,
  onScrollToRow,
}: {
  row: LeaderboardTableRow | undefined;
  mode: BoardMode;
  variant: "desktop" | "mobile";
  stickyTop: number;
  hidden: boolean;
  onScrollToRow: () => void;
}) {
  if (!row || hidden) {
    return null;
  }
  return (
    <div
      className="sticky z-[5] border-b border-border bg-surface"
      style={{ top: stickyTop }}
    >
      <div
        onClick={onScrollToRow}
        className="cursor-pointer bg-green/[0.07] shadow-[inset_3px_0_0_0_#2ee85c,inset_-3px_0_0_0_#2ee85c]"
      >
        {variant === "mobile" ? (
          <MobileRow row={row} mode={mode} />
        ) : (
          <DesktopRow row={row} mode={mode} />
        )}
      </div>
    </div>
  );
}

// ─── Column header ─────────────────────────────────────────────────────────
// Exported so pages that want to put it inside their own sticky chrome (mobile
// leaderboard) can render it themselves and pass `showHeader={false}` to the table.

export function LeaderboardColumnHeader({
  variant,
  mode = "points",
  sort,
  onSort,
}: {
  variant: "desktop" | "mobile";
  mode?: BoardMode;
  sort?: SortState;
  onSort?: (key: SortKey) => void;
}) {
  if (variant === "mobile") {
    return (
      <div
        className="grid gap-3 py-1.5 pl-2 pr-3.5 font-display text-[10px] tracking-[0.2em] text-muted border-b border-border"
        style={{ gridTemplateColumns: COLS_MOBILE[mode] }}
      >
        <span className="text-center">#</span>
        <span>PLAYER</span>
        {mode === "lcq" && <SortHeader label="$" sortKey="earnings" sort={sort} onSort={onSort} />}
        <SortHeader label="TR" sortKey="trophies" sort={sort} onSort={onSort} />
        {(mode === "points" || mode === "lcq") && (
          <ScoringSortHeader label="PTS" sort={sort} onSort={onSort} />
        )}
        {mode === "pod" && (
          <>
            <SortHeader label="PODS" sortKey="events" sort={sort} onSort={onSort} />
            <SortHeader label="RECORD" sortKey="record" sort={sort} onSort={onSort} />
          </>
        )}
        {mode === "direct" && (
          <>
            <SortHeader label="RECORD" sortKey="record" sort={sort} onSort={onSort} />
            <SortHeader label="BOXES" sortKey="boxes" sort={sort} onSort={onSort} />
          </>
        )}
      </div>
    );
  }
  return (
    <div
      className="grid gap-x-3 py-2.5 pl-2 pr-5 mb-1 font-display text-[11px] tracking-[0.2em] text-muted"
      style={{ gridTemplateColumns: COLS_DESKTOP[mode] }}
    >
      <span className="text-center">RANK</span>
      <span>PLAYER</span>
      {mode === "lcq" && <SortHeader label="$" sortKey="earnings" sort={sort} onSort={onSort} />}
      <SortHeader label="TROPHIES" sortKey="trophies" sort={sort} onSort={onSort} />
      <SortHeader label="EVENTS" sortKey="events" sort={sort} onSort={onSort} />
      <SortHeader label="RECORD" sortKey="record" sort={sort} onSort={onSort} />
      <SortHeader label="WIN %" sortKey="winPct" sort={sort} onSort={onSort} />
      {(mode === "points" || mode === "lcq" || mode === "pod") && (
        <ScoringSortHeader label="POINTS" sort={sort} onSort={onSort} />
      )}
      {mode === "direct" && <SortHeader label="BOXES" sortKey="boxes" sort={sort} onSort={onSort} />}
    </div>
  );
}

function SortHeader({
  label,
  sortKey,
  sort,
  onSort,
  inline = false,
}: {
  label: string;
  sortKey: SortKey;
  sort?: SortState;
  onSort?: (key: SortKey) => void;
  inline?: boolean;
}) {
  if (!onSort) {
    return <span className="text-right">{label}</span>;
  }
  const active = sort?.key === sortKey;
  const Icon = active && sort?.dir === "asc" ? ChevronUp : ChevronDown;
  return (
    <button
      type="button"
      onClick={() => onSort(sortKey)}
      aria-label={`Sort by ${label}`}
      aria-sort={active ? (sort?.dir === "asc" ? "ascending" : "descending") : "none"}
      className={cn(
        "relative cursor-pointer transition-colors tracking-[inherit] text-[inherit] font-[inherit]",
        inline ? "inline-flex items-center" : "block w-full text-right",
        active ? "text-text" : "hover:text-text",
      )}
    >
      <span>{label}</span>
      <Icon
        size={11}
        strokeWidth={2.5}
        className={cn(
          "absolute left-full top-1/2 -translate-y-1/2 ml-0.5 shrink-0",
          active ? "opacity-100" : "opacity-30",
        )}
        aria-hidden="true"
      />
    </button>
  );
}

// The POINTS / PTS header with the scoring "(?)" affordance to the left of the
// sortable label, kept together at the column's right edge.
function ScoringSortHeader({
  label,
  sort,
  onSort,
}: {
  label: string;
  sort?: SortState;
  onSort?: (key: SortKey) => void;
}) {
  return (
    <div className="flex items-center justify-end gap-1.5">
      <ScoringInfoButton />
      <SortHeader label={label} sortKey="score" sort={sort} onSort={onSort} inline />
    </div>
  );
}

// ─── Row variants ──────────────────────────────────────────────────────────

const rankLabel = (rank: number): string => (rank > 0 ? String(rank) : "—");

const EmptyStat = () => <span className="mono text-right text-[13px] text-dim">—</span>;

function DesktopRow({
  row,
  mode,
  onToggle,
  href,
}: {
  row: LeaderboardTableRow;
  mode: BoardMode;
  onToggle?: () => void;
  href?: string | null;
}) {
  const cols = COLS_DESKTOP[mode];
  const rowLinked = !!href && !onToggle;
  const body = (
    <>
      <span className="mono text-[13px] text-muted text-center">{rankLabel(row.rank)}</span>
      <PlayerCell row={row} avatarSize={30} nameSize={18} linked={rowLinked} />
      {mode === "lcq" && <EarningsCell earnings={row.earnings ?? 0} />}
      <TrophyCell trophies={row.trophies} compact={false} large={mode === "pod"} />
      {row.events > 0 ? (
        <span className="mono text-right text-[13px] text-muted">{row.events}</span>
      ) : (
        <EmptyStat />
      )}
      {row.events > 0 ? (
        <Record className="mono text-right text-[13px]" wins={row.wins} losses={row.losses} />
      ) : (
        <EmptyStat />
      )}
      {row.events > 0 ? (
        <span className="mono text-right text-[13px] text-muted">{winPct(row.wins, row.losses)}%</span>
      ) : (
        <EmptyStat />
      )}
      {(mode === "points" || mode === "lcq" || mode === "pod") && (
        <ScoreCell score={row.score ?? 0} large unranked={row.rank === 0} />
      )}
      {mode === "direct" && <BoxesCell boxes={row.boxes ?? 0} large />}
    </>
  );
  if (rowLinked) {
    return (
      <Link
        to={href!}
        className="group/row grid items-center gap-x-3 py-2.5 pl-2 pr-5 cursor-pointer no-underline text-inherit"
        style={{ gridTemplateColumns: cols }}
      >
        {body}
      </Link>
    );
  }
  return (
    <div
      onClick={onToggle}
      className={cn(
        "grid items-center gap-x-3 py-2.5 pl-2 pr-5",
        onToggle && "cursor-pointer",
      )}
      style={{ gridTemplateColumns: cols }}
    >
      {body}
    </div>
  );
}

function MobileRow({
  row,
  mode,
  onToggle,
  href,
}: {
  row: LeaderboardTableRow;
  mode: BoardMode;
  onToggle?: () => void;
  href?: string | null;
}) {
  const cols = COLS_MOBILE[mode];
  const rowLinked = !!href && !onToggle;
  const body = (
    <>
      <span className="mono text-[12px] text-muted text-center">{rankLabel(row.rank)}</span>
      <PlayerCell row={row} avatarSize={26} nameSize={17} linked={rowLinked} />
      {mode === "lcq" && <EarningsCell earnings={row.earnings ?? 0} compact />}
      <TrophyCell trophies={row.trophies} compact large={mode === "pod"} />
      {(mode === "points" || mode === "lcq") &&
        (row.rank === 0 ? (
          <span className="mono text-right text-[13px] text-dim">—</span>
        ) : (
          <span className="font-display text-right text-[18px] tracking-[0.02em] tabular-nums leading-none">
            {fmtPts(row.score ?? 0)}
          </span>
        ))}
      {mode === "pod" && (
        <>
          <span className="mono text-right text-[13px] text-muted tabular-nums">{row.events}</span>
          <Record className="mono text-right text-[13px]" wins={row.wins} losses={row.losses} />
        </>
      )}
      {mode === "direct" && (
        <>
          <Record className="mono text-right text-[13px]" wins={row.wins} losses={row.losses} />
          <BoxesCell boxes={row.boxes ?? 0} />
        </>
      )}
    </>
  );
  if (rowLinked) {
    return (
      <Link
        to={href!}
        className="group/row py-[9px] pl-2 pr-3.5 grid gap-3 items-center cursor-pointer no-underline text-inherit"
        style={{ gridTemplateColumns: cols }}
      >
        {body}
      </Link>
    );
  }
  return (
    <div
      onClick={onToggle}
      className={cn(
        "py-[9px] pl-2 pr-3.5 grid gap-3 items-center",
        onToggle && "cursor-pointer",
      )}
      style={{ gridTemplateColumns: cols }}
    >
      {body}
    </div>
  );
}

// ─── Subcells ──────────────────────────────────────────────────────────────

function PlayerCell({
  row,
  avatarSize,
  nameSize,
  linked = false,
}: {
  row: LeaderboardTableRow;
  avatarSize: number;
  nameSize: number;
  linked?: boolean;
}) {
  return (
    <div className="flex items-center gap-2.5 min-w-0">
      <AAvatar displayName={row.displayName} avatarUrl={row.avatarUrl} size={avatarSize} />
      <div
        className={cn(
          "font-display leading-none tracking-[0.04em] whitespace-nowrap overflow-hidden text-ellipsis",
          linked && "transition-colors group-hover/row:text-green",
        )}
        style={{ fontSize: nameSize }}
      >
        {row.displayName.toUpperCase()}
      </div>
    </div>
  );
}

function TrophyCell({
  trophies,
  compact,
  large = false,
}: {
  trophies: number;
  compact: boolean;
  large?: boolean;
}) {
  const iconSize = compact ? 15 : 18;
  const textSize = compact
    ? large
      ? "text-[18px]"
      : "text-[15px]"
    : "text-[18px]";
  return (
    <div
      className={cn(
        "text-right flex items-center justify-end",
        compact ? "gap-1" : "gap-1.5",
      )}
    >
      {trophies > 0 ? (
        <>
          <Trophy size={iconSize} color="#ffc63a" />
          <span className={cn("font-display tracking-[0.02em] tabular-nums leading-none", textSize)}>
            {trophies}
          </span>
        </>
      ) : (
        <span className={cn("font-display text-dim tabular-nums leading-none", textSize)}>—</span>
      )}
    </div>
  );
}

function ScoreCell({ score, large, unranked }: { score: number; large?: boolean; unranked?: boolean }) {
  if (unranked) {
    return <span className="mono text-right text-[13px] text-dim">—</span>;
  }
  return (
    <div
      className={cn(
        "text-right font-display tracking-[0.02em] tabular-nums",
        large ? "text-[24px] leading-none" : "text-[18px] leading-none",
      )}
    >
      {fmtPts(score)}
    </div>
  );
}

function EarningsCell({ earnings, compact = false }: { earnings: number; compact?: boolean }) {
  if (earnings <= 0) {
    return <span className="mono text-right text-[13px] text-dim">—</span>;
  }
  return (
    <span
      className={cn(
        "text-right font-display tracking-[0.02em] tabular-nums leading-none text-green",
        compact ? "text-[16px]" : "text-[18px]",
      )}
    >
      ${earnings / 1000}K
    </span>
  );
}

function BoxesCell({ boxes, large = false }: { boxes: number; large?: boolean }) {
  return (
    <div className={cn("flex items-center justify-end", large ? "gap-1.5" : "gap-1")}>
      <span className={cn("leading-none", large ? "text-[15px]" : "text-[11px]")} aria-hidden="true">
        📦
      </span>
      <span
        className={cn(
          "font-display tracking-[0.02em] tabular-nums leading-none",
          large ? "text-[24px]" : "text-[18px]",
          boxes === 0 && "text-dim",
        )}
      >
        {boxes}
      </span>
    </div>
  );
}

// ─── States ────────────────────────────────────────────────────────────────

function LoadingRows({ variant }: { variant: "desktop" | "mobile" }) {
  return (
    <div className={variant === "mobile" ? "py-2 px-3.5" : "py-3 px-3.5"}>
      {[0, 1, 2, 3, 4].map((i) => (
        <div
          key={i}
          className="grid gap-2.5 py-2.5 border-b border-border items-center"
          style={{ gridTemplateColumns: "32px 1fr 60px" }}
        >
          <div className="h-8 bg-surface2" />
          <div
            className="h-3.5 bg-surface2 animate-pulse"
            style={{ width: `${50 + i * 8}%` }}
          />
          <div className="h-3.5 bg-surface2" />
        </div>
      ))}
    </div>
  );
}

function EmptyState({ children }: { children?: React.ReactNode }) {
  return (
    <div className="p-10 text-center">
      <div className="font-display text-[22px] tracking-[0.04em] text-text">NO EVENTS YET</div>
      <div className="mono text-[11px] text-muted mt-2">
        {children ?? "NO PLAYER DATA FOR THIS SET / FILTER YET. CHECK BACK SOON."}
      </div>
    </div>
  );
}
