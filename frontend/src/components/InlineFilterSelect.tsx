import type React from "react";
import { ChevronDown } from "./Icons";
import { FilterDropdown, type FilterOption } from "./FilterDropdown";
import { cn } from "../lib/utils";

export interface InlineFilterOption extends FilterOption {
  icon?: React.ReactNode;
}

// A filter that reads as a line of running text next to a section heading, and falls back to the
// boxed control the mobile filter bar uses. Labels are sentence-cased, so both trigger and menu
// override the display font the surrounding chrome sets.
export function InlineFilterSelect({
  value,
  options,
  onChange,
  variant = "inline",
  align = "left",
}: {
  value: string;
  options: InlineFilterOption[];
  onChange: (value: string) => void;
  variant?: "inline" | "mobile";
  align?: "left" | "right";
}) {
  const iconFor = (option: FilterOption) => options.find((o) => o.value === option.value)?.icon;
  const render = (option: FilterOption) => (
    <span className="flex w-full items-center gap-2 min-w-0 font-body tracking-normal text-[15px]">
      {iconFor(option)}
      <span className="truncate">{option.label}</span>
    </span>
  );
  return (
    <FilterDropdown
      value={value}
      options={options}
      onChange={onChange}
      variant={variant === "mobile" ? "mobile" : "desktop"}
      align={align}
      renderValue={render}
      renderOption={render}
      renderTrigger={
        variant === "inline"
          ? ({ open, selected, toggle }) => (
              <button
                type="button"
                onClick={toggle}
                className="flex items-center gap-1.5 cursor-pointer transition-colors font-body leading-none bg-transparent border-0 p-0 text-[18px] text-text hover:text-muted whitespace-nowrap"
              >
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
