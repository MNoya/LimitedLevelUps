// Per-episode transcription status derived from the transcript `source`. The `-basic` suffix marks a
// row the Claude pass has not touched yet; stripping it marks the pass done for either origin.

export type TranscriptTier = "youtube" | "done";

export interface TranscriptStatus {
  source: string;
  wordCount: number;
  sections: number;
  subsections: number;
}

export type TranscriptIndex = Map<string, TranscriptStatus>;

export function transcriptTier(source: string): TranscriptTier {
  if (source.endsWith("-basic")) {
    return "youtube";
  }
  return "done";
}

export const TIER_META: Record<TranscriptTier, { label: string; dot: string; text: string }> = {
  done: { label: "Done", dot: "bg-green", text: "text-green" },
  youtube: { label: "YouTube", dot: "bg-red", text: "text-red" },
};

export const NONE_META = { label: "None", dot: "bg-zinc-600", text: "text-zinc-500" };

export const TIER_RANK: Record<TranscriptTier, number> = { done: 2, youtube: 1 };
