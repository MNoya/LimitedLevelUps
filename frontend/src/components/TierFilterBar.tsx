import { useLayoutEffect, useRef, useState, type ReactNode } from "react";
import { Search } from "lucide-react";
import { cn } from "../lib/utils";
import { RaritySetGlyph, SetGlyph, type Rarity } from "./Brand";
import { FilterDropdown, type FilterOption } from "./FilterDropdown";
import { ChevronDown } from "./Icons";
import { Pips } from "./ManaPips";
import { columnPipClass } from "./TierGrid";
import { Tooltip } from "./Tooltip";
import {
  MANA_VALUE_BUCKETS,
  TREND_COLOR,
  TREND_GLYPH,
  type TierFilterOptions,
  type TierFilters,
} from "../data/tierList";
import { colorsDisplayName } from "../data/filters";

const RARITY_KEYRUNE: Record<string, Rarity> = { C: "common", U: "uncommon", R: "rare", M: "mythic" };

export function TierFilterBar({
  filters,
  setFilters,
  options,
  setCode,
  hideArt,
  setHideArt,
  onSearch,
  dataGrades,
  setDataGrades,
  decks = [],
  deck = null,
  setDeck,
  stacked = false,
  maxWidth,
  onMinWidth,
}: {
  filters: TierFilters;
  setFilters: (f: TierFilters) => void;
  options: TierFilterOptions;
  setCode: string;
  hideArt: boolean;
  setHideArt: (value: boolean) => void;
  onSearch: () => void;
  dataGrades?: boolean;
  setDataGrades?: (value: boolean) => void;
  decks?: string[];
  deck?: string | null;
  setDeck?: (deck: string | null) => void;
  stacked?: boolean;
  maxWidth?: number;
  onMinWidth?: (width: number) => void;
}) {
  const toggle = (key: keyof TierFilters, value: string) => {
    const arr = filters[key];
    const next = arr.includes(value) ? arr.filter((x) => x !== value) : [...arr, value];
    setFilters({ ...filters, [key]: next });
  };

  const pickColor = (value: string) => {
    setFilters({ ...filters, colors: filters.colors.includes(value) ? [] : [value] });
  };

  const deckEnabled = decks.length > 0;
  const [trendTipOpen, setTrendTipOpen] = useState(false);
  const trendMode =
    filters.trends.length === 2
      ? "both"
      : filters.trends.length === 1
        ? (filters.trends[0] as "up" | "down")
        : "off";
  const cycleTrend = () => {
    const next =
      trendMode === "off" ? ["up", "down"] : trendMode === "both" ? ["up"] : trendMode === "up" ? ["down"] : [];
    setFilters({ ...filters, trends: next });
    setTrendTipOpen(true);
  };
  const trends = options.trends;
  const trendCycleLabel =
    trendMode === "off"
      ? withCount("Show cards that moved", trends && trends.up + trends.down)
      : trendMode === "both"
        ? withCount("Show only cards that moved up", trends?.up)
        : trendMode === "up"
          ? withCount("Show only cards that moved down", trends?.down)
          : "Show all cards";

  const colorGroup = (
    <FilterGroup label="COLOR" stacked={stacked} joined>
      {options.colors.map((c) => (
        <IconToggle
          key={c.value}
          active={filters.colors.includes(c.value)}
          onClick={() => pickColor(c.value)}
          label={withCount(c.name, c.count)}
          narrow
        >
          <i className={columnPipClass(c.value)} style={{ fontSize: c.value === "M" ? 21 : 15 }} />
        </IconToggle>
      ))}
    </FilterGroup>
  );

  const rarityGroup = (
    <FilterGroup label="RARITY" stacked={stacked} joined>
      {options.rarities.map((r) => {
        return (
          <IconToggle
            key={r.value}
            active={filters.rarities.includes(r.value)}
            onClick={() => toggle("rarities", r.value)}
            label={withCount(r.name, r.count)}
            roomy
          >
            <RaritySetGlyph code={setCode} rarity={RARITY_KEYRUNE[r.value]} size={22} />
          </IconToggle>
        );
      })}
    </FilterGroup>
  );

  const typeGroup = (
    <FilterGroup label="TYPE" stacked={stacked} joined>
      {options.types.map((t) => (
        <IconToggle
          key={t.value}
          active={filters.cardTypes.includes(t.value)}
          onClick={() => toggle("cardTypes", t.value)}
          label={withCount(t.label, t.count)}
          roomy
        >
          <i
            className={`ms ms-${t.ms} relative -top-[2px]`}
            style={{ fontSize: 20, WebkitTextStroke: "0.6px currentColor" }}
          />
        </IconToggle>
      ))}
    </FilterGroup>
  );

  const compact = stacked && options.sets.length >= 3;

  const manaValueGroup = (
    <FilterGroup label="MANA VALUE" stacked={stacked} joined>
      {MANA_VALUE_BUCKETS.map((mv) => (
        <IconToggle
          key={mv}
          active={filters.manaValues.includes(mv)}
          onClick={() => toggle("manaValues", mv)}
          label={`Mana value ${mv}`}
          narrow
        >
          <span className="font-display text-[18px] leading-none">{mv}</span>
        </IconToggle>
      ))}
    </FilterGroup>
  );

  const setGroup =
    options.sets.length > 1 ? (
      <FilterGroup label="SET GROUP" stacked={stacked} joined>
        {options.sets.map((s) => (
          <IconToggle
            key={s.value}
            active={filters.sets.includes(s.value)}
            onClick={() => toggle("sets", s.value)}
            label={withCount(s.label, s.count)}
            compact={compact}
          >
            <SetGlyph code={s.glyph} size={compact ? 16 : 19} className="" />
          </IconToggle>
        ))}
      </FilterGroup>
    ) : null;

  const trendGroup = (
    <FilterGroup label="TREND" stacked={stacked} joined>
      <IconToggle
        active={trendMode !== "off"}
        onClick={cycleTrend}
        label={trendCycleLabel}
        narrow
        tooltipOpen={trendTipOpen}
        onTooltipOpenChange={setTrendTipOpen}
      >
        <span className="flex w-[28px] items-center justify-center">
          {trendMode === "up" || trendMode === "down" ? (
            <span className="text-[15px] leading-none" style={{ color: TREND_COLOR[trendMode] }}>
              {TREND_GLYPH[trendMode]}
            </span>
          ) : (
            <span className={cn("flex gap-0.5 text-[12px] leading-none", trendMode === "off" && "opacity-70")}>
              <span style={{ color: TREND_COLOR.up }}>{TREND_GLYPH.up}</span>
              <span style={{ color: TREND_COLOR.down }}>{TREND_GLYPH.down}</span>
            </span>
          )}
        </span>
      </IconToggle>
    </FilterGroup>
  );

  const artGroup = (
    <FilterGroup label="ART" stacked={stacked} joined>
      <IconToggle
        active={hideArt}
        onClick={() => setHideArt(!hideArt)}
        label={hideArt ? "Show card art" : "Hide card art"}
        narrow
        mutedActive
      >
        <span className="flex w-[28px] items-center justify-center">
          <ArtIcon hidden={hideArt} />
        </span>
      </IconToggle>
    </FilterGroup>
  );

  const gradesGroup = setDataGrades ? (
    <FilterGroup label="GRADES" stacked={stacked} joined>
      <IconToggle active={!dataGrades} onClick={() => setDataGrades(false)} label="Show cards by LLU grade" narrow>
        <span className="px-1 text-[12px] font-semibold">LLU</span>
      </IconToggle>
      <IconToggle
        active={Boolean(dataGrades)}
        onClick={() => setDataGrades(true)}
        label="Show cards by 17Lands stats"
        narrow
      >
        <span className="px-1 text-[12px] font-semibold">17L</span>
      </IconToggle>
    </FilterGroup>
  ) : null;

  const allDecks = "ALL";
  const deckOptions: FilterOption[] = [
    { value: allDecks, label: "All decks" },
    ...decks.map((code) => ({ value: code, label: sentenceCase(colorsDisplayName(code)) })),
  ];
  const deckLabel = (option: FilterOption) => (
    <DeckLabel code={option.value === allDecks ? null : option.value} label={option.label} />
  );
  const deckGroup =
    setDataGrades && setDeck ? (
      <FilterGroup label="DECK" stacked={stacked}>
        <FilterDropdown
          value={deck ?? allDecks}
          options={deckOptions}
          onChange={(value) => setDeck(value === allDecks ? null : value)}
          align="right"
          searchable={false}
          menuClassName="z-30 w-full"
          optionClassName="h-10 py-0 pl-[8.5px] pr-3 font-body text-[14px] font-semibold tracking-normal"
          renderOption={deckLabel}
          renderTrigger={({ open, selected, toggle }) => (
            <button
              type="button"
              onClick={toggle}
              disabled={!deckEnabled}
              title={deckEnabled ? undefined : "No deck data yet"}
              aria-expanded={open}
              className={cn(
                "flex h-10 items-center gap-2 rounded border px-3 text-[14px] font-semibold transition-colors",
                deck && "border-green bg-green/10 text-text",
                !deck && deckEnabled && "border-border2 text-muted hover:bg-surface2 hover:text-text",
                !deckEnabled && "cursor-not-allowed border-border2 text-muted opacity-50",
              )}
            >
              <span className="grid">
                {deckOptions.map((option) => (
                  <span
                    key={option.value}
                    className={cn("col-start-1 row-start-1", option.value !== selected.value && "invisible")}
                  >
                    {deckLabel(option)}
                  </span>
                ))}
              </span>
              <ChevronDown className={cn("h-3.5 w-3.5 transition-transform", open && "rotate-180")} />
            </button>
          )}
        />
      </FilterGroup>
    ) : null;

  const searchGroup = (
    <FilterGroup label="SEARCH" stacked={stacked} joined>
      <IconToggle active={false} onClick={onSearch} label="Search" tooltip={false} narrow>
        <span className="flex w-[28px] items-center justify-center">
          <Search size={17} />
        </span>
      </IconToggle>
    </FilterGroup>
  );

  if (stacked) {
    return (
      <div
        className={cn(
          "flex w-full flex-col items-center gap-y-3",
          "sm:flex-row sm:flex-wrap sm:items-end sm:justify-center sm:gap-x-6",
        )}
      >
        <div className="grid w-full grid-cols-[max-content_max-content] items-end justify-around gap-y-3 sm:contents">
          {rarityGroup}
          {typeGroup}
          <div className="col-span-2 flex items-end justify-between sm:contents">
            {setGroup}
            {trendGroup}
            {gradesGroup}
            {artGroup}
            {searchGroup}
          </div>
        </div>
        <div className="flex flex-wrap items-end justify-center gap-x-4 gap-y-3 sm:contents">
          {colorGroup}
          {deckGroup}
        </div>
      </div>
    );
  }

  return (
    <FittedRow
      maxWidth={maxWidth}
      onMinWidth={onMinWidth}
      droppable={{ mv: manaValueGroup, type: typeGroup, set: setGroup }}
    >
      {(droppable) => (
        <>
          {rarityGroup}
          {droppable.type}
          {droppable.mv}
          {droppable.set}
          {trendGroup}
          {gradesGroup}
          {deckGroup}
          {artGroup}
          {searchGroup}
        </>
      )}
    </FittedRow>
  );
}

