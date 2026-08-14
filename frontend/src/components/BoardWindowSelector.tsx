import type React from "react";
import { SetGlyph } from "./Brand";
import { ChevronDown } from "./Icons";
import { FilterDropdown, type FilterOption } from "./FilterDropdown";
import { cn } from "../lib/utils";

export interface BoardWindowOption {
  value: string;
  label: string;
  // A set symbol by code, or a ready-made icon for an option that is not a set
  glyph?: string;
  icon?: React.ReactNode;
}

// Picks which window of a board is open: a cube run on the leaderboard, a season on a pod board.
// Built on FilterDropdown so the menu width, scrolling and alignment match every other picker; the
// "hero" variant only swaps the trigger for an inline one matched to the set-hero date line.
export function BoardWindowSelector({
  value,
  options,
  onSelect,
  variant = "hero",
}: {
  value: string;
  options: BoardWindowOption[];
  onSelect: (value: string) => void;
  variant?: "hero" | "mobile";
}) {
  const byValue = new Map(options.map((o) => [o.value, o]));
  const iconFor = (value: string, size: number) => {
    const option = byValue.get(value);
    if (option?.icon) return option.icon;
    return <SetGlyph code={option?.glyph ?? value} size={size} className="text-white shrink-0" />;
  };
  const render = (option: FilterOption) => (
    <span className="flex w-full items-center gap-2.5 min-w-0">
      {iconFor(option.value, 20)}
      <span className="truncate">{option.label}</span>
    </span>
  );
  return (
    <FilterDropdown
      value={value}
      options={options}
      onChange={onSelect}
      variant={variant === "hero" ? "desktop" : "mobile"}
      renderValue={render}
      renderOption={render}
      renderTrigger={
        variant === "hero"
          ? ({ open, selected, toggle }) => (
              <button
                type="button"
                onClick={toggle}
                className="flex items-center gap-2 cursor-pointer transition-colors font-display leading-none bg-transparent border-0 p-0 text-[20px] tracking-[0.04em] text-text hover:text-muted"
              >
                {iconFor(selected.value, 22)}
                <span>{selected.label}</span>
                <ChevronDown
                  strokeWidth={2.5}
                  className={cn("text-muted h-3.5 w-3.5 transition-transform", open && "rotate-180")}
                />
              </button>
            )
          : undefined
      }
    />
  );
}
