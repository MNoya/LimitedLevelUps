import { Fragment, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { ChevronDown, ChevronRight, ChevronUp, RefreshCw } from "../Icons";
import { useQuery, useQueryClient } from "@tanstack/react-query";

import { cn } from "../../lib/utils";
import { useIsMobile } from "../../lib/use-is-mobile";
import { Pips } from "../ManaPips";
import { SectionLabel } from "../SectionLabel";
import { FilterDropdown } from "../FilterDropdown";
import { COLOR_OPTIONS_LONG, FORMAT_OPTIONS, matchesFormatFilter, type FilterOption } from "../../data/filters";
import { renderColorOption, renderFormatOption } from "../../data/format-display";
import { colorsOf, lastUpdated } from "../../data/utils";
import type { SortDir } from "../LeaderboardTable";
import { payoutFor } from "../../data/prizes";
import { prettyFormat } from "../../data/utils";
import { arenaDrafts } from "../../data/trackerDrafts";
import {
  fetchDraftNotes,
  fetchMatchNotes,
  fetchTrackerDrafts,
  refreshOneDraft,
  saveDraftNote,
  saveMatchNote,
  type DraftNote,
  type MatchNote,
} from "../../data/trackerApi";
import type { PlayerDraftEvent, TrackedMatch } from "../../types/leaderboard";
import { HEADER_CLS, TRACKER_HEADER_H } from "./trackerStyles";

// Mirrors the spreadsheet's own deck-log columns so the layout reads the way the tab did
const LOG_COLS_DESKTOP =
  "42px 76px 116px 96px 68px 52px 38px 38px 50px 42px minmax(0, 1fr) 30px";
const LOG_COLS_MOBILE = "26px minmax(0, 1.2fr) 42px minmax(0, 1.25fr) 24px";

const CELL_CLS = "flex items-center min-w-0 px-2 py-2.5";
const LOG_HEADER_CLS = "font-display text-[13px] tracking-[0.16em] text-muted";
const GROUP_END = "border-r border-border";
const GRID_CLS = "grid [&>*:last-child]:border-r-0";

/** "TradDraft" reads as "TRADITIONAL": the whole column is drafts, so the word carries nothing */
function formatLabel(format: string): string {
  return prettyFormat(format).replace(/\s*Draft$/i, "").toUpperCase();
}

// ─── Draft log ─────────────────────────────────────────────────────────────

type TrackerSortKey = "number" | "date" | "colors" | "record" | "rares" | "mythics";
type TrackerSort = { key: TrackerSortKey; dir: SortDir };

const SORT_STORAGE_KEY = "tracker-draft-sort";
const DEFAULT_SORT: TrackerSort = { key: "number", dir: "asc" };

function isSortKey(v: unknown): v is TrackerSortKey {
  return v === "number" || v === "date" || v === "colors" || v === "record" || v === "rares" || v === "mythics";
}

function storedSort(): TrackerSort {
  if (typeof window === "undefined") {
    return DEFAULT_SORT;
  }
  const [key, dir] = (window.localStorage.getItem(SORT_STORAGE_KEY) ?? "").split(":");
  if (!isSortKey(key) || (dir !== "asc" && dir !== "desc")) {
    return DEFAULT_SORT;
  }
  return { key, dir };
}

/** Keeps the date-order draft number attached, so sorting relabels no row */
interface NumberedDraft {
  event: PlayerDraftEvent;
  index: number;
}

function sortNumberedDrafts(
  drafts: NumberedDraft[],
  { key, dir }: TrackerSort,
  notesById: Map<string, DraftNote>,
): NumberedDraft[] {
  const sign = dir === "desc" ? -1 : 1;
  const rares = ({ event }: NumberedDraft) => notesById.get(event.eventId)?.rares ?? event.poolRares ?? 0;
  const mythics = ({ event }: NumberedDraft) => notesById.get(event.eventId)?.mythics ?? event.poolMythics ?? 0;

  return [...drafts].sort((a, b) => {
    if (key === "colors") {
      const diff = a.event.colors.localeCompare(b.event.colors);
      return diff !== 0 ? sign * diff : a.index - b.index;
    }

    let av: number;
    let bv: number;
    if (key === "number") {
      av = a.index;
      bv = b.index;
    } else if (key === "date") {
      av = a.event.finishedAt ? Date.parse(a.event.finishedAt) : 0;
      bv = b.event.finishedAt ? Date.parse(b.event.finishedAt) : 0;
    } else if (key === "record") {
      av = a.event.wins - a.event.losses;
      bv = b.event.wins - b.event.losses;
    } else if (key === "rares") {
      av = rares(a);
      bv = rares(b);
    } else {
      av = mythics(a);
      bv = mythics(b);
    }
    return av !== bv ? sign * (av < bv ? -1 : 1) : a.index - b.index;
  });
}

export function DraftLog({
  slug, setCode, accountId, updatedAt = null,
}: { slug: string | undefined; setCode: string; accountId: number | null; updatedAt?: string | null }) {
  const qc = useQueryClient();
  const isMobile = useIsMobile();
  const { data: events, isLoading } = useQuery({
    queryKey: ["tracker-drafts", slug, setCode],
    queryFn: () => fetchTrackerDrafts(slug!, setCode),
    enabled: !!slug,
  });
  const { data: draftNotes } = useQuery({ queryKey: ["tracker-draft-notes"], queryFn: fetchDraftNotes });
  const { data: matchNotes } = useQuery({ queryKey: ["tracker-match-notes"], queryFn: fetchMatchNotes });
  const [open, setOpen] = useState<string | null>(null);
  const [sort, setSort] = useState<TrackerSort>(storedSort);
  const [formatFilter, setFormatFilter] = useState("ALL");
  const [colorsFilter, setColorsFilter] = useState("ALL");

  const all = useMemo(() => arenaDrafts(events, accountId), [events, accountId]);
  const rows = useMemo(
    () => all.filter((e) =>
      matchesFormatFilter(e.format, formatFilter) &&
      (colorsFilter === "ALL" || colorsOf(e.colors) === colorsFilter)),
    [all, formatFilter, colorsFilter],
  );
  const colorOptions = useMemo<FilterOption[]>(() => {
    const present = [...new Set(all.map((e) => colorsOf(e.colors)).filter(Boolean))].sort();
    return [COLOR_OPTIONS_LONG[0], ...present.map((c) => ({ value: c, label: c }))];
  }, [all]);
  // FORMAT_OPTIONS covers the queues the public board scores; anything else drafted gets its own
  // entry here so no row in the log is unreachable by the filter
  const formatOptions = useMemo<FilterOption[]>(() => {
    const present = [...new Set(all.map((e) => e.format))];
    const known = FORMAT_OPTIONS.filter(
      (o) => o.value !== "ALL" && present.some((f) => matchesFormatFilter(f, o.value)),
    );
    const uncovered = present
      .filter((f) => !known.some((o) => matchesFormatFilter(f, o.value)))
      .map((f) => ({ value: f, label: formatLabel(f) }));
    return [{ value: "ALL", label: "ALL FORMATS" }, ...known, ...uncovered];
  }, [all]);

  const notesById = useMemo(() => {
    const m = new Map<string, DraftNote>();
    for (const n of draftNotes ?? []) m.set(n.draftEventId, n);
    return m;
  }, [draftNotes]);

  const numbered = useMemo(() => {
    const time = (e: PlayerDraftEvent) => (e.finishedAt ? Date.parse(e.finishedAt) : 0);
    const byDateAsc = [...rows].sort((a, b) => time(a) - time(b));
    const rank = new Map(byDateAsc.map((e, i) => [e.eventId, i + 1]));
    return rows.map((event) => ({ event, index: rank.get(event.eventId) ?? 0 }));
  }, [rows]);
  const ordered = useMemo(() => sortNumberedDrafts(numbered, sort, notesById), [numbered, sort, notesById]);
  const toggleSort = (key: TrackerSortKey) =>
    setSort((s) => ({ key, dir: s.key === key && s.dir === "asc" ? "desc" : "asc" }));
  useEffect(() => {
    window.localStorage.setItem(SORT_STORAGE_KEY, `${sort.key}:${sort.dir}`);
  }, [sort]);

  if (isLoading) return <div className="px-5 md:px-10 py-8 text-muted text-[14px]">Loading drafts</div>;
  if (!rows.length) return <div className="px-5 md:px-10 py-8 text-muted text-[14px]">No drafts recorded for {setCode}</div>;

  return (
    <div>
      {isMobile && (
        <div className="px-[18px]">
          <div className="flex items-center justify-between gap-2 mb-2.5">
            <div className="flex items-baseline gap-2">
              <SectionLabel size={12}>DRAFTS</SectionLabel>
              <span className="font-display text-[11px] tracking-[0.12em] text-dim">{rows.length} EVENTS</span>
            </div>
            {updatedAt && (
              <span className="font-display text-[11px] tracking-[0.12em] text-muted">
                UPDATED {lastUpdated(updatedAt)}
              </span>
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
                label="COLORS"
                value={colorsFilter}
                onChange={setColorsFilter}
                options={colorOptions}
                variant="mobile"
                renderValue={renderColorOption}
                renderOption={renderColorOption}
              />
            </div>
          </div>
        </div>
      )}

      <div
        className={cn(GRID_CLS, isMobile ? "border-y border-border2" : "border-x border-b border-border2",
                      LOG_HEADER_CLS, TRACKER_HEADER_H)}
        style={{ gridTemplateColumns: isMobile ? LOG_COLS_MOBILE : LOG_COLS_DESKTOP }}
      >
        {isMobile ? (
          <>
            <SortHeaderCell label="#" sortKey="number" sort={sort} onSort={toggleSort} />
            <SortHeaderCell label="COLORS DECK" sortKey="colors" sort={sort} onSort={toggleSort}
                            cellClassName={GROUP_END} />
            <SortHeaderCell label="W/L" sortKey="record" sort={sort} onSort={toggleSort}
                            align="center" cellClassName={GROUP_END} />
            <Cell>NOTES</Cell>
            <Cell />
          </>
        ) : (
          <>
            <SortHeaderCell label="#" sortKey="number" sort={sort} onSort={toggleSort} />
            <SortHeaderCell label="COLORS" sortKey="colors" sort={sort} onSort={toggleSort} />
            <Cell className={GROUP_END}>DECK</Cell>
            <FormatFilterHeaderCell value={formatFilter} options={formatOptions} onChange={setFormatFilter} />
            <SortHeaderCell label="DATE" sortKey="date" sort={sort} onSort={toggleSort} />
            <SortHeaderCell label="W/L" sortKey="record" sort={sort} onSort={toggleSort}
                            align="end" cellClassName={GROUP_END} />
            <SortHeaderCell label="R" sortKey="rares" sort={sort} onSort={toggleSort} align="center" />
            <SortHeaderCell label="M" sortKey="mythics" sort={sort} onSort={toggleSort} align="center" />
            <Cell className="justify-end">GEMS</Cell>
            <Cell className={cn("justify-center", GROUP_END)}>PACKS</Cell>
            <Cell>NOTE</Cell>
            <Cell />
          </>
        )}
      </div>

      <div className="flex flex-col">
        {ordered.map(({ event: e, index }) => (
          <DraftRow
            key={e.eventId}
            index={index}
            event={e}
            isMobile={isMobile}
            note={notesById.get(e.eventId)?.note ?? ""}
            deckLabel={notesById.get(e.eventId)?.deckLabel ?? ""}
            rares={notesById.get(e.eventId)?.rares ?? null}
            mythics={notesById.get(e.eventId)?.mythics ?? null}
            matchNotes={(matchNotes ?? []).filter((m) => m.draftEventId === e.eventId)}
            expanded={open === e.eventId}
            onToggle={() => setOpen(open === e.eventId ? null : e.eventId)}
            onSaved={() => {
              qc.invalidateQueries({ queryKey: ["tracker-draft-notes"] });
              qc.invalidateQueries({ queryKey: ["tracker-match-notes"] });
            }}
          />
        ))}
      </div>
    </div>
  );
}

function DraftRow({
  index, event, isMobile, note, deckLabel, rares, mythics, matchNotes, expanded, onToggle, onSaved,
}: {
  index: number;
  event: PlayerDraftEvent;
  isMobile: boolean;
  note: string;
  deckLabel: string;
  rares: number | null;
  mythics: number | null;
  matchNotes: MatchNote[];
  expanded: boolean;
  onToggle: () => void;
  onSaved: () => void;
}) {
  const payout = payoutFor(event.format, event.wins);
  const date = event.finishedAt
    ? new Date(event.finishedAt).toLocaleDateString(undefined, { month: "short", day: "numeric" })
    : "";

  return (
    <div className={cn(isMobile ? "border-b border-border" : "border-x border-b border-border",
                       expanded ? "bg-surface2" : "bg-surface")}>
      <div
        onClick={onToggle}
        className={cn(GRID_CLS, "cursor-pointer hover:bg-surface2")}
        style={{ gridTemplateColumns: isMobile ? LOG_COLS_MOBILE : LOG_COLS_DESKTOP }}
      >
        {isMobile ? (
          <>
            <DraftIndexCell index={index} externalUrl={event.externalUrl} />
            <Cell className={cn("p-0", GROUP_END)}>
              <span className="shrink-0 pl-1 flex items-center"><Pips colors={event.colors} size={13} /></span>
              <div className="flex-1 min-w-0">
                <DeckNameCell
                  value={deckLabel}
                  placeholder={event.colors}
                  onCommit={async (v) => { await saveDraftNote(event.eventId, { deckLabel: v }); onSaved(); }}
                />
              </div>
            </Cell>
            <Cell className={cn("justify-center", GROUP_END)}>
              <span className="font-display tabular-nums text-[17px]">{event.wins}-{event.losses}</span>
            </Cell>
            <Cell>
              <span className="font-spectral text-[14px] text-subtle truncate">{note}</span>
            </Cell>
            <Cell className="p-0 justify-center">
              {expanded
                ? <ChevronDown size={18} strokeWidth={2.5} className="text-subtle" />
                : <ChevronRight size={18} strokeWidth={2.5} className="text-subtle" />}
            </Cell>
          </>
        ) : (
          <>
            <DraftIndexCell index={index} externalUrl={event.externalUrl} />
            <Cell><Pips colors={event.colors} size={13} /></Cell>
            <Cell className={cn("p-0", GROUP_END)}>
              <DeckNameCell
                value={deckLabel}
                placeholder={event.colors}
                onCommit={async (v) => { await saveDraftNote(event.eventId, { deckLabel: v }); onSaved(); }}
              />
            </Cell>
            <Cell>
              <span className="font-display text-[14px] tracking-[0.1em] text-muted truncate">
                {formatLabel(event.format)}
              </span>
            </Cell>
            <Cell><span className="mono text-[13px] text-muted whitespace-nowrap">{date}</span></Cell>
            <Cell className={cn("justify-end", GROUP_END)}>
              <span className="font-display tabular-nums text-[17px]">{event.wins}-{event.losses}</span>
            </Cell>
            <Cell className="p-0">
              <CountCell
                value={rares ?? event.poolRares ?? null}
                onCommit={async (n) => { await saveDraftNote(event.eventId, { rares: n }); onSaved(); }}
              />
            </Cell>
            <Cell className="p-0">
              <CountCell
                value={mythics ?? event.poolMythics ?? null}
                onCommit={async (n) => { await saveDraftNote(event.eventId, { mythics: n }); onSaved(); }}
              />
            </Cell>
            <Cell className="justify-end">
              <span className="font-display tabular-nums text-[16px] text-subtle">{payout ? payout.gems : ""}</span>
            </Cell>
            <Cell className={cn("justify-center", GROUP_END)}>
              <span className="font-display tabular-nums text-[16px] text-subtle">{payout ? payout.packs : ""}</span>
            </Cell>
            <Cell>
              <span className="font-spectral text-[14px] text-subtle truncate">{note}</span>
            </Cell>
            <Cell className="p-0 justify-center">
              {expanded
                ? <ChevronDown size={16} strokeWidth={2.5} className="text-subtle" />
                : <ChevronRight size={16} strokeWidth={2.5} className="text-subtle" />}
            </Cell>
          </>
        )}
      </div>

      {expanded && (
        <DraftNotesPanel event={event} note={note} matchNotes={matchNotes} onSaved={onSaved}>
          {isMobile && (
            <div className="flex items-center gap-3 px-2 py-2 border-b border-border">
              <span className="mono text-[13px] text-muted">
                {formatLabel(event.format)} {date}{payout ? ` ${payout.gems}g ${payout.packs}p` : ""}
              </span>
              <span className="ml-auto flex items-center gap-3 font-display text-[13px] tracking-[0.12em] text-muted">
                <span className="flex items-center gap-1.5">
                  R
                  <span className="w-9 h-7 border border-border2 flex">
                    <CountCell
                      value={rares ?? event.poolRares ?? null}
                      onCommit={async (n) => { await saveDraftNote(event.eventId, { rares: n }); onSaved(); }}
                    />
                  </span>
                </span>
                <span className="flex items-center gap-1.5">
                  M
                  <span className="w-9 h-7 border border-border2 flex">
                    <CountCell
                      value={mythics ?? event.poolMythics ?? null}
                      onCommit={async (n) => { await saveDraftNote(event.eventId, { mythics: n }); onSaved(); }}
                    />
                  </span>
                </span>
              </span>
            </div>
          )}
        </DraftNotesPanel>
      )}
    </div>
  );
}

// One grid for the whole panel, so the score and colour tracks take only the width this draft needs
// and every note still starts on the same axis
const MATCH_COLS = "36px auto auto auto minmax(0, 1fr)";
const MATCH_ROW_H = "min-h-[42px]";

function DraftNotesPanel({
  event, note, matchNotes, onSaved, children,
}: {
  event: PlayerDraftEvent;
  note: string;
  matchNotes: MatchNote[];
  onSaved: () => void;
  children?: ReactNode;
}) {
  const matches = event.wins + event.losses;
  const divider = "border-t border-border";
  const fetchedFor = (n: number) => (event.matchResults ?? []).find((x) => x.match_number === n) ?? null;
  const rows = Array.from({ length: matches }, (_, i) => i + 1).map((n) => {
    const fetched = fetchedFor(n);
    const stored = matchNotes.find((x) => x.matchNumber === n);
    return {
      matchNumber: n,
      score: gameScore(fetched?.games ?? []),
      opponent: stored?.opponentColors || fetched?.opponent_colors || "",
      note: stored?.note ?? "",
    };
  });
  // A column nobody in this draft fills collapses to nothing, dividers included
  const scoreCell = rows.some((r) => r.score) ? cn("justify-center px-2", divider, GROUP_END) : cn("p-0", divider);
  const opponentCell = rows.some((r) => r.opponent) ? cn("px-2", divider, GROUP_END) : cn("p-0", divider);

  return (
    <div className="border-t border-border2 bg-bg">
      {children}
      <div className="grid" style={{ gridTemplateColumns: MATCH_COLS }}>
        <Cell className={cn("justify-center p-0", MATCH_ROW_H, GROUP_END)}>
          {event.seventeenlandsEventId && (
            <RefetchDraftButton
              eventId={event.seventeenlandsEventId}
              onDone={onSaved}
              className="w-full h-full bg-surface2 hover:bg-surface"
            />
          )}
        </Cell>
        <div className={cn("col-span-4 flex", MATCH_ROW_H)}>
          <div className="flex-1 min-w-0">
            <NoteField
              initial={note}
              placeholder="Notes"
              onSave={async (v) => { await saveDraftNote(event.eventId, { note: v }); onSaved(); }}
            />
          </div>
        </div>
        {rows.map(({ matchNumber, score, opponent, note: matchNote }) => (
          <Fragment key={matchNumber}>
            <Cell className={cn("justify-center", MATCH_ROW_H, divider, GROUP_END)}>
              <span className="font-display tabular-nums text-[15px] text-subtle">M{matchNumber}</span>
            </Cell>
            <Cell className={scoreCell}>
              {score && (
                <span className="font-display tabular-nums text-[17px]">{score.won}-{score.lost}</span>
              )}
            </Cell>
            <Cell className={opponentCell}>{opponent && <Pips colors={opponent} size={13} />}</Cell>
            <Cell className={cn(divider, GROUP_END, score ? "p-0" : "px-1.5")}>
              {!score && event.seventeenlandsEventId && (
                <RefetchDraftButton eventId={event.seventeenlandsEventId} onDone={onSaved} />
              )}
            </Cell>
            <Cell className={cn("p-0 items-stretch", divider)}>
              <NoteField
                initial={matchNote}
                onSave={async (v) => { await saveMatchNote(event.eventId, matchNumber, { note: v }); onSaved(); }}
              />
            </Cell>
          </Fragment>
        ))}
      </div>
    </div>
  );
}

/** 17lands details come per draft, so one match with nothing recorded refetches the whole draft */
function RefetchDraftButton({ eventId, onDone, className }: { eventId: string; onDone: () => void; className?: string }) {
  const qc = useQueryClient();
  const [running, setRunning] = useState(false);

  const run = async () => {
    setRunning(true);
    try {
      await refreshOneDraft(eventId);
      qc.invalidateQueries({ queryKey: ["tracker-drafts"] });
      onDone();
    } finally {
      setRunning(false);
    }
  };

  return (
    <button
      type="button"
      onClick={run}
      disabled={running}
      aria-label="Refetch this draft from 17lands"
      className={cn("flex items-center justify-center text-muted hover:text-text disabled:opacity-50", className)}
    >
      <RefreshCw size={13} className={running ? "animate-spin" : undefined} />
    </button>
  );
}

function gameScore(games: TrackedMatch["games"]): { won: number; lost: number } | null {
  let won = 0;
  let lost = 0;
  for (const game of games ?? []) {
    if (game.won === true) {
      won += 1;
    } else if (game.won === false) {
      lost += 1;
    }
  }
  return won + lost ? { won, lost } : null;
}

/** The format column filters itself, the way the other headers sort themselves */
function FormatFilterHeaderCell({
  value, options, onChange,
}: { value: string; options: FilterOption[]; onChange: (v: string) => void }) {
  return (
    <Cell className="p-0">
      <FilterDropdown
        value={value}
        onChange={onChange}
        options={options}
        renderOption={renderFormatOption}
        className="h-full"
        renderTrigger={({ open, toggle }) => (
          <button
            type="button"
            onClick={toggle}
            aria-label="Filter by format"
            className={cn(
              "flex items-center gap-1 w-full h-full px-2 py-2.5 cursor-pointer",
              "tracking-[inherit] text-[inherit] font-[inherit]",
              value === "ALL" ? "hover:text-text" : "text-green",
            )}
          >
            FORMAT
            <ChevronDown size={13} strokeWidth={2.5}
                         className={cn("transition-transform", open && "rotate-180")} />
          </button>
        )}
      />
    </Cell>
  );
}

function Cell({ className, children }: { className?: string; children?: ReactNode }) {
  return <div className={cn(CELL_CLS, className)}>{children}</div>;
}

const SORT_ALIGN = { start: "justify-start", center: "justify-center", end: "justify-end" } as const;

/** The whole cell is the click target, and the caret shows only on the column being sorted */
function SortHeaderCell({
  label, sortKey, sort, onSort, align = "start", cellClassName,
}: {
  label: string; sortKey: TrackerSortKey; sort: TrackerSort;
  onSort: (key: TrackerSortKey) => void;
  align?: keyof typeof SORT_ALIGN; cellClassName?: string;
}) {
  const active = sort.key === sortKey;
  const Icon = sort.dir === "asc" ? ChevronUp : ChevronDown;

  return (
    <Cell className={cn("p-0", cellClassName)}>
      <button
        type="button"
        onClick={() => onSort(sortKey)}
        aria-label={`Sort by ${label}`}
        aria-sort={active ? (sort.dir === "asc" ? "ascending" : "descending") : "none"}
        className={cn(
          "flex items-center gap-1 w-full h-full px-2 py-2.5 cursor-pointer",
          "tracking-[inherit] text-[inherit] font-[inherit]",
          SORT_ALIGN[align],
          active ? "text-text" : "hover:text-text",
        )}
      >
        {label}
        {active && <Icon size={13} strokeWidth={2.5} />}
      </button>
    </Cell>
  );
}

/** The whole cell is the 17lands link, so the anchor fills it instead of wrapping the digits */
function DraftIndexCell({ index, externalUrl }: { index: number; externalUrl?: string | null }) {
  const digits = "font-display tabular-nums text-[15px] text-subtle";
  if (!externalUrl) {
    return <Cell className="pl-2"><span className={digits}>{index}</span></Cell>;
  }

  return (
    <Cell className="p-0">
      <a
        href={externalUrl}
        target="_blank"
        rel="noopener noreferrer"
        aria-label={`open draft ${index} on 17lands`}
        onClick={(e) => e.stopPropagation()}
        className={cn(digits, "flex items-center w-full h-full pl-2 hover:text-green hover:bg-surface2")}
      >
        {index}
      </a>
    </Cell>
  );
}

function DeckNameCell({
  value, placeholder, onCommit,
}: { value: string; placeholder: string; onCommit: (v: string) => Promise<void> }) {
  const [draft, setDraft] = useState(value);
  useEffect(() => { setDraft(value); }, [value]);

  return (
    <input
      value={draft}
      placeholder={placeholder}
      aria-label="deck name"
      onClick={(e) => e.stopPropagation()}
      onChange={(e) => setDraft(e.target.value)}
      onKeyDown={(e) => { if (e.key === "Enter") e.currentTarget.blur(); }}
      onBlur={() => { if (draft !== value) void onCommit(draft); }}
      className="w-full h-full font-body text-[14px] bg-transparent border border-transparent
                 px-2 text-text placeholder:text-subtle hover:border-border2 focus:border-green focus:bg-bg outline-none"
    />
  );
}

/** Sits inside a row whose click expands it, so every pointer event stops here */
function CountCell({
  value, onCommit,
}: {
  value: number | null;
  onCommit: (n: number | null) => Promise<void>;
}) {
  const shown = value == null ? "" : String(value);
  const [draft, setDraft] = useState(shown);
  useEffect(() => { setDraft(shown); }, [shown]);

  return (
    <input
      value={draft}
      inputMode="numeric"
      aria-label="cards opened"
      onClick={(e) => e.stopPropagation()}
      onChange={(e) => setDraft(e.target.value.replace(/[^0-9]/g, "").slice(0, 2))}
      onFocus={(e) => e.currentTarget.select()}
      onKeyDown={(e) => { if (e.key === "Enter") e.currentTarget.blur(); }}
      onBlur={(e) => {
        const raw = e.target.value.trim();
        const next = raw === "" ? null : Math.min(99, Number(raw));
        if (next !== value) void onCommit(next);
      }}
      className="font-display tabular-nums text-[16px] w-full h-full text-center text-subtle bg-transparent
                 border border-transparent hover:border-border2 focus:border-green focus:bg-bg outline-none"
    />
  );
}

function NoteField({ initial, placeholder = "", onSave }: { initial: string; placeholder?: string; onSave: (v: string) => Promise<void> }) {
  const [value, setValue] = useState(initial);
  const [saving, setSaving] = useState(false);
  const inputRef = useRef<HTMLTextAreaElement | null>(null);

  useEffect(() => { setValue(initial); }, [initial]);

  useEffect(() => {
    const el = inputRef.current;
    if (!el) { return; }
    el.style.height = "auto";
    const frame = el.offsetHeight - el.clientHeight;
    el.style.height = `${el.scrollHeight + frame}px`;
  }, [value]);

  const commit = async () => {
    if (value === initial) { return; }
    setSaving(true);
    await onSave(value);
    setSaving(false);
  };

  return (
    <textarea
      ref={inputRef}
      value={value}
      rows={1}
      placeholder={placeholder}
      aria-label="note"
      onChange={(e) => setValue(e.target.value)}
      onKeyDown={(e) => {
        if (e.key === "Enter" && !e.shiftKey) {
          e.preventDefault();
          e.currentTarget.blur();
        }
      }}
      onBlur={commit}
      className={cn(
        `block w-full h-full min-h-[42px] px-2 py-2.5 bg-transparent font-spectral text-[15px] leading-relaxed
         text-text outline-none resize-none overflow-hidden border border-transparent
         placeholder:font-body placeholder:text-[13px] placeholder:text-muted
         hover:border-border2 focus:border-green focus:bg-bg`,
        saving && "opacity-60",
      )}
    />
  );
}
