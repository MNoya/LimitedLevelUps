import { useState, type ReactNode } from "react";

import { cn } from "../../../lib/utils";
import { ToggleSwitch } from "../../ToggleSwitch";
import { Tooltip } from "../../Tooltip";

export const SURFACE_BUTTON = cn(
  "flex h-9 shrink-0 items-center gap-2 rounded-md border border-border bg-surface2 px-2.5 transition-colors",
  "font-display text-[12px] tracking-[0.12em] text-subtle [-webkit-tap-highlight-color:transparent]",
  "hover:border-white/40 hover:bg-white/10 hover:text-text disabled:cursor-not-allowed disabled:opacity-40",
);

export const chipClass = (active: boolean) =>
  cn(
    "rounded border font-display transition-colors",
    active
      ? "border-green/60 bg-green/15 text-green"
      : "border-border bg-surface2 text-subtle hover:border-white/40 hover:bg-white/10 hover:text-text",
  );

export function SwitchToggle({
  label,
  on,
  onToggle,
  tooltip,
  ariaLabel,
  disabled = false,
}: {
  label: ReactNode;
  on: boolean;
  onToggle: () => void;
  tooltip: string;
  ariaLabel: string;
  disabled?: boolean;
}) {
  const [hover, setHover] = useState(false);
  return (
    <Tooltip label={tooltip} side="bottom" open={hover && !disabled}>
      <button
        onClick={onToggle}
        onPointerEnter={(e) => e.pointerType === "mouse" && setHover(true)}
        onPointerLeave={() => setHover(false)}
        disabled={disabled}
        role="switch"
        aria-checked={on}
        aria-label={ariaLabel}
        className={cn(
          "flex h-9 shrink-0 items-center gap-2 rounded-md border border-border bg-surface2 px-2.5 transition-colors",
          "[-webkit-tap-highlight-color:transparent]",
          disabled ? "cursor-not-allowed opacity-40" : "hover:border-white/40 hover:bg-white/10",
        )}
      >
        <span className={cn("font-display text-[12px] tracking-[0.12em]", on ? "text-green" : "text-subtle")}>
          {label}
        </span>
        <ToggleSwitch on={on} />
      </button>
    </Tooltip>
  );
}

export function ChevronIcon({ dir }: { dir: "up" | "down" | "left" | "right" }) {
  const path = {
    up: "M6 15l6-6 6 6",
    down: "M6 9l6 6 6-6",
    left: "M15 18l-6-6 6-6",
    right: "M9 6l6 6-6 6",
  }[dir];
  return (
    <svg className="shrink-0" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
      <path d={path} />
    </svg>
  );
}
