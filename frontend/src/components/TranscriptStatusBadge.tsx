import { NONE_META, TIER_META, transcriptTier, type TranscriptStatus } from "../data/transcriptStatus";
import { cn } from "../lib/utils";

export function TranscriptStatusBadge({ status }: { status: TranscriptStatus | undefined }) {
  const meta = status ? TIER_META[transcriptTier(status.source)] : NONE_META;
  return <span className={cn("font-display text-[13px] uppercase tracking-[0.12em]", meta.text)}>{meta.label}</span>;
}
