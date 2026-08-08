import { useEffect, useRef, useState } from "react";
import { SetGlyph } from "../Brand";
import { ChevronDown } from "../Icons";
import { FilterDropdown, type FilterOption } from "../FilterDropdown";
import { cn } from "../../lib/utils";
import { useSetVisibleCap } from "../../lib/use-is-mobile";
import type { ContestChipInfo } from "../../data/p0p1Slots";

const CHAMFER = "polygon(8px 0, 100% 0, calc(100% - 8px) 100%, 0 100%)";

const MONTHS = ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"];

function chipDateLabel(release: number): string {
  const d = new Date(release);
  const month = MONTHS[d.getUTCMonth()];
  const year = String(d.getUTCFullYear()).slice(2);
  return month ? `${month} '${year}` : "";
}

const MAX_NEWER_CONTEXT = 2;

function partitionContests(
  contests: ContestChipInfo[],
  selectedCode: string,
  cap: number,
) {
  const votingPin = contests.find((c) => c.status === "live" && c.code !== selectedCode);
  const leadPins: ContestChipInfo[] = votingPin ? [votingPin] : [];
  const pinnedCodes = new Set(leadPins.map((c) => c.code));
  const history = contests.filter((c) => !pinnedCodes.has(c.code));

  const windowSize = Math.max(1, cap - leadPins.length);
  if (history.length <= windowSize) {
    return { visible: [...leadPins, ...history], overflow: [] };
  }

  const selectedIndex = history.findIndex((c) => c.code === selectedCode);
  const maxStart = history.length - windowSize;
  const newerContext = Math.min(MAX_NEWER_CONTEXT, Math.max(0, windowSize - 2));
  const desiredStart = selectedIndex < 0 ? 0 : selectedIndex - newerContext;
  const start = Math.max(0, Math.min(desiredStart, maxStart));
  const window = history.slice(start, start + windowSize);

  const windowCodes = new Set(window.map((c) => c.code));
  const overflow = history.filter((c) => !windowCodes.has(c.code));
  return { visible: [...leadPins, ...window], overflow };
}

// --- Desktop ---

export function P0P1ContestSwitcherDesktop({
  contests,
  activeCode,
  onSelect,
}: {
  contests: ContestChipInfo[];
  activeCode: string;
  onSelect: (code: string) => void;
}) {
  const cap = useSetVisibleCap(contests.length);
  const { visible, overflow } = partitionContests(contests, activeCode, cap);
  return (
    <div className="flex gap-1.5">
      {visible.map((c) => (
        <ContestChip
          key={c.code}
          contest={c}
          active={c.code === activeCode}
          onClick={() => onSelect(c.code)}
        />
      ))}
      {overflow.length > 0 && (
        <ContestOverflow contests={overflow} activeCode={activeCode} onSelect={onSelect} />
      )}
    </div>
  );
}

function ContestChip({
  contest,
  active,
  onClick,
}: {
  contest: ContestChipInfo;
  active: boolean;
  onClick: () => void;
}) {
  const isLive = contest.status === "live";
  const isResults = contest.status === "results";
  const hasGreenBorder = !active && (isLive || isResults);

  return (
    <div className="relative">
      <button
        onClick={onClick}
        className="group block cursor-pointer"
        style={{
          clipPath: CHAMFER,
          background: active ? "#2ee85c" : hasGreenBorder ? "#2ee85c" : "#3b4458",
          padding: 1,
          minHeight: 42,
        }}
      >
        <span
          className={cn(
            "flex items-center justify-center gap-[7px] w-[98px] px-[17px] font-display h-full",
            active
              ? "bg-green text-bg"
              : "bg-surface text-text group-hover:bg-surface2",
          )}
          style={{ clipPath: CHAMFER, minHeight: 40 }}
        >
          <SetGlyph
            code={contest.code}
            size={22}
            className={cn(
              "shrink-0",
              active ? "text-bg" : hasGreenBorder ? "text-green" : "text-text",
            )}
          />
          <span className="text-[20px] tracking-[0.06em] leading-none">{contest.code}</span>
        </span>
      </button>
      <span
        className={cn(
          "absolute left-0 right-0 top-full mt-1 mono text-center text-[10px] leading-none tracking-[0.06em]",
          isLive ? "text-green tracking-[0.12em]" : isResults && !active ? "text-green/70 tracking-[0.08em]" : "text-muted",
        )}
      >
        {isLive ? "LIVE" : isResults ? "RESULTS" : chipDateLabel(contest.release)}
      </span>
    </div>
  );
}

