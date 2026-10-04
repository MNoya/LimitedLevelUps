import { Search, X } from "lucide-react";
import { columnPipClass } from "./TierGrid";
import { ToggleSwitch } from "./ToggleSwitch";
import { cn } from "../lib/utils";
import { TOGGLE_ACTIVE, TOGGLE_INACTIVE } from "../lib/toggle-styles";
import {
  EMPTY_POD_CARD_FILTERS,
  activePodCardFilterCount,
  type PodCardFilterOptions,
  type PodCardFilters,
} from "../data/podCards";

const CHIP = "shrink-0 h-[26px] px-2 border inline-flex items-center justify-center gap-1 cursor-pointer transition-colors";

export function PodCardFilterBar({
  options,
  filters,
  setFilters,
  minDrafts,
  setMinDrafts,
  search,
  setSearch,
  hasCurrentList,
  currentListOnly,
  setCurrentListOnly,
  compact = false,
}: {
  options: PodCardFilterOptions;
  filters: PodCardFilters;
  setFilters: (f: PodCardFilters) => void;
  minDrafts: number;
  setMinDrafts: (n: number) => void;
  search: string;
  setSearch: (value: string) => void;
  hasCurrentList: boolean;
  currentListOnly: boolean;
  setCurrentListOnly: (on: boolean) => void;
  compact?: boolean;
}) {
  const toggle = (key: keyof PodCardFilters, value: string) => {
    const arr = filters[key];
    const next = arr.includes(value) ? arr.filter((x) => x !== value) : [...arr, value];
    setFilters({ ...filters, [key]: next });
  };
  const pickColor = (value: string) => {
    setFilters({ ...filters, colors: filters.colors.includes(value) ? [] : [value] });
  };

  const count = activePodCardFilterCount(filters);
  const listLabelColor = currentListOnly ? "text-green" : "text-muted";
  const compactFill = compact && "min-w-0 flex-1";
  const minDraftsAccent = minDrafts > 0 ? "accent-green" : "accent-subtle";

  const searchBox = (
    <div className={cn("relative flex h-[26px] items-center", compactFill)}>
      <Search size={13} className="pointer-events-none absolute left-2 text-muted" />
      <input
        type="text"
        value={search}
        onChange={(e) => setSearch(e.target.value)}
        placeholder="Search…"
        className={cn(
          "h-[26px] border border-border2 bg-transparent pl-7 pr-6 text-[13px] text-text placeholder:text-muted focus:border-green focus:outline-none",
          compact ? "w-full" : "w-60",
        )}
      />
      {search ? (
        <button
          type="button"
          onClick={() => setSearch("")}
          aria-label="Clear search"
          className="absolute right-1.5 text-muted hover:text-text"
        >
          <X size={13} />
        </button>
      ) : null}
    </div>
  );

  const colorChips = (
    <div className="flex items-center gap-[4px]">
      {options.colors.map((c) => (
        <button
          key={c.value}
          type="button"
          onClick={() => pickColor(c.value)}
          aria-label={`${c.name} (${c.count})`}
          className={cn(CHIP, "w-[32px] px-0", filters.colors.includes(c.value) ? TOGGLE_ACTIVE : TOGGLE_INACTIVE)}
        >
          <i className={columnPipClass(c.value)} style={{ fontSize: c.value === "M" ? 20 : 14 }} />
        </button>
      ))}
    </div>
  );

  const typeChips = (
    <div className="flex items-center gap-[4px]">
      {options.types.map((t) => (
        <button
          key={t.value}
          type="button"
          onClick={() => toggle("types", t.value)}
          aria-label={`${t.label} (${t.count})`}
          className={cn(CHIP, "w-[32px] px-0", filters.types.includes(t.value) ? TOGGLE_ACTIVE : TOGGLE_INACTIVE)}
        >
          <i className={`ms ms-${t.ms}`} style={{ fontSize: 17, WebkitTextStroke: "0.6px currentColor" }} />
        </button>
      ))}
    </div>
  );

  const manaChips = (
    <div className="flex items-center gap-[4px]">
      {options.manaValues.map((mv) => (
        <button
          key={mv.value}
          type="button"
          onClick={() => toggle("manaValues", mv.value)}
          aria-label={`Mana value ${mv.value} (${mv.count})`}
          className={cn(CHIP, "w-[26px] px-0", filters.manaValues.includes(mv.value) ? TOGGLE_ACTIVE : TOGGLE_INACTIVE)}
        >
          <span className="font-display text-[15px] leading-none">{mv.value}</span>
        </button>
      ))}
    </div>
  );

  const minDraftsSlider = (
    <div className={cn("flex h-[26px] items-center gap-2 border border-border2 pl-2.5 pr-2", compactFill)}>
      <span className="mr-0.5 shrink-0 font-display text-[11px] tracking-[0.16em] text-muted">MIN DRAFTS</span>
      <input
        type="range"
        min={0}
        max={20}
        step={5}
        value={minDrafts}
        onChange={(e) => setMinDrafts(Number(e.target.value))}
        className={cn(compact ? "min-w-0 flex-1" : "w-24", "cursor-pointer", minDraftsAccent)}
      />
      <span
        className={cn(
          "font-num w-6 shrink-0 text-center text-[15px] leading-none tabular-nums",
          minDrafts > 0 ? "text-text" : "text-muted",
        )}
      >
        {minDrafts}
      </span>
    </div>
  );

  const currentListSwitch = hasCurrentList ? (
    <button
      type="button"
      role="switch"
      aria-checked={currentListOnly}
      onClick={() => setCurrentListOnly(!currentListOnly)}
      className={cn(CHIP, "gap-2 border-border2 pl-2.5 pr-2 hover:bg-surface")}
    >
      <span className={cn("font-display text-[11px] tracking-[0.16em]", listLabelColor)}>
        CURRENT LIST
      </span>
      <ToggleSwitch on={currentListOnly} />
    </button>
  ) : null;

  const clearButton = count > 0 ? (
    <button
      type="button"
      onClick={() => setFilters(EMPTY_POD_CARD_FILTERS)}
      className="flex h-[26px] items-center border border-border2 px-2.5 font-display text-[12px] tracking-[0.14em] text-muted transition-colors hover:border-green hover:text-green"
    >
      CLEAR
    </button>
  ) : null;

  if (compact) {
    return (
      <div className="flex flex-col gap-2">
        <div className="flex items-center gap-3">
          {searchBox}
          {currentListSwitch}
        </div>
        <div className="flex items-center gap-3">
          {colorChips}
          {clearButton}
        </div>
        {typeChips}
        <div className="flex items-center gap-3">
          {manaChips}
          {minDraftsSlider}
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
      {searchBox}
      {colorChips}
      {typeChips}
      {manaChips}
      {minDraftsSlider}
      {currentListSwitch}
      {clearButton}
    </div>
  );
}
