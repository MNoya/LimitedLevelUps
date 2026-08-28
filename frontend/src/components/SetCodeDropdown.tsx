import React from "react";
import { cn } from "../lib/utils";
import { SetGlyph } from "./Brand";
import { BsAsterisk, ChevronDown } from "./Icons";
import { FilterDropdown, type FilterOption } from "./FilterDropdown";
import { isMtgoFlashbackCode } from "../data/mtgoSets";
import type { SetSummary } from "../types/leaderboard";

const CHAMFER = "polygon(8px 0, 100% 0, calc(100% - 8px) 100%, 0 100%)";

// Sentinel value the dropdown emits for the set-agnostic lifetime profile
export const LIFETIME_SET_CODE = "__lifetime__";

export function SetCodeDropdown({
  sets,
  activeCode,
  onChange,
  size = "md",
  chamfer = true,
  includeLifetime = false,
}: {
  sets: SetSummary[];
  activeCode: string;
  onChange: (code: string) => void;
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
        label: s.name,
        section: isMtgoFlashbackCode(s.code) ? "MTGO FLASHBACKS" : undefined,
      }));
    const lifetime = includeLifetime ? [{ value: LIFETIME_SET_CODE, label: "Lifetime" }] : [];
    return [...lifetime, ...setOptions];
  }, [sets, includeLifetime]);

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
        <SetGlyph code={option.value} size={glyphSize} />
        <span className={cn(labelFs, "leading-none")}>{option.value}</span>
        <span className="text-muted text-[13px] tracking-[0.06em] truncate">{option.label}</span>
      </span>
    );

  return (
    <FilterDropdown
      value={activeCode}
      options={options}
      onChange={onChange}
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
              <SetGlyph code={activeCode} size={glyphSize} />
            )}
            <span className={cn(labelFs, "leading-none")}>{isLifetime ? "ALL" : activeCode}</span>
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
