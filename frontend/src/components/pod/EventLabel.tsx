import type { ReactNode } from "react";

import { podEventQualifier, podSlotName } from "../../data/utils";
import type { PodEventSummary } from "../../types/leaderboard";

const SPLIT_RE = /(#\d+|\bmock\b)/gi;

// Green execution-ordered `#N` (absent until the pod runs), the slot phrase, then a muted qualifier
export function PodEventTitle({
  event,
  omitQualifier = false,
}: {
  event: PodEventSummary;
  omitQualifier?: boolean;
}): ReactNode {
  const slot = podSlotName(event.name, event.setCode).toUpperCase();
  const qualifier = omitQualifier ? "" : podEventQualifier(event).toUpperCase();
  return (
    <>
      {event.ordinal != null && <span className="text-green">#{event.ordinal} </span>}
      {slot}
      {qualifier && <span className="text-muted">{qualifier}</span>}
    </>
  );
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
