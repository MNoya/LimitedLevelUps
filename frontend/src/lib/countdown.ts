import { useEffect, useState } from "react";

/** Current time, re-rendering on an interval so clock-derived values refresh without a page load.
 * The returned timestamp doubles as a dependency handle for memos that read the clock. */
export function useNow(intervalMs: number): number {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), intervalMs);
    return () => clearInterval(id);
  }, [intervalMs]);
  return now;
}

export function formatCountdown(targetMs: number, nowMs: number): string {
  let secs = Math.max(0, Math.floor((targetMs - nowMs) / 1000));
  const days = Math.floor(secs / 86400);
  secs -= days * 86400;
  const hours = Math.floor(secs / 3600);
  secs -= hours * 3600;
  const minutes = Math.floor(secs / 60);
  const seconds = secs - minutes * 60;
  const pad = (n: number) => String(n).padStart(2, "0");
  if (days > 0) return `${days}d ${pad(hours)}:${pad(minutes)}:${pad(seconds)}`;
  return `${pad(hours)}:${pad(minutes)}:${pad(seconds)}`;
}
