import { useEffect, useState } from "react";

import { nextTurnover } from "../../data/dailySealed";

const TICK_MS = 30_000;

export const useCountdown = (active: boolean): string | null => {
  const [now, setNow] = useState(() => new Date());
  useEffect(() => {
    if (!active) {
      return;
    }
    const timer = window.setInterval(() => setNow(new Date()), TICK_MS);
    return () => window.clearInterval(timer);
  }, [active]);
  if (!active) {
    return null;
  }
  const minutes = Math.max(0, Math.floor((nextTurnover(now).getTime() - now.getTime()) / 60_000));
  return `${Math.floor(minutes / 60)}h ${minutes % 60}m`;
};
