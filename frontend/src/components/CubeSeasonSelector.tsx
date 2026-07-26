import { useEffect, useRef, useState } from "react";
import { SetGlyph } from "./Brand";
import { ChevronDown } from "./Icons";
import { isCubeSeasonCode } from "../data/utils";
import { cubeBoardCode, CUBE_VARIANTS, SEASONED_CUBE_VARIANT } from "../data/cubeVariants";
import { cn } from "../lib/utils";
import type { CubeSeason } from "../types/leaderboard";

const LIFETIME_LABEL = "LIFETIME";

interface BoardOption {
  value: string;
  label: string;
  glyph: string;
  trigger?: string;
}

// Arena swaps its cube every few sets; this picks which cube, or which of the seasoned cube's set
// windows, the board scores over. The seasoned cube leads as LIFETIME with its seasons under it,
// then one entry per other cube, historical ones last. Each option shows its own symbol.
//
// The "hero" variant renders inline, matched to the set-hero date line so the CUBE header keeps a
// normal set's height; "mobile" is a tappable boxed trigger.
export function CubeSeasonSelector({
  activeSet,
  seasons,
  onSelect,
  variant = "hero",
}: {
  activeSet: string;
  seasons: CubeSeason[] | undefined;
  onSelect: (setCode: string) => void;
  variant?: "hero" | "mobile";
}) {
  const seasonedBoard = cubeBoardCode(SEASONED_CUBE_VARIANT.slug);
  const value = isCubeSeasonCode(activeSet) ? activeSet : seasonedBoard;
  const rowByCode = new Map((seasons ?? []).map((s) => [s.setCode, s]));
  // Every cube comes from the registry, so the list is complete before any data arrives; only the
  // seasons wait on the view. A slow fetch never hides a board, it just delays the seasons.
  const boards: BoardOption[] = [
    ...(seasons ?? [])
      .filter((s) => s.kind === "season")
      .map((s) => ({ value: s.setCode, label: `${s.label} SEASON`, glyph: s.label })),
    // A cube without seasons is one window, so the closed selector spells that out
    ...CUBE_VARIANTS.filter((v) => !v.seasoned).map((v) => ({
      value: cubeBoardCode(v.slug),
      label: v.name.toUpperCase(),
      trigger: `LIFETIME`,
      glyph: cubeBoardCode(v.slug),
    })),
  ];
  // Cubes and seasons interleave in one historical order, newest run first, so a cube that ran after
  // a season sits above it. A cube with no drafts yet has no date and falls to the bottom.
  const lastEventOf = (code: string) => rowByCode.get(code)?.lastEvent ?? "";
  boards.sort((a, b) => lastEventOf(b.value).localeCompare(lastEventOf(a.value)));

  const options: BoardOption[] = [
    { value: seasonedBoard, label: LIFETIME_LABEL, glyph: seasonedBoard },
    ...boards,
  ];
  const selected = options.find((o) => o.value === value) ?? options[0];
  const triggerLabel = selected.trigger ?? selected.label;
  const [open, setOpen] = useState(false);
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

  const hero = variant === "hero";
  return (
    <div ref={ref} className={cn("relative", hero ? "" : "flex-1 min-w-0")}>
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className={cn(
          "flex items-center cursor-pointer transition-colors font-display leading-none",
          hero
            ? "gap-2 text-[20px] tracking-[0.04em] text-muted hover:text-text"
            : "w-full gap-2 bg-transparent border border-border2 text-text px-2.5 py-1.5 text-[15px] tracking-[0.12em] hover:bg-surface",
          !hero && open && "bg-surface",
        )}
      >
        <SetGlyph code={selected.glyph} size={hero ? 22 : 20} />
        <span className={cn(hero ? "text-text" : "")}>{triggerLabel}</span>
        {!hero && <span className="flex-1" />}
        <ChevronDown
          strokeWidth={2.5}
          className={cn("transition-transform", hero ? "h-3.5 w-3.5" : "h-3 w-3", open && "rotate-180")}
        />
      </button>

      {open && (
        <div
          className="absolute left-0 top-[calc(100%+4px)] w-max max-w-[calc(100vw-24px)] bg-surface border border-border2 z-50 shadow-lg"
          role="listbox"
        >
          {options.map((o, i) => {
            const isSelected = o.value === value;
            return (
              <button
                key={o.value}
                type="button"
                onClick={() => {
                  onSelect(o.value);
                  setOpen(false);
                }}
                role="option"
                aria-selected={isSelected}
                className={cn(
                  "w-full text-left flex items-center gap-2.5 font-display cursor-pointer transition-colors whitespace-nowrap px-3.5 py-2 text-[15px] tracking-[0.08em]",
                  i > 0 && "border-t border-border",
                  isSelected ? "bg-surface2 text-text" : "bg-transparent text-text hover:bg-surface2",
                )}
              >
                <SetGlyph code={o.glyph} size={20} />
                {o.label}
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}
