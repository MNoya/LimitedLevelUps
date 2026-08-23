import { useEffect, useRef, useState } from "react";
import { SetGlyph } from "../Brand";
import { ChevronDown } from "../Icons";
import { FilterDropdown, type FilterOption } from "../FilterDropdown";
import { cn } from "../../lib/utils";
import { CHAMFER } from "./P0P1BallotScorecard";
import type { ContestChipInfo } from "../../data/p0p1Slots";

const MONTHS = ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"];

function chipDateLabel(release: number): string {
  const d = new Date(release);
  const month = MONTHS[d.getUTCMonth()];
  const year = String(d.getUTCFullYear()).slice(2);
  return month ? `${month} '${year}` : "";
}

function statusLabel(contest: ContestChipInfo): string {
  if (contest.status === "live") return "· LIVE";
  if (contest.status === "results") return "· RESULTS";
  return "";
}

function statusBadge(contest: ContestChipInfo): { text: string; className: string } {
  if (contest.status === "live") return { text: "LIVE", className: "text-green" };
  if (contest.status === "results") return { text: "RESULTS", className: "text-green/70" };
  return { text: chipDateLabel(contest.release), className: "text-dim" };
}

function renderContestOption(contests: ContestChipInfo[]) {
  return (option: FilterOption) => {
    const contest = contests.find((c) => c.code === option.value);
    const badge = contest ? statusBadge(contest) : null;
    return (
      <span className="flex w-full min-w-0 items-center gap-3">
        <SetGlyph code={option.value} size={22} />
        <span className="text-[20px] leading-none">{option.value}</span>
        <span className="text-muted text-[13px] tracking-[0.06em] truncate">{option.label}</span>
        {badge && (
          <span className={cn("ml-auto text-[11px] tracking-[0.04em] mono shrink-0", badge.className)}>
            {badge.text}
          </span>
        )}
      </span>
    );
  };
}

// P0P1-specific cap. Not useSetVisibleCap: that hook's breakpoint table was sized for the
// leaderboard banner owning the full page width, a different budget than a results-heading gutter.
const P0P1_VISIBLE_BREAKPOINTS: Array<[number, number]> = [
  [1440, 6],
  [1280, 5],
  [1152, 4],
];
const P0P1_VISIBLE_FLOOR = 3;

function computeP0P1VisibleCap(): number {
  if (typeof window === "undefined") return P0P1_VISIBLE_FLOOR;
  for (const [w, cap] of P0P1_VISIBLE_BREAKPOINTS) {
    if (window.matchMedia(`(min-width: ${w}px)`).matches) return cap;
  }
  return P0P1_VISIBLE_FLOOR;
}

function useP0P1VisibleCap(): number {
  const [cap, setCap] = useState(computeP0P1VisibleCap);
  useEffect(() => {
    const mqls = P0P1_VISIBLE_BREAKPOINTS.map(([w]) => window.matchMedia(`(min-width: ${w}px)`));
    const update = () => setCap(computeP0P1VisibleCap());
    mqls.forEach((m) => m.addEventListener("change", update));
    update();
    return () => mqls.forEach((m) => m.removeEventListener("change", update));
  }, []);
  return cap;
}

// --- Desktop pills (postVoting / midway / final) ---

export function P0P1ContestSwitcherPills({
  contests,
  activeCode,
  onSelect,
}: {
  contests: ContestChipInfo[];
  activeCode: string;
  onSelect: (code: string) => void;
}) {
  const cap = useP0P1VisibleCap();
  if (contests.length <= 1) return null;
  const active = contests.find((c) => c.code === activeCode);
  const ordered = active ? [active, ...contests.filter((c) => c.code !== activeCode)] : contests;
  const visible = ordered.slice(0, cap);
  const overflow = ordered.slice(cap);
  return (
    <div className="flex items-center gap-1.5">
      {visible.map((c) => (
        <ContestPill
          key={c.code}
          contest={c}
          active={c.code === activeCode}
          onClick={() => onSelect(c.code)}
        />
      ))}
      {overflow.length > 0 && (
        <ContestPillsOverflow contests={overflow} activeCode={activeCode} onSelect={onSelect} />
      )}
    </div>
  );
}

