import { cn } from "../../lib/utils";

export const PIXEL_BUTTON = cn(
  "relative inline-flex items-center justify-center gap-2 border-[3px] border-[color:var(--px-ink)] font-display",
  "leading-none shadow-[5px_5px_0_#05070a]",
  "after:absolute after:-top-[6px] after:-left-[6px] after:-right-[9px] after:-bottom-[9px] after:content-['']",
  "hover:-translate-y-0.5 hover:shadow-[6px_7px_0_#05070a] hover:brightness-110 hover:after:-bottom-[11px]",
  "active:translate-x-[3px] active:translate-y-[3px] active:shadow-[2px_2px_0_#05070a]",
  "active:after:-top-[9px] active:after:-left-[9px]",
);
export const GOLD_BUTTON = cn(
  PIXEL_BUTTON,
  "bg-[linear-gradient(180deg,#fff3cf_0%,#f6c95e_45%,#cf8e2c_100%)] text-[#1a120b]",
);
export const ACCENT_BUTTON = cn(PIXEL_BUTTON, "bg-[image:var(--px-button)] text-[color:var(--px-ink)]");
export const DARK_PIXEL_BUTTON = cn(PIXEL_BUTTON, "bg-[#2b3445] text-text");
export const WAITING_PIXEL_BUTTON = cn(
  "inline-flex cursor-not-allowed items-center justify-center gap-2 border-[3px] border-[color:var(--px-ink)]",
  "bg-[#3a404c] font-display leading-none text-[#9aa3b4] shadow-[inset_0_-3px_0_#2a2f38,5px_5px_0_#05070a]",
);
export const PIXEL_PANEL = cn(
  "border-[3px] border-[color:var(--px-ink)] bg-[color:var(--px-panel-glass)]",
  "shadow-[inset_0_0_0_2px_var(--px-rim),6px_6px_0_#05070a]",
);
export const PIXEL_TAG = cn(
  "border-[3px] border-[color:var(--px-ink)] bg-[color:var(--px-accent)] px-2.5 pt-1.5 pb-1 font-display text-xl",
  "leading-none text-[color:var(--px-ink)] shadow-[3px_3px_0_#05070a]",
);
export const PIXEL_WELL = "border-2 border-[color:var(--px-well-rim)] bg-[color:var(--px-well)]";
export const PIXEL_TOOLTIP = cn(
  "rounded-none border-2 border-[#1a120b] bg-[#16110c] px-2.5 py-1.5 font-display text-base leading-none text-text",
  "shadow-[3px_3px_0_#05070a]",
);
export const HARD_TEXT_SHADOW = "[text-shadow:2px_2px_0_#05070a]";
export const PIXEL_HEADING = cn("font-display leading-none text-[color:var(--px-accent)]", HARD_TEXT_SHADOW);
