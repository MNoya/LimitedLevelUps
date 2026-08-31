import React from "react";
import { setGlyphCode, SetGlyph } from "./Brand";
import { ChevronDown } from "./Icons";
import { FilterDropdown, type FilterOption } from "./FilterDropdown";
import { cn } from "../lib/utils";
import { useSetVisibleCap } from "../lib/use-is-mobile";
import { CUBE_BASE, isCubeCode } from "../data/utils";
import { isMtgoFlashbackCode } from "../data/mtgoSets";
import type { SetSummary } from "../types/leaderboard";

const MTGO_SECTION = "MTGO FLASHBACKS";

const FUTURE_RELEASE_RANK = "9999-99-99";
const NO_RELEASE_RANK = "";

const MAX_NEWER_CONTEXT = 2;

function releaseRank(s: SetSummary): string {
  return s.startDate || (s.custom ? NO_RELEASE_RANK : FUTURE_RELEASE_RANK);
}

function byDateDesc(a: SetSummary, b: SetSummary): number {
  const aMtgo = isMtgoFlashbackCode(a.code);
  const bMtgo = isMtgoFlashbackCode(b.code);
  if (aMtgo !== bMtgo) return aMtgo ? 1 : -1;
  return releaseRank(b).localeCompare(releaseRank(a));
}

function partitionSets(sets: SetSummary[], selectedCode: string, cap: number) {
  const leadPins: SetSummary[] = [];
  const live = sets.find((s) => s.isActive);
  const cube = sets.find((s) => s.code === CUBE_BASE);
  const early = sets.filter((s) => s.early && s.code !== CUBE_BASE && !s.isActive).sort(byDateDesc);
  leadPins.push(...early);
  if (live) leadPins.push(live);
  if (cube && cube.code !== live?.code) leadPins.push(cube);
  leadPins.push(...sets.filter((s) => s.custom));

  const pinnedCodes = new Set(leadPins.map((s) => s.code));
  const history = sets.filter((s) => !pinnedCodes.has(s.code)).sort(byDateDesc);

  const windowSize = Math.max(1, cap - leadPins.length);
  if (history.length <= windowSize) {
    return { visible: [...leadPins, ...history], overflow: [] };
  }

  const selectedIndex = history.findIndex((s) => s.code === selectedCode);
  const maxStart = history.length - windowSize;
  const newerContext = Math.min(MAX_NEWER_CONTEXT, Math.max(0, windowSize - 2));
  const desiredStart = selectedIndex < 0 ? 0 : selectedIndex - newerContext;
  const start = Math.max(0, Math.min(desiredStart, maxStart));
  const window = history.slice(start, start + windowSize);

  const windowCodes = new Set(window.map((s) => s.code));
  const overflow = history.filter((s) => !windowCodes.has(s.code));
  return { visible: [...leadPins, ...window], overflow };
}

export function SetSwitcherDesktop({
  sets,
  activeCode,
  onChange,
  onPrefetch,
  extraHide = 0,
}: {
  sets: SetSummary[];
  activeCode: string;
  onChange: (code: string) => void;
  onPrefetch?: (code: string) => void;
  extraHide?: number;
}) {
  const cap = useSetVisibleCap(sets.length, extraHide);
  const { visible, overflow } = partitionSets(sets, activeCode, cap);
  return (
    <div className="flex gap-1.5">
      {visible.map((s) => (
        <SetChip
          key={s.code}
          set={s}
          active={s.code === activeCode}
          onClick={() => onChange(s.code)}
          onHover={onPrefetch ? () => onPrefetch(s.code) : undefined}
        />
      ))}
      {overflow.length > 0 && <SetOverflow sets={overflow} activeCode={activeCode} onChange={onChange} />}
    </div>
  );
}

const CHAMFER = "polygon(8px 0, 100% 0, calc(100% - 8px) 100%, 0 100%)";

const MONTHS = ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"];

function chipDateLabel(set: SetSummary): string {
  if (set.isActive || isCubeCode(set.code) || !set.startDate) return "";
  const [year, month] = set.startDate.split("-");
  const name = MONTHS[Number(month) - 1];
  return name ? `${name} ${year.slice(2)}'` : "";
}

function SetChip({
  set,
  active,
  onClick,
  onHover,
}: {
  set: SetSummary;
  active: boolean;
  onClick: () => void;
  onHover?: () => void;
}) {
  return (
    <div className="relative">
      <button
        onClick={onClick}
        onMouseEnter={onHover}
        onFocus={onHover}
        className="group block cursor-pointer"
        style={{
          clipPath: CHAMFER,
          background: active ? "#2ee85c" : "#3b4458",
          padding: 1,
          minHeight: 42,
        }}
      >
        <span
          className={cn(
            "flex items-center justify-center gap-[7px] w-[98px] px-[17px] font-display h-full",
            active ? "bg-green text-bg" : "bg-surface text-text group-hover:bg-surface2",
          )}
          style={{ clipPath: CHAMFER, minHeight: 40 }}
        >
          <SetGlyph code={setGlyphCode(set)} size={22} className={active ? "text-bg" : "text-text"} />
          <span className="text-[20px] tracking-[0.06em] leading-none">{set.shortCode ?? set.code}</span>
        </span>
      </button>
      {set.early ? (
        <span className="absolute left-0 right-0 top-full mt-1 mono flex flex-col items-center text-[10px] leading-[1.15] tracking-[0.12em] text-green">
          <span>EARLY</span>
          <span>ACCESS</span>
        </span>
      ) : (
        <span className="absolute left-0 right-0 top-full mt-1 mono text-center text-[10px] leading-none tracking-[0.06em] text-muted">
          {chipDateLabel(set)}
        </span>
      )}
    </div>
  );
}