function ContestOverflow({
  contests,
  activeCode,
  onSelect,
}: {
  contests: ContestChipInfo[];
  activeCode: string;
  onSelect: (code: string) => void;
}) {
  const options: FilterOption[] = contests.map((c) => ({
    value: c.code,
    label: c.name,
  }));
  const renderOption = (option: FilterOption) => {
    const contest = contests.find((c) => c.code === option.value);
    return (
      <span className="flex w-full min-w-0 items-center gap-3">
        <SetGlyph code={option.value} size={22} />
        <span className="text-[20px] leading-none">{option.value}</span>
        <span className="text-muted text-[13px] tracking-[0.06em] truncate">{option.label}</span>
        {contest && (
          <span className="ml-auto text-dim text-[11px] tracking-[0.04em] mono shrink-0">
            {chipDateLabel(contest.release)}
          </span>
        )}
      </span>
    );
  };
  return (
    <FilterDropdown
      value={activeCode}
      options={options}
      onChange={onSelect}
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
              +{contests.length} MORE
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

// --- Mobile ---

function mobileStatusLabel(contest: ContestChipInfo): string {
  if (contest.status === "live") return "· LIVE";
  if (contest.status === "results") return "· RESULTS";
  return "";
}

function mobileBadge(contest: ContestChipInfo): { text: string; className: string } {
  if (contest.status === "live") return { text: "LIVE", className: "text-green" };
  if (contest.status === "results") return { text: "RESULTS", className: "text-green/70" };
  return { text: chipDateLabel(contest.release), className: "text-dim" };
}

export function P0P1ContestSwitcherMobile({
  contests,
  activeCode,
  onSelect,
}: {
  contests: ContestChipInfo[];
  activeCode: string;
  onSelect: (code: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const active = contests.find((c) => c.code === activeCode) ?? contests[0];
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
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
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="w-full py-1.5 px-2.5 flex items-center gap-2 bg-transparent border border-border2 text-text font-display text-[13px] tracking-[0.12em] cursor-pointer"
      >
        <SetGlyph code={active.code} size={16} />
        <span>{active.code}</span>
        <span
          className={cn(
            "text-[10px] tracking-[0.18em]",
            active.status === "live" ? "text-green" : "text-muted",
          )}
        >
          {mobileStatusLabel(active)}
        </span>
        <span className="flex-1" />
        <ChevronDown
          strokeWidth={2.5}
          className={cn("text-muted h-3.5 w-3.5 transition-transform", open && "rotate-180")}
        />
      </button>
      {open && (
        <div className="absolute left-0 right-0 top-[calc(100%+4px)] bg-surface border border-border2 z-20">
          {contests.map((c) => {
            const badge = mobileBadge(c);
            return (
              <button
                key={c.code}
                type="button"
                onClick={() => {
                  onSelect(c.code);
                  setOpen(false);
                }}
                className={cn(
                  "w-full py-[9px] px-2.5 flex items-center gap-2 border-none border-b border-border text-text font-display text-[13px] tracking-[0.1em] cursor-pointer text-left transition-colors",
                  c.code === activeCode ? "bg-surface2" : "bg-transparent hover:bg-surface2",
                )}
              >
                <SetGlyph code={c.code} size={16} />
                <span>{c.code}</span>
                <span className="text-muted text-[10px] tracking-[0.06em] flex-1 truncate">
                  {c.name}
                </span>
                <span className={cn("text-[10px] tracking-[0.06em] mono shrink-0", badge.className)}>
                  {badge.text}
                </span>
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}
