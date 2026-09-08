export function P0P1ProgressBar({
  filled,
  total,
  isComplete,
  doneLabel,
  doneHint,
}: {
  filled: number;
  total: number;
  isComplete: boolean;
  doneLabel?: string;
  doneHint?: string;
}) {
  if (isComplete && doneLabel) {
    return (
      <div className="h-7 rounded-full bg-green/10 border border-green/30 flex items-center justify-center gap-2 px-3 animate-fadeIn">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" className="shrink-0">
          <path
            d="M5 12.5 L10 17.5 L19 7"
            stroke="#2ee85c"
            strokeWidth="2.5"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        </svg>
        <span className="font-display text-green text-[14px] tracking-[0.08em] leading-none whitespace-nowrap">
          {doneLabel}
        </span>
        {doneHint && <span className="font-body text-subtle text-[12px] leading-none whitespace-nowrap">{doneHint}</span>}
      </div>
    );
  }

  const pct = Math.round((filled / total) * 100);
  return (
    <div className="flex items-center gap-3">
      <div className="flex-1 h-2 bg-surface2 overflow-hidden rounded-full">
        <div
          className={`h-full rounded-full transition-all ${isComplete ? "bg-green" : "bg-green/70"}`}
          style={{ width: `${pct}%` }}
        />
      </div>
      <span className={`font-num tabular-nums text-[12px] shrink-0 ${isComplete ? "text-green" : "text-muted"}`}>
        {filled}/{total}
      </span>
    </div>
  );
}