function ContestPill({
  contest,
  active,
  onClick,
}: {
  contest: ContestChipInfo;
  active: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="group block cursor-pointer"
      style={{ clipPath: CHAMFER, background: active ? "#2ee85c" : "#3b4458", padding: 1 }}
    >
      <span
        className={cn(
          "flex items-center justify-center gap-1.5 px-3 h-[30px] font-display transition-colors",
          active ? "bg-green text-bg" : "bg-surface text-text group-hover:bg-surface2",
        )}
        style={{ clipPath: CHAMFER }}
      >
        <SetGlyph
          code={contest.code}
          size={16}
          className={cn("shrink-0", active ? "text-bg" : "text-text")}
        />
        <span className="text-[15px] tracking-[0.06em] leading-none">{contest.code}</span>
      </span>
    </button>
  );
}

function ContestPillsOverflow({
  contests,
  activeCode,
  onSelect,
}: {
  contests: ContestChipInfo[];
  activeCode: string;
  onSelect: (code: string) => void;
}) {
  const options: FilterOption[] = contests.map((c) => ({ value: c.code, label: c.name }));
  return (
    <FilterDropdown
      value={activeCode}
      options={options}
      onChange={onSelect}
      align="right"
      searchable
      renderOption={renderContestOption(contests)}
      renderTrigger={({ open, toggle }) => (
        <button
          type="button"
          onClick={toggle}
          className="group block cursor-pointer"
          style={{ clipPath: CHAMFER, background: "#3b4458", padding: 1 }}
        >
          <span
            className="flex items-center gap-2 h-[30px] px-3 font-display transition-colors bg-surface text-text group-hover:bg-surface2"
            style={{ clipPath: CHAMFER }}
          >
            <span className="text-[15px] tracking-[0.06em] leading-none">+{contests.length} MORE</span>
            <ChevronDown
              strokeWidth={2.5}
              className={cn("text-muted h-3.5 w-3.5 transition-transform", open && "rotate-180")}
            />
          </span>
        </button>
      )}
    />
  );
}

// --- Desktop dropdown (voting) ---

export function P0P1ContestSwitcherDropdown({
  contests,
  activeCode,
  onSelect,
}: {
  contests: ContestChipInfo[];
  activeCode: string;
  onSelect: (code: string) => void;
}) {
  if (contests.length <= 1) return null;
  const active = contests.find((c) => c.code === activeCode) ?? contests[0];
  const options: FilterOption[] = contests.map((c) => ({ value: c.code, label: c.name }));
  return (
    <FilterDropdown
      value={activeCode}
      options={options}
      onChange={onSelect}
      align="right"
      renderOption={renderContestOption(contests)}
      renderTrigger={({ open, toggle }) => (
        <button
          type="button"
          onClick={toggle}
          className="flex items-center gap-2 bg-transparent border border-border2 text-text font-display text-[15px] tracking-[0.12em] cursor-pointer transition-colors hover:bg-surface px-3.5 py-2"
        >
          <SetGlyph code={active.code} size={18} />
          <span>{active.code}</span>
          <span
            className={cn(
              "text-[11px] tracking-[0.18em]",
              active.status === "live" ? "text-green" : "text-muted",
            )}
          >
            {statusLabel(active)}
          </span>
          <ChevronDown
            strokeWidth={2.5}
            className={cn("text-muted h-4 w-4 transition-transform", open && "rotate-180")}
          />
        </button>
      )}
    />
  );
}

// --- Mobile ---

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
          {statusLabel(active)}
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
            const badge = statusBadge(c);
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