const DROP_ORDER = ["mv", "type", "set"];

function FittedRow({
  maxWidth,
  onMinWidth,
  droppable,
  children,
}: {
  maxWidth?: number;
  onMinWidth?: (width: number) => void;
  droppable: Record<string, ReactNode>;
  children: (droppable: Record<string, ReactNode>) => ReactNode;
}) {
  const rowRef = useRef<HTMLDivElement>(null);
  const naturalWidths = useRef(new Map<string, number>());
  const [dropped, setDropped] = useState<string[]>([]);

  useLayoutEffect(() => {
    const row = rowRef.current;
    if (!row) {
      return;
    }
    const gap = parseFloat(getComputedStyle(row).columnGap) || 0;
    let keptWidth = 0;
    let keptCount = 0;
    for (const item of row.children) {
      const key = (item as HTMLElement).dataset.drop;
      if (key) {
        naturalWidths.current.set(key, (item as HTMLElement).offsetWidth);
      } else {
        keptWidth += (item as HTMLElement).offsetWidth;
        keptCount += 1;
      }
    }
    const present = DROP_ORDER.filter((key) => droppable[key]);
    let total = keptWidth + gap * (keptCount - 1);
    onMinWidth?.(Math.ceil(total));
    for (const key of present) {
      total += (naturalWidths.current.get(key) ?? 0) + gap;
    }
    const next: string[] = [];
    for (const key of present) {
      if (maxWidth === undefined || total <= maxWidth) {
        break;
      }
      next.push(key);
      total -= (naturalWidths.current.get(key) ?? 0) + gap;
    }
    if (next.join() !== dropped.join()) {
      setDropped(next);
    }
  });

  const shown: Record<string, ReactNode> = {};
  for (const [key, group] of Object.entries(droppable)) {
    shown[key] =
      group && !dropped.includes(key) ? (
        <div key={key} data-drop={key}>
          {group}
        </div>
      ) : null;
  }
  return (
    <div ref={rowRef} className="flex items-end gap-x-5">
      {children(shown)}
    </div>
  );
}

