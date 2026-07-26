import { useEffect, useRef, useState } from "react";
import { SetGlyph } from "./Brand";
import { ChevronDown } from "./Icons";
import { isCubeSeasonCode } from "../data/utils";
import {
  cubeBoardCode, cubeListName, cubeVariantForBoard, CUBE_BOARD_PREFIX, CUBE_VARIANTS,
  SEASONED_CUBE_VARIANT,
  type CubeVariant,
} from "../data/cubeVariants";
import { cn } from "../lib/utils";
import type { CubeSeason } from "../types/leaderboard";

const LIFETIME_LABEL = "LIFETIME";

interface BoardOption {
  value: string;
  label: string;
  glyph: string;
  trigger?: string;
}

// Every whole-cube entry names its cube, so the list never asks the reader which cube LIFETIME meant;
// the trigger says which window of it is open.
const cubeOption = (variant: CubeVariant): BoardOption => ({
  value: cubeBoardCode(variant.slug),
  label: cubeListName(variant).toUpperCase(),
  trigger: LIFETIME_LABEL,
  glyph: cubeBoardCode(variant.slug),
});

const seasonOption = (season: CubeSeason): BoardOption => ({
  value: season.setCode,
  label: `${season.label} SEASON`,
  glyph: season.label,
});

const isWholeCube = (code: string) => cubeVariantForBoard(code) !== undefined;

// A board the view has not returned yet still names itself, so the trigger never borrows another
// board's label while the seasons load.
function optionFor(code: string): BoardOption {
  const variant = cubeVariantForBoard(code);
  if (variant) {
    return cubeOption(variant);
  }
  const label = code.slice(CUBE_BOARD_PREFIX.length);
  return { value: code, label: `${label} SEASON`, glyph: label };
}

// Arena swaps its cube every few sets; this picks which cube, or which of the seasoned cube's set
// windows, the board scores over. Cubes and their seasons list in one historical order, each option
// under its own symbol.
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
  const value = isCubeSeasonCode(activeSet) ? activeSet : cubeBoardCode(SEASONED_CUBE_VARIANT.slug);
  const rowByCode = new Map((seasons ?? []).map((s) => [s.setCode, s]));
  // Every cube comes from the registry, so the list is complete before any data arrives; only the
  // seasons wait on the view. A slow fetch never hides a board, it just delays the seasons.
  const options: BoardOption[] = [
    ...(seasons ?? []).filter((s) => s.kind === "season").map(seasonOption),
    ...CUBE_VARIANTS.map(cubeOption),
  ];
  // One historical order, newest run first, so the cube running now heads the list and a cube that
  // ran after a season sits above it. A cube shares its newest season's last draft, so the tiebreak
  // puts the whole cube above that season and its older seasons trail it. No dates yet sorts last.
  const lastEventOf = (code: string) => rowByCode.get(code)?.lastEvent ?? "";
  options.sort((a, b) => {
    const byRun = lastEventOf(b.value).localeCompare(lastEventOf(a.value));
    return byRun !== 0 ? byRun : Number(isWholeCube(b.value)) - Number(isWholeCube(a.value));
  });

  const selected = options.find((o) => o.value === value) ?? optionFor(value);
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
