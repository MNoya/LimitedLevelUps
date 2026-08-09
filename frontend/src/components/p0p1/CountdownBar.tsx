import { p0p1Now } from "../../data/p0p1DevState";
import type { P0P1Phase } from "../../data/p0p1Results";

export function P0P1CountdownBar({ from, to, phase }: { from: Date; to: Date; phase?: P0P1Phase }) {
  if (phase === "loading") {
    return <div className="w-full h-2 bg-surface2 overflow-hidden rounded-full animate-pulse" />;
  }

  const span = to.getTime() - from.getTime();
  const elapsed = p0p1Now() - from.getTime();
  const pct = Math.max(0, Math.min(100, Math.round((elapsed / span) * 100)));

  return (
    <div className="w-full h-2 bg-surface2 overflow-hidden rounded-full">
      <div className="h-full rounded-full bg-green/70 transition-all" style={{ width: `${pct}%` }} />
    </div>
  );
}
