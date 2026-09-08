// Surfaced when a useQuery throws (network failure, RLS denial, etc).

export function ErrorState({
  error,
  onRetry,
  compact = false,
}: {
  error: Error;
  onRetry?: () => void;
  compact?: boolean;
}) {
  return (
    <div className={compact ? "p-6 text-center" : "p-10 text-center"}>
      <div
        className={
          compact
            ? "font-display text-base tracking-[0.04em] text-red"
            : "font-display text-[22px] tracking-[0.04em] text-red"
        }
      >
        SOMETHING WENT WRONG
      </div>
      <div className="font-mono text-[11px] text-muted mt-2 max-w-[460px] mx-auto break-words">
        {error.message || "UNKNOWN ERROR"}
      </div>
      {onRetry && (
        <button
          onClick={onRetry}
          className="mt-3 py-1.5 px-[18px] bg-transparent border border-border2 text-text font-display text-[12px] tracking-[0.16em] cursor-pointer transition-colors hover:bg-surface2"
        >
          RETRY
        </button>
      )}
    </div>
  );
}
