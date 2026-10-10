import React from "react";
import type { To } from "react-router-dom";
import { cn } from "../lib/utils";
import { SetGlyph, setGlyphCode } from "./Brand";
import { BsAsterisk, ChevronDown } from "./Icons";
import { FilterDropdown, type FilterOption } from "./FilterDropdown";
import { isMtgoFlashbackCode } from "../data/mtgoSets";
import { cubeBoardGlyphCode, cubeForBoard } from "../data/cubeVariants";
import { podBoardWindowFor } from "../data/podFormats";
import { isCubeCode } from "../data/utils";
import type { SetSummary } from "../types/leaderboard";

const CHAMFER = "polygon(8px 0, 100% 0, calc(100% - 8px) 100%, 0 100%)";

// Sentinel value the dropdown emits for the set-agnostic lifetime profile
export const LIFETIME_SET_CODE = "__lifetime__";

export function SetCodeDropdown({
  sets,
  activeCode,
  onChange,
  hrefFor,
  size = "md",
  chamfer = true,
  includeLifetime = false,
}: {
  sets: SetSummary[];
  activeCode: string;
  onChange?: (code: string) => void;
  hrefFor?: (code: string) => To;
  size?: "sm" | "md";
  chamfer?: boolean;
  includeLifetime?: boolean;
}) {
  const options: FilterOption[] = React.useMemo(() => {
    const setOptions = [...sets]
      .sort((a, b) => {
        const aMtgo = isMtgoFlashbackCode(a.code);
        const bMtgo = isMtgoFlashbackCode(b.code);
        if (aMtgo !== bMtgo) return aMtgo ? 1 : -1;
        return b.startDate.localeCompare(a.startDate);
      })
      .map((s) => ({
        value: s.code,
        label: cubeForBoard(s.code)?.name ?? s.name,
        section: isMtgoFlashbackCode(s.code) ? "MTGO FLASHBACKS" : undefined,
      }));
    const lifetime = includeLifetime ? [{ value: LIFETIME_SET_CODE, label: "Lifetime" }] : [];
    return [...lifetime, ...setOptions];
  }, [sets, includeLifetime]);
  const setByCode = React.useMemo(() => new Map(sets.map((s) => [s.code, s])), [sets]);
  const glyphFor = (code: string) => {
    const set = setByCode.get(code);
    return set ? setGlyphCode(set) : code;
  };
  const tagFor = (code: string) => setByCode.get(code)?.shortCode ?? code;
  const selectedCode = boardCodeFor(activeCode);

  const isSm = size === "sm";
  const labelFs = isSm ? "text-[22px]" : "text-[26px]";
  // The chamfer's slant eats the corners, so it needs generous side padding; a rectangle doesn't.
  const padL = chamfer ? (isSm ? "pl-[14px]" : "pl-[16px]") : "pl-2";
  const padR = chamfer ? (isSm ? "pr-[18px]" : "pr-[20px]") : "pr-1.5";
  const gap = chamfer ? "gap-2" : "gap-1.5";
  const heightOuter = isSm ? 38 : 46;
  const heightInner = isSm ? 36 : 44;
  const glyphSize = isSm ? 26 : 32;
  const clip = chamfer ? CHAMFER : undefined;
  const isLifetime = activeCode === LIFETIME_SET_CODE;

  const renderOption = (option: FilterOption) =>
    option.value === LIFETIME_SET_CODE ? (
      <span className="flex w-full min-w-0 items-center gap-2.5">
        <span className="flex items-center justify-center" style={{ width: glyphSize, height: glyphSize }}>
          <BsAsterisk size={Math.round(glyphSize * 0.62)} />
        </span>
        <span className={cn(labelFs, "leading-none")}>ALL</span>
        <span className="text-muted text-[13px] tracking-[0.06em] truncate">{option.label}</span>
      </span>
    ) : (
      <span className="flex w-full min-w-0 items-center gap-2.5">
        <SetGlyph code={glyphFor(option.value)} size={glyphSize} />
        <span className={cn(labelFs, "leading-none")}>{tagFor(option.value)}</span>
        <span className="text-muted text-[13px] tracking-[0.06em] truncate">{option.label}</span>
      </span>
    );

  return (
    <FilterDropdown
      value={selectedCode}
      options={options}
      onChange={onChange}
      hrefFor={hrefFor}
      searchable
      searchPlaceholder="Search sets or codes…"
      mobileCentered
      renderOption={renderOption}
      renderTrigger={({ open, toggle }) => (
        <button
          type="button"
          onClick={toggle}
          className="group block cursor-pointer transition-colors"
          style={{ clipPath: clip, background: "#3b4458", padding: 1, minHeight: heightOuter }}
        >
          <span
            className={cn(
              "flex items-center font-display tracking-[0.06em] transition-colors h-full bg-surface text-text group-hover:bg-surface2",
              gap,
              padL,
              padR,
            )}
            style={{ clipPath: clip, minHeight: heightInner }}
          >
            {isLifetime ? (
              <span className="flex items-center justify-center" style={{ width: glyphSize, height: glyphSize }}>
                <BsAsterisk size={Math.round(glyphSize * 0.62)} />
              </span>
            ) : (
              <SetGlyph code={glyphFor(selectedCode)} size={glyphSize} />
            )}
            <span className={cn(labelFs, "leading-none")}>{isLifetime ? "ALL" : tagFor(selectedCode)}</span>
            <ChevronDown
              strokeWidth={2.5}
              className={cn(
                "text-muted transition-transform",
                isSm ? "h-4 w-4" : "h-[18px] w-[18px]",
                open && "rotate-180",
              )}
            />
          </span>
        </button>
      )}
    />
  );
}

function boardCodeFor(code: string): string {
  if (isCubeCode(code)) {
    return cubeBoardGlyphCode(code);
  }
  return podBoardWindowFor(code)?.board ?? code;
}