function SetOverflow({
  sets,
  activeCode,
  onChange,
}: {
  sets: SetSummary[];
  activeCode: string;
  onChange: (code: string) => void;
}) {
  const options: FilterOption[] = sets.map((s) => ({
    value: s.code,
    label: s.name,
    section: isMtgoFlashbackCode(s.code) ? MTGO_SECTION : undefined,
  }));
  const renderOption = (option: FilterOption) => {
    const set = sets.find((s) => s.code === option.value);
    const named = isCubeCode(option.value);
    return (
      <span className="flex w-full min-w-0 items-center gap-3">
        <SetGlyph code={set ? setGlyphCode(set) : option.value} size={22} />
        <span className="text-[20px] leading-none truncate">{named ? option.label : option.value}</span>
        {!named && (
          <span className="text-muted text-[13px] tracking-[0.06em] truncate">{option.label}</span>
        )}
      </span>
    );
  };
  return (
    <FilterDropdown
      value={activeCode}
      options={options}
      onChange={onChange}
      align="right"
      searchable
      renderOption={renderOption}
      renderTrigger={({ open, toggle }) => (
        <button
          type="button"
          onClick={toggle}
          className="group block cursor-pointer transition-colors"
          style={{ clipPath: CHAMFER, background: "#3b4458", padding: 1, minHeight: 42 }}
        >
          <span
            className="flex items-center gap-2 min-w-[98px] pl-[17px] pr-[21px] font-display transition-colors h-full bg-surface text-text group-hover:bg-surface2"
            style={{ clipPath: CHAMFER, minHeight: 40 }}
          >
            <span className="text-[20px] tracking-[0.06em] leading-none">
              +{sets.length} {sets.length === 1 ? "SET" : "SETS"}
            </span>
            <ChevronDown
              strokeWidth={2.5}
              className={cn("text-muted h-4 w-4 transition-transform", open && "rotate-180")}
            />
          </span>
        </button>
      )}
    />
  );
}

// Mobile: a single button that opens a sheet of options.
export function SetSwitcherMobile({
  sets,
  activeCode,
  onChange,
  onPrefetch,
}: {
  sets: SetSummary[];
  activeCode: string;
  onChange: (code: string) => void;
  onPrefetch?: (code: string) => void;
}) {
  const [open, setOpen] = React.useState(false);
  const active = sets.find((s) => s.code === activeCode) ?? sets[0];
  const ref = React.useRef<HTMLDivElement>(null);

  React.useEffect(() => {
    if (!open) return;
    const onClickOutside = (e: MouseEvent) => {
      if (!ref.current?.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    document.addEventListener("mousedown", onClickOutside);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onClickOutside);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  return (
    <div ref={ref} className="relative">
      <button
        onClick={() => setOpen((o) => !o)}
        className="w-full py-1.5 px-2.5 flex items-center gap-2 bg-transparent border border-border2 text-text font-display text-[13px] tracking-[0.12em] cursor-pointer"
      >
        <SetGlyph code={setGlyphCode(active)} size={16} />
        <span>{isCubeCode(active.code) ? active.name : active.code}</span>
        {active.isActive && (
          <span className="text-muted text-[10px] tracking-[0.18em]">· LIVE</span>
        )}
        <span className="flex-1" />
        <ChevronDown
          strokeWidth={2.5}
          className={cn("text-muted h-3.5 w-3.5 transition-transform", open && "rotate-180")}
        />
      </button>
      {open && (
        <div className="absolute left-0 right-0 top-[calc(100%+4px)] bg-surface border border-border2 z-20">
          {sets.map((s) => (
            <button
              key={s.code}
              onClick={() => {
                onChange(s.code);
                setOpen(false);
              }}
              onTouchStart={onPrefetch ? () => onPrefetch(s.code) : undefined}
              onFocus={onPrefetch ? () => onPrefetch(s.code) : undefined}
              className={cn(
                "w-full py-[9px] px-2.5 flex items-center gap-2 border-none border-b border-border text-text font-display text-[13px] tracking-[0.1em] cursor-pointer text-left transition-colors",
                s.code === activeCode ? "bg-surface2" : "bg-transparent hover:bg-surface2",
              )}
            >
              <SetGlyph code={setGlyphCode(s)} size={16} />
              <span>{isCubeCode(s.code) ? s.name : s.shortCode ?? s.code}</span>
              {!isCubeCode(s.code) && (
                <span className="text-muted text-[10px] tracking-[0.06em] flex-1">{s.name}</span>
              )}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
