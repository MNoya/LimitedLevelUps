import React from "react";
import { cn } from "../lib/utils";

// Win–loss record renderer. Two visual modes:
//   <Record wins={67} losses={16} />               → tricolor: W green, "–" dim, L muted
//   <Record wins={67} losses={16} mono />          → single tone, both text-colored
//   <Record wins={7} losses={2} mono color={...}>  → single tone, custom color

export function Record({
  wins,
  losses,
  mono = false,
  color,
  separatorMargin = 0,
  centered = false,
  className,
  style,
}: {
  wins: number;
  losses: number;
  mono?: boolean;
  color?: string;
  separatorMargin?: number;
  centered?: boolean;
  className?: string;
  style?: React.CSSProperties;
}) {
  if (centered) {
    const tricolor = !mono && !color;
    const gridStyle: React.CSSProperties = {
      ...style,
      display: "inline-grid",
      gridTemplateColumns: "1fr auto 1fr",
      alignItems: "center",
      ...(color ? { color } : null),
    };
    return (
      <span className={cn(mono && !color ? "text-text" : "", className)} style={gridStyle}>
        <span className={cn("text-right", tricolor && "text-green")}>{wins}</span>
        <span
          className="text-dim"
          style={separatorMargin ? { margin: `0 ${separatorMargin}px` } : undefined}
        >
          –
        </span>
        <span className={cn("text-left", tricolor && "text-muted")}>{losses}</span>
      </span>
    );
  }
  if (mono) {
    return (
      <span
        className={cn(color ? "" : "text-text", className)}
        style={{ ...(color ? { color } : null), ...style }}
      >
        {wins}
        <span
          className="text-dim"
          style={separatorMargin ? { margin: `0 ${separatorMargin}px` } : undefined}
        >
          –
        </span>
        {losses}
      </span>
    );
  }
  return (
    <span className={className} style={style}>
      <span className="text-green">{wins}</span>
      <span className="text-dim">–</span>
      <span className="text-muted">{losses}</span>
    </span>
  );
}
