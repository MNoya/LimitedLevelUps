import { SetGlyph } from "../Brand";
import type { FeaturedContest } from "../../data/p0p1Slots";
import { formatCountdown, useNow } from "../../lib/countdown";

/** Counts down to the instant the featured contest flips to the next set's voting window. Ticks per
 * second so a frozen results page stays accurate without a reload, and renders nothing once that
 * instant passes, by which point the resolver has already moved the featured contest on. */
export function NextContestOpens({ next }: { next: FeaturedContest["next"] }) {
  const now = useNow(1000);
  if (!next || next.previewsOpen.getTime() <= now) return null;

  return (
    <span className="flex items-center justify-center gap-2">
      <SetGlyph code={next.code} size={17} className="text-white" />
      <span className="font-semibold text-text">{next.code}</span>
      <span>picks open</span>
      <span
        className="mono text-green tabular-nums border border-border2 bg-surface2/40 px-2 py-1"
        style={{ fontSize: 13, lineHeight: 1, letterSpacing: "0.02em" }}
      >
        {formatCountdown(next.previewsOpen.getTime(), now)}
      </span>
    </span>
  );
}
