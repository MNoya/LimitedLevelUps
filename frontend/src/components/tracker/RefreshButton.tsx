import { useEffect, useState } from "react";
import { RefreshCw } from "lucide-react";
import { useQueryClient } from "@tanstack/react-query";

import { cn } from "../../lib/utils";
import { Tooltip } from "../Tooltip";
import { refreshDraftData } from "../../data/trackerApi";
import { HEADER_CLS } from "./trackerStyles";

const RESULT_VISIBLE_MS = 10_000;

export function RefreshButton({ setCode, className }: { setCode: string; className?: string }) {
  const qc = useQueryClient();
  const [running, setRunning] = useState(false);
  const [result, setResult] = useState<{ text: string; failed: boolean } | null>(null);

  useEffect(() => {
    if (!result) {
      return;
    }
    const timer = setTimeout(() => setResult(null), RESULT_VISIBLE_MS);
    return () => clearTimeout(timer);
  }, [result]);

  const run = async () => {
    setRunning(true);
    try {
      const counts = await refreshDraftData(setCode);
      setResult({ text: refreshSummary(counts), failed: false });
      qc.invalidateQueries({ queryKey: ["tracker-drafts"] });
    } catch {
      setResult({ text: "Refresh failed", failed: true });
    }
    setRunning(false);
  };

  return (
    <span className={cn("relative inline-flex items-center", className)}>
      <Tooltip label="Pull new drafts and deck detail from 17lands">
        <button
          onClick={run}
          disabled={running || !setCode}
          className={cn(
            "flex items-center gap-1.5 border border-border2 px-2.5 py-1 text-subtle",
            "hover:text-text hover:border-border disabled:opacity-50",
            HEADER_CLS,
          )}
        >
          <RefreshCw size={13} className={running ? "animate-spin" : undefined} />
          17L
        </button>
      </Tooltip>
      {result && (
        <span
          className={cn(
            "absolute left-1/2 -translate-x-1/2 bottom-full mb-2 z-30 whitespace-nowrap animate-fadeUpIn",
            "rounded-md border border-border2 bg-black px-3 py-2 font-body text-[13px] leading-none",
            "shadow-lg shadow-black/60",
            result.failed ? "text-red" : "text-text",
          )}
        >
          {result.text}
        </span>
      )}
    </span>
  );
}

function refreshSummary({ ingested, filled, missed }: { ingested: number; filled: number; missed: number }): string {
  const parts: string[] = [];
  if (ingested) {
    parts.push(`${ingested} new`);
  }
  if (filled) {
    parts.push(`${filled} fetched`);
  }
  if (missed) {
    parts.push(`${missed} unavailable`);
  }
  return parts.length ? parts.join(", ") : "Nothing to update";
}
