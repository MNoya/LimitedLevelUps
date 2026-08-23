import { useEffect, useRef, useState } from "react";
import { SetGlyph } from "../Brand";
import { ChevronDown } from "../Icons";
import { cn } from "../../lib/utils";
import { useWheelTrap } from "../../lib/use-wheel-trap";
import type { ContestChipInfo } from "../../data/p0p1Slots";

// TierSetDropdown-style contest selector, rendered as the P0P1 title. Desktop
// shows code + name; mobile shows glyph + code. Both open the same searchable
// option list.

const MONTHS = ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"];

function chipDateLabel(release: number): string {
  const d = new Date(release);
  const month = MONTHS[d.getUTCMonth()];
  const year = String(d.getUTCFullYear()).slice(2);
  return month ? `${month} '${year}` : "";
}

function statusBadge(contest: ContestChipInfo): { text: string; className: string } {
  if (contest.status === "live") return { text: "LIVE", className: "text-green" };
  if (contest.status === "results") return { text: "RESULTS", className: "text-green/70" };
  return { text: chipDateLabel(contest.release), className: "text-dim" };
}

export function P0P1ContestDropdown({
  contests,
  activeCode,
  onSelect,
  isMobile = false,
}: {
  contests: ContestChipInfo[];
  activeCode: string;
  onSelect: (code: string) => void;
  isMobile?: boolean;
}) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const ref = useRef<HTMLDivElement>(null);
  const menuRef = useWheelTrap<HTMLDivElement>(open);

  if (contests.length <= 1) return null;

  const active = contests.find((c) => c.code === activeCode) ?? contests[0];
  const searchable = contests.length > 7;
  const trimmed = query.trim().toLowerCase();
  const filtered = trimmed
    ? contests.filter((c) => c.code.toLowerCase().includes(trimmed) || c.name.toLowerCase().includes(trimmed))
    : contests;

  const close = () => setOpen(false);

  useEffect(() => {
    if (!open) return;
    const onClickOutside = (e: MouseEvent) => {
      if (!ref.current?.contains(e.target as Node)) close();
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") close();
    };
    document.addEventListener("mousedown", onClickOutside);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onClickOutside);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  useEffect(() => {
    if (!open) setQuery("");
  }, [open]);

  return (
    <div ref={ref} className="relative min-w-0">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
        className={cn(
          "group flex max-w-full min-w-0 items-center border border-border2 text-text transition-colors cursor-pointer hover:bg-surface",
          isMobile ? "gap-1.5 px-1.5 py-1" : "gap-3 px-2 py-1",
          open && "bg-surface",
        )}
      >
        {isMobile ? (
          <>
            <SetGlyph code={active.code} size={22} />
            <span className="font-display tracking-[0.04em] leading-none" style={{ fontSize: 22 }}>
              {active.code}
            </span>
            <ChevronDown
              strokeWidth={2.5}
              className={cn("text-muted transition-transform shrink-0 h-4 w-4", open && "rotate-180")}
            />
          </>
        ) : (
          <>
            <span className="font-display tracking-[0.04em] leading-[0.9]" style={{ fontSize: 44 }}>
              {active.code}
            </span>
            <span className="font-display text-[20px] text-muted tracking-[0.06em]">{active.name.toUpperCase()}</span>
            <ChevronDown
              strokeWidth={2.5}
              className={cn("text-muted transition-transform shrink-0 h-5 w-5", open && "rotate-180")}
            />
          </>
        )}
      </button>

      {open && (
        <div
          ref={menuRef}
          className="absolute left-0 top-full z-30 flex max-h-[min(60vh,400px)] min-w-full w-max max-w-[80vw] flex-col overflow-hidden border border-border2 bg-surface shadow-xl"
        >
          {searchable && (
            <div className="shrink-0 border-b border-border p-1.5">
              <input
                autoFocus
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="Search contests…"
                className="w-full border border-border bg-bg px-2.5 py-1.5 font-body text-[14px] text-text placeholder:text-dim outline-none focus:border-green"
              />
            </div>
          )}
          <div className="menu-scrollbar min-h-0 flex-1 overflow-y-auto">
            {filtered.map((c, i) => {
              const activeRow = c.code === activeCode;
              const badge = statusBadge(c);
              return (
                <button
                  key={c.code}
                  type="button"
                  onClick={() => {
                    onSelect(c.code);
                    close();
                  }}
                  className={cn(
                    "flex w-full items-center gap-3 border-l-2 px-3.5 py-2.5 text-left font-display tracking-[0.06em] transition-colors",
                    i > 0 && "border-t border-border",
                    activeRow
                      ? "border-l-green bg-surface2 text-green"
                      : "border-l-transparent text-text hover:bg-surface2",
                  )}
                >
                  <SetGlyph code={c.code} size={22} />
                  <span className={cn("flex-1 truncate text-[16px] leading-none", activeRow ? "text-green" : "text-text")}>
                    {c.name.toUpperCase()}
                  </span>
                  <span className={cn("text-[11px] tracking-[0.04em] mono shrink-0", activeRow ? "text-green" : badge.className)}>
                    {badge.text}
                  </span>
                </button>
              );
            })}
            {filtered.length === 0 && (
              <div className="px-3.5 py-3 font-body text-[14px] text-muted">No contests match</div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
