import { Link } from "react-router-dom";
import type { Episode } from "../data/episodes";
import type { TranscriptStatus } from "../data/transcriptStatus";
import { CategoryTag } from "./CategoryTag";
import { SetGlyph } from "./Brand";
import { TranscriptStatusBadge } from "./TranscriptStatusBadge";
import { SortHeaderButton, type SortDir } from "./SortHeader";
import { Tooltip } from "./Tooltip";
import { cn } from "../lib/utils";

export type TranscriptSortKey = "title" | "set" | "category" | "date" | "words" | "status" | "structure";
export type TranscriptSort = { key: TranscriptSortKey; dir: SortDir };

const GRID_COLS_ADMIN =
  "grid-cols-[80px_1fr] sm:grid-cols-[80px_1fr_96px_96px_96px_80px] " +
  "md:grid-cols-[80px_1fr_56px_144px_96px_96px_96px_80px]";
const GRID_COLS_PLAIN =
  "grid-cols-[80px_1fr] sm:grid-cols-[80px_1fr_96px_80px] " +
  "md:grid-cols-[80px_1fr_56px_144px_96px_80px]";
const transcriptGridCols = (showStatus: boolean) => (showStatus ? GRID_COLS_ADMIN : GRID_COLS_PLAIN);

export function TranscriptRowHeader({
  sort,
  onSort,
  showStatus = false,
}: {
  sort: TranscriptSort;
  onSort: (key: TranscriptSortKey) => void;
  showStatus?: boolean;
}) {
  const header = (key: TranscriptSortKey, label: string, align: "left" | "center" | "right") => (
    <SortHeaderButton
      label={label}
      align={align}
      fill
      active={sort.key === key}
      dir={sort.dir}
      onClick={() => onSort(key)}
    />
  );
  return (
    <div
      className={cn(
        "hidden items-center gap-x-3 border-b border-border pt-3 pb-2.5 font-display text-[11px] tracking-[0.2em] text-muted sm:grid",
        transcriptGridCols(showStatus),
      )}
    >
      <span />
      <div className="min-w-0">{header("title", "EPISODE", "left")}</div>
      <div className="hidden md:block">{header("set", "SET", "center")}</div>
      <div className="hidden md:block">{header("category", "CATEGORY", "left")}</div>
      {showStatus ? <div>{header("status", "STATUS", "left")}</div> : null}
      {showStatus ? <div>{header("structure", "SECTIONS", "center")}</div> : null}
      <div>{header("date", "DATE", "left")}</div>
      <div>{header("words", "WORDS", "center")}</div>
    </div>
  );
}

export function TranscriptListSkeleton({ showStatus = false, rows = 8 }: { showStatus?: boolean; rows?: number }) {
  return (
    <div>
      <TranscriptRowHeader sort={{ key: "date", dir: "desc" }} onSort={() => {}} showStatus={showStatus} />
      <div className="divide-y divide-border">
        {Array.from({ length: rows }).map((_, i) => (
          <TranscriptRowSkeleton key={i} showStatus={showStatus} widthSeed={i} />
        ))}
      </div>
    </div>
  );
}

function TranscriptRowSkeleton({ showStatus, widthSeed }: { showStatus: boolean; widthSeed: number }) {
  const titleWidth = `${72 - (widthSeed % 4) * 11}%`;
  return (
    <div className={cn("grid items-center gap-x-3 py-2.5", transcriptGridCols(showStatus))}>
      <div className="aspect-video animate-pulse rounded bg-surface" />
      <div className="min-w-0">
        <div className="h-3.5 animate-pulse rounded bg-surface" style={{ width: titleWidth }} />
      </div>
      <div className="hidden justify-center md:flex">
        <div className="h-5 w-5 animate-pulse rounded-full bg-surface" />
      </div>
      <div className="hidden md:block">
        <div className="h-5 w-20 animate-pulse rounded bg-surface" />
      </div>
      {showStatus ? (
        <div className="hidden sm:block">
          <div className="h-3 w-14 animate-pulse rounded bg-surface" />
        </div>
      ) : null}
      {showStatus ? (
        <div className="hidden sm:block">
          <div className="mx-auto h-3 w-10 animate-pulse rounded bg-surface" />
        </div>
      ) : null}
      <div className="hidden sm:block">
        <div className="h-3 w-16 animate-pulse rounded bg-surface" />
      </div>
      <div className="hidden sm:block">
        <div className="mx-auto h-3 w-10 animate-pulse rounded bg-surface" />
      </div>
    </div>
  );
}

export function TranscriptRow({
  episode,
  detailBase,
  status,
  showStatus = false,
}: {
  episode: Episode;
  detailBase: string;
  status?: TranscriptStatus;
  showStatus?: boolean;
}) {
  const href = (status || showStatus) && episode.slug ? `${detailBase}/${episode.slug}` : null;
  const pending = !status;
  const words = status?.wordCount ? status.wordCount.toLocaleString() : "—";
  const date = episode.publishedLabel.toUpperCase();

  const body = (
    <div className={cn("group grid items-center gap-x-3 py-2.5", transcriptGridCols(showStatus))}>
      <div className="relative aspect-video overflow-hidden rounded bg-black/30">
        {episode.image ? (
          <img src={episode.image} alt="" loading="lazy" className="h-full w-full object-cover" />
        ) : null}
      </div>
      <div className="min-w-0">
        <span
          className={cn(
            "block font-body text-[14px] font-medium leading-snug line-clamp-1 transition-colors",
            pending ? "text-muted" : "text-text group-hover:text-green",
          )}
        >
          {episode.title}
        </span>
        <div className="mt-1 flex flex-wrap items-center gap-x-2.5 gap-y-1 font-num text-[11px] tracking-[0.04em] text-muted sm:hidden">
          {episode.setCode ? <SetGlyph code={episode.setCode} size={15} /> : null}
          <CategoryTag category={episode.category} className="!px-1.5 !py-0.5 !text-[10px]" />
          <span>{date}</span>
          <span>{words} words</span>
          {showStatus ? <TranscriptStatusBadge status={status} /> : null}
        </div>
      </div>
      <div className="hidden justify-center md:flex">
        {episode.setCode ? <SetGlyph code={episode.setCode} size={22} /> : null}
      </div>
      <div className="hidden md:block">
        <CategoryTag category={episode.category} />
      </div>
      {showStatus ? (
        <span className="hidden sm:block">
          <TranscriptStatusBadge status={status} />
        </span>
      ) : null}
      {showStatus ? (
        <span
          className={cn(
            "hidden text-center font-num text-[12px] tabular-nums sm:block",
            status && status.sections === 0 && status.subsections === 0 ? "text-red" : "text-muted",
          )}
        >
          {status ? `${status.sections} / ${status.subsections}` : "—"}
        </span>
      ) : null}
      <span className="hidden font-num text-[11px] tracking-[0.06em] text-muted sm:block">{date}</span>
      <span className="hidden text-center font-num text-[12px] tabular-nums text-muted sm:block">{words}</span>
    </div>
  );

  if (href) {
    return (
      <Link to={href} className="block no-underline">
        {body}
      </Link>
    );
  }
  return (
    <Tooltip label="Transcript Pending" side="top">
      <div>{body}</div>
    </Tooltip>
  );
}
