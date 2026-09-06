import type { ReactNode } from "react";

import { podSlotName } from "../../data/utils";
import type { PodEventSummary } from "../../types/leaderboard";

const SPLIT_RE = /(#\d+|\bmock\b)/gi;

// The slot phrase alone. The set glyph to the left carries the format now
export function PodEventTitle({ event }: { event: PodEventSummary }): ReactNode {
  return podSlotName(event.name, event.setCode, event.formatLabel).toUpperCase();
}

// The green execution ordinal only ever leads the label, so a leading `#N` (and "MOCK") light up
// green; a later `#N` is a baked collision marker and renders muted, keeping the two senses of `#N`
// visually apart. Shared by the pod table medallion, the mobile stack, the draft reviewer, and every
// plain event label so the same words light up consistently.
export function highlightEventLabel(label: string): ReactNode {
  const parts = label.split(SPLIT_RE);
  return parts.map((part, i) => {
    if (/^mock$/i.test(part)) {
      return <span key={i} className="text-green">{part}</span>;
    }
    if (/^#\d+$/.test(part)) {
      const leadingOrdinal = parts.slice(0, i).join("").trim() === "";
      const tone = leadingOrdinal ? "text-green" : "text-muted";
      return <span key={i} className={tone}>{part}</span>;
    }
    return part;
  });
}
