import { useEffect, useRef, useState, type ReactNode, type RefObject } from "react";

import { cn } from "../../../lib/utils";
import { wheelPixels } from "../../../lib/use-wheel-trap";
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

export const ZoomControl = ({
  label,
  fitting,
  canShrink,
  canGrow,
  onStep,
  onToggleFit,
  fitTooltip,
  highlightFit = true,
  className,
  labelClassName,
}: {
  label: string;
  fitting: boolean;
  canShrink: boolean;
  canGrow: boolean;
  onStep: (dir: 1 | -1) => void;
  onToggleFit?: () => void;
  fitTooltip: string;
  highlightFit?: boolean;
  className?: string;
  labelClassName?: string;
}) => {
  const stepButton = cn(
    "flex h-full w-8 items-center justify-center text-[16px] text-subtle transition-colors",
    "hover:bg-white/10 hover:text-text disabled:cursor-not-allowed disabled:opacity-40 disabled:hover:bg-transparent",
  );
  const labelCell = "flex min-w-[52px] flex-1 items-center justify-center border-x border-border px-1.5";
  const shown = (
    <span
      className={cn(
        "font-display text-[14px] tracking-[0.12em] tabular-nums [text-box:trim-both_cap_alphabetic]",
        fitting && highlightFit ? "text-green" : cn("text-subtle", labelClassName),
      )}
    >
      {fitting ? "FIT" : label}
    </span>
  );
  return (
    <div
      className={cn(
        "flex shrink-0 items-stretch overflow-hidden rounded-md border border-border bg-surface2",
        className,
      )}
    >
      <Tooltip label="Smaller cards (Ctrl+Scroll)" side="top">
        <button onClick={() => onStep(-1)} disabled={!canShrink} aria-label="Smaller cards" className={stepButton}>
          −
        </button>
      </Tooltip>
      {onToggleFit ? (
        <Tooltip label={fitTooltip} side="top">
          <button
            onClick={onToggleFit}
            role="switch"
            aria-checked={fitting}
            aria-label="Fit"
            className={cn(labelCell, "transition-colors hover:bg-white/10")}
          >
            {shown}
          </button>
        </Tooltip>
      ) : (
        <span className={labelCell}>{shown}</span>
      )}
      <Tooltip label="Bigger cards (Ctrl+Scroll)" side="top">
        <button onClick={() => onStep(1)} disabled={!canGrow} aria-label="Bigger cards" className={stepButton}>
          +
        </button>
      </Tooltip>
    </div>
  );
};

export const useCtrlWheelZoom = (ref: RefObject<HTMLElement | null>, onStep: (dir: 1 | -1) => void) => {
  const onStepRef = useRef(onStep);
  onStepRef.current = onStep;
  useEffect(() => {
    const el = ref.current;
    if (!el) {
      return;
    }
    let pending = 0;
    const onWheel = (e: WheelEvent) => {
      if (!e.ctrlKey) {
        return;
      }
      e.preventDefault();
      pending += wheelPixels(e, el);
      if (Math.abs(pending) < 40) {
        return;
      }
      onStepRef.current(pending < 0 ? 1 : -1);
      pending = 0;
    };
    el.addEventListener("wheel", onWheel, { passive: false });
    return () => el.removeEventListener("wheel", onWheel);
  }, [ref]);
};