function DeckLabel({ code, label }: { code: string | null; label: string }) {
  return (
    <span className="flex items-center gap-2 whitespace-nowrap">
      {code && <Pips colors={code} size={12} />}
      {label}
    </span>
  );
}

function sentenceCase(text: string): string {
  return text.charAt(0) + text.slice(1).toLowerCase();
}

function withCount(label: string, count: number | null | undefined): string {
  return count == null ? label : `${label} (${count})`;
}

function ArtIcon({ hidden }: { hidden: boolean }) {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <rect x="3" y="3" width="18" height="18" rx="2" strokeLinejoin="round" />
      <circle cx="8.5" cy="8.5" r="1.5" />
      <path d="M21 15l-5-5L5 21" strokeLinecap="round" strokeLinejoin="round" />
      {hidden && <path d="M3 3l18 18" strokeLinecap="round" />}
    </svg>
  );
}

export const LABEL = "font-display text-[13px] tracking-[0.2em] text-subtle";

export const JOINED = cn(
  "[&>button]:rounded-none",
  "[&>button:first-child]:rounded-l-md [&>button:last-child]:rounded-r-md",
  "[&>button:not(:first-child)]:-ml-px",
);

export function FilterGroup({
  label,
  children,
  stacked,
  joined = false,
  className,
}: {
  label: string;
  children: ReactNode;
  stacked: boolean;
  joined?: boolean;
  className?: string;
}) {
  return (
    <div className={cn("flex flex-col", stacked ? "items-center gap-1" : "gap-1.5", className)}>
      <span className={cn(LABEL, !stacked && "[text-box:trim-both_cap_alphabetic]")}>{label}</span>
      <div className={cn("flex", joined ? JOINED : "gap-1.5")}>{children}</div>
    </div>
  );
}

