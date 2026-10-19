import { DailyCountdown } from "../GameChrome";

export function NextPacksCountdown({ className }: { className?: string }) {
  return <DailyCountdown label="New Packs In" className={className} />;
}
