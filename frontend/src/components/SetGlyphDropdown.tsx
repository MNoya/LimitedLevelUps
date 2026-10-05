import type { Ref } from "react";
import type { To } from "react-router-dom";
import { SetGlyph, setGlyphCode } from "./Brand";
import { FilterDropdown, type FilterOption } from "./FilterDropdown";
import { ChevronDown } from "./Icons";
import { cn } from "../lib/utils";
import type { SetSummary } from "../types/leaderboard";

export function SetGlyphDropdown({
  sets,
  activeCode,
  glyphCode,
  label,
  isMobile,
  loading = false,
  onChange,
  hrefFor,
  size = "large",
  align = "left",
  openOnHover = false,
  triggerClassName,
  labelRef,
}: {
  sets: SetSummary[];
  activeCode: string;
  glyphCode: string;
  label: string;
  isMobile: boolean;
  loading?: boolean;
  onChange?: (code: string) => void;
  hrefFor?: (code: string) => To;
  size?: "compact" | "toolbar" | "large";
  align?: "left" | "right";
  openOnHover?: boolean;
  triggerClassName?: string;
  labelRef?: Ref<HTMLSpanElement>;
}) {
  const glyphSize = { compact: 20, toolbar: 30, large: isMobile ? 26 : 38 }[size];
  const labelSize = {
    compact: "text-[18px]",
    toolbar: "text-[26px]",
    large: "text-[17px] md:text-[30px]",
  }[size];
  const chevronSize = size === "large" ? "h-4 w-4 md:h-5 md:w-5" : "h-4 w-4";
  const triggerSize = {
    compact: "h-7 gap-1.5 px-2",
    toolbar: "h-full gap-2.5 px-3",
    large: "gap-2 px-3 py-1.5 md:gap-3",
  }[size];

  if (!loading && sets.length <= 1) {
    return (
      <span className="flex items-center gap-2 md:gap-3 min-w-0">
        <SetGlyph code={glyphCode} size={glyphSize} />
        <span className="flex-1 min-w-0 truncate font-display tracking-[0.06em] text-[17px] md:text-[30px]">{label}</span>
      </span>
    );
  }

  const hasOptions = sets.length > 1;
  const byCode = new Map(sets.map((s) => [s.code, s]));
  const options: FilterOption[] = sets.map((s) => ({ value: s.code, label: s.name }));
  const menuOffset = align === "right" ? "top-[calc(100%+6px)]" : "top-full";

  return (
    <FilterDropdown
      value={activeCode}
      options={options}
      onChange={onChange}
      hrefFor={hrefFor}
      align={align}
      searchable={sets.length > 7}
      searchPlaceholder="Search sets…"
      emptyText="No sets match"
      openOnHover={openOnHover}
      className={cn("min-w-0", size === "toolbar" && "h-full")}
      menuClassName={cn("z-30 max-h-[min(60vh,400px)] max-w-[80vw] overflow-hidden shadow-xl", menuOffset)}
      optionClassName="gap-3"
      renderOption={(option) => <SetOptionRow set={byCode.get(option.value)!} active={option.value === activeCode} />}
      renderTrigger={({ open, toggle }) => (
        <button
          type="button"
          disabled={!hasOptions}
          onClick={toggle}
          aria-expanded={open}
          className={cn(
            "group flex max-w-full min-w-0 items-center border border-border2 text-text transition-colors",
            triggerSize,
            open && "bg-surface",
            hasOptions && "cursor-pointer hover:bg-surface",
            triggerClassName,
          )}
        >
          <SetGlyph code={glyphCode} size={glyphSize} />
          <span ref={labelRef} className={cn("flex-1 min-w-0 truncate font-display tracking-[0.06em]", labelSize)}>
            {label}
          </span>
          <ChevronDown
            strokeWidth={2.5}
            className={cn("text-muted transition-transform", chevronSize, open && "rotate-180")}
          />
        </button>
      )}
    />
  );
}

const SetOptionRow = ({ set, active }: { set: SetSummary; active: boolean }) => {
  const today = new Date().toISOString().slice(0, 10);
  return (
    <>
      <SetGlyph code={setGlyphCode(set)} size={24} />
      <span className="flex-1 truncate text-[17px] leading-none">{set.name.toUpperCase()}</span>
      {set.isActive ? (
        <span className={cn("text-[13px] tracking-[0.18em]", active ? "text-green" : "text-muted")}>LIVE</span>
      ) : (
        set.startDate > today && (
          <span className="text-[13px] tracking-[0.18em]" style={{ color: "#cca54e" }}>
            PREVIEW
          </span>
        )
      )}
    </>
  );
};
