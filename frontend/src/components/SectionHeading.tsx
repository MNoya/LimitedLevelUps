import React from "react";
import { cn } from "../lib/utils";

// The bordered section header used across the pods and cube pages: a display-font label on the left,
// optional inline controls, and either a right-aligned "<count> <unit>" or a free-form meta node.
export function SectionHeading({
  label,
  count,
  unit,
  compact,
  meta,
  controls,
  center,
  padLeftClass = "pl-2",
}: {
  label: string;
  count?: number;
  unit?: string;
  compact?: boolean;
  meta?: React.ReactNode;
  controls?: React.ReactNode;
  center?: React.ReactNode;
  padLeftClass?: string;
}) {
  if (compact) {
    return (
      <div className="flex items-baseline justify-between gap-3 py-2 pl-5 pr-3 border-b border-border">
        <span className="font-display text-text text-[14px] tracking-[0.16em] leading-none">{label}</span>
        {meta && (
          <span className="font-display text-[12px] tracking-[0.14em] leading-none text-muted">{meta}</span>
        )}
      </div>
    );
  }
  return (
    <div className={cn("relative flex items-center justify-between h-[50px] pr-5 border-b border-border gap-4", padLeftClass)}>
      <div className={cn("min-w-0 flex items-center gap-3", !center && "flex-1 basis-0")}>
        <span className="shrink-0 font-display text-text tracking-[0.18em] leading-none" style={{ fontSize: 17 }}>
          {label}
        </span>
        {controls}
      </div>
      {center && <div className="min-w-0 flex-1 flex justify-center">{center}</div>}
      {meta ? (
        <div className="absolute inset-y-0 right-0 flex items-center">{meta}</div>
      ) : (
        <div className={cn("min-w-0 flex justify-end", !center && "flex-1 basis-0")}>
          {!unit ? null : count === undefined ? (
            <span className="inline-block h-3.5 w-24 bg-surface2 animate-pulse" />
          ) : count === 0 ? null : (
            <span
              className="font-display tracking-[0.18em] leading-none flex items-baseline gap-1.5 whitespace-nowrap"
              style={{ fontSize: 17 }}
            >
              <span className="tabular-nums text-subtle">{count}</span>
              <span className="text-muted">{unit}</span>
            </span>
          )}
        </div>
      )}
    </div>
  );
}
