import { cn } from "../lib/utils";
import { winRateColor, wilsonInterval } from "../data/winRate";

// Win rate rendered as the payoff number: colored by value, with a Wilson 95% interval bar beneath.
// A small sample yields a wide band; n is read off the bar rather than printed.
export function WinRate({ rate, games, size = 17 }: { rate: number | null; games: number; size?: number }) {
  const color = winRateColor(rate);
  const ci = rate == null ? null : wilsonInterval(rate, games);
  return (
    <div className="inline-flex flex-col items-end gap-1">
      <span className={cn("font-num font-medium leading-none")} style={{ fontSize: size, color }}>
        {rate == null ? "—" : `${(rate * 100).toFixed(1)}%`}
      </span>
      {ci ? <CiBar lo={ci.lo} hi={ci.hi} p={rate!} color={color} /> : null}
    </div>
  );
}

const DOMAIN_MIN = 0.25;
const DOMAIN_MAX = 0.75;
const BAR_WIDTH = 54;
const BAR_HEIGHT = 3;

function CiBar({ lo, hi, p, color }: { lo: number; hi: number; p: number; color: string }) {
  const x = (v: number) => Math.max(0, Math.min(1, (v - DOMAIN_MIN) / (DOMAIN_MAX - DOMAIN_MIN))) * BAR_WIDTH;
  const bandLeft = x(lo);
  const bandWidth = Math.max(2, x(hi) - bandLeft);
  return (
    <div className="relative" style={{ width: BAR_WIDTH, height: BAR_HEIGHT }}>
      <div className="absolute inset-0 rounded-full bg-surface2" />
      <div
        className="absolute rounded-full"
        style={{ left: bandLeft, width: bandWidth, top: 0, height: BAR_HEIGHT, backgroundColor: color, opacity: 0.45 }}
      />
      <div
        className="absolute rounded-full"
        style={{ left: x(p) - 1, width: 2, top: -1, height: BAR_HEIGHT + 2, backgroundColor: color }}
      />
    </div>
  );
}