export function IconToggle({
  active,
  onClick,
  label,
  children,
  roomy = false,
  narrow = false,
  compact = false,
  mutedActive = false,
  className,
  tooltip = true,
  tooltipOpen,
  onTooltipOpenChange,
}: {
  active: boolean;
  onClick: () => void;
  label: string;
  children: ReactNode;
  roomy?: boolean;
  narrow?: boolean;
  compact?: boolean;
  mutedActive?: boolean;
  className?: string;
  tooltip?: boolean;
  tooltipOpen?: boolean;
  onTooltipOpenChange?: (open: boolean) => void;
}) {
  const activeClass = mutedActive
    ? "z-10 border-border2 bg-surface2 text-subtle"
    : "z-10 border-green bg-green/10 text-text";
  const button = (
    <button
      type="button"
      onClick={onClick}
      aria-label={label}
      className={cn(
          "relative flex h-10 items-center justify-center rounded border transition-colors",
          roomy
            ? "min-w-[40px] px-2.5"
            : narrow
              ? compact
                ? "min-w-[28px] px-1"
                : "min-w-[34px] px-1.5"
              : compact
                ? "min-w-[32px] px-1.5"
                : "min-w-[40px] px-2",
          active
            ? activeClass
            : "border-border2 bg-transparent text-muted hover:bg-surface2 hover:text-text",
        className,
      )}
    >
      {children}
    </button>
  );
  if (!tooltip) {
    return button;
  }
  return (
    <Tooltip label={label} open={tooltipOpen} onOpenChange={onTooltipOpenChange}>
      {button}
    </Tooltip>
  );
}
