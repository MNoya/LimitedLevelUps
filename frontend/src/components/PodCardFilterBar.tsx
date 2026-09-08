import { Search, X } from "lucide-react";
import { columnPipClass } from "./TierGrid";
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
}: {
  options: PodCardFilterOptions;
  filters: PodCardFilters;
  setFilters: (f: PodCardFilters) => void;
  minDrafts: number;
  setMinDrafts: (n: number) => void;
  search: string;
  setSearch: (value: string) => void;
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

  return (
    <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
      <div className="relative flex h-[26px] items-center">
        <Search size={13} className="pointer-events-none absolute left-2 text-muted" />
        <input
          type="text"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Search…"
          className="h-[26px] w-60 border border-border2 bg-transparent pl-7 pr-6 text-[13px] text-text placeholder:text-muted focus:border-green focus:outline-none"
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

      <div className="flex items-center gap-1">
        {options.colors.map((c) => (
          <button
            key={c.value}
            type="button"
            onClick={() => pickColor(c.value)}
            aria-label={`${c.name} (${c.count})`}
            className={cn(CHIP, "min-w-[28px]", filters.colors.includes(c.value) ? TOGGLE_ACTIVE : TOGGLE_INACTIVE)}
          >
            <i className={columnPipClass(c.value)} style={{ fontSize: c.value === "M" ? 20 : 14 }} />
          </button>
        ))}
      </div>

      <div className="flex items-center gap-1">
        {options.types.map((t) => (
          <button
            key={t.value}
            type="button"
            onClick={() => toggle("types", t.value)}
            aria-label={`${t.label} (${t.count})`}
            className={cn(CHIP, filters.types.includes(t.value) ? TOGGLE_ACTIVE : TOGGLE_INACTIVE)}
          >
            <i className={`ms ms-${t.ms}`} style={{ fontSize: 17, WebkitTextStroke: "0.6px currentColor" }} />
          </button>
        ))}
      </div>

      <div className="flex items-center gap-1">
        {options.manaValues.map((mv) => (
          <button
            key={mv.value}
            type="button"
            onClick={() => toggle("manaValues", mv.value)}
            aria-label={`Mana value ${mv.value} (${mv.count})`}
            className={cn(CHIP, "min-w-[26px]", filters.manaValues.includes(mv.value) ? TOGGLE_ACTIVE : TOGGLE_INACTIVE)}
          >
            <span className="font-display text-[15px] leading-none">{mv.value}</span>
          </button>
        ))}
      </div>

      <div className="flex h-[26px] items-center gap-2 border border-border2 pl-2.5 pr-2">
        <span className="mr-0.5 font-display text-[11px] tracking-[0.16em] text-muted">MIN DRAFTS</span>
        <input
          type="range"
          min={1}
          max={20}
          value={minDrafts}
          onChange={(e) => setMinDrafts(Number(e.target.value))}
          className={cn("w-24 cursor-pointer", minDrafts > 1 ? "accent-green" : "accent-subtle")}
        />
        <span
          className={cn(
            "font-num w-6 text-center text-[15px] leading-none tabular-nums",
            minDrafts > 1 ? "text-text" : "text-muted",
          )}
        >
          {minDrafts}
        </span>
      </div>

      {count > 0 ? (
        <button
          type="button"
          onClick={() => setFilters(EMPTY_POD_CARD_FILTERS)}
          className="flex h-[26px] items-center border border-border2 px-2.5 font-display text-[12px] tracking-[0.14em] text-muted transition-colors hover:border-green hover:text-green"
        >
          CLEAR
        </button>
      ) : null}
    </div>
  );
}
