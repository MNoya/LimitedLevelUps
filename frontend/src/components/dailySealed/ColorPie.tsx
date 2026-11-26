import { Pips } from "../ManaPips";
import { colorSplashRows } from "../../data/dailySealedBreakdown";
import type { DailySealedBuild } from "../../data/dailySealed";

const PIE_ORDER = ["W", "U", "B", "R", "G"];
const PIE_SIZE = 220;
const GREEN = "#2ee85c";
const GUIDE = "#2a3140";



export const ColorPie = ({ builds, size = PIE_SIZE }: { builds: DailySealedBuild[]; size?: number }) => {
  const mains = new Map(colorSplashRows(builds).map((row) => [row.color as string, row.main]));
  return <StarChart mains={mains} total={builds.length} size={size} />;
};

const StarChart = ({ mains, total, size }: { mains: Map<string, number>; total: number; size: number }) => {
  const center = size / 2;
  const radius = center - 22;
  const guides = [1 / 3, 2 / 3, 1].map((step) => pentagon(center, radius * step));
  const labels = guides[2];
  const shape = PIE_ORDER.map((color, i) => {
    const share = Math.max(0.05, (mains.get(color) ?? 0) / Math.max(1, total));
    const angle = -Math.PI / 2 + (i * 2 * Math.PI) / 5;
    return `${center + radius * share * Math.cos(angle)},${center + radius * share * Math.sin(angle)}`;
  }).join(" ");
  return (
    <div className="flex justify-center">
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} role="img" aria-label="Share of builds in each color">
        {guides.map((guide, index) => (
          <polygon key={index} points={polygonPoints(guide)} fill="none" stroke={GUIDE} strokeWidth={1} />
        ))}
        {PIE_ORDER.map((color) => {
          const end = labels.get(color)!;
          return <line key={color} x1={center} y1={center} x2={end.x} y2={end.y} stroke={GUIDE} strokeWidth={1} />;
        })}
        <polygon points={shape} fill={GREEN} fillOpacity={0.22} stroke={GREEN} strokeWidth={2} strokeLinejoin="round" />
        {PIE_ORDER.map((color) => (
          <ColorLabel key={color} color={color} count={mains.get(color) ?? 0} at={labels.get(color)!} />
        ))}
      </svg>
    </div>
  );
};

const ColorLabel = ({ color, count, at }: { color: string; count: number; at: { x: number; y: number } }) => (
  <foreignObject x={at.x - 16} y={at.y - 9} width={32} height={34}>
    <div className="flex flex-col items-center gap-0.5">
      <Pips colors={color} size={16} />
      <span className="font-num text-[12px] leading-tight text-text [text-shadow:0_0_2px_#0b0d11,0_0_2px_#0b0d11,0_0_3px_#0b0d11]">{count}</span>
    </div>
  </foreignObject>
);

const pentagon = (center: number, radius: number) =>
  new Map(
    PIE_ORDER.map((color, i) => {
      const angle = -Math.PI / 2 + (i * 2 * Math.PI) / 5;
      return [color, { x: center + radius * Math.cos(angle), y: center + radius * Math.sin(angle) }];
    }),
  );

const polygonPoints = (points: Map<string, { x: number; y: number }>) =>
  [...points.values()].map((point) => `${point.x},${point.y}`).join(" ");
