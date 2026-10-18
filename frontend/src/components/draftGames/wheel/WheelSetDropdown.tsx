import { useMemo } from "react";

import { SetGlyph } from "../../Brand";
import { FilterDropdown, type FilterOption } from "../../FilterDropdown";
import { BsAsterisk, ChevronDown } from "../../Icons";
import { cn } from "../../../lib/utils";
import { ALL_SETS_CODE, setShortLabel, type WheelSetOption } from "../../../data/draftGames";
import { DARK_PIXEL_BUTTON } from "../pixelStyles";

export function WheelSetDropdown({
  sets,
  value,
  onChange,
  compact = false,
  includeAll = false,
  className,
}: {
  sets: WheelSetOption[];
  value: string;
  onChange: (code: string) => void;
  compact?: boolean;
  includeAll?: boolean;
  className?: string;
}) {
  const options: FilterOption[] = useMemo(() => {
    const setOptions = sets.map((set) => ({ value: set.code, label: set.name }));
    return includeAll ? [{ value: ALL_SETS_CODE, label: ALL_SETS_LABEL }, ...setOptions] : setOptions;
  }, [sets, includeAll]);
  const fullLabel = options.find((option) => option.value === value)?.label ?? value;
  return (
    <FilterDropdown
      value={value}
      options={options}
      onChange={onChange}
      searchable={sets.length > 8}
      searchPlaceholder="Search sets…"
      variant={compact ? "mobile" : "desktop"}
      className={className}
      renderOption={(option) => (
        <span className="flex items-center gap-2.5">
          <SetIcon code={option.value} size={16} />
          {option.label}
        </span>
      )}
      renderTrigger={({ open, toggle }) => (
        <button
          type="button"
          onClick={toggle}
          aria-label="Set"
          className={cn(DARK_PIXEL_BUTTON, compact ? COMPACT_TRIGGER : "h-10 w-full gap-2 px-3 text-lg")}
        >
          <SetIcon code={value} size={compact ? 16 : 18} />
          {compact ? shortLabel(value) : fullLabel}
          <ChevronDown
            size={compact ? 12 : 14}
            className={cn("ml-auto shrink-0 transition-transform", open && "rotate-180")}
          />
        </button>
      )}
    />
  );
}

const ALL_SETS_LABEL = "All Sets";
const COMPACT_TRIGGER = cn(
  "h-8 gap-1.5 px-2.5 text-lg shadow-[3px_3px_0_#05070a]",
  "hover:-translate-y-px hover:shadow-[3px_4px_0_#05070a]",
  "active:translate-x-px active:translate-y-px active:shadow-[2px_2px_0_#05070a]",
);

function SetIcon({ code, size }: { code: string; size: number }) {
  if (code === ALL_SETS_CODE) {
    return <BsAsterisk size={size} className="shrink-0" />;
  }
  return <SetGlyph code={code} size={size} className="shrink-0 text-current" />;
}

function shortLabel(code: string): string {
  return code === ALL_SETS_CODE ? "All" : setShortLabel(code);
}
