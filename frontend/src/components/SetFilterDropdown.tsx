import type { ReactNode } from "react";
import { SetGlyph, setGlyphCode } from "./Brand";
import { FilterDropdown, type FilterOption } from "./FilterDropdown";
import { isCubeCode } from "../data/utils";
import type { SetSummary } from "../types/leaderboard";

export interface SetFilterOption extends FilterOption {
  glyphCode?: string;
  meta?: ReactNode;
  triggerLabel?: string;
  icon?: ReactNode;
  code?: string;
}

// Newest release first, with the trigger showing the code and the list the set's own name.
// `pinCustom` lifts the custom boards to sit right under the live entry, the slot the leaderboard
// gives CUBE; without it a board with no dates sorts to the bottom.
export function setFilterOptionsFrom(sets: SetSummary[], pinCustom = false): SetFilterOption[] {
  const ordered = [...sets].sort((a, b) => setReleaseRank(b).localeCompare(setReleaseRank(a)));
  if (pinCustom) {
    const custom = ordered.filter((s) => s.custom);
    const rest = ordered.filter((s) => !s.custom);
    const liveIndex = rest.findIndex((s) => s.isActive);
    rest.splice(liveIndex + 1, 0, ...custom);
    ordered.splice(0, ordered.length, ...rest);
  }
  return ordered.map((s) => ({
    value: s.code,
    label: s.name,
    triggerLabel: isCubeCode(s.code) ? s.name : undefined,
    glyphCode: setGlyphCode(s),
    meta: s.isActive ? (
      <span className="mono text-[10px] tracking-[0.18em] text-green shrink-0">LIVE</span>
    ) : undefined,
  }));
}

function setReleaseRank(s: SetSummary): string {
  return s.startDate || (s.custom ? "" : "9999-99-99");
}

// Searchable, scrollable set picker: trigger shows the selected set's glyph + code, the open list
// shows glyph + full name plus optional trailing meta (a count, a LIVE badge). Shared so the
// Episodes and Leaderboard set switchers stay identical.
export function SetFilterDropdown({
  label,
  value,
  options,
  onChange,
  variant,
  align,
  searchable,
  searchPlaceholder = "Search sets or codes…",
  className,
  triggerClassName,
  subtext,
  valueLabel = "code",
}: {
  label?: string;
  value: string;
  options: SetFilterOption[];
  onChange: (next: string) => void;
  variant?: "desktop" | "mobile";
  align?: "left" | "right";
  searchable?: boolean;
  searchPlaceholder?: string;
  className?: string;
  triggerClassName?: string;
  subtext?: string;
  valueLabel?: "code" | "name";
}) {
  const byValue = new Map(options.map((option) => [option.value, option]));
  const glyphFor = (code: string) => byValue.get(code)?.glyphCode ?? code;

  const renderValue = (option: FilterOption) =>
    option.value ? (
      <span className="flex w-full items-center gap-2 min-w-0">
        {byValue.get(option.value)?.icon ?? (
          <SetGlyph code={glyphFor(option.value)} size={20} className="text-white shrink-0" />
        )}
        <span className="truncate">
          {valueLabel === "name"
            ? option.label
            : byValue.get(option.value)?.triggerLabel ?? option.value}
        </span>
        {subtext && (
          <span className="ml-auto shrink-0 pl-2 mono text-[9px] tracking-normal text-muted whitespace-nowrap">
            {subtext}
          </span>
        )}
      </span>
    ) : (
      option.label
    );

  const renderOption = (option: FilterOption) => {
    const opt = byValue.get(option.value);
    return (
      <span className="flex w-full min-w-0 items-center gap-2.5">
        {opt?.icon ??
          (option.value ? <SetGlyph code={glyphFor(option.value)} size={20} /> : <span className="w-5 shrink-0" />)}
        {opt?.code ? (
          <span className="flex-1 min-w-0 flex items-baseline gap-2">
            <span className="shrink-0 leading-none">{opt.code}</span>
            <span className="truncate text-muted text-[11px] tracking-[0.08em]">{option.label}</span>
          </span>
        ) : (
          <span className="flex-1 truncate">{option.label}</span>
        )}
        {opt?.meta ?? null}
      </span>
    );
  };

  return (
    <FilterDropdown
      label={label}
      value={value}
      options={options}
      onChange={onChange}
      variant={variant}
      align={align}
      renderValue={renderValue}
      renderOption={renderOption}
      searchable={searchable}
      searchPlaceholder={searchPlaceholder}
      className={className}
      triggerClassName={triggerClassName}
    />
  );
}
